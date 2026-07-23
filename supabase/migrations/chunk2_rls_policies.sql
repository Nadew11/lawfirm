-- ============================================================
-- Chunk 2: RLS Policies — Firm-scoped access control
-- Generated from live schema verified on 2026-07-22.
-- DO NOT RUN until reviewed. This is a manual-review migration.
-- ============================================================
-- IMPORTANT: The submit_intake() function is SECURITY DEFINER
-- and currently does NOT set firm_id on insert. It is already
-- broken after Chunk 1 made firm_id NOT NULL. That function
-- must be updated in a future chunk — this migration does NOT
-- touch it.
-- ============================================================

BEGIN;

-- ==========================================================
-- Step 1: Helper function — get_my_firm_id()
--   Returns the firm_id for the currently authenticated user.
--   SECURITY DEFINER so it can always read profiles.
-- ==========================================================
CREATE OR REPLACE FUNCTION get_my_firm_id()
RETURNS uuid
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = 'public'
AS $$
  SELECT firm_id FROM profiles WHERE id = auth.uid();
$$;

-- ==========================================================
-- Step 2: Drop all "any authenticated user" policies
--   These allow cross-firm access — exactly what we're fixing.
--   7 policies being removed:
-- ==========================================================

-- 2a. clients
DROP POLICY IF EXISTS "Authenticated users full access on clients" ON clients;

-- 2b. conflict_checks
DROP POLICY IF EXISTS "Authenticated users full access on conflict_checks" ON conflict_checks;

-- 2c. consultations
DROP POLICY IF EXISTS "Authenticated users full access on consultations" ON consultations;

-- 2d. documents
DROP POLICY IF EXISTS "Authenticated users full access on documents" ON documents;

-- 2e. email_log
DROP POLICY IF EXISTS "Authenticated users full access on email_log" ON email_log;

-- 2f. intake_forms
DROP POLICY IF EXISTS "Authenticated users full access on intake_forms" ON intake_forms;

-- 2g. matters
DROP POLICY IF EXISTS "Authenticated users full access on matters" ON matters;

-- ==========================================================
-- Step 3: Firm-scoped policies for each data table
--   Pattern: SELECT/INSERT/UPDATE/DELETE all require
--   firm_id = get_my_firm_id()
-- ==========================================================

-- ----- clients -----
CREATE POLICY "Firm members can view own clients"
  ON clients FOR SELECT TO authenticated
  USING (firm_id = get_my_firm_id());

CREATE POLICY "Firm members can insert own clients"
  ON clients FOR INSERT TO authenticated
  WITH CHECK (firm_id = get_my_firm_id());

CREATE POLICY "Firm members can update own clients"
  ON clients FOR UPDATE TO authenticated
  USING (firm_id = get_my_firm_id())
  WITH CHECK (firm_id = get_my_firm_id());

CREATE POLICY "Firm members can delete own clients"
  ON clients FOR DELETE TO authenticated
  USING (firm_id = get_my_firm_id());

-- ----- matters -----
CREATE POLICY "Firm members can view own matters"
  ON matters FOR SELECT TO authenticated
  USING (firm_id = get_my_firm_id());

CREATE POLICY "Firm members can insert own matters"
  ON matters FOR INSERT TO authenticated
  WITH CHECK (firm_id = get_my_firm_id());

CREATE POLICY "Firm members can update own matters"
  ON matters FOR UPDATE TO authenticated
  USING (firm_id = get_my_firm_id())
  WITH CHECK (firm_id = get_my_firm_id());

CREATE POLICY "Firm members can delete own matters"
  ON matters FOR DELETE TO authenticated
  USING (firm_id = get_my_firm_id());

-- ----- conflict_checks -----
CREATE POLICY "Firm members can view own conflict_checks"
  ON conflict_checks FOR SELECT TO authenticated
  USING (firm_id = get_my_firm_id());

CREATE POLICY "Firm members can insert own conflict_checks"
  ON conflict_checks FOR INSERT TO authenticated
  WITH CHECK (firm_id = get_my_firm_id());

CREATE POLICY "Firm members can update own conflict_checks"
  ON conflict_checks FOR UPDATE TO authenticated
  USING (firm_id = get_my_firm_id())
  WITH CHECK (firm_id = get_my_firm_id());

CREATE POLICY "Firm members can delete own conflict_checks"
  ON conflict_checks FOR DELETE TO authenticated
  USING (firm_id = get_my_firm_id());

-- ----- documents -----
CREATE POLICY "Firm members can view own documents"
  ON documents FOR SELECT TO authenticated
  USING (firm_id = get_my_firm_id());

CREATE POLICY "Firm members can insert own documents"
  ON documents FOR INSERT TO authenticated
  WITH CHECK (firm_id = get_my_firm_id());

CREATE POLICY "Firm members can update own documents"
  ON documents FOR UPDATE TO authenticated
  USING (firm_id = get_my_firm_id())
  WITH CHECK (firm_id = get_my_firm_id());

CREATE POLICY "Firm members can delete own documents"
  ON documents FOR DELETE TO authenticated
  USING (firm_id = get_my_firm_id());

-- ----- email_log -----
CREATE POLICY "Firm members can view own email_log"
  ON email_log FOR SELECT TO authenticated
  USING (firm_id = get_my_firm_id());

CREATE POLICY "Firm members can insert own email_log"
  ON email_log FOR INSERT TO authenticated
  WITH CHECK (firm_id = get_my_firm_id());

CREATE POLICY "Firm members can update own email_log"
  ON email_log FOR UPDATE TO authenticated
  USING (firm_id = get_my_firm_id())
  WITH CHECK (firm_id = get_my_firm_id());

CREATE POLICY "Firm members can delete own email_log"
  ON email_log FOR DELETE TO authenticated
  USING (firm_id = get_my_firm_id());

-- ----- intake_forms -----
CREATE POLICY "Firm members can view own intake_forms"
  ON intake_forms FOR SELECT TO authenticated
  USING (firm_id = get_my_firm_id());

CREATE POLICY "Firm members can insert own intake_forms"
  ON intake_forms FOR INSERT TO authenticated
  WITH CHECK (firm_id = get_my_firm_id());

CREATE POLICY "Firm members can update own intake_forms"
  ON intake_forms FOR UPDATE TO authenticated
  USING (firm_id = get_my_firm_id())
  WITH CHECK (firm_id = get_my_firm_id());

CREATE POLICY "Firm members can delete own intake_forms"
  ON intake_forms FOR DELETE TO authenticated
  USING (firm_id = get_my_firm_id());

-- ----- consultations -----
CREATE POLICY "Firm members can view own consultations"
  ON consultations FOR SELECT TO authenticated
  USING (firm_id = get_my_firm_id());

CREATE POLICY "Firm members can insert own consultations"
  ON consultations FOR INSERT TO authenticated
  WITH CHECK (firm_id = get_my_firm_id());

CREATE POLICY "Firm members can update own consultations"
  ON consultations FOR UPDATE TO authenticated
  USING (firm_id = get_my_firm_id())
  WITH CHECK (firm_id = get_my_firm_id());

CREATE POLICY "Firm members can delete own consultations"
  ON consultations FOR DELETE TO authenticated
  USING (firm_id = get_my_firm_id());

-- ==========================================================
-- Step 4: Policies for firms table
--   Users can only see their own firm. No INSERT/DELETE
--   (firm creation is an admin/system operation).
-- ==========================================================
CREATE POLICY "Users can view own firm"
  ON firms FOR SELECT TO authenticated
  USING (id = get_my_firm_id());

CREATE POLICY "Users can update own firm"
  ON firms FOR UPDATE TO authenticated
  USING (id = get_my_firm_id())
  WITH CHECK (id = get_my_firm_id());

-- ==========================================================
-- Step 5: Policies for profiles table
--   Users can see all profiles in their firm (team list).
--   No INSERT/UPDATE/DELETE — managed via admin or
--   SECURITY DEFINER functions.
-- ==========================================================
CREATE POLICY "Firm members can view team profiles"
  ON profiles FOR SELECT TO authenticated
  USING (firm_id = get_my_firm_id());

-- ==========================================================
-- Step 6: Anon INSERT policies — intentionally KEPT
--   These 4 policies are NOT dropped. They remain open for
--   the public client-intake flow. See notes below.
-- ==========================================================
-- KEPT: "Anon can insert clients"       ON clients       (INSERT, WITH CHECK true)
-- KEPT: "Anon can insert matters"        ON matters       (INSERT, WITH CHECK true)
-- KEPT: "Anon can insert intake_forms"   ON intake_forms  (INSERT, WITH CHECK true)
-- KEPT: "Anon can insert documents"      ON documents     (INSERT, WITH CHECK true)
--
-- WHY: The public intake form allows anonymous visitors to
-- submit client information and upload documents. The main
-- intake path uses the submit_intake() SECURITY DEFINER
-- function (which bypasses RLS entirely), but document
-- uploads are direct anon inserts into the documents table.
--
-- CAVEAT: firm_id is now NOT NULL on all these tables.
-- The submit_intake() function does NOT yet set firm_id,
-- so it is currently BROKEN. Both submit_intake and the
-- direct document insert flow must be updated in a future
-- chunk to supply firm_id. Until then, the public intake
-- form will fail.

COMMIT;
