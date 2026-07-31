from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('collab', '0005_collabpost_range_km'),
        ('users', '0012_friendship'),
    ]

    operations = [
        migrations.CreateModel(
            name='CollabTask',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('title', models.CharField(max_length=200)),
                ('is_done', models.BooleanField(default=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('assignee', models.ForeignKey(
                    blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                    related_name='assigned_collab_tasks', to='users.user',
                )),
                ('collab_post', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='tasks', to='collab.collabpost',
                )),
                ('created_by', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='created_collab_tasks', to='users.user',
                )),
            ],
            options={
                'ordering': ['is_done', '-created_at'],
            },
        ),
    ]
