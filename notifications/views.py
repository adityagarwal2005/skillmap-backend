from django.http import JsonResponse
from .models import Notification
from users.views import get_user_from_token


def get_user_from_request(request):
    return get_user_from_token(request)


def get_my_notifications(request):
    if request.method == "GET":
        user, error = get_user_from_request(request)
        if error:
            return error

        notifications = Notification.objects.filter(user=user).order_by("-created_at")
        data = [
            {
                "id": n.id,
                "type": n.notification_type,
                "message": n.message,
                "is_read": n.is_read,
                "created_at": n.created_at,
            }
            for n in notifications
        ]
        return JsonResponse({"notifications": data, "count": len(data)})

    return JsonResponse({"error": "Method not allowed"}, status=405)


def mark_as_read(request, notification_id):
    if request.method == "POST":
        user, error = get_user_from_request(request)
        if error:
            return error

        try:
            notification = Notification.objects.get(id=notification_id, user=user)
            notification.is_read = True
            notification.save()
            return JsonResponse({"message": "Notification marked as read"})
        except Notification.DoesNotExist:
            return JsonResponse({"error": "Notification not found"}, status=404)

    return JsonResponse({"error": "Method not allowed"}, status=405)


def mark_all_as_read(request):
    if request.method == "POST":
        user, error = get_user_from_request(request)
        if error:
            return error

        Notification.objects.filter(user=user, is_read=False).update(is_read=True)
        return JsonResponse({"message": "All notifications marked as read"})

    return JsonResponse({"error": "Method not allowed"}, status=405)


def get_unread_count(request):
    if request.method == "GET":
        user, error = get_user_from_request(request)
        if error:
            return error

        count = Notification.objects.filter(user=user, is_read=False).count()
        return JsonResponse({"unread_count": count})

    return JsonResponse({"error": "Method not allowed"}, status=405)