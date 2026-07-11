from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('work', '0004_workrequest_media')]
    operations = [
        migrations.AddField(model_name='workrequest', name='range_km',
                            field=models.FloatField(blank=True, null=True)),
    ]
