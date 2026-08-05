from .models import Notification


def send_web_push(recipient, title, body, url='/'):
    """Best-effort Web Push. Never raises — if VAPID keys, the pywebpush
    package, or the subscription table are missing, it silently no-ops."""
    try:
        from django.conf import settings
        priv = getattr(settings, 'VAPID_PRIVATE_KEY', '')
        if not priv:
            return
        import json
        from pywebpush import webpush, WebPushException
        from users.models import PushSubscription

        claims = {'sub': getattr(settings, 'VAPID_CLAIMS_EMAIL', 'mailto:admin@doithere.in')}
        payload = json.dumps({'title': title, 'body': body, 'url': url})

        for sub in PushSubscription.objects.filter(user=recipient):
            try:
                webpush(
                    subscription_info={
                        'endpoint': sub.endpoint,
                        'keys': {'p256dh': sub.p256dh, 'auth': sub.auth},
                    },
                    data=payload,
                    vapid_private_key=priv,
                    vapid_claims=dict(claims),   # pywebpush mutates this dict
                    timeout=5,
                )
            except WebPushException as ex:
                # Subscription gone/expired → drop it so we stop trying.
                resp = getattr(ex, 'response', None)
                if resp is not None and resp.status_code in (404, 410):
                    sub.delete()
            except Exception:
                pass
    except Exception:
        pass


def notify(recipient, notification_type, message, actor=None):
    """Create a notification, safely, and fire a web push if the user opted in.

    - Never notifies a user about their own action (recipient == actor).
    - Never lets a notification failure break the underlying action.
    """
    if recipient is None:
        return
    if actor is not None and getattr(recipient, "id", None) == getattr(actor, "id", None):
        return
    try:
        Notification.objects.create(
            user=recipient,
            notification_type=notification_type,
            message=message,
            actor=actor,
        )
    except Exception:
        pass
    # Push is fully isolated — its own try/except inside.
    send_web_push(recipient, 'SkillMap', message, url='/notifications')


# Cap how many people a single post can fan out to — a popular category
# shouldn't turn one post into a notification storm.
MATCHING_NOTIFY_CAP = 200


def _notify_category_match_sync(category_ids, poster_id, notification_type, message):
    try:
        from users.models import User, Block

        blocked = set(Block.objects.filter(blocker_id=poster_id).values_list('blocked_id', flat=True))
        blocked_by = set(Block.objects.filter(blocked_id=poster_id).values_list('blocker_id', flat=True))
        hidden = blocked | blocked_by

        matches = (
            User.objects.filter(category_id__in=category_ids)
            .exclude(id=poster_id)
            .exclude(id__in=hidden)[:MATCHING_NOTIFY_CAP]
        )
        for u in matches:
            notify(u, notification_type, message, actor=None)
    except Exception:
        pass


def notify_category_match(skill_objects, poster, notification_type, message):
    """Notify users whose profile category matches one of a new post's
    required/needed skills' categories. This is the 'matching jobs' feature
    Settings already advertises ("Get pinged for messages, applications, and
    matching jobs") but that had zero backend support until now — every new
    freelance job or collab post silently reached nobody but people already
    browsing the feed.

    Runs in a background thread — up to MATCHING_NOTIFY_CAP recipients, each
    a notify() call that can itself do a blocking web-push request per
    device, so doing this inline would make posting a job noticeably slower
    (or risk a timeout) in exactly the case where it worked best: a
    popular category with lots of matching people. Same pattern already
    used for OTP emails elsewhere in this file's neighborhood.
    """
    category_ids = {s.category_id for s in skill_objects if s.category_id}
    if not category_ids:
        return
    import threading
    thread = threading.Thread(
        target=_notify_category_match_sync,
        args=(category_ids, poster.id, notification_type, message),
    )
    thread.daemon = True
    thread.start()
