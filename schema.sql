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
  id              uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  client_id       uuid        REFERENCES clients (id) ON DELETE CASCADE,
  matter_type     text,
  status          text        DEFAULT 'intake_pending',
  esign_status    text        DEFAULT 'not_sent',
  esign_reference text,
  created_at      timestamptz DEFAULT now()
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

CREATE POLICY "Anon can select clients"
  ON clients FOR SELECT
  TO anon
  USING (true);

CREATE POLICY "Anon can insert matters"
  ON matters FOR INSERT
  TO anon
  WITH CHECK (true);

CREATE POLICY "Anon can select matters"
  ON matters FOR SELECT
  TO anon
  USING (true);

CREATE POLICY "Anon can insert intake_forms"
  ON intake_forms FOR INSERT
  TO anon
  WITH CHECK (true);

CREATE POLICY "Anon can select intake_forms"
  ON intake_forms FOR SELECT
  TO anon
  USING (true);

CREATE POLICY "Anon can insert documents"
  ON documents FOR INSERT
  TO anon
  WITH CHECK (true);

CREATE POLICY "Anon can select documents"
  ON documents FOR SELECT
  TO anon
  USING (true);

-- =============================================================
-- Storage bucket: client-documents
-- Allow both anon (public intake) and authenticated (staff)
-- to upload and read files in this bucket.
-- =============================================================

CREATE POLICY "Anon can upload to client-documents"
  ON storage.objects FOR INSERT
  TO anon
  WITH CHECK (bucket_id = 'client-documents');

CREATE POLICY "Anon can read client-documents"
  ON storage.objects FOR SELECT
  TO anon
  USING (bucket_id = 'client-documents');

CREATE POLICY "Authenticated can upload to client-documents"
  ON storage.objects FOR INSERT
  TO authenticated
  WITH CHECK (bucket_id = 'client-documents');

CREATE POLICY "Authenticated can read client-documents"
  ON storage.objects FOR SELECT
  TO authenticated
  USING (bucket_id = 'client-documents');
