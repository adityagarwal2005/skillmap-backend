from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('work', '0003_message_media'),
    ]

    operations = [
        migrations.AddField(
            model_name='workrequest',
            name='media',
            field=models.CharField(blank=True, default='', max_length=500),
        ),
        migrations.AddField(
            model_name='workrequest',
            name='media_type',
            field=models.CharField(blank=True, default='', max_length=10),
        ),
    ]
