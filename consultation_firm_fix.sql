-- Keep a consultation in the same firm as its parent matter.
-- Run this once in the Supabase SQL Editor.

CREATE OR REPLACE FUNCTION public.set_consultation_firm_from_matter()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = public, pg_temp
AS $$
BEGIN
  SELECT matters.firm_id
    INTO NEW.firm_id
    FROM public.matters
   WHERE matters.id = NEW.matter_id;

  IF NEW.firm_id IS NULL THEN
    RAISE EXCEPTION 'The consultation matter is missing or has no firm';
  END IF;

  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS consultations_set_firm
  ON public.consultations;

CREATE TRIGGER consultations_set_firm
BEFORE INSERT OR UPDATE OF matter_id
ON public.consultations
FOR EACH ROW
EXECUTE FUNCTION public.set_consultation_firm_from_matter();

-- Repair any existing rows if the constraint was temporarily nullable.
UPDATE public.consultations AS consultations
   SET firm_id = matters.firm_id
  FROM public.matters AS matters
 WHERE consultations.matter_id = matters.id
   AND consultations.firm_id IS DISTINCT FROM matters.firm_id;
