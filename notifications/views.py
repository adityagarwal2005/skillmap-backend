from django.http import JsonResponse
from .models import Notification
from users.views import get_user_from_token, friend_state


def get_user_from_request(request):
    return get_user_from_token(request)


def get_my_notifications(request):
    if request.method == "GET":
        user, error = get_user_from_request(request)
        if error:
            return error

        notifications = Notification.objects.filter(user=user).select_related("actor").order_by("-created_at")
        data = []
        for n in notifications:
            item = {
                "id": n.id,
                "type": n.notification_type,
                "message": n.message,
                "is_read": n.is_read,
                "created_at": n.created_at,
                "actor_id": n.actor_id,
                "actor_username": n.actor.username if n.actor else None,
                "actor_avatar": (
                    request.build_absolute_uri(n.actor.profile_image.url)
                    if n.actor and n.actor.profile_image else None
                ),
            }
            # Live status, not a snapshot — so Accept/Decline disappears here
            # the moment it's actioned from anywhere (this page, People, etc).
            if n.notification_type == "friend_request" and n.actor_id:
                item["friendship_status"] = friend_state(user, n.actor)
            data.append(item)
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

def get_vapid_key(request):
    """Public — the browser needs the VAPID public key to subscribe."""
    from django.conf import settings
    return JsonResponse({'public_key': getattr(settings, 'VAPID_PUBLIC_KEY', '')})


def subscribe_push(request):
    if request.method != "POST":
        return JsonResponse({"error": "Method not allowed"}, status=405)
    user, error = get_user_from_request(request)
    if error:
        return error

    import json
    from users.models import PushSubscription
    try:
        body = json.loads(request.body.decode() or "{}")
    except Exception:
        return JsonResponse({"error": "Invalid body"}, status=400)

    endpoint = body.get('endpoint')
    keys = body.get('keys', {}) or {}
    p256dh = keys.get('p256dh')
    auth = keys.get('auth')
    if not (endpoint and p256dh and auth):
        return JsonResponse({"error": "Invalid subscription"}, status=400)

    PushSubscription.objects.update_or_create(
        endpoint=endpoint,
        defaults={'user': user, 'p256dh': p256dh, 'auth': auth},
    )
    return JsonResponse({"message": "Subscribed"}, status=201)


def unsubscribe_push(request):
    if request.method != "POST":
        return JsonResponse({"error": "Method not allowed"}, status=405)
    user, error = get_user_from_request(request)
    if error:
        return error

    import json
    from users.models import PushSubscription
    try:
        body = json.loads(request.body.decode() or "{}")
    except Exception:
        body = {}
    endpoint = body.get('endpoint')
    qs = PushSubscription.objects.filter(user=user)
    if endpoint:
        qs = qs.filter(endpoint=endpoint)
    qs.delete()
    return JsonResponse({"message": "Unsubscribed"})
