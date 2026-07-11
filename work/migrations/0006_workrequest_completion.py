from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('work', '0005_workrequest_range_km'),
    ]

    operations = [
        migrations.AddField(
            model_name='workrequest',
            name='completed_by_poster',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='workrequest',
            name='completed_by_worker',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='workrequest',
            name='completed_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
