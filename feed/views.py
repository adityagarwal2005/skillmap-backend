from django.http import JsonResponse
from django.db.models import Q
from users.models import User, Block
from skills.models import Skill, Tag
from users.views import get_user_from_token
import math
from portfolio.models import PortfolioItem, Reaction, Comment


STOP_WORDS = {
    'a', 'an', 'the', 'and', 'or', 'but', 'in', 'on', 'at', 'to',
    'for', 'of', 'with', 'by', 'from', 'is', 'it', 'its', 'this',
    'that', 'was', 'are', 'be', 'been', 'being', 'have', 'has',
    'had', 'do', 'does', 'did', 'will', 'would', 'could', 'should',
    'may', 'might', 'shall', 'can', 'need', 'i', 'my', 'me', 'we',
    'our', 'you', 'your', 'he', 'she', 'they', 'them', 'their',
    'what', 'which', 'who', 'how', 'when', 'where', 'consisting',
    'using', 'built', 'made', 'project', 'projects', 'show', 'get',
    'together', 'some', 'any', 'all', 'just', 'also', 'about'
}


def parse_pagination(request):
    """Read ?limit=&offset= from the query string, clamped to sane bounds."""
    try:
        limit = int(request.GET.get('limit', 20))
    except (TypeError, ValueError):
        limit = 20
    try:
        offset = int(request.GET.get('offset', 0))
    except (TypeError, ValueError):
        offset = 0
    return max(1, min(limit, 50)), max(0, offset)


def get_distance_km(lat1, lon1, lat2, lon2):
    R = 6371
    d_lat = math.radians(lat2 - lat1)
    d_lon = math.radians(lon2 - lon1)
    a = (math.sin(d_lat / 2) ** 2 +
         math.cos(math.radians(lat1)) *
         math.cos(math.radians(lat2)) *
         math.sin(d_lon / 2) ** 2)
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def relevance_score(item, words):
    score = 0
    text = f"{item.title} {item.description}".lower()
    tags = [t.name.lower() for t in item.tags.all()]
    skills = [s.name.lower() for s in item.skills.all()]
    all_text = text + " " + " ".join(tags) + " " + " ".join(skills)
    for word in words:
        if word.lower() in all_text:
            score += 1
    return score


def format_item(item, request):
    return {
        "id": item.id,
        "user": {
            "id": item.user.id,
            "username": item.user.username,
            "category": item.user.category.name if item.user.category else None,
            "profile_image": request.build_absolute_uri(item.user.profile_image.url) if item.user.profile_image else None,
        },
        "title": item.title,
        "description": item.description,
        "portfolio_type": item.portfolio_type,
        "skills": [s.name for s in item.skills.all()],
        "tags": [t.name for t in item.tags.all()],
        "media": [
            {
                "id": m.id,
                "media_type": m.media_type,
                "url": m.url if m.url else request.build_absolute_uri(m.file.url) if m.file else None,
                "order": m.order,
            }
            for m in item.media.all()
        ],
        "reactions": item.reactions.count(),
        "comments": item.comments.count(),
        "latitude": item.latitude,
        "longitude": item.longitude,
        "created_at": item.created_at,
    }


def apply_radius_filter(items, lat, lon, radius):
    filtered = []
    for item in items:
        if item.latitude and item.longitude:
            distance = get_distance_km(lat, lon, item.latitude, item.longitude)
            if distance <= radius:
                filtered.append(item)
        elif item.user.latitude and item.user.longitude:
            distance = get_distance_km(lat, lon, item.user.latitude, item.user.longitude)
            if distance <= radius:
                filtered.append(item)
    return filtered


def _feed_user(u, request):
    return {
        'id': u.id,
        'username': u.username,
        'category': u.category.name if u.category else None,
        'profile_image': request.build_absolute_uri(u.profile_image.url) if u.profile_image else None,
    }


def _job_item(wr, request, distance=None):
    return {
        'kind': 'freelance',
        'id': wr.id,
        'title': (wr.description or '').strip()[:70],
        'description': wr.description,
        'skills': [s.name for s in wr.required_skills.all()],
        'created_at': str(wr.created_at) if wr.created_at else None,
        'payment_amount': wr.payment_amount,
        'time_limit_hours': wr.time_limit_hours,
        'responses_count': wr.responses.count(),
        'distance_km': distance,
        'media': wr.media or None,
        'media_type': wr.media_type or None,
        'user': _feed_user(wr.created_by, request),
    }


def _collab_item(cp, request, distance=None):
    return {
        'kind': 'collab',
        'id': cp.id,
        'title': cp.title,
        'description': cp.description,
        'skills': [s.name for s in cp.skills_needed.all()],
        'created_at': str(cp.created_at) if cp.created_at else None,
        'collab_type': cp.collab_type,
        'applicants': cp.requests.count() if hasattr(cp, 'requests') else 0,
        'distance_km': distance,
        'media': cp.media or None,
        'media_type': cp.media_type or None,
        'user': _feed_user(cp.user, request),
    }


def _ts(dt):
    return dt.timestamp() if dt else 0


def smart_feed(request):
    """For You — open freelance jobs + collab posts, ranked by how well they
    match the viewer's skills/category (falls back to most-recent)."""
    result = get_user_from_token(request)
    user = result[0] if isinstance(result, tuple) else result
    if not user:
        return JsonResponse({'error': 'Unauthorized'}, status=401)

    from work.models import WorkRequest
    from collab.models import CollabPost

    user_skills = {s.name.lower() for s in user.skills.all()}
    cat_id = user.category_id
    blocked = set(Block.objects.filter(blocker=user).values_list('blocked_id', flat=True))

    scored = []  # (score, created_at, kind, obj)

    for wr in WorkRequest.objects.filter(status='open').exclude(created_by=user).exclude(created_by_id__in=blocked):
        sk = {s.name.lower() for s in wr.required_skills.all()}
        score = 2 * len(user_skills & sk)
        if cat_id and wr.created_by.category_id == cat_id:
            score += 3
        if not user_skills and not cat_id:
            score = 1
        scored.append((score, wr.created_at, 'j', wr))

    for cp in CollabPost.objects.filter(status='open').exclude(user=user).exclude(user_id__in=blocked):
        sk = {s.name.lower() for s in cp.skills_needed.all()}
        score = 2 * len(user_skills & sk)
        if cat_id and cp.user.category_id == cat_id:
            score += 3
        if not user_skills and not cat_id:
            score = 1
        scored.append((score, cp.created_at, 'c', cp))

    scored.sort(key=lambda x: (x[0], _ts(x[1])), reverse=True)

    limit, offset = parse_pagination(request)
    total = len(scored)
    page = scored[offset:offset + limit]
    feed = [_job_item(o, request) if k == 'j' else _collab_item(o, request) for (_, _, k, o) in page]
    return JsonResponse({'feed': feed, 'count': total, 'has_more': offset + limit < total})
def search_feed(request):
    if request.method == "GET":
        q = request.GET.get("q", "").strip()
        tags = request.GET.get("tags", "").strip()
        radius_km = request.GET.get("radius", "").strip()
        latitude = request.GET.get("latitude", "").strip()
        longitude = request.GET.get("longitude", "").strip()
        portfolio_type = request.GET.get("type", "").strip()

        items = PortfolioItem.objects.select_related(
            "user", "user__category"
        ).prefetch_related(
            "skills", "tags", "media", "reactions", "comments"
        ).order_by("-created_at")

        search_words = []
        if q:
            search_words = [w for w in q.lower().split() if w not in STOP_WORDS]
            if not search_words:
                return JsonResponse({"error": "Please enter more specific search terms"}, status=400)
            query = Q()
            for word in search_words:
                query |= (
                    Q(title__icontains=word) |
                    Q(description__icontains=word) |
                    Q(tags__name__icontains=word) |
                    Q(skills__name__icontains=word) |
                    Q(user__username__icontains=word)
                )
            items = items.filter(query).distinct()

        if tags:
            tag_list = [t.strip() for t in tags.split(",")]
            for tag_name in tag_list:
                items = items.filter(
                    Q(tags__name__iexact=tag_name) |
                    Q(skills__name__iexact=tag_name)
                ).distinct()

        if portfolio_type:
            items = items.filter(portfolio_type=portfolio_type)

        if radius_km and latitude and longitude:
            try:
                items = apply_radius_filter(
                    list(items),
                    float(latitude),
                    float(longitude),
                    float(radius_km)
                )
            except ValueError:
                return JsonResponse({"error": "Invalid location values"}, status=400)

        if search_words:
            items = list(items)
            items.sort(key=lambda x: relevance_score(x, search_words), reverse=True)

        total = items.count() if hasattr(items, 'count') else len(items)
        limit, offset = parse_pagination(request)
        page = items[offset:offset + limit]

        data = [format_item(i, request) for i in page]
        return JsonResponse({"results": data, "count": total, "has_more": offset + limit < total})

    return JsonResponse({"error": "Method not allowed"}, status=405)
def trending_feed(request):
    """Trending — open freelance jobs + collab posts, nearest-first when we know
    the viewer's location, otherwise by popularity (applicants) + recency."""
    if request.method != "GET":
        return JsonResponse({"error": "Method not allowed"}, status=405)

    user, error = get_user_from_token(request)
    if error:
        return error

    from work.models import WorkRequest
    from collab.models import CollabPost

    blocked = set(Block.objects.filter(blocker=user).values_list('blocked_id', flat=True))
    has_loc = user.latitude is not None and user.longitude is not None

    entries = []  # (distance_or_None, popularity, created_at, kind, obj)

    for wr in WorkRequest.objects.filter(status='open').exclude(created_by=user).exclude(created_by_id__in=blocked):
        # Prefer the job's own (live) location, fall back to the poster's profile.
        j_lat = wr.latitude if wr.latitude is not None else wr.created_by.latitude
        j_lon = wr.longitude if wr.longitude is not None else wr.created_by.longitude
        dist = None
        if has_loc and j_lat is not None and j_lon is not None:
            dist = round(get_distance_km(user.latitude, user.longitude, j_lat, j_lon), 1)
        entries.append((dist, wr.responses.count(), wr.created_at, 'j', wr))

    for cp in CollabPost.objects.filter(status='open').exclude(user=user).exclude(user_id__in=blocked):
        dist = None
        if has_loc and cp.latitude is not None and cp.longitude is not None:
            dist = round(get_distance_km(user.latitude, user.longitude, cp.latitude, cp.longitude), 1)
        elif has_loc and cp.user.latitude is not None and cp.user.longitude is not None:
            dist = round(get_distance_km(user.latitude, user.longitude, cp.user.latitude, cp.user.longitude), 1)
        pop = cp.requests.count() if hasattr(cp, 'requests') else 0
        entries.append((dist, pop, cp.created_at, 'c', cp))

    if has_loc:
        # nearest first (unknown-distance last), then most applicants, then newest
        entries.sort(key=lambda e: (e[0] is None, e[0] if e[0] is not None else 0, -e[1], -_ts(e[2])))
    else:
        entries.sort(key=lambda e: (-e[1], -_ts(e[2])))

    limit, offset = parse_pagination(request)
    total = len(entries)
    page = entries[offset:offset + limit]
    trending = [_job_item(o, request, distance=d) if k == 'j' else _collab_item(o, request, distance=d)
                for (d, _, _, k, o) in page]
    return JsonResponse({"trending": trending, "count": total, "has_more": offset + limit < total})
