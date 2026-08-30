from django.http import JsonResponse
from django.utils import timezone
from .models import CollabPost, CollabRequest, CollabTask
from users.models import User
# Skill is reached via skills.utils now (see create_collab_post).
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
        if recent and recent.created_at and (timezone.now() - recent.created_at).total_seconds() < 20:
            return JsonResponse({"error": "Please wait a moment before posting again."}, status=429)

        title = request.POST.get("title", "").strip()
        description = request.POST.get("description", "").strip()
        skills_input = request.POST.get("skills", "").strip()

        if not title or not description:
            return JsonResponse({"error": "title and description are required"}, status=400)

        latitude = request.POST.get("latitude", "").strip()
        longitude = request.POST.get("longitude", "").strip()
        range_km = request.POST.get("range_km", "").strip()

        # Visibility window — collab posts now expire like freelance jobs.
        # (timezone is imported at module level; re-importing it here made it a
        # function-local name, so the flood-guard's timezone.now() above blew
        # up with UnboundLocalError before this line ever ran.)
        from datetime import timedelta
        tlh = request.POST.get("time_limit_hours", "").strip()
        try:
            time_limit_hours = int(tlh) if tlh else None
        except ValueError:
            time_limit_hours = None
        expires_at = timezone.now() + timedelta(hours=time_limit_hours) if time_limit_hours else None

        try:
            people_needed = int(request.POST.get("people_needed", 1))
        except (TypeError, ValueError):
            people_needed = 1
        people_needed = max(1, min(people_needed, 5))

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
            time_limit_hours=time_limit_hours,
            people_needed=people_needed,
            expires_at=expires_at,
            media=media_url,
            media_type=media_type,
        )

        if skills_input:
            # Create unknown skills rather than rejecting the post — the
            # freelance side already does, and a collab was otherwise
            # impossible to file under any skill that didn't exist yet.
            from skills.utils import get_or_create_skill
            skill_list = [s.strip() for s in skills_input.split(",") if s.strip()]
            skill_objects = []
            for skill_name in skill_list:
                skill = get_or_create_skill(skill_name)
                if skill:
                    skill_objects.append(skill)
            post.skills_needed.set(skill_objects)

            from notifications.utils import notify_category_match
            notify_category_match(
                skill_objects, user, 'collab_match',
                f"New collab matching your category: {title[:60]}"
            )

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
    from django.db.models import Count, Q
    blocked = set(Block.objects.filter(blocker=user).values_list('blocked_id', flat=True))
    blocked_by = set(Block.objects.filter(blocked=user).values_list('blocker_id', flat=True))
    hidden = blocked | blocked_by

    # Declined applicants stop seeing the post they were turned down for.
    declined_posts = set(
        CollabRequest.objects.filter(applicant=user, status='declined')
        .values_list('collab_post_id', flat=True)
    )

    # select_related/prefetch_related + annotate so the loop below doesn't
    # issue a fresh query per post for the owner's username, skills list,
    # and applicant count (was N+1 across the whole open-posts table).
    posts = (
        CollabPost.objects.filter(status='open')
        .select_related('user')
        .prefetch_related('skills_needed')
        .annotate(
            applicants_count=Count('requests', distinct=True),
            hired_count=Count('requests', filter=Q(requests__status='accepted'), distinct=True),
        )
    )

    now = timezone.now()

    results = []
    for post in posts:
        if post.user_id in hidden:
            continue
        if post.id in declined_posts:
            continue

        # Hide collabs whose visibility window has elapsed (nothing auto-closes
        # status on expiry), mirroring the freelance board.
        if getattr(post, 'expires_at', None) and post.expires_at < now:
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
            'applicants':   post.applicants_count,
            'people_needed': getattr(post, 'people_needed', 1) or 1,
            'hired_count':  post.hired_count,
            'distance_km':  dist_display,
            'expires_at':   str(post.expires_at) if getattr(post, 'expires_at', None) else None,
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
                "people_needed": getattr(p, 'people_needed', 1) or 1,
                "hired_count": sum(1 for r in p.requests.all() if r.status == 'accepted'),
                "expires_at": str(p.expires_at) if getattr(p, 'expires_at', None) else None,
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
            ).select_related("applicant").prefetch_related("applicant__skills")

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
            people_needed = getattr(post, 'people_needed', 1) or 1
            hired_count = sum(1 for r in data if r["status"] == 'accepted')
            return JsonResponse({
                "applicants": data,
                "count": len(data),
                "people_needed": people_needed,
                "hired_count": hired_count,
                "spots_left": max(0, people_needed - hired_count),
            })

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
            post = collab_request.collab_post
            people_needed = getattr(post, 'people_needed', 1) or 1

            if status == 'accepted':
                if collab_request.status == 'accepted':
                    return JsonResponse({"error": "You've already accepted this person"}, status=400)
                accepted_count = CollabRequest.objects.filter(
                    collab_post=post, status='accepted'
                ).count()
                if accepted_count >= people_needed:
                    return JsonResponse(
                        {"error": f"All {people_needed} spot(s) are already filled"}, status=400
                    )

            collab_request.status = status
            collab_request.save()

            # Close the post once every spot is taken so it drops out of
            # everyone else's feed; a partly-filled collab stays open.
            if status == 'accepted':
                filled = CollabRequest.objects.filter(collab_post=post, status='accepted').count()
                if filled >= people_needed and post.status == 'open':
                    post.status = 'closed'
                    post.save(update_fields=['status'])

            from notifications.utils import notify
            ntype = 'proposal_accepted' if status == 'accepted' else 'proposal_declined'
            notify(collab_request.applicant, ntype,
                   f"{user.username} {status} your collab application", actor=user)

            # If accepted, add them to the ONE shared group thread for this
            # collab post (get-or-create it on the first acceptance) —
            # previously every acceptance spun up its own separate 1:1 with
            # the owner, so an accepted team could never actually talk to
            # each other, only individually to the post owner.
            if status == 'accepted':
                from work.models import Conversation
                conversation, _ = Conversation.objects.get_or_create(
                    collab_post=collab_request.collab_post,
                    defaults={'conversation_type': 'collab'},
                )
                conversation.participants.add(user, collab_request.applicant)
                return JsonResponse({
                    "message": "Request accepted — conversation started",
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


def _is_collab_participant(collab_post, user):
    """Owner or an accepted applicant — the same group that shares the
    collab conversation, and the only people allowed to see/use its task
    board."""
    if collab_post.user_id == user.id:
        return True
    return CollabRequest.objects.filter(
        collab_post=collab_post, applicant=user, status='accepted'
    ).exists()


def get_collab_tasks(request, post_id):
    if request.method != "GET":
        return JsonResponse({"error": "Method not allowed"}, status=405)

    user, error = get_user_from_request(request)
    if error:
        return error

    try:
        post = CollabPost.objects.get(id=post_id)
    except CollabPost.DoesNotExist:
        return JsonResponse({"error": "Collab post not found"}, status=404)

    if not _is_collab_participant(post, user):
        return JsonResponse({"error": "You're not part of this collab"}, status=403)

    tasks = post.tasks.select_related('assignee', 'created_by')
    data = [{
        "id": t.id,
        "title": t.title,
        "is_done": t.is_done,
        "assignee_id": t.assignee_id,
        "assignee_username": t.assignee.username if t.assignee else None,
        "created_by_id": t.created_by_id,
        "created_by_username": t.created_by.username,
        "created_at": str(t.created_at),
    } for t in tasks]
    return JsonResponse({"tasks": data, "count": len(data)})


def create_collab_task(request, post_id):
    if request.method != "POST":
        return JsonResponse({"error": "Method not allowed"}, status=405)

    user, error = get_user_from_request(request)
    if error:
        return error

    try:
        post = CollabPost.objects.get(id=post_id)
    except CollabPost.DoesNotExist:
        return JsonResponse({"error": "Collab post not found"}, status=404)

    if not _is_collab_participant(post, user):
        return JsonResponse({"error": "You're not part of this collab"}, status=403)

    title = request.POST.get("title", "").strip()
    if not title:
        return JsonResponse({"error": "Task title is required"}, status=400)
    if len(title) > 200:
        return JsonResponse({"error": "Task title is too long"}, status=400)

    assignee_id = request.POST.get("assignee_id", "").strip()
    assignee = None
    if assignee_id:
        try:
            candidate = User.objects.get(id=assignee_id)
        except User.DoesNotExist:
            return JsonResponse({"error": "Assignee not found"}, status=404)
        if not _is_collab_participant(post, candidate):
            return JsonResponse({"error": "Assignee must be part of this collab"}, status=400)
        assignee = candidate

    task = CollabTask.objects.create(
        collab_post=post, title=title, assignee=assignee, created_by=user,
    )
    return JsonResponse({"message": "Task created", "task_id": task.id}, status=201)


def toggle_collab_task(request, task_id):
    if request.method != "POST":
        return JsonResponse({"error": "Method not allowed"}, status=405)

    user, error = get_user_from_request(request)
    if error:
        return error

    try:
        task = CollabTask.objects.select_related('collab_post').get(id=task_id)
    except CollabTask.DoesNotExist:
        return JsonResponse({"error": "Task not found"}, status=404)

    if not _is_collab_participant(task.collab_post, user):
        return JsonResponse({"error": "You're not part of this collab"}, status=403)

    task.is_done = not task.is_done
    task.save()
    return JsonResponse({"message": "Task updated", "is_done": task.is_done})


def assign_collab_task(request, task_id):
    if request.method != "POST":
        return JsonResponse({"error": "Method not allowed"}, status=405)

    user, error = get_user_from_request(request)
    if error:
        return error

    try:
        task = CollabTask.objects.select_related('collab_post').get(id=task_id)
    except CollabTask.DoesNotExist:
        return JsonResponse({"error": "Task not found"}, status=404)

    if not _is_collab_participant(task.collab_post, user):
        return JsonResponse({"error": "You're not part of this collab"}, status=403)

    assignee_id = request.POST.get("assignee_id", "").strip()
    if not assignee_id:
        task.assignee = None
        task.save()
        return JsonResponse({"message": "Task unassigned"})

    try:
        candidate = User.objects.get(id=assignee_id)
    except User.DoesNotExist:
        return JsonResponse({"error": "Assignee not found"}, status=404)
    if not _is_collab_participant(task.collab_post, candidate):
        return JsonResponse({"error": "Assignee must be part of this collab"}, status=400)

    task.assignee = candidate
    task.save()
    return JsonResponse({
        "message": "Task assigned",
        "assignee_id": candidate.id,
        "assignee_username": candidate.username,
    })


def delete_collab_task(request, task_id):
    if request.method != "DELETE":
        return JsonResponse({"error": "Method not allowed"}, status=405)

    user, error = get_user_from_request(request)
    if error:
        return error

    try:
        task = CollabTask.objects.select_related('collab_post').get(id=task_id)
    except CollabTask.DoesNotExist:
        return JsonResponse({"error": "Task not found"}, status=404)

    # Any participant can create/toggle/assign, but deletion is a bit more
    # destructive so it's scoped tighter — task creator or the collab owner.
    if task.created_by_id != user.id and task.collab_post.user_id != user.id:
        return JsonResponse({"error": "Only the task creator or collab owner can delete this"}, status=403)

    task.delete()
    return JsonResponse({"message": "Task deleted"})