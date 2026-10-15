-- Explicit operator-run upgrade, never executed by preflight or ordinary startup.
-- rc.544's model requires event_type VARCHAR NOT NULL DEFAULT 'ADD'. The old
-- table recorded attachment additions without an event type. Preserve all rows.
-- Run against the reviewed registry database with psql -v ON_ERROR_STOP=1.
BEGIN;
SET LOCAL lock_timeout = '5s';
ALTER TABLE public.g2p_register_document_history
    ADD COLUMN IF NOT EXISTS event_type VARCHAR NOT NULL DEFAULT 'ADD';
COMMIT;
