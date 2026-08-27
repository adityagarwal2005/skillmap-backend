from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('collab', '0006_collabtask'),
    ]

    operations = [
        migrations.AddField(
            model_name='collabpost',
            name='time_limit_hours',
            field=models.IntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='collabpost',
            name='expires_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
