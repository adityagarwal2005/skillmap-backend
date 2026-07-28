from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('work', '0006_workrequest_completion'),
        ('collab', '0005_collabpost_range_km'),
    ]

    operations = [
        migrations.AlterField(
            model_name='conversation',
            name='conversation_type',
            field=models.CharField(
                choices=[
                    ('freelance', 'Freelance'),
                    ('work', 'Work'),
                    ('direct', 'Direct'),
                    ('collab', 'Collab'),
                ],
                max_length=10,
            ),
        ),
        migrations.AddField(
            model_name='conversation',
            name='collab_post',
            field=models.OneToOneField(
                blank=True, null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='conversation', to='collab.collabpost',
            ),
        ),
    ]
