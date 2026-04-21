from django.db import models
from users.models import User
from skills.models import Skill


class WorkRequest(models.Model):
    STATUS_CHOICES = [
        ('open', 'Open'),
        ('assigned', 'Assigned'),
        ('closed', 'Closed'),
    ]

    created_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='work_requests')
    description = models.TextField()
    required_skills = models.ManyToManyField(Skill, related_name='work_requests')
    payment_amount = models.FloatField()
    time_limit_hours = models.IntegerField()
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='open')
    assigned_to = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='assigned_work')
    created_at = models.DateTimeField(auto_now_add=True, null=True)
    expires_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.created_by.username} - {self.description[:30]}"


class WorkRequestResponse(models.Model):
    STATUS_CHOICES = [
        ('accepted', 'Accepted'),
        ('declined', 'Declined'),
    ]

    work_request = models.ForeignKey(WorkRequest, on_delete=models.CASCADE, related_name='responses')
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES)
    message = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, null=True)

    class Meta:
        unique_together = [["work_request", "user"]]

    def __str__(self):
        return f"{self.user.username} - {self.status}"


class WorkProposal(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('accepted', 'Accepted'),
        ('declined', 'Declined'),
    ]

    sender = models.ForeignKey(User, on_delete=models.CASCADE, related_name='sent_proposals')
    receiver = models.ForeignKey(User, on_delete=models.CASCADE, related_name='received_proposals')
    description = models.TextField()
    payment_per_hour = models.FloatField(null=True, blank=True)
    payment_per_day = models.FloatField(null=True, blank=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending')
    created_at = models.DateTimeField(auto_now_add=True, null=True)

    class Meta:
        unique_together = [["sender", "receiver"]]

    def __str__(self):
        return f"{self.sender.username} → {self.receiver.username} - {self.status}"


class Conversation(models.Model):
    TYPE_CHOICES = [
        ('freelance', 'Freelance'),
        ('work', 'Work'),
    ]

    participants = models.ManyToManyField(User, related_name='conversations')
    work_request = models.OneToOneField(
        WorkRequest, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='conversation'
    )
    conversation_type = models.CharField(max_length=10, choices=TYPE_CHOICES)
    created_at = models.DateTimeField(auto_now_add=True, null=True)

    def __str__(self):
        return f"Conversation {self.id} - {self.conversation_type}"


class Message(models.Model):
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name='messages')
    sender = models.ForeignKey(User, on_delete=models.CASCADE)
    text = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True, null=True)

    def __str__(self):
        return f"{self.sender.username}: {self.text[:30]}"