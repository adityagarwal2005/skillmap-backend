from django.http import JsonResponse
from django.utils import timezone
from .models import CollabPost, CollabRequest
from users.models import User
from skills.models import Skill
from users.views import get_user_from_token, require_contact
from work.views import get_distance_km


def get_user_from_request(request):
    return get_user_from_token(request)


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


def create_collab_post(request):
    if request.method == "POST":
        user, error = get_user_from_request(request)
        if error:
            return error

        guard = require_contact(user)
        if guard:
            return guard

        # Cheap flood guard — without this a bad actor (or a buggy retry loop)
        # could spam the Collab feed with dozens of posts in seconds.
        recent = CollabPost.objects.filter(user=user).order_by('-created_at').first()
        if recent and (timezone.now() - recent.created_at).total_seconds() < 20:
            return JsonResponse({"error": "Please wait a moment before posting again."}, status=429)

        title = request.POST.get("title", "").strip()
        description = request.POST.get("description", "").strip()
        skills_input = request.POST.get("skills", "").strip()

        if not title or not description:
            return JsonResponse({"error": "title and description are required"}, status=400)

        latitude = request.POST.get("latitude", "").strip()
        longitude = request.POST.get("longitude", "").strip()
        range_km = request.POST.get("range_km", "").strip()
        from users.views import upload_media_file
        media_url, media_type = upload_media_file(request.FILES.get("media"))
        post = CollabPost.objects.create(
            user=user,
            title=title,
            description=description,
            collab_type='experience',   # collab has no money deal — type removed
            latitude=float(latitude) if latitude else None,
            longitude=float(longitude) if longitude else None,
            range_km=float(range_km) if range_km else None,
            media=media_url,
            media_type=media_type,
        )

        if skills_input:
            skill_list = [s.strip() for s in skills_input.split(",")]
            skill_objects = []
            invalid = []
            for skill_name in skill_list:
                try:
                    skill = Skill.objects.get(name__iexact=skill_name)
                    skill_objects.append(skill)
                except Skill.DoesNotExist:
                    invalid.append(skill_name)
            if invalid:
                post.delete()
                return JsonResponse({"error": f"Invalid skills: {', '.join(invalid)}"}, status=400)
            post.skills_needed.set(skill_objects)

        return JsonResponse({
            "message": "Collab post created",
            "post_id": post.id,
            "title": post.title,
            "collab_type": post.collab_type,
            "skills_needed": [s.name for s in post.skills_needed.all()],
        }, status=201)

    return JsonResponse({"error": "Method not allowed"}, status=405)


def show_collab_posts(request):
    user, error = get_user_from_request(request)
    if error:
        return error

    skill_filter = request.GET.get('skill', '').strip().lower()
    collab_type  = request.GET.get('type', '').strip()
    radius_km    = float(request.GET.get('radius', 50))
    latitude     = request.GET.get('latitude')
    longitude    = request.GET.get('longitude')

    from users.models import Block
    blocked = set(Block.objects.filter(blocker=user).values_list('blocked_id', flat=True))
    blocked_by = set(Block.objects.filter(blocked=user).values_list('blocker_id', flat=True))
    hidden = blocked | blocked_by

    posts = CollabPost.objects.filter(status='open')

    results = []
    for post in posts:
        if post.user_id in hidden:
            continue

        # Type filter
        if collab_type and post.collab_type != collab_type:
            continue

        # Skill filter
        if skill_filter:
            skills = [s.name.lower() for s in post.skills_needed.all()]
            if not any(skill_filter in s for s in skills):
                continue

        # Honest radius filtering: if the searcher shared a location, only show
        # posts with a known location within the radius. Posts with no location
        # can't be verified as "nearby", so they're excluded from a location
        # search (rather than falsely shown as within range).
        dist_display = None
        if latitude and longitude:
            if post.latitude is not None and post.longitude is not None:
                distance = get_distance_km(float(latitude), float(longitude), post.latitude, post.longitude)
                # The poster's chosen range caps visibility; the searcher's radius
                # narrows it further. A post is shown only within both.
                limit = radius_km
                if post.range_km:
                    limit = min(limit, post.range_km)
                if distance > limit:
                    continue
                dist_display = round(distance, 1)
            else:
                continue

        results.append({
            'id':           post.id,
            'title':        post.title,
            'description':  post.description,
            'collab_type':  post.collab_type,
            'status':       post.status,
            'posted_by':    post.user.username,
            'skills_needed':[s.name for s in post.skills_needed.all()],
            'applicants':   post.requests.count() if hasattr(post, 'requests') else 0,
            'distance_km':  dist_display,
            'media':        post.media or None,
            'media_type':   post.media_type or None,
        })

    total = len(results)
    limit, offset = parse_pagination(request)
    page = results[offset:offset + limit]
    return JsonResponse({'collab_posts': page, 'count': total, 'has_more': offset + limit < total})

def show_my_collab_posts(request):
    """Show all collab posts created by logged in user"""
    if request.method == "GET":
        user, error = get_user_from_request(request)
        if error:
            return error

        posts = CollabPost.objects.filter(user=user).prefetch_related(
            "skills_needed", "requests"
        ).order_by("-created_at")

        data = [
            {
                "id": p.id,
                "title": p.title,
                "description": p.description,
                "collab_type": p.collab_type,
                "status": p.status,
                "skills_needed": [s.name for s in p.skills_needed.all()],
                "applicants": p.requests.count(),
                "created_at": p.created_at,
            }
            for p in posts
        ]
        return JsonResponse({"collab_posts": data, "count": len(data)})

    return JsonResponse({"error": "Method not allowed"}, status=405)


def apply_to_collab(request, post_id):
    """Apply to someone's collab post"""
    if request.method == "POST":
        user, error = get_user_from_request(request)
        if error:
            return error

        guard = require_contact(user)
        if guard:
            return guard

        try:
            post = CollabPost.objects.get(id=post_id)

            if post.user == user:
                return JsonResponse({"error": "You cannot apply to your own collab post"}, status=400)

            if post.status != 'open':
                return JsonResponse({"error": "This collab post is closed"}, status=400)

            if CollabRequest.objects.filter(collab_post=post, applicant=user).exists():
                return JsonResponse({"error": "You already applied to this post"}, status=400)

            from users.models import Block
            from django.db.models import Q
            if Block.objects.filter(
                Q(blocker=user, blocked=post.user) | Q(blocker=post.user, blocked=user)
            ).exists():
                return JsonResponse({"error": "You can't apply to this post"}, status=403)

            message = request.POST.get("message", "").strip()

            collab_request = CollabRequest.objects.create(
                collab_post=post,
                applicant=user,
                message=message if message else None,
            )

            from notifications.utils import notify
            notify(post.user, 'proposal',
                   f"{user.username} applied to your collab \"{post.title}\"", actor=user)

            return JsonResponse({
                "message": "Application sent",
                "request_id": collab_request.id,
            }, status=201)

        except CollabPost.DoesNotExist:
            return JsonResponse({"error": "Collab post not found"}, status=404)

    return JsonResponse({"error": "Method not allowed"}, status=405)


def get_collab_applicants(request, post_id):
    """Post owner sees all applicants"""
    if request.method == "GET":
        user, error = get_user_from_request(request)
        if error:
            return error

        try:
            post = CollabPost.objects.get(id=post_id, user=user)
            applicants = CollabRequest.objects.filter(
                collab_post=post
            ).select_related("applicant")

            data = [
                {
                    "id": r.id,
                    "applicant": r.applicant.username,
                    "applicant_id": r.applicant.id,
                    "skills": [s.name for s in r.applicant.skills.all()],
                    "message": r.message,
                    "status": r.status,
                    "applied_at": r.created_at,
                }
                for r in applicants
            ]
            return JsonResponse({"applicants": data, "count": len(data)})

        except CollabPost.DoesNotExist:
            return JsonResponse({"error": "Post not found or not yours"}, status=404)

    return JsonResponse({"error": "Method not allowed"}, status=405)


def respond_to_collab_request(request, request_id):
    """Post owner accepts or declines an applicant"""
    if request.method == "POST":
        user, error = get_user_from_request(request)
        if error:
            return error

        status = request.POST.get("status", "").strip().lower()
        if status not in ["accepted", "declined"]:
            return JsonResponse({"error": "status must be accepted or declined"}, status=400)

        if status == 'accepted':
            guard = require_contact(user)
            if guard:
                return guard

        try:
            collab_request = CollabRequest.objects.get(
                id=request_id,
                collab_post__user=user
            )

            collab_request.status = status
            collab_request.save()

            from notifications.utils import notify
            ntype = 'proposal_accepted' if status == 'accepted' else 'proposal_declined'
            notify(collab_request.applicant, ntype,
                   f"{user.username} {status} your collab application", actor=user)

            # if accepted, create a conversation
            if status == 'accepted':
                from work.models import Conversation
                conversation = Conversation.objects.create(
                    conversation_type='work'
                )
                conversation.participants.add(user, collab_request.applicant)
                return JsonResponse({
                    "message": f"Request accepted — conversation started",
                    "conversation_id": conversation.id
                })

            return JsonResponse({"message": "Request declined"})

        except CollabRequest.DoesNotExist:
            return JsonResponse({"error": "Request not found or not yours"}, status=404)

    return JsonResponse({"error": "Method not allowed"}, status=405)


def close_collab_post(request, post_id):
    """Post owner closes a collab post"""
    if request.method == "POST":
        user, error = get_user_from_request(request)
        if error:
            return error

        try:
            post = CollabPost.objects.get(id=post_id, user=user)
            post.status = 'closed'
            post.save()
            return JsonResponse({"message": "Collab post closed"})
        except CollabPost.DoesNotExist:
            return JsonResponse({"error": "Post not found or not yours"}, status=404)

    return JsonResponse({"error": "Method not allowed"}, status=405)