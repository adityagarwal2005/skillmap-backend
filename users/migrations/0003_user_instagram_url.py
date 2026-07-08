from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0002_otpverification'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='instagram_url',
            field=models.URLField(blank=True, null=True),
        ),
    ]
