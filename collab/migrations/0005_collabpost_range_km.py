from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('collab', '0004_collabpost_media')]
    operations = [
        migrations.AddField(model_name='collabpost', name='range_km',
                            field=models.FloatField(blank=True, null=True)),
    ]
