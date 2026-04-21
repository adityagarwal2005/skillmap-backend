from django.http import JsonResponse
from .models import Review
from users.models import User
from work.models import WorkRequest
from users.views import get_user_from_token


def get_user_from_request(request):
    return get_user_from_token(request)


def add_review(request, reviewee_id):
    if request.method == "POST":
        user, error = get_user_from_request(request)
        if error:
            return error

        if user.id == reviewee_id:
            return JsonResponse({"error": "You cannot review yourself"}, status=400)

        try:
            reviewee = User.objects.get(id=reviewee_id)

            rating = request.POST.get("rating", "").strip()
            comment = request.POST.get("comment", "").strip()
            work_request_id = request.POST.get("work_request_id", "").strip()

            if not rating:
                return JsonResponse({"error": "Rating is required"}, status=400)

            rating = int(rating)
            if rating < 1 or rating > 5:
                return JsonResponse({"error": "Rating must be between 1 and 5"}, status=400)

            work_request = None
            if work_request_id:
                try:
                    work_request = WorkRequest.objects.get(id=work_request_id)
                except WorkRequest.DoesNotExist:
                    return JsonResponse({"error": "Work request not found"}, status=404)

            if Review.objects.filter(
                reviewer=user,
                reviewee=reviewee,
                work_request=work_request
            ).exists():
                return JsonResponse({"error": "You have already reviewed this user for this work"}, status=400)

            review = Review.objects.create(
                reviewer=user,
                reviewee=reviewee,
                work_request=work_request,
                rating=rating,
                comment=comment if comment else None,
            )

            # update reviewee's average rating
            all_reviews = Review.objects.filter(reviewee=reviewee)
            avg = sum(r.rating for r in all_reviews) / all_reviews.count()
            reviewee.rating = round(avg, 2)
            reviewee.save()

            return JsonResponse({
                "message": "Review submitted",
                "review_id": review.id,
                "rating": review.rating,
            }, status=201)

        except User.DoesNotExist:
            return JsonResponse({"error": "User not found"}, status=404)

    return JsonResponse({"error": "Method not allowed"}, status=405)


def get_user_reviews(request, user_id):
    if request.method == "GET":
        try:
            user = User.objects.get(id=user_id)
            reviews = Review.objects.filter(reviewee=user).select_related("reviewer", "work_request")
            data = [
                {
                    "id": r.id,
                    "from": r.reviewer.username,
                    "rating": r.rating,
                    "comment": r.comment,
                    "work_request_id": r.work_request.id if r.work_request else None,
                    "created_at": r.created_at,
                }
                for r in reviews
            ]
            return JsonResponse({
                "user": user.username,
                "average_rating": user.rating,
                "reviews": data,
                "count": len(data)
            })
        except User.DoesNotExist:
            return JsonResponse({"error": "User not found"}, status=404)

    return JsonResponse({"error": "Method not allowed"}, status=405)