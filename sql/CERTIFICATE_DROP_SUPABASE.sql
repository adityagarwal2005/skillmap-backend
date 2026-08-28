-- Run this in the Supabase SQL Editor to drop the unused certificates table.
-- (Matches skills/migrations/0003_delete_certificate.py.) Safe to run once.
-- The Certificate feature was never actually exposed in the frontend UI —
-- this just removes the dead table backing the dead backend code.

BEGIN;

DROP TABLE IF EXISTS "skills_certificate";

COMMIT;
