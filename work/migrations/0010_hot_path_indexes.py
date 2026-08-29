from django.db import migrations, models


class Migration(migrations.Migration):
    """Indexes for the two highest-frequency query shapes in the app.

    The feed filters WorkRequest on status + an expires_at window and orders
    by -created_at; the open chat thread re-fetches its messages every few
    seconds ordered by created_at. Both were sequential scans.
    """

    dependencies = [
        ('work', '0009_workrequest_gender_preference'),
    ]

    operations = [
        migrations.AddIndex(
            model_name='workrequest',
            index=models.Index(fields=['status', '-created_at'], name='wr_status_created_idx'),
        ),
        migrations.AddIndex(
            model_name='workrequest',
            index=models.Index(fields=['expires_at'], name='wr_expires_idx'),
        ),
        migrations.AddIndex(
            model_name='message',
            index=models.Index(fields=['conversation', 'created_at'], name='msg_conv_created_idx'),
        ),
    ]
