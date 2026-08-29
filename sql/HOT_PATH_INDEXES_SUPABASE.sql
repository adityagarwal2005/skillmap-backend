-- Indexes for the highest-frequency query shapes in the app.
--
-- Run in the Supabase SQL Editor (the connection pooler doesn't reliably
-- apply Django DDL migrations), then redeploy the backend.
--
-- IF NOT EXISTS makes this safe to re-run. Index names match the ones in the
-- Django migrations (work/0010, collab/0008, notifications/0005), so Django's
-- state and the database agree either way.
--
-- Note on CONCURRENTLY: a plain CREATE INDEX takes a lock that blocks writes
-- to the table for the duration. That's fine at today's row counts (a second
-- or less). If you ever re-run this against a large, live table, use
-- CREATE INDEX CONCURRENTLY instead — but note it cannot run inside a
-- transaction block, so each statement has to be executed on its own.

-- Feed: WHERE status='open' AND expires_at > now() ORDER BY created_at DESC
CREATE INDEX IF NOT EXISTS wr_status_created_idx
    ON "work_workrequest" ("status", "created_at" DESC);
CREATE INDEX IF NOT EXISTS wr_expires_idx
    ON "work_workrequest" ("expires_at");

CREATE INDEX IF NOT EXISTS cp_status_created_idx
    ON "collab_collabpost" ("status", "created_at" DESC);
CREATE INDEX IF NOT EXISTS cp_expires_idx
    ON "collab_collabpost" ("expires_at");

-- Open chat thread — re-fetched every few seconds while a conversation is open
CREATE INDEX IF NOT EXISTS msg_conv_created_idx
    ON "work_message" ("conversation_id", "created_at");

-- Unread badge — polled on every screen
CREATE INDEX IF NOT EXISTS notif_user_unread_idx
    ON "notifications_notification" ("user_id", "is_read");
CREATE INDEX IF NOT EXISTS notif_user_created_idx
    ON "notifications_notification" ("user_id", "created_at" DESC);
