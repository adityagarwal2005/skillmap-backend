-- Reconcile django_migrations with the schema that is actually in the database.
--
-- WHY: DDL for these migrations was applied by hand in the Supabase SQL
-- editor and never recorded, so `migrate` re-attempts them on every deploy and
-- aborts on the first "already exists". The Dockerfile's `|| true` hides that,
-- which means migrate never gets past the failure — so any NEW migration would
-- silently never apply.
--
-- SAFETY: every row below is conditional on the corresponding schema object
-- actually existing (or, for drops, actually being gone). A migration is only
-- recorded if its effect is genuinely present. If a condition doesn't hold,
-- nothing is inserted and the next `migrate` will legitimately apply it —
-- which is exactly what you'd want. Faking a migration whose DDL never ran is
-- the one dangerous outcome, and this makes that impossible.
--
-- Re-running is harmless: each insert is guarded by NOT EXISTS.
-- Read the RESULT at the end to confirm.

BEGIN;

-- Helper conditions are inlined per row so each stands on its own.

-- collab.0006_collabtask -> CollabTask table must exist
INSERT INTO django_migrations (app, name, applied)
SELECT 'collab', '0006_collabtask', now()
WHERE to_regclass('public.collab_collabtask') IS NOT NULL
  AND NOT EXISTS (SELECT 1 FROM django_migrations WHERE app='collab' AND name='0006_collabtask');

-- collab.0007_collabpost_visibility -> expires_at column must exist
INSERT INTO django_migrations (app, name, applied)
SELECT 'collab', '0007_collabpost_visibility', now()
WHERE EXISTS (SELECT 1 FROM information_schema.columns
              WHERE table_name='collab_collabpost' AND column_name='expires_at')
  AND NOT EXISTS (SELECT 1 FROM django_migrations WHERE app='collab' AND name='0007_collabpost_visibility');

-- collab.0008_hot_path_indexes -> index must exist
INSERT INTO django_migrations (app, name, applied)
SELECT 'collab', '0008_hot_path_indexes', now()
WHERE EXISTS (SELECT 1 FROM pg_indexes WHERE indexname='cp_status_created_idx')
  AND NOT EXISTS (SELECT 1 FROM django_migrations WHERE app='collab' AND name='0008_hot_path_indexes');

-- notifications.0003_notification_actor -> actor_id column must exist
INSERT INTO django_migrations (app, name, applied)
SELECT 'notifications', '0003_notification_actor', now()
WHERE EXISTS (SELECT 1 FROM information_schema.columns
              WHERE table_name='notifications_notification' AND column_name='actor_id')
  AND NOT EXISTS (SELECT 1 FROM django_migrations WHERE app='notifications' AND name='0003_notification_actor');

-- notifications.0004 -> choices-only, emits no DDL on Postgres, so unconditional
INSERT INTO django_migrations (app, name, applied)
SELECT 'notifications', '0004_notification_collab_match_type', now()
WHERE NOT EXISTS (SELECT 1 FROM django_migrations WHERE app='notifications' AND name='0004_notification_collab_match_type');

-- notifications.0005_hot_path_indexes -> index must exist
INSERT INTO django_migrations (app, name, applied)
SELECT 'notifications', '0005_hot_path_indexes', now()
WHERE EXISTS (SELECT 1 FROM pg_indexes WHERE indexname='notif_user_unread_idx')
  AND NOT EXISTS (SELECT 1 FROM django_migrations WHERE app='notifications' AND name='0005_hot_path_indexes');

-- portfolio.0004 -> choices-only, no DDL
INSERT INTO django_migrations (app, name, applied)
SELECT 'portfolio', '0004_alter_portfolioitem_portfolio_type', now()
WHERE NOT EXISTS (SELECT 1 FROM django_migrations WHERE app='portfolio' AND name='0004_alter_portfolioitem_portfolio_type');

-- skills.0003_delete_certificate -> table must be GONE
INSERT INTO django_migrations (app, name, applied)
SELECT 'skills', '0003_delete_certificate', now()
WHERE to_regclass('public.skills_certificate') IS NULL
  AND NOT EXISTS (SELECT 1 FROM django_migrations WHERE app='skills' AND name='0003_delete_certificate');

-- users.0013_user_google_sub -> google_sub column must exist
INSERT INTO django_migrations (app, name, applied)
SELECT 'users', '0013_user_google_sub', now()
WHERE EXISTS (SELECT 1 FROM information_schema.columns
              WHERE table_name='users_user' AND column_name='google_sub')
  AND NOT EXISTS (SELECT 1 FROM django_migrations WHERE app='users' AND name='0013_user_google_sub');

-- users.0014 -> phone_verified column AND the OTP table must both exist
INSERT INTO django_migrations (app, name, applied)
SELECT 'users', '0014_phoneotpverification_user_phone_verified', now()
WHERE EXISTS (SELECT 1 FROM information_schema.columns
              WHERE table_name='users_user' AND column_name='phone_verified')
  AND to_regclass('public.users_phoneotpverification') IS NOT NULL
  AND NOT EXISTS (SELECT 1 FROM django_migrations WHERE app='users' AND name='0014_phoneotpverification_user_phone_verified');

-- users.0015_delete_studentprofile -> table must be GONE
INSERT INTO django_migrations (app, name, applied)
SELECT 'users', '0015_delete_studentprofile', now()
WHERE to_regclass('public.users_studentprofile') IS NULL
  AND NOT EXISTS (SELECT 1 FROM django_migrations WHERE app='users' AND name='0015_delete_studentprofile');

-- work.0007_conversation_collab_post -> collab_post_id column must exist
INSERT INTO django_migrations (app, name, applied)
SELECT 'work', '0007_conversation_collab_post', now()
WHERE EXISTS (SELECT 1 FROM information_schema.columns
              WHERE table_name='work_conversation' AND column_name='collab_post_id')
  AND NOT EXISTS (SELECT 1 FROM django_migrations WHERE app='work' AND name='0007_conversation_collab_post');

-- work.0008 -> read_at column AND typing-status table must both exist
INSERT INTO django_migrations (app, name, applied)
SELECT 'work', '0008_message_read_at_typingstatus', now()
WHERE EXISTS (SELECT 1 FROM information_schema.columns
              WHERE table_name='work_message' AND column_name='read_at')
  AND to_regclass('public.work_typingstatus') IS NOT NULL
  AND NOT EXISTS (SELECT 1 FROM django_migrations WHERE app='work' AND name='0008_message_read_at_typingstatus');

-- work.0009_workrequest_gender_preference -> column must exist
INSERT INTO django_migrations (app, name, applied)
SELECT 'work', '0009_workrequest_gender_preference', now()
WHERE EXISTS (SELECT 1 FROM information_schema.columns
              WHERE table_name='work_workrequest' AND column_name='gender_preference')
  AND NOT EXISTS (SELECT 1 FROM django_migrations WHERE app='work' AND name='0009_workrequest_gender_preference');

-- work.0010_hot_path_indexes -> indexes must exist
INSERT INTO django_migrations (app, name, applied)
SELECT 'work', '0010_hot_path_indexes', now()
WHERE EXISTS (SELECT 1 FROM pg_indexes WHERE indexname='wr_status_created_idx')
  AND EXISTS (SELECT 1 FROM pg_indexes WHERE indexname='msg_conv_created_idx')
  AND NOT EXISTS (SELECT 1 FROM django_migrations WHERE app='work' AND name='0010_hot_path_indexes');

-- work.0011 -> choices-only, no DDL
INSERT INTO django_migrations (app, name, applied)
SELECT 'work', '0011_alter_message_media_type', now()
WHERE NOT EXISTS (SELECT 1 FROM django_migrations WHERE app='work' AND name='0011_alter_message_media_type');

COMMIT;

-- RESULT: anything still listed here was NOT recorded, because its schema
-- object was missing. That is correct and safe — the next deploy's `migrate`
-- will apply it for real. An empty result means state is fully reconciled.
WITH expected(app, name) AS (VALUES
    ('collab','0006_collabtask'),
    ('collab','0007_collabpost_visibility'),
    ('collab','0008_hot_path_indexes'),
    ('notifications','0003_notification_actor'),
    ('notifications','0004_notification_collab_match_type'),
    ('notifications','0005_hot_path_indexes'),
    ('portfolio','0004_alter_portfolioitem_portfolio_type'),
    ('skills','0003_delete_certificate'),
    ('users','0013_user_google_sub'),
    ('users','0014_phoneotpverification_user_phone_verified'),
    ('users','0015_delete_studentprofile'),
    ('work','0007_conversation_collab_post'),
    ('work','0008_message_read_at_typingstatus'),
    ('work','0009_workrequest_gender_preference'),
    ('work','0010_hot_path_indexes'),
    ('work','0011_alter_message_media_type')
)
SELECT e.app, e.name AS still_unrecorded
FROM expected e
LEFT JOIN django_migrations m ON m.app = e.app AND m.name = e.name
WHERE m.id IS NULL
ORDER BY e.app, e.name;
