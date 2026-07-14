from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('notifications', '0001_initial'),
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
                ],
                max_length=20,
            ),
        ),
    ]
