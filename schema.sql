-- Run once in the Supabase SQL Editor before deploying the web service.
-- Contains no credentials. The server connects as the table owner (postgres).
CREATE TABLE IF NOT EXISTS public.module3_feedback (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name TEXT NOT NULL CHECK (char_length(btrim(name)) BETWEEN 1 AND 60),
    message TEXT NOT NULL CHECK (char_length(btrim(message)) BETWEEN 1 AND 500),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- No client-facing policies: direct anonymous/authenticated Data API access is denied.
ALTER TABLE public.module3_feedback ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.module3_feedback FROM anon, authenticated;
REVOKE ALL ON SEQUENCE public.module3_feedback_id_seq FROM anon, authenticated;
