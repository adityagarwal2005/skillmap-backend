from django.db import models
from users.models import User
from skills.models import Skill


class CollabPost(models.Model):
    COLLAB_TYPE_CHOICES = [
        ('equity', 'Equity'),
        ('experience', 'Experience'),
        ('paid', 'Paid'),
    ]

    STATUS_CHOICES = [
        ('open', 'Open'),
        ('closed', 'Closed'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='collab_posts')
    title = models.CharField(max_length=200)
    description = models.TextField()
    skills_needed = models.ManyToManyField(Skill, related_name='collab_posts', blank=True)
    collab_type = models.CharField(max_length=15, choices=COLLAB_TYPE_CHOICES, default='experience')
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='open')
    created_at = models.DateTimeField(auto_now_add=True, null=True)

    def __str__(self):
        return f"{self.user.username} - {self.title}"


class CollabRequest(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('accepted', 'Accepted'),
        ('declined', 'Declined'),
    ]

    collab_post = models.ForeignKey(CollabPost, on_delete=models.CASCADE, related_name='requests')
    applicant = models.ForeignKey(User, on_delete=models.CASCADE, related_name='collab_requests')
    message = models.TextField(null=True, blank=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending')
    latitude = models.FloatField(null=True, blank=True)   # new
    longitude = models.FloatField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, null=True)

    class Meta:
        unique_together = [["collab_post", "applicant"]]

    def __str__(self):
        return f"{self.applicant.username} → {self.collab_post.title} - {self.status}"