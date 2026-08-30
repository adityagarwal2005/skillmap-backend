-- Multi-person gigs and collabs.
--
-- people_needed: how many people the post is hiring (1-5, enforced in the
-- view). hired/rejected record the POSTER's decision per applicant — hiring
-- used to be a single work_workrequest.assigned_to FK (so only one person
-- could be hired) and rejecting deleted the row, which let the rejected
-- applicant re-apply and kept the post in their feed.
--
-- Defaults mean existing rows keep today's behaviour exactly: every current
-- post becomes a 1-person post with nobody hired or rejected.
--
-- Run in the Supabase SQL Editor, then redeploy. Safe to re-run.
ALTER TABLE "work_workrequest"
    ADD COLUMN IF NOT EXISTS "people_needed" smallint NOT NULL DEFAULT 1;

ALTER TABLE "work_workrequestresponse"
    ADD COLUMN IF NOT EXISTS "hired" boolean NOT NULL DEFAULT false;
ALTER TABLE "work_workrequestresponse"
    ADD COLUMN IF NOT EXISTS "rejected" boolean NOT NULL DEFAULT false;

ALTER TABLE "collab_collabpost"
    ADD COLUMN IF NOT EXISTS "people_needed" smallint NOT NULL DEFAULT 1;

-- Backfill: anyone already hired via the old single-assignee field keeps that
-- state, so in-flight gigs don't lose their worker.
UPDATE "work_workrequestresponse" r
SET "hired" = true
FROM "work_workrequest" w
WHERE r."work_request_id" = w."id"
  AND w."assigned_to_id" = r."user_id"
  AND r."hired" = false;
