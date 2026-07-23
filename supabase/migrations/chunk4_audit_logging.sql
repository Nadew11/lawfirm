-- ============================================================
-- Chunk 4: Audit Logging
-- Append-only audit_log table with write triggers on 4 tables
-- and firm-scoped RLS. Read logging is handled at the
-- application layer (see src/lib/auditLog.js).
-- DO NOT RUN until reviewed. This is a manual-review migration.
-- ============================================================

BEGIN;

-- ==========================================================
-- Step 1: Create the audit_log table
-- ==========================================================
CREATE TABLE IF NOT EXISTS audit_log (
  id         uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id    uuid,
  firm_id    uuid        NOT NULL REFERENCES firms(id) ON DELETE CASCADE,
  action     text        NOT NULL,
  table_name text        NOT NULL,
  record_id  uuid,
  metadata   jsonb       DEFAULT '{}',
  created_at timestamptz DEFAULT now()
);

ALTER TABLE audit_log ENABLE ROW LEVEL SECURITY;

-- ==========================================================
-- Step 2: RLS — append-only, firm-scoped
--   Authenticated users can SELECT and INSERT their own
--   firm's audit trail. No UPDATE or DELETE — logs are
--   immutable.
-- ==========================================================
CREATE POLICY "Firm members can view own audit_log"
  ON audit_log FOR SELECT TO authenticated
  USING (firm_id = get_my_firm_id());

CREATE POLICY "Firm members can insert own audit_log"
  ON audit_log FOR INSERT TO authenticated
  WITH CHECK (firm_id = get_my_firm_id());

-- ==========================================================
-- Step 3: Index for efficient firm-scoped queries
-- ==========================================================
CREATE INDEX idx_audit_log_firm_created
  ON audit_log(firm_id, created_at DESC);

CREATE INDEX idx_audit_log_record
  ON audit_log(table_name, record_id);

-- ==========================================================
-- Step 4: Trigger function — log_audit_write()
--   SECURITY DEFINER so it can always insert into audit_log,
--   even when called from anon or service_role contexts.
--   Derives firm_id from the row's own firm_id column.
--   Captures auth.uid() as user_id (NULL for anon).
-- ==========================================================
CREATE OR REPLACE FUNCTION log_audit_write()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = 'public'
AS $$
DECLARE
  audit_action  text;
  audit_record  uuid;
  audit_firm    uuid;
  audit_meta    jsonb := '{}';
BEGIN
  -- Determine action and record id
  IF TG_OP = 'DELETE' THEN
    audit_action := 'DELETE';
    audit_record := OLD.id;
    audit_firm   := OLD.firm_id;
    audit_meta   := jsonb_build_object('deleted_record', OLD.id);
  ELSIF TG_OP = 'UPDATE' THEN
    audit_action := 'UPDATE';
    audit_record := NEW.id;
    audit_firm   := NEW.firm_id;
    -- Capture which columns changed (lightweight diff)
    audit_meta   := (
      SELECT jsonb_object_agg(key, value)
      FROM jsonb_each(to_jsonb(NEW))
      WHERE to_jsonb(NEW) ->> key IS DISTINCT FROM to_jsonb(OLD) ->> key
        AND key NOT IN ('id', 'created_at', 'firm_id')
    );
    IF audit_meta IS NULL THEN
      audit_meta := '{}';
    END IF;
  ELSE -- INSERT
    audit_action := 'INSERT';
    audit_record := NEW.id;
    audit_firm   := NEW.firm_id;
  END IF;

  INSERT INTO audit_log (user_id, firm_id, action, table_name, record_id, metadata)
  VALUES (auth.uid(), audit_firm, audit_action, TG_TABLE_NAME, audit_record, audit_meta);

  IF TG_OP = 'DELETE' THEN
    RETURN OLD;
  END IF;
  RETURN NEW;
END;
$$;

-- ==========================================================
-- Step 5: AFTER triggers on 4 tables
--   matters, clients, documents, conflict_checks
-- ==========================================================
CREATE TRIGGER trg_audit_matters
  AFTER INSERT OR UPDATE OR DELETE ON matters
  FOR EACH ROW
  EXECUTE FUNCTION log_audit_write();

CREATE TRIGGER trg_audit_clients
  AFTER INSERT OR UPDATE OR DELETE ON clients
  FOR EACH ROW
  EXECUTE FUNCTION log_audit_write();

CREATE TRIGGER trg_audit_documents
  AFTER INSERT OR UPDATE OR DELETE ON documents
  FOR EACH ROW
  EXECUTE FUNCTION log_audit_write();

CREATE TRIGGER trg_audit_conflict_checks
  AFTER INSERT OR UPDATE OR DELETE ON conflict_checks
  FOR EACH ROW
  EXECUTE FUNCTION log_audit_write();

COMMIT;
