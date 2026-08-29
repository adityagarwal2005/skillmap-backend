from django.db import migrations, models


class Migration(migrations.Migration):
    """Same feed query shape as WorkRequest — see work/0010."""

    dependencies = [
        ('collab', '0007_collabpost_visibility'),
    ]

    operations = [
        migrations.AddIndex(
            model_name='collabpost',
            index=models.Index(fields=['status', '-created_at'], name='cp_status_created_idx'),
        ),
        migrations.AddIndex(
            model_name='collabpost',
            index=models.Index(fields=['expires_at'], name='cp_expires_idx'),
        ),
    ]
