-- ============================================================
-- Chunk 3: Fix firm_id on all insert paths
-- Adds a BEFORE INSERT trigger that auto-derives firm_id from
-- matter_id, and updates submit_intake() to accept firm_id.
-- DO NOT RUN until reviewed. This is a manual-review migration.
-- ============================================================

BEGIN;

-- ==========================================================
-- Step 1: Trigger function — auto_set_firm_id()
--   Derives firm_id from the row's matter_id when firm_id is
--   NULL. Falls back to auth.uid() → profiles if no matter_id.
--   SECURITY DEFINER so it can read matters/profiles for any
--   caller role (including anon and service_role).
-- ==========================================================
CREATE OR REPLACE FUNCTION auto_set_firm_id()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = 'public'
AS $$
BEGIN
  IF NEW.firm_id IS NOT NULL THEN
    RETURN NEW;
  END IF;

  -- Try to derive from matter_id (all 5 target tables have this column)
  IF NEW.matter_id IS NOT NULL THEN
    SELECT firm_id INTO NEW.firm_id
      FROM matters
     WHERE id = NEW.matter_id;
  END IF;

  -- Fallback: derive from the authenticated user's profile
  IF NEW.firm_id IS NULL AND auth.uid() IS NOT NULL THEN
    SELECT firm_id INTO NEW.firm_id
      FROM profiles
     WHERE id = auth.uid();
  END IF;

  IF NEW.firm_id IS NULL THEN
    RAISE EXCEPTION 'Could not determine firm_id for this record';
  END IF;

  RETURN NEW;
END;
$$;

-- ==========================================================
-- Step 2: Attach BEFORE INSERT triggers to 5 tables
--   These all have matter_id, so the trigger can derive
--   firm_id automatically from the parent matter.
-- ==========================================================

CREATE TRIGGER trg_auto_firm_id_documents
  BEFORE INSERT ON documents
  FOR EACH ROW
  EXECUTE FUNCTION auto_set_firm_id();

CREATE TRIGGER trg_auto_firm_id_conflict_checks
  BEFORE INSERT ON conflict_checks
  FOR EACH ROW
  EXECUTE FUNCTION auto_set_firm_id();

CREATE TRIGGER trg_auto_firm_id_email_log
  BEFORE INSERT ON email_log
  FOR EACH ROW
  EXECUTE FUNCTION auto_set_firm_id();

CREATE TRIGGER trg_auto_firm_id_intake_forms
  BEFORE INSERT ON intake_forms
  FOR EACH ROW
  EXECUTE FUNCTION auto_set_firm_id();

CREATE TRIGGER trg_auto_firm_id_consultations
  BEFORE INSERT ON consultations
  FOR EACH ROW
  EXECUTE FUNCTION auto_set_firm_id();

-- ==========================================================
-- Step 3: Replace submit_intake() with firm_id-aware version
--   New parameter: target_firm_id uuid
--   All 3 INSERT statements now include firm_id.
-- ==========================================================
CREATE OR REPLACE FUNCTION public.submit_intake(
  target_firm_id uuid,
  client_name text,
  client_email text,
  client_phone text,
  selected_matter_type text,
  matter_description text
)
RETURNS uuid
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path TO 'public', 'pg_temp'
AS $$
DECLARE
  new_client_id uuid;
  new_matter_id uuid;
BEGIN
  -- Validate firm exists
  IF NOT EXISTS (SELECT 1 FROM firms WHERE id = target_firm_id) THEN
    RAISE EXCEPTION 'Invalid firm';
  END IF;

  IF length(trim(client_name)) NOT BETWEEN 1 AND 200 THEN
    RAISE EXCEPTION 'A valid name is required';
  END IF;
  IF length(trim(client_email)) NOT BETWEEN 3 AND 320
     OR position('@' in client_email) = 0 THEN
    RAISE EXCEPTION 'A valid email is required';
  END IF;
  IF selected_matter_type NOT IN ('Family Law', 'Contract', 'Estate Planning', 'Other') THEN
    RAISE EXCEPTION 'Invalid matter type';
  END IF;
  IF length(coalesce(client_phone, '')) > 50
     OR length(coalesce(matter_description, '')) > 10000 THEN
    RAISE EXCEPTION 'Intake field is too long';
  END IF;

  INSERT INTO public.clients (name, email, phone, firm_id)
  VALUES (trim(client_name), trim(client_email), nullif(trim(client_phone), ''), target_firm_id)
  RETURNING id INTO new_client_id;

  INSERT INTO public.matters (client_id, matter_type, firm_id)
  VALUES (new_client_id, selected_matter_type, target_firm_id)
  RETURNING id INTO new_matter_id;

  INSERT INTO public.intake_forms (matter_id, form_data, firm_id)
  VALUES (
    new_matter_id,
    jsonb_build_object(
      'name', trim(client_name),
      'email', trim(client_email),
      'phone', coalesce(trim(client_phone), ''),
      'matterType', selected_matter_type,
      'description', coalesce(trim(matter_description), '')
    ),
    target_firm_id
  );

  RETURN new_matter_id;
END;
$$;

COMMIT;
