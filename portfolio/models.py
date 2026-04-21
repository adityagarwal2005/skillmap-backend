from django.db import models
from django.core.validators import MaxLengthValidator
from users.models import User
from skills.models import Skill, Tag


class PortfolioItem(models.Model):
    PORTFOLIO_TYPE_CHOICES = [
        ('project', 'Project'),
        ('design', 'Design'),
        ('photo', 'Photo'),
        ('baked_good', 'Baked Good'),
        ('artwork', 'Artwork'),
        ('video', 'Video'),
        ('other', 'Other'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='portfolio_items')
    title = models.CharField(max_length=100)
    description = models.CharField(
        max_length=200,
        validators=[MaxLengthValidator(200)],
        help_text="Max 200 characters — keep it short and to the point"
    )
    portfolio_type = models.CharField(max_length=20, choices=PORTFOLIO_TYPE_CHOICES, default='project')
    skills = models.ManyToManyField(Skill, related_name='portfolio_items', blank=True)
    tags = models.ManyToManyField(Tag, related_name='portfolio_items', blank=True)
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)
    verified = models.BooleanField(default=False)
    verified_via_work = models.ForeignKey(
        'work.WorkRequest',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='portfolio_items'
    )
    created_at = models.DateTimeField(auto_now_add=True, null=True)

    def __str__(self):
        return f"{self.user.username} - {self.title}"


class Media(models.Model):
    MEDIA_TYPE_CHOICES = [
        ('image', 'Image'),
        ('video', 'Video'),
        ('link', 'Link'),
    ]

    portfolio_item = models.ForeignKey(PortfolioItem, on_delete=models.CASCADE, related_name='media')
    file = models.FileField(upload_to='portfolio/', null=True, blank=True)
    url = models.URLField(null=True, blank=True)
    media_type = models.CharField(max_length=10, choices=MEDIA_TYPE_CHOICES)
    order = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True, null=True)

    class Meta:
        ordering = ['order']

    def __str__(self):
        return f"{self.portfolio_item.title} - {self.media_type}"


class Reaction(models.Model):
    REACTION_TYPE_CHOICES = [
        ('like', 'Like'),
        ('love', 'Love'),
        ('fire', 'Fire'),
    ]

    portfolio_item = models.ForeignKey(PortfolioItem, on_delete=models.CASCADE, related_name='reactions')
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    reaction_type = models.CharField(max_length=10, choices=REACTION_TYPE_CHOICES, default='like')
    created_at = models.DateTimeField(auto_now_add=True, null=True)

    class Meta:
        unique_together = [["portfolio_item", "user"]]

    def __str__(self):
        return f"{self.user.username} - {self.reaction_type} - {self.portfolio_item.title}"


class Comment(models.Model):
    portfolio_item = models.ForeignKey(PortfolioItem, on_delete=models.CASCADE, related_name='comments')
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    text = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True, null=True)

    def __str__(self):
        return f"{self.user.username} - {self.text[:30]}"