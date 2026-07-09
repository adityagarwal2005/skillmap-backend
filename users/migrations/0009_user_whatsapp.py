from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0008_profileviews_endorsements'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='whatsapp',
            field=models.CharField(blank=True, default='', max_length=20),
        ),
    ]
