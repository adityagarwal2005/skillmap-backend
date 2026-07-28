from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('skills', '0002_initial'),
    ]

    operations = [
        migrations.DeleteModel(
            name='Certificate',
        ),
    ]
