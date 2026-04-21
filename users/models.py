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