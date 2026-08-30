from django.db import migrations, models


class Migration(migrations.Migration):
    """Teammates wanted — mirrors WorkRequest.people_needed."""

    dependencies = [
        ('collab', '0008_hot_path_indexes'),
    ]

    operations = [
        migrations.AddField(
            model_name='collabpost',
            name='people_needed',
            field=models.PositiveSmallIntegerField(default=1),
        ),
    ]
