from .models import Notification


def notify(recipient, notification_type, message, actor=None):
    """Create a notification, safely.

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
