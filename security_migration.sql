-- Run once in the Supabase SQL Editor on an existing project.
-- Removes public reads, makes documents private, and adds secure intake submission.

DROP POLICY IF EXISTS "Anon can select clients" ON public.clients;
DROP POLICY IF EXISTS "Anon can select matters" ON public.matters;
DROP POLICY IF EXISTS "Anon can select intake_forms" ON public.intake_forms;
DROP POLICY IF EXISTS "Anon can select documents" ON public.documents;
DROP POLICY IF EXISTS "Anon can read client-documents" ON storage.objects;

INSERT INTO storage.buckets (id, name, public)
VALUES ('client-documents', 'client-documents', false)
ON CONFLICT (id) DO UPDATE SET public = false;

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
