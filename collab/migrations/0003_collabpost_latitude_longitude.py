from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('collab', '0002_collabrequest_latitude_collabrequest_longitude'),
    ]

    operations = [
        migrations.AddField(
            model_name='collabpost',
            name='latitude',
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='collabpost',
            name='longitude',
            field=models.FloatField(blank=True, null=True),
        ),
    ]
