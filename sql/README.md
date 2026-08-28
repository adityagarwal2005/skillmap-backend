# Manual Supabase migrations

Django migrations live in each app's `migrations/` folder and are the source
of truth for the schema. These files exist because the **Supabase connection
pooler doesn't reliably apply Django DDL** — `manage.py migrate` can report
success while the column never lands, which then shows up as a 500
(`column ... does not exist`) on the next request.

So for any migration that adds a column or table, the DDL is mirrored here and
run by hand.

## How to apply

1. Supabase dashboard → **SQL Editor**
2. Paste the file's contents, choose **Run without RLS**
3. Only then deploy the backend:

   ```bash
   gcloud run deploy doithere-backend --source . --region asia-southeast1 --quiet
   ```

Running the SQL *before* deploying matters — deploying first means the new
code queries a column the database doesn't have yet.

All statements are written to be idempotent (`IF NOT EXISTS`), so re-running a
file is safe.

## Files

Each corresponds to the Django migration of the same feature:

| File | Adds |
|---|---|
| `CERTIFICATE_DROP_SUPABASE.sql` | drops the retired certificate table |
| `COLLAB_GROUP_CHAT_SUPABASE.sql` | collab group conversations |
| `COLLAB_TASKS_SUPABASE.sql` | collab task board |
| `COLLAB_VISIBILITY_SUPABASE.sql` | `collab_collabpost.time_limit_hours`, `expires_at` |
| `FRIENDSHIP_SUPABASE.sql` | friendships |
| `NOTIFICATION_ACTOR_SUPABASE.sql` | notification actor FK |
| `PUSH_SUBSCRIPTION_SUPABASE.sql` | web-push subscriptions |
| `READ_RECEIPTS_TYPING_SUPABASE.sql` | message read receipts + typing status |
| `WORK_GENDER_PREFERENCE_SUPABASE.sql` | `work_workrequest.gender_preference` |
