from django.db import models
from users.models import User
from work.models import WorkRequest


class Review(models.Model):
    reviewer = models.ForeignKey(User, on_delete=models.CASCADE, related_name='given_reviews')
    reviewee = models.ForeignKey(User, on_delete=models.CASCADE, related_name='received_reviews')
    work_request = models.ForeignKey(
        WorkRequest, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='reviews'
    )
    rating = models.IntegerField()  # 1-5
    comment = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, null=True)

    class Meta:
        unique_together = [["reviewer", "reviewee", "work_request"]]

    def __str__(self):
        return f"{self.reviewer.username} → {self.reviewee.username} - {self.rating}★"