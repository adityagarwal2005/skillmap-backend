from django.db import migrations, models


class Migration(migrations.Migration):
    """The unread badge polls on every screen, so the unread count is one of
    the most-run queries in the app."""

    dependencies = [
        ('notifications', '0004_notification_collab_match_type'),
    ]

    operations = [
        migrations.AddIndex(
            model_name='notification',
            index=models.Index(fields=['user', 'is_read'], name='notif_user_unread_idx'),
        ),
        migrations.AddIndex(
            model_name='notification',
            index=models.Index(fields=['user', '-created_at'], name='notif_user_created_idx'),
        ),
    ]
