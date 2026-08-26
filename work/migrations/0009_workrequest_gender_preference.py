from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('work', '0008_message_read_at_typingstatus'),
    ]

    operations = [
        migrations.AddField(
            model_name='workrequest',
            name='gender_preference',
            field=models.CharField(
                default='any',
                max_length=10,
                choices=[('any', 'Any'), ('male', 'Male'), ('female', 'Female')],
            ),
        ),
    ]
