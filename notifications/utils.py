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
        )
    except Exception:
        pass
    # Push is fully isolated — its own try/except inside.
    send_web_push(recipient, 'SkillMap', message, url='/notifications')
