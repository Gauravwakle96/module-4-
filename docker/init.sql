-- Initialize a fresh local PostgreSQL volume with the same feedback table shape.
-- Supabase-specific roles and RLS remain in schema.sql for the managed cloud DB.
CREATE TABLE IF NOT EXISTS public.module3_feedback (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name TEXT NOT NULL CHECK (char_length(btrim(name)) BETWEEN 1 AND 60),
    message TEXT NOT NULL CHECK (char_length(btrim(message)) BETWEEN 1 AND 500),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
