from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('collab', '0003_collabpost_latitude_longitude'),
    ]

    operations = [
        migrations.AddField(
            model_name='collabpost',
            name='media',
            field=models.CharField(blank=True, default='', max_length=500),
        ),
        migrations.AddField(
            model_name='collabpost',
            name='media_type',
            field=models.CharField(blank=True, default='', max_length=10),
        ),
    ]
