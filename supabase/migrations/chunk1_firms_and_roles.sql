-- ============================================================
-- Chunk 1: Firms Table + Roles Migration
-- Generated from Chunk 0 discovery on 2026-07-22.
-- DO NOT RUN until reviewed. This is a manual-review migration.
-- ============================================================

BEGIN;

-- ==========================================================
-- Step 1: Create the firms table
-- ==========================================================
CREATE TABLE IF NOT EXISTS firms (
  id         uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  name       text        NOT NULL,
  created_at timestamptz DEFAULT now()
);

ALTER TABLE firms ENABLE ROW LEVEL SECURITY;

-- ==========================================================
-- Step 2: Create the profiles table (staff/user table)
--   Links auth.users 1:1 to a firm with a role.
--   Chunk 0 confirmed NO staff/user/profiles table exists.
-- ==========================================================
CREATE TABLE IF NOT EXISTS profiles (
  id         uuid        PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
  firm_id    uuid        NOT NULL REFERENCES firms(id) ON DELETE CASCADE,
  role       text        NOT NULL CHECK (role IN ('partner', 'associate', 'paralegal')),
  created_at timestamptz DEFAULT now()
);

ALTER TABLE profiles ENABLE ROW LEVEL SECURITY;

-- ==========================================================
-- Step 3: Add firm_id FK to all 7 firm-specific tables
--   Starts nullable so the backfill in Step 4 can run.
-- ==========================================================
ALTER TABLE clients         ADD COLUMN firm_id uuid REFERENCES firms(id) ON DELETE CASCADE;
ALTER TABLE matters         ADD COLUMN firm_id uuid REFERENCES firms(id) ON DELETE CASCADE;
ALTER TABLE conflict_checks ADD COLUMN firm_id uuid REFERENCES firms(id) ON DELETE CASCADE;
ALTER TABLE documents       ADD COLUMN firm_id uuid REFERENCES firms(id) ON DELETE CASCADE;
ALTER TABLE email_log       ADD COLUMN firm_id uuid REFERENCES firms(id) ON DELETE CASCADE;
ALTER TABLE intake_forms    ADD COLUMN firm_id uuid REFERENCES firms(id) ON DELETE CASCADE;
ALTER TABLE consultations   ADD COLUMN firm_id uuid REFERENCES firms(id) ON DELETE CASCADE;

-- ==========================================================
-- Step 4: Seed the firm and backfill all existing rows
-- ==========================================================

-- 4a. Insert the seed firm
INSERT INTO firms (id, name)
VALUES ('00000000-0000-4000-a000-000000000001', 'BoardLaw');

-- 4b. Backfill firm_id on every firm-specific table
UPDATE clients         SET firm_id = '00000000-0000-4000-a000-000000000001';
UPDATE matters         SET firm_id = '00000000-0000-4000-a000-000000000001';
UPDATE conflict_checks SET firm_id = '00000000-0000-4000-a000-000000000001';
UPDATE documents       SET firm_id = '00000000-0000-4000-a000-000000000001';
UPDATE email_log       SET firm_id = '00000000-0000-4000-a000-000000000001';
UPDATE intake_forms    SET firm_id = '00000000-0000-4000-a000-000000000001';
UPDATE consultations   SET firm_id = '00000000-0000-4000-a000-000000000001';

-- 4c. Insert profiles for the 2 existing auth.users (both partners)
--     Source: Chunk 0 query of auth.users
--       77c3da93-e812-450b-a517-b98f41af1796  nathnaeleabraham@gmail.com
--       10788605-ea00-4540-a055-4948eca3cced  nadewalem@gmail.com
INSERT INTO profiles (id, firm_id, role) VALUES
  ('77c3da93-e812-450b-a517-b98f41af1796', '00000000-0000-4000-a000-000000000001', 'partner'),
  ('10788605-ea00-4540-a055-4948eca3cced', '00000000-0000-4000-a000-000000000001', 'partner');

-- ==========================================================
-- Step 5: Now that every row has a firm_id, set NOT NULL
-- ==========================================================
ALTER TABLE clients         ALTER COLUMN firm_id SET NOT NULL;
ALTER TABLE matters         ALTER COLUMN firm_id SET NOT NULL;
ALTER TABLE conflict_checks ALTER COLUMN firm_id SET NOT NULL;
ALTER TABLE documents       ALTER COLUMN firm_id SET NOT NULL;
ALTER TABLE email_log       ALTER COLUMN firm_id SET NOT NULL;
ALTER TABLE intake_forms    ALTER COLUMN firm_id SET NOT NULL;
ALTER TABLE consultations   ALTER COLUMN firm_id SET NOT NULL;

-- ==========================================================
-- Step 6: Create indexes on firm_id for query performance
-- ==========================================================
CREATE INDEX idx_profiles_firm_id         ON profiles(firm_id);
CREATE INDEX idx_clients_firm_id          ON clients(firm_id);
CREATE INDEX idx_matters_firm_id          ON matters(firm_id);
CREATE INDEX idx_conflict_checks_firm_id  ON conflict_checks(firm_id);
CREATE INDEX idx_documents_firm_id        ON documents(firm_id);
CREATE INDEX idx_email_log_firm_id        ON email_log(firm_id);
CREATE INDEX idx_intake_forms_firm_id     ON intake_forms(firm_id);
CREATE INDEX idx_consultations_firm_id    ON consultations(firm_id);

COMMIT;
