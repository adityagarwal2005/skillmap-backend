from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0010_pushsubscription'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='invited_by',
            field=models.ForeignKey(
                blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                related_name='referrals', to='users.user',
            ),
        ),
    ]
