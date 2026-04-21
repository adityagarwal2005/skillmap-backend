from django.db import models
from users.models import User


class Category(models.Model):
    name = models.CharField(max_length=100, unique=True)

    def __str__(self):
        return self.name


class Skill(models.Model):
    name = models.CharField(max_length=100, unique=True)
    category = models.ForeignKey(
        Category, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='skills'
    )

    def __str__(self):
        return self.name


class Tag(models.Model):
    """
    Flexible tags for portfolio items.
    More generic than skills — covers any profession.
    Examples:
      Developer  → Python, React, Docker
      Baker      → Fondant, Sourdough, Wedding Cakes
      Photographer → Portrait, Landscape, Wedding
    """
    name = models.CharField(max_length=100, unique=True)
    category = models.ForeignKey(
        Category, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='tags'
    )

    def __str__(self):
        return self.name


class UserSkill(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    skill = models.ForeignKey(Skill, on_delete=models.CASCADE)

    class Meta:
        unique_together = [["user", "skill"]]

    def __str__(self):
        return f"{self.user.username} - {self.skill.name}"


class Certificate(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    title = models.CharField(max_length=255)
    issued_by = models.CharField(max_length=255)
    issued_date = models.DateField(null=True, blank=True)
    certificate_url = models.URLField(null=True, blank=True)
    image = models.ImageField(upload_to='certificates/', null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, null=True)

    def __str__(self):
        return f"{self.user.username} - {self.title}"