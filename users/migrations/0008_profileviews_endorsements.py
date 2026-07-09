from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0007_user_headline_bio'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='profile_views',
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.CreateModel(
            name='SkillEndorsement',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('skill', models.CharField(max_length=100)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('endorser', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='endorsements_given', to='users.user')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='endorsements_received', to='users.user')),
            ],
            options={
                'unique_together': {('user', 'endorser', 'skill')},
            },
        ),
    ]
