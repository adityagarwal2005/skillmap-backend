from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('work', '0002_workrequest_location'),
    ]

    operations = [
        migrations.AddField(
            model_name='message',
            name='media',
            field=models.CharField(blank=True, default='', max_length=500),
        ),
        migrations.AddField(
            model_name='message',
            name='media_type',
            field=models.CharField(blank=True, default='', max_length=10),
        ),
        migrations.AlterField(
            model_name='message',
            name='text',
            field=models.TextField(blank=True, default=''),
        ),
    ]
