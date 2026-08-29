-- Drop the StudentProfile table.
--
-- The degree / year / class data it held was never surfaced anywhere in the
-- app (the frontend never called any of its three endpoints), and its read
-- endpoint was unauthenticated — so it was exposure with no product value.
--
-- Run in the Supabase SQL Editor (the connection pooler doesn't reliably
-- apply Django DDL migrations), then redeploy the backend.
DROP TABLE IF EXISTS "users_studentprofile";
