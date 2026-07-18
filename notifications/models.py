from django.db import models
from users.models import User


class Notification(models.Model):
    TYPE_CHOICES = [
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
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications')
    notification_type = models.CharField(max_length=20, choices=TYPE_CHOICES)
    message = models.TextField()
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True, null=True)
    # Who did the thing that triggered this notification (was accepted by
    # notify() but never actually saved — meant the Notifications page had no
    # way to act on a friend request, e.g. Accept/Decline right there).
    actor = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name='notifications_sent'
    )

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user.username} - {self.notification_type}"