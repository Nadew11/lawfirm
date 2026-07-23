-- Run once in the Supabase SQL Editor before testing consultation scheduling.

CREATE TABLE IF NOT EXISTS public.consultations (
  id             uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  matter_id      uuid        UNIQUE NOT NULL REFERENCES public.matters (id) ON DELETE CASCADE,
  provider       text        NOT NULL DEFAULT 'calendly',
  status         text        NOT NULL DEFAULT 'not_invited'
                               CHECK (status IN ('not_invited', 'invited', 'scheduled', 'cancelled', 'completed', 'no_show')),
  booking_url    text,
  attorney_email text,
  invited_at     timestamptz,
  scheduled_at   timestamptz,
  created_at     timestamptz DEFAULT now(),
  updated_at     timestamptz DEFAULT now()
);

ALTER TABLE public.consultations ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Authenticated users full access on consultations"
  ON public.consultations;

CREATE POLICY "Authenticated users full access on consultations"
  ON public.consultations FOR ALL
  TO authenticated
  USING (true)
  WITH CHECK (true);

CREATE INDEX IF NOT EXISTS consultations_status_idx
  ON public.consultations (status);

CREATE INDEX IF NOT EXISTS consultations_scheduled_at_idx
  ON public.consultations (scheduled_at);
