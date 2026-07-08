from django.http import JsonResponse
from .models import CollabPost, CollabRequest
from users.models import User
from skills.models import Skill
from users.views import get_user_from_token


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

        title = request.POST.get("title", "").strip()
        description = request.POST.get("description", "").strip()
        collab_type = request.POST.get("collab_type", "experience").strip()
        skills_input = request.POST.get("skills", "").strip()

        if not title or not description:
            return JsonResponse({"error": "title and description are required"}, status=400)

        valid_types = ['equity', 'experience', 'paid']
        if collab_type not in valid_types:
            return JsonResponse({"error": "collab_type must be equity, experience or paid"}, status=400)
        
        latitude = request.POST.get("latitude", "").strip()
        longitude = request.POST.get("longitude", "").strip()
        post = CollabPost.objects.create(
            user=user,
            title=title,
            description=description,
            collab_type=collab_type,
            latitude = request.POST.get("latitude", "").strip(),
            longitude = request.POST.get("longitude", "").strip(),
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
    # Get filter params
    skill_filter = request.GET.get('skill', '').strip().lower()
    collab_type  = request.GET.get('type', '').strip()
    radius_km    = float(request.GET.get('radius', 50))
    latitude     = request.GET.get('latitude')
    longitude    = request.GET.get('longitude')

    posts = CollabPost.objects.filter(status='open')

    results = []
    for post in posts:
        # Type filter
        if collab_type and post.collab_type != collab_type:
            continue

        # Skill filter
        if skill_filter:
            skills = [s.name.lower() for s in post.skills_needed.all()]
            if not any(skill_filter in s for s in skills):
                continue

        # Location filter
        if latitude and longitude and post.latitude and post.longitude:
            distance = get_distance_km(
                float(latitude), float(longitude),
                post.latitude, post.longitude
            )
            if distance > radius_km:
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

        try:
            post = CollabPost.objects.get(id=post_id)

            if post.user == user:
                return JsonResponse({"error": "You cannot apply to your own collab post"}, status=400)

            if post.status != 'open':
                return JsonResponse({"error": "This collab post is closed"}, status=400)

            if CollabRequest.objects.filter(collab_post=post, applicant=user).exists():
                return JsonResponse({"error": "You already applied to this post"}, status=400)

            message = request.POST.get("message", "").strip()

            collab_request = CollabRequest.objects.create(
                collab_post=post,
                applicant=user,
                message=message if message else None,
            )

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

        try:
            collab_request = CollabRequest.objects.get(
                id=request_id,
                collab_post__user=user
            )

            collab_request.status = status
            collab_request.save()

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