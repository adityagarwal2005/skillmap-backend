from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('notifications', '0003_notification_actor'),
    ]

    operations = [
        migrations.AlterField(
            model_name='notification',
            name='notification_type',
            field=models.CharField(
                choices=[
                    ('work_request', 'Work Request'),
                    ('proposal', 'Proposal'),
                    ('proposal_accepted', 'Proposal Accepted'),
                    ('proposal_declined', 'Proposal Declined'),
                    ('work_assigned', 'Work Assigned'),
                    ('message', 'Message'),
                    ('reaction', 'Reaction'),
                    ('comment', 'Comment'),
                    ('referral', 'Referral'),
                    ('job_complete', 'Job Complete'),
                    ('friend_request', 'Friend Request'),
                    ('friend_accepted', 'Friend Accepted'),
                    ('collab_match', 'Collab Match'),
                ],
                max_length=20,
            ),
        ),
    ]
