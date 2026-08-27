-- Adds the visibility window columns to collab posts (so collabs expire like
-- freelance jobs). Run in the Supabase SQL Editor, then redeploy the backend.
ALTER TABLE "collab_collabpost"
    ADD COLUMN IF NOT EXISTS "time_limit_hours" integer NULL;
ALTER TABLE "collab_collabpost"
    ADD COLUMN IF NOT EXISTS "expires_at" timestamptz NULL;
