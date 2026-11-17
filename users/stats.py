"""Founder-only analytics — the single endpoint behind the private /dashboard.

Gated on settings.FOUNDER_EMAILS (set from the environment), so only the
founder's own account can read it; every other authenticated user gets a 403.
Day boundaries follow the project TIME_ZONE (Asia/Kolkata), so "today" means
today where the founder actually is.
"""
from datetime import timedelta

from django.conf import settings
from django.db.models import Count
from django.db.models.functions import TruncDate
from django.http import JsonResponse
from django.utils import timezone

from users.views import get_user_from_token
from users.models import User
from work.models import WorkRequest, WorkRequestResponse, Conversation, Message
from collab.models import CollabPost, CollabRequest
from portfolio.models import Video


def _is_founder(user):
    allow = [e.strip().lower() for e in getattr(settings, 'FOUNDER_EMAILS', []) if e.strip()]
    email = (getattr(user, 'email', '') or '').lower()
    return bool(email and email in allow)


def founder_stats(request):
    if request.method != 'GET':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    user, error = get_user_from_token(request)
    if error:
        return error
    if not _is_founder(user):
        return JsonResponse({'error': 'Not authorised'}, status=403)

    now = timezone.now()
    today = timezone.localtime(now).replace(hour=0, minute=0, second=0, microsecond=0)
    week = now - timedelta(days=7)
    month = now - timedelta(days=30)

    def b(qs, field='created_at'):
        """total / today / this-week / this-month counts for a queryset."""
        since = lambda t: qs.filter(**{f'{field}__gte': t}).count()
        return {'total': qs.count(), 'today': since(today), 'week': since(week), 'month': since(month)}

    # 14-day signup trend — one count per local day, zero-filled, oldest first.
    start = today - timedelta(days=13)
    by_day = {
        r['day']: r['c']
        for r in (User.objects.filter(created_at__gte=start)
                  .annotate(day=TruncDate('created_at')).values('day').annotate(c=Count('id')))
    }
    trend = []
    for i in range(14):
        d = (start + timedelta(days=i)).date()
        trend.append({'date': d.isoformat(), 'count': by_day.get(d, 0)})

    users = b(User.objects.all())
    users['trend'] = trend

    recent = User.objects.select_related('category').order_by('-created_at')[:8]
    recent_signups = [{
        'username': u.username,
        'category': (u.category.name if u.category_id and u.category else None),
        'created_at': u.created_at.isoformat() if u.created_at else None,
    } for u in recent]

    return JsonResponse({
        'generated_at': now.isoformat(),
        'users': users,
        'recent_signups': recent_signups,
        'gigs': {**b(WorkRequest.objects.all()), 'active': WorkRequest.objects.filter(status='open').count()},
        'collabs': {**b(CollabPost.objects.all()), 'active': CollabPost.objects.filter(status='open').count()},
        'applications': b(WorkRequestResponse.objects.all()),
        'collab_requests': b(CollabRequest.objects.all()),
        'videos': b(Video.objects.all()),
        'messages': b(Message.objects.all()),
        'conversations': b(Conversation.objects.all()),
        'completed_jobs': WorkRequest.objects.filter(completed_at__isnull=False).count(),
    })
