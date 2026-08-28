-- Run this in the Supabase SQL Editor to add group-chat support for collab
-- teams. (Matches work/migrations/0007_conversation_collab_post.py.)
-- Safe to run once. The conversation_type choice list change needs no SQL —
-- choices are enforced in Django only.

BEGIN;

ALTER TABLE "work_conversation"
    ADD COLUMN "collab_post_id" bigint NULL;

ALTER TABLE "work_conversation"
    ADD CONSTRAINT "work_conversation_collab_post_id_uniq" UNIQUE ("collab_post_id");

ALTER TABLE "work_conversation"
    ADD CONSTRAINT "work_conversation_collab_post_id_fk_collab_collabpost"
    FOREIGN KEY ("collab_post_id") REFERENCES "collab_collabpost" ("id")
    DEFERRABLE INITIALLY DEFERRED;

CREATE INDEX "work_conversation_collab_post_id_idx"
    ON "work_conversation" ("collab_post_id");

COMMIT;
