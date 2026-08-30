from django.db import migrations, models


class Migration(migrations.Migration):
    """Multi-person gigs.

    people_needed lets one gig hire a small team (1-5) instead of forcing the
    poster to repost. hired/rejected move the poster's decision onto each
    response: hiring used to be a single WorkRequest.assigned_to FK (so only
    one person could ever be hired) and rejecting deleted the row, which let
    the rejected applicant re-apply and kept the gig in their feed.
    """

    dependencies = [
        ('work', '0011_alter_message_media_type'),
    ]

    operations = [
        migrations.AddField(
            model_name='workrequest',
            name='people_needed',
            field=models.PositiveSmallIntegerField(default=1),
        ),
        migrations.AddField(
            model_name='workrequestresponse',
            name='hired',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='workrequestresponse',
            name='rejected',
            field=models.BooleanField(default=False),
        ),
    ]
