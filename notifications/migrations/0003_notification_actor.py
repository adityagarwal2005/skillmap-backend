from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('notifications', '0002_notification_friend_types'),
        ('users', '0012_friendship'),
    ]

    operations = [
        migrations.AddField(
            model_name='notification',
            name='actor',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='notifications_sent', to='users.user',
            ),
        ),
    ]
