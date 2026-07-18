-- =============================================================
-- Legal Client-Intake MVP — Supabase Schema
-- Paste this entire script into the Supabase SQL Editor and run.
-- =============================================================

-- 1. clients
CREATE TABLE IF NOT EXISTS clients (
  id         uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  name       text        NOT NULL,
  email      text        NOT NULL,
  phone      text,
  created_at timestamptz DEFAULT now()
);

-- 2. matters
CREATE TABLE IF NOT EXISTS matters (
  id          uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  client_id   uuid        REFERENCES clients (id) ON DELETE CASCADE,
  matter_type text,
  status      text        DEFAULT 'intake_pending',
  created_at  timestamptz DEFAULT now()
);

-- 3. intake_forms
CREATE TABLE IF NOT EXISTS intake_forms (
  id           uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  matter_id    uuid        REFERENCES matters (id) ON DELETE CASCADE,
  form_data    jsonb,
  submitted_at timestamptz DEFAULT now()
);

-- 4. documents
CREATE TABLE IF NOT EXISTS documents (
  id          uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  matter_id   uuid        REFERENCES matters (id) ON DELETE CASCADE,
  file_url    text,
  doc_type    text,
  uploaded_at timestamptz DEFAULT now()
);

-- 5. conflict_checks
CREATE TABLE IF NOT EXISTS conflict_checks (
  id         uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  matter_id  uuid        REFERENCES matters (id) ON DELETE CASCADE,
  checked_by text,
  result     text,
  notes      text,
  checked_at timestamptz DEFAULT now()
);

-- =============================================================
-- Row Level Security — enable on all tables, then add a
-- permissive policy for authenticated users (to be tightened).
-- =============================================================

ALTER TABLE clients          ENABLE ROW LEVEL SECURITY;
ALTER TABLE matters          ENABLE ROW LEVEL SECURITY;
ALTER TABLE intake_forms     ENABLE ROW LEVEL SECURITY;
ALTER TABLE documents        ENABLE ROW LEVEL SECURITY;
ALTER TABLE conflict_checks  ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Authenticated users full access on clients"
  ON clients FOR ALL
  TO authenticated
  USING (true)
  WITH CHECK (true);

CREATE POLICY "Authenticated users full access on matters"
  ON matters FOR ALL
  TO authenticated
  USING (true)
  WITH CHECK (true);

CREATE POLICY "Authenticated users full access on intake_forms"
  ON intake_forms FOR ALL
  TO authenticated
  USING (true)
  WITH CHECK (true);

CREATE POLICY "Authenticated users full access on documents"
  ON documents FOR ALL
  TO authenticated
  USING (true)
  WITH CHECK (true);

CREATE POLICY "Authenticated users full access on conflict_checks"
  ON conflict_checks FOR ALL
  TO authenticated
  USING (true)
  WITH CHECK (true);

-- =============================================================
-- Public intake: anon INSERT-only on tables the form writes to.
-- =============================================================

CREATE POLICY "Anon can insert clients"
  ON clients FOR INSERT
  TO anon
  WITH CHECK (true);

CREATE POLICY "Anon can insert matters"
  ON matters FOR INSERT
  TO anon
  WITH CHECK (true);

CREATE POLICY "Anon can insert intake_forms"
  ON intake_forms FOR INSERT
  TO anon
  WITH CHECK (true);

CREATE POLICY "Anon can insert documents"
  ON documents FOR INSERT
  TO anon
  WITH CHECK (true);

-- =============================================================
-- Storage bucket: client-documents
-- Allow both anon (public intake) and authenticated (staff)
-- to upload and read files in this bucket.
-- =============================================================

CREATE POLICY "Anon can upload to client-documents"
  ON storage.objects FOR INSERT
  TO anon
  WITH CHECK (bucket_id = 'client-documents');

CREATE POLICY "Authenticated can upload to client-documents"
  ON storage.objects FOR INSERT
  TO authenticated
  WITH CHECK (bucket_id = 'client-documents');

CREATE POLICY "Authenticated can read client-documents"
  ON storage.objects FOR SELECT
  TO authenticated
  USING (bucket_id = 'client-documents');

-- Keep legal documents private. Staff access them through short-lived URLs.
INSERT INTO storage.buckets (id, name, public)
VALUES ('client-documents', 'client-documents', false)
ON CONFLICT (id) DO UPDATE SET public = false;

-- Save a public intake atomically without granting anonymous table reads.
CREATE OR REPLACE FUNCTION public.submit_intake(
  client_name text,
  client_email text,
  client_phone text,
  selected_matter_type text,
  matter_description text
)
RETURNS uuid
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
  new_client_id uuid;
  new_matter_id uuid;
BEGIN
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

  INSERT INTO public.clients (name, email, phone)
  VALUES (trim(client_name), trim(client_email), nullif(trim(client_phone), ''))
  RETURNING id INTO new_client_id;

  INSERT INTO public.matters (client_id, matter_type)
  VALUES (new_client_id, selected_matter_type)
  RETURNING id INTO new_matter_id;

  INSERT INTO public.intake_forms (matter_id, form_data)
  VALUES (
    new_matter_id,
    jsonb_build_object(
      'name', trim(client_name),
      'email', trim(client_email),
      'phone', coalesce(trim(client_phone), ''),
      'matterType', selected_matter_type,
      'description', coalesce(trim(matter_description), '')
    )
  );

  RETURN new_matter_id;
END;
$$;

REVOKE ALL ON FUNCTION public.submit_intake(text, text, text, text, text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.submit_intake(text, text, text, text, text) TO anon, authenticated;

-- Also makes this script safe as a migration from the earlier policies.
DROP POLICY IF EXISTS "Anon can select clients" ON clients;
DROP POLICY IF EXISTS "Anon can select matters" ON matters;
DROP POLICY IF EXISTS "Anon can select intake_forms" ON intake_forms;
DROP POLICY IF EXISTS "Anon can select documents" ON documents;
DROP POLICY IF EXISTS "Anon can read client-documents" ON storage.objects;
