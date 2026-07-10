from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('work', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='workrequest',
            name='latitude',
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='workrequest',
            name='longitude',
            field=models.FloatField(blank=True, null=True),
        ),
    ]
