from django.db import models


class User(models.Model):
    STATUS_CHOICES = [
        ('open_to_freelance', 'Open to Freelance'),
        ('open_to_work', 'Open to Work'),
        ('not_available', 'Not Available'),
    ]

    username = models.CharField(max_length=100, unique=True)
    email = models.EmailField(unique=True)
    password = models.CharField(max_length=255)
    category = models.ForeignKey(
        'skills.Category', on_delete=models.SET_NULL, null=True, blank=True
    )
    skills = models.ManyToManyField(
        'skills.Skill', through='skills.UserSkill', blank=True
    )
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)
    rating = models.FloatField(default=0.0)
    linkedin_url = models.URLField(null=True, blank=True)
    github_url = models.URLField(null=True, blank=True)
    instagram_url = models.URLField(null=True, blank=True)
    whatsapp = models.CharField(max_length=20, blank=True, default='')
    dob = models.DateField(null=True, blank=True)
    headline = models.CharField(max_length=120, blank=True, default='')
    bio = models.TextField(blank=True, default='')
    profile_views = models.PositiveIntegerField(default=0)
    profile_image = models.ImageField(upload_to='avatars/', null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='not_available')
    created_at = models.DateTimeField(auto_now_add=True, null=True)

    def __str__(self):
        return self.username


class StudentProfile(models.Model):
    EDUCATION_TYPE_CHOICES = [
        ('school', 'School'),
        ('college', 'College'),
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE)
    education_type = models.CharField(max_length=10, choices=EDUCATION_TYPE_CHOICES)
    degree_name = models.CharField(max_length=255, null=True, blank=True)
    current_year = models.IntegerField(null=True, blank=True)
    current_class = models.IntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, null=True)

    def __str__(self):
        return f"{self.user.username} - {self.education_type}"
    

import random
from django.utils import timezone

class OTPVerification(models.Model):
    email   = models.EmailField()
    otp     = models.CharField(max_length=6)
    created_at = models.DateTimeField(auto_now_add=True)
    is_used = models.BooleanField(default=False)

    def is_expired(self):
        return (timezone.now() - self.created_at).seconds > 600  # 10 min expiry


class Block(models.Model):
    """blocker no longer sees blocked's posts / can message them."""
    blocker = models.ForeignKey(User, on_delete=models.CASCADE, related_name='blocking')
    blocked = models.ForeignKey(User, on_delete=models.CASCADE, related_name='blocked_by')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('blocker', 'blocked')

    def __str__(self):
        return f"{self.blocker.username} blocked {self.blocked.username}"


class SkillEndorsement(models.Model):
    """One peer endorsing one of a user's skills (by name)."""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='endorsements_received')
    endorser = models.ForeignKey(User, on_delete=models.CASCADE, related_name='endorsements_given')
    skill = models.CharField(max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'endorser', 'skill')

    def __str__(self):
        return f"{self.endorser.username} → {self.user.username} ({self.skill})"


class PushSubscription(models.Model):
    """A browser Web Push subscription so we can notify a user when the app is closed."""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='push_subscriptions')
    endpoint = models.TextField(unique=True)
    p256dh = models.CharField(max_length=255)
    auth = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"push: {self.user.username}"


class Report(models.Model):
    REPORT_TYPE_CHOICES = [
        ('user', 'User'),
        ('post', 'Post'),
    ]
    REASON_CHOICES = [
        ('spam', 'Spam'),
        ('harassment', 'Harassment or bullying'),
        ('inappropriate', 'Inappropriate content'),
        ('scam', 'Scam or fraud'),
        ('other', 'Other'),
    ]

    reporter = models.ForeignKey(User, on_delete=models.CASCADE, related_name='reports_made')
    report_type = models.CharField(max_length=10, choices=REPORT_TYPE_CHOICES)
    reported_user = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.CASCADE, related_name='reports_received'
    )
    reported_post = models.ForeignKey(
        'portfolio.PortfolioItem', null=True, blank=True,
        on_delete=models.CASCADE, related_name='reports'
    )
    reason = models.CharField(max_length=20, choices=REASON_CHOICES)
    details = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        target = self.reported_user.username if self.reported_user else f"post #{self.reported_post_id}"
        return f"{self.reporter.username} reported {target} ({self.reason})"