-- Run this in the Supabase SQL Editor to add actor tracking to notifications.
-- (Matches notifications/migrations/0003_notification_actor.py.) Safe to run once.
-- Existing rows just get actor_id = NULL — no backfill needed or possible
-- (we never stored who triggered a notification before this).

BEGIN;

ALTER TABLE "notifications_notification"
    ADD COLUMN "actor_id" bigint NULL;

ALTER TABLE "notifications_notification"
    ADD CONSTRAINT "notifications_notification_actor_id_fk_users_user"
    FOREIGN KEY ("actor_id") REFERENCES "users_user" ("id")
    DEFERRABLE INITIALLY DEFERRED;

CREATE INDEX "notifications_notification_actor_id_idx"
    ON "notifications_notification" ("actor_id");

COMMIT;
