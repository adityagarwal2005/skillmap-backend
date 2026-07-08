from django.http import JsonResponse
from django.db.models import Q
from users.models import User
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


def smart_feed(request):
    result = get_user_from_token(request)
    if isinstance(result, tuple):
        user = result[0]
    else:
        user = result

    if not user:
        return JsonResponse({'error': 'Unauthorized'}, status=401)

    user_skills = [s.name.lower() for s in user.skills.all()]
    user_category = user.category

    items = PortfolioItem.objects.all().order_by('-created_at')

    results = []
    for item in items:
        item_skills = [s.name.lower() for s in item.skills.all()]
        score = 0

        if user_category and item.user.category == user_category:
            score += 3

        for skill in user_skills:
            if skill in item_skills:
                score += 2

        if not user_skills and not user_category:
            score = 1

        if item.verified:
            score += 1

        results.append({'score': score, 'item': item})

    results.sort(key=lambda x: (x['score'], x['item'].created_at.timestamp()), reverse=True)

    feed = []
    for r in results:
        item = r['item']
        reactions = Reaction.objects.filter(portfolio_item=item).count()
        comments  = Comment.objects.filter(portfolio_item=item).count()
        feed.append({
            'id':             item.id,
            'title':          item.title,
            'description':    item.description,
            'portfolio_type': item.portfolio_type,
            'verified':       item.verified,
            'created_at':     str(item.created_at),
            'user': {
                'id':       item.user.id,
                'username': item.user.username,
                'category': item.user.category.name if item.user.category else None,
            },
            'skills':    [s.name for s in item.skills.all()],
            'tags':      [t.name for t in item.tags.all()],
            'media':     [{'id': m.id, 'url': m.url or (request.build_absolute_uri(m.file.url) if m.file else None), 'media_type': m.media_type} for m in item.media.all()],
            'reactions': reactions,
            'comments':  comments,
        })

    return JsonResponse({'feed': feed})
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

        data = [format_item(i, request) for i in items]
        return JsonResponse({"results": data, "count": len(data)})

    return JsonResponse({"error": "Method not allowed"}, status=405)
def trending_feed(request):
    if request.method == "GET":
        user, error = get_user_from_token(request)
        if error:
            return error

        from django.utils import timezone
        from datetime import timedelta

        one_week_ago = timezone.now() - timedelta(days=7)

        items = PortfolioItem.objects.select_related(
            "user", "user__category"
        ).prefetch_related(
            "skills", "tags", "media", "reactions", "comments"
        ).filter(created_at__gte=one_week_ago)

        if user.category:
            items = items.filter(user__category=user.category)

        items = sorted(items, key=lambda x: x.reactions.count(), reverse=True)

        data = [format_item(i, request) for i in items[:20]]
        return JsonResponse({"trending": data, "count": len(data)})

    return JsonResponse({"error": "Method not allowed"}, status=405)
