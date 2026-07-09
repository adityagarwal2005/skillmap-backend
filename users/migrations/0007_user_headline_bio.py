from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0006_block_report'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='headline',
            field=models.CharField(blank=True, default='', max_length=120),
        ),
        migrations.AddField(
            model_name='user',
            name='bio',
            field=models.TextField(blank=True, default=''),
        ),
    ]
