-- Adds the gender_preference column to freelance work requests.
-- Run this in the Supabase SQL Editor (the pooler doesn't reliably apply
-- Django DDL migrations), then redeploy the backend.
ALTER TABLE "work_workrequest"
    ADD COLUMN IF NOT EXISTS "gender_preference" varchar(10) NOT NULL DEFAULT 'any';
