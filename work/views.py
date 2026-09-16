from django.http import JsonResponse
from django.db.models import Prefetch, Count, Q
from django.utils import timezone
from datetime import timedelta
from .models import WorkRequest, WorkRequestResponse, WorkProposal, Conversation, Message, TypingStatus
from users.models import User
# Skill/Category are reached via skills.utils now (see create_work_request).
from users.views import get_user_from_token, require_contact
from social.validators import parse_lat, parse_lon, parse_float, MAX_VISIBILITY_HOURS


def get_distance_km(lat1, lon1, lat2, lon2):
    import math
    R = 6371
    d_lat = math.radians(lat2 - lat1)
    d_lon = math.radians(lon2 - lon1)
    a = (math.sin(d_lat / 2) ** 2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(d_lon / 2) ** 2)
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


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


def get_user_from_request(request):
    result = get_user_from_token(request)
    if isinstance(result, tuple):
        user = result[0]
    else:
        user = result
    if not user:
        return None, JsonResponse({'error': 'Unauthorized'}, status=401)
    return user, None


def create_work_request(request):
    if request.method == "POST":
        user, error = get_user_from_request(request)
        if error:
            return error

        guard = require_contact(user)
        if guard:
            return guard

        # Cheap flood guard — without this a bad actor (or a buggy retry loop)
        # could spam the Freelance feed with dozens of jobs in seconds.
        recent = WorkRequest.objects.filter(created_by=user).order_by('-created_at').first()
        if recent and recent.created_at and (timezone.now() - recent.created_at).total_seconds() < 20:
            return JsonResponse({"error": "Please wait a moment before posting again."}, status=429)

        description = request.POST.get("description", "").strip()
        payment_amount = request.POST.get("payment_amount", "").strip()
        time_limit_hours = request.POST.get("time_limit_hours", "").strip()
        skills = request.POST.get("skills", "").strip()

        if not description or not payment_amount or not time_limit_hours or not skills:
            return JsonResponse({"error": "description, payment_amount, time_limit_hours and skills are required"}, status=400)

        from skills.utils import get_or_create_skill
        skill_list = [s.strip() for s in skills.split(",") if s.strip()]
        skill_objects = []
        for skill_name in skill_list:
            skill = get_or_create_skill(skill_name)
            if skill:
                skill_objects.append(skill)

        try:
            time_limit_hours = int(time_limit_hours)
        except ValueError:
            return JsonResponse({"error": "time_limit_hours must be a number"}, status=400)
        # The picker only offers 2–48h, but the field is a plain POST value,
        # so the ceiling has to hold here too or a listing can be made to
        # sit on the board indefinitely.
        time_limit_hours = max(1, min(time_limit_hours, MAX_VISIBILITY_HOURS))
        expires_at = timezone.now() + timedelta(hours=time_limit_hours)

        # time_limit_hours was validated above but payment_amount never was,
        # so a non-numeric (or negative) budget reached float() and 500'd.
        try:
            payment_amount = float(payment_amount)
        except (TypeError, ValueError):
            return JsonResponse({"error": "payment_amount must be a number"}, status=400)
        if payment_amount < 0:
            return JsonResponse({"error": "payment_amount cannot be negative"}, status=400)

        latitude = request.POST.get("latitude", "").strip()
        longitude = request.POST.get("longitude", "").strip()
        range_km = request.POST.get("range_km", "").strip()
        gender_preference = request.POST.get("gender_preference", "any").strip().lower()
        if gender_preference not in ("any", "male", "female"):
            gender_preference = "any"

        # Clamp rather than reject: a bad value shouldn't fail the whole post.
        try:
            people_needed = int(request.POST.get("people_needed", 1))
        except (TypeError, ValueError):
            people_needed = 1
        people_needed = max(1, min(people_needed, 5))
        from users.views import upload_media_file
        media_url, media_type = upload_media_file(request.FILES.get("media"))
        work_request = WorkRequest.objects.create(
            created_by=user,
            description=description,
            payment_amount=payment_amount,
            time_limit_hours=time_limit_hours,
            gender_preference=gender_preference,
            people_needed=people_needed,
            expires_at=expires_at,
            status='open',
            latitude=parse_lat(latitude),
            longitude=parse_lon(longitude),
            range_km=parse_float(range_km, None, minimum=0) if range_km else None,
            media=media_url,
            media_type=media_type,
        )
        work_request.required_skills.set(skill_objects)

        from notifications.utils import notify_category_match
        notify_category_match(
            skill_objects, user, 'work_request',
            f"New freelance job matching your category: {description[:60]}"
        )

        return JsonResponse({
            "message": "Work request created",
            "work_request_id": work_request.id,
            "expires_at": str(work_request.expires_at),
        }, status=201)

    return JsonResponse({"error": "Method not allowed"}, status=405)


def get_my_work_requests(request, user_id):
    """Your own posted jobs — including applicant counts, who you assigned,
    and closed/expired ones that never appear on the public board.

    Self-only. The user_id in the path was previously trusted outright, so
    anyone could read any user's posting history by changing the number.
    """
    if request.method == "GET":
        user, error = get_user_from_request(request)
        if error:
            return error
        if user.id != user_id:
            return JsonResponse({"error": "You can only view your own posts"}, status=403)

        requests = (
            WorkRequest.objects
            .filter(created_by=user)
            .select_related('assigned_to')
            .prefetch_related('required_skills', 'responses')
            .order_by("-created_at")
        )
        data = [
            {
                "id": wr.id,
                "description": wr.description,
                "skills": [s.name for s in wr.required_skills.all()],
                "payment_amount": wr.payment_amount,
                "time_limit_hours": wr.time_limit_hours,
                "gender_preference": getattr(wr, "gender_preference", "any"),
                "people_needed": getattr(wr, "people_needed", 1) or 1,
                "hired_count": sum(1 for r in wr.responses.all() if getattr(r, 'hired', False)),
                "status": wr.status,
                "assigned_to": wr.assigned_to.username if wr.assigned_to else None,
                "assigned_to_id": wr.assigned_to_id,
                "completed_by_poster": wr.completed_by_poster,
                "completed_by_worker": wr.completed_by_worker,
                "expires_at": str(wr.expires_at),
                "responses_count": wr.responses.count(),
                "created_at": str(wr.created_at),
            }
            for wr in requests
        ]
        return JsonResponse({"work_requests": data, "count": len(data)})

    return JsonResponse({"error": "Method not allowed"}, status=405)


def get_available_work_requests(request, user_id):
    user, error = get_user_from_request(request)
    if error:
        return error

    skill_filter = request.GET.get('skill', '').strip().lower()
    radius_km    = parse_float(request.GET.get('radius'), 50, minimum=0)
    latitude     = parse_lat(request.GET.get('latitude'))
    longitude    = parse_lon(request.GET.get('longitude'))

    from users.models import Block
    blocked = set(Block.objects.filter(blocker=user).values_list('blocked_id', flat=True))
    blocked_by = set(Block.objects.filter(blocked=user).values_list('blocker_id', flat=True))
    hidden = blocked | blocked_by

    # Newest first — this is a live job board. Expired-but-still-"open" jobs
    # (nothing auto-closes status on expiry) are hidden from browsing, even
    # though respond_to_work_request already blocked applying to them.
    from django.db.models import Q
    work_requests = (
        WorkRequest.objects.filter(status='open')
        .filter(Q(expires_at__isnull=True) | Q(expires_at__gt=timezone.now()))
        .order_by('-created_at')
    )

    results = []
    for wr in work_requests:
        if wr.created_by.id == user.id:
            continue
        if wr.created_by.id in hidden:
            continue

        if skill_filter:
            skills = [s.name.lower() for s in wr.required_skills.all()]
            if not any(skill_filter in s for s in skills):
                continue

        # Honest radius filtering. Use the job's OWN location (captured live when
        # it was posted); for older jobs with no location, fall back to the
        # poster's profile location. If neither is known, the job can't be
        # verified as "nearby", so it's excluded from a location search rather
        # than falsely shown.
        dist_display = None
        job_lat = wr.latitude if wr.latitude is not None else wr.created_by.latitude
        job_lon = wr.longitude if wr.longitude is not None else wr.created_by.longitude
        if latitude is not None and longitude is not None:
            if job_lat is not None and job_lon is not None:
                distance = get_distance_km(
                    latitude, longitude,
                    job_lat, job_lon
                )
                # The poster's chosen range caps visibility; the searcher's
                # radius narrows it further. Shown only within both.
                limit = radius_km
                if wr.range_km:
                    limit = min(limit, wr.range_km)
                if distance > limit:
                    continue
                dist_display = round(distance, 1)
            else:
                continue

        results.append({
            'id':               wr.id,
            'description':      wr.description,
            'payment_amount':   wr.payment_amount,
            'time_limit_hours': wr.time_limit_hours,
            'gender_preference': getattr(wr, 'gender_preference', 'any'),
            'status':           wr.status,
            'created_by':       wr.created_by.username,
            'skills':           [s.name for s in wr.required_skills.all()],
            'expires_at':       str(wr.expires_at) if wr.expires_at else None,
            'created_at':       str(wr.created_at) if wr.created_at else None,
            'distance_km':      dist_display,
            'responses_count':  wr.responses.count(),
            'media':            wr.media or None,
            'media_type':       wr.media_type or None,
        })

    total = len(results)
    limit, offset = parse_pagination(request)
    page = results[offset:offset + limit]
    return JsonResponse({'work_requests': page, 'count': total, 'has_more': offset + limit < total})


def respond_to_work_request(request, work_request_id):
    if request.method == "POST":
        user, error = get_user_from_request(request)
        if error:
            return error

        guard = require_contact(user)
        if guard:
            return guard

        status = request.POST.get("status", "").strip().lower()
        message = request.POST.get("message", "").strip()

        if status not in ["accepted", "declined"]:
            return JsonResponse({"error": "status must be 'accepted' or 'declined'"}, status=400)

        try:
            work_request = WorkRequest.objects.get(id=work_request_id)

            if work_request.expires_at < timezone.now():
                return JsonResponse({"error": "Work request has expired"}, status=400)

            if work_request.status != 'open':
                return JsonResponse({"error": "Work request is no longer open"}, status=400)

            if WorkRequestResponse.objects.filter(work_request=work_request, user=user).exists():
                return JsonResponse({"error": "You have already responded to this request"}, status=400)

            from users.models import Block
            from django.db.models import Q
            if Block.objects.filter(
                Q(blocker=user, blocked=work_request.created_by) | Q(blocker=work_request.created_by, blocked=user)
            ).exists():
                return JsonResponse({"error": "You can't respond to this request"}, status=403)

            WorkRequestResponse.objects.create(
                work_request=work_request,
                user=user,
                status=status,
                message=message if message else None,
            )

            if status == 'accepted':
                from notifications.utils import notify
                notify(work_request.created_by, 'proposal',
                       f"{user.username} applied to your job: {work_request.description[:50]}", actor=user)

            return JsonResponse({"message": f"Response '{status}' submitted successfully"})

        except WorkRequest.DoesNotExist:
            return JsonResponse({"error": "Work request not found"}, status=404)

    return JsonResponse({"error": "Method not allowed"}, status=405)


def get_work_request_responses(request, work_request_id):
    """Applicants for one of YOUR jobs.

    Owner-only: this returns each applicant's identity, skills, rating and the
    pitch they wrote, which is private between them and the poster. It used to
    be unauthenticated, so anyone could walk the id range and harvest every
    applicant on the platform. (collab's equivalent was already owner-scoped.)
    """
    if request.method == "GET":
        user, error = get_user_from_request(request)
        if error:
            return error
        try:
            work_request = WorkRequest.objects.get(id=work_request_id, created_by=user)
            responses = (
                WorkRequestResponse.objects
                .filter(work_request=work_request, status='accepted')
                # Rejected applicants stay in the table (so they stop seeing
                # the gig) but drop out of the poster's actionable list.
                .exclude(rejected=True)
                .select_related("user")
                .prefetch_related("user__skills")
            )

            data = [
                {
                    "user_id": r.user.id,
                    "username": r.user.username,
                    "skills": [s.name for s in r.user.skills.all()],
                    "rating": r.user.rating,
                    "message": r.message,
                    "hired": r.hired,
                    "responded_at": str(r.created_at),
                }
                for r in responses
            ]
            people_needed = getattr(work_request, 'people_needed', 1) or 1
            hired_count = sum(1 for r in data if r["hired"])
            return JsonResponse({
                "applicants": data,
                "count": len(data),
                "people_needed": people_needed,
                "hired_count": hired_count,
                "spots_left": max(0, people_needed - hired_count),
            })
        except WorkRequest.DoesNotExist:
            # Same response whether it doesn't exist or isn't yours — don't
            # confirm the existence of other people's jobs.
            return JsonResponse({"error": "Work request not found or not yours"}, status=404)

    return JsonResponse({"error": "Method not allowed"}, status=405)


def assign_work_request(request, work_request_id):
    if request.method == "POST":
        user, error = get_user_from_request(request)
        if error:
            return error

        guard = require_contact(user)
        if guard:
            return guard

        assignee_id = request.POST.get("assignee_id", "").strip()
        if not assignee_id:
            return JsonResponse({"error": "assignee_id is required"}, status=400)

        try:
            work_request = WorkRequest.objects.get(id=work_request_id, created_by=user)

            if work_request.status != 'open':
                return JsonResponse({"error": "Work request is no longer open"}, status=400)

            assignee = User.objects.get(id=assignee_id)

            response = WorkRequestResponse.objects.filter(
                work_request=work_request, user=assignee, status='accepted'
            ).exclude(rejected=True).first()
            if not response:
                return JsonResponse({"error": "This user has not applied to this gig"}, status=400)

            people_needed = getattr(work_request, 'people_needed', 1) or 1
            hired_qs = WorkRequestResponse.objects.filter(work_request=work_request, hired=True)

            if response.hired:
                return JsonResponse({"error": "You've already hired this person"}, status=400)
            if hired_qs.count() >= people_needed:
                return JsonResponse(
                    {"error": f"All {people_needed} spot(s) are already filled"}, status=400
                )

            response.hired = True
            response.save(update_fields=['hired'])

            # assigned_to holds the FIRST hire — completion/rating and the
            # existing 1:1 conversation still key off it, so multi-hire gigs
            # stay compatible with everything built around a single worker.
            if work_request.assigned_to is None:
                work_request.assigned_to = assignee

            # Only leave 'open' once every spot is taken; a partly-filled gig
            # must stay visible so the remaining spots can still be applied to.
            hired_count = hired_qs.count()
            if hired_count >= people_needed:
                work_request.status = 'assigned'
            work_request.save()

            # Reuse an existing 1:1 conversation with this person (from a friend
            # DM, an earlier job together, etc.) instead of always spinning up a
            # fresh thread — otherwise hiring someone you're already talking to
            # silently splits the conversation in two.
            conversation = next(
                (c for c in Conversation.objects.filter(participants=user).filter(participants=assignee)
                 if c.participants.count() == 2),
                None,
            )
            # Conversation.work_request is one-to-one, so only one thread can
            # carry the gig. The second hire on a multi-person gig used to create
            # another linked thread and 500 on the constraint. Each hire still
            # gets a private thread; hires aren't pooled into one, since the
            # first could be an existing DM whose history isn't theirs to see.
            gig_linked = Conversation.objects.filter(work_request=work_request).exists()
            if conversation:
                if conversation.work_request_id is None and not gig_linked:
                    conversation.work_request = work_request
                    conversation.save(update_fields=['work_request'])
            else:
                conversation = Conversation.objects.create(
                    work_request=None if gig_linked else work_request,
                    conversation_type='freelance'
                )
                conversation.participants.add(user, assignee)

            from notifications.utils import notify
            notify(assignee, 'proposal_accepted',
                   f"{user.username} hired you for: {work_request.description[:50]}", actor=user)

            return JsonResponse({
                "message": f"Work assigned to {assignee.username} successfully",
                "conversation_id": conversation.id,
                "people_needed": people_needed,
                "hired_count": hired_count,
                "spots_left": max(0, people_needed - hired_count),
                "is_full": hired_count >= people_needed,
            })

        except WorkRequest.DoesNotExist:
            return JsonResponse({"error": "Work request not found or not yours"}, status=404)
        except User.DoesNotExist:
            return JsonResponse({"error": "Assignee not found"}, status=404)

    return JsonResponse({"error": "Method not allowed"}, status=405)


def reject_work_applicant(request, work_request_id):
    """Post owner declines an applicant. The decline is permanent: the
    applicant is told, and the gig drops out of their feed for good."""
    if request.method != "POST":
        return JsonResponse({"error": "Method not allowed"}, status=405)

    user, error = get_user_from_request(request)
    if error:
        return error

    applicant_id = request.POST.get("applicant_id", "").strip()
    if not applicant_id:
        return JsonResponse({"error": "applicant_id is required"}, status=400)

    try:
        work_request = WorkRequest.objects.get(id=work_request_id, created_by=user)
    except WorkRequest.DoesNotExist:
        return JsonResponse({"error": "Work request not found or not yours"}, status=404)

    response = WorkRequestResponse.objects.filter(
        work_request=work_request, user_id=applicant_id
    ).first()
    if not response:
        return JsonResponse({"error": "That applicant was not found on this gig"}, status=404)
    if response.hired:
        return JsonResponse({"error": "You've already hired this person"}, status=400)

    # Flagged, not deleted. Deleting let them re-apply and put the gig back in
    # their feed; keeping the row is what makes the rejection stick and hides
    # the gig from them for good.
    response.rejected = True
    response.save(update_fields=['rejected'])

    # Gig declines were silent while collab declines already notified; the
    # applicant was left refreshing a status that had quietly changed.
    from notifications.utils import notify
    notify(response.user, 'proposal_declined',
           f"Your application for \"{work_request.description[:50]}\" wasn't selected", actor=user)
    return JsonResponse({"message": "Applicant declined"})


def close_work_request(request, work_request_id):
    """Take a gig off the board early. Closing is not completing: verified
    projects only come from mutual completion, otherwise a poster could close
    a gig the hire never did and still award them one."""
    if request.method != "POST":
        return JsonResponse({"error": "Method not allowed"}, status=405)

    user, error = get_user_from_request(request)
    if error:
        return error

    try:
        work_request = WorkRequest.objects.get(id=work_request_id, created_by=user)
    except WorkRequest.DoesNotExist:
        return JsonResponse({"error": "Work request not found or not yours"}, status=404)

    if work_request.status != 'closed':
        work_request.status = 'closed'
        work_request.save(update_fields=['status'])
    return JsonResponse({"message": "Work request closed"})


def complete_work_request(request, work_request_id):
    """Mutual completion: the poster and someone they hired must both confirm
    before a gig closes, so neither side can declare it done alone. Any hire
    can confirm for the workers, a partly staffed gig can still finish, and
    every hire gets a verified project once it closes."""
    if request.method != "POST":
        return JsonResponse({"error": "Method not allowed"}, status=405)

    user, error = get_user_from_request(request)
    if error:
        return error

    try:
        wr = WorkRequest.objects.select_related('created_by').get(id=work_request_id)
    except WorkRequest.DoesNotExist:
        return JsonResponse({"error": "Job not found"}, status=404)

    from django.db.models import Q
    hired_ids = WorkRequestResponse.objects.filter(work_request=wr, hired=True).values('user_id')
    hires = list(User.objects.filter(Q(id__in=hired_ids) | Q(id=wr.assigned_to_id)).distinct())

    is_poster = user.id == wr.created_by_id
    is_worker = any(h.id == user.id for h in hires)
    if not (is_poster or is_worker):
        return JsonResponse({"error": "You're not part of this job"}, status=403)
    if wr.status == 'closed':
        return JsonResponse({"error": "This job is already closed"}, status=400)
    if not hires:
        return JsonResponse({"error": "Hire someone before marking the job complete"}, status=400)

    from notifications.utils import notify
    from django.utils import timezone

    if is_poster:
        wr.completed_by_poster = True
    else:
        wr.completed_by_worker = True
    snippet = (wr.description or '')[:50]
    poster = wr.created_by
    both_confirmed = wr.completed_by_poster and wr.completed_by_worker

    if both_confirmed:
        wr.status = 'closed'
        wr.completed_at = timezone.now()
        wr.save()

        from portfolio.models import PortfolioItem
        skills = list(wr.required_skills.all())
        for hire in hires:
            if PortfolioItem.objects.filter(verified_via_work=wr, user=hire).exists():
                continue
            item = PortfolioItem.objects.create(
                user=hire,
                title=f"Completed: {(wr.description or '')[:80]}",
                description="Completed work for a client. Verified on DoitHere.",
                portfolio_type='project',
                verified=True,
                verified_via_work=wr,
            )
            item.skills.set(skills)

        # One notification per pairing, each carrying the person to rate as
        # its actor, so tapping it lands on the profile with the Rate button.
        for hire in hires:
            notify(hire, 'job_complete', f"Done on both sides: {snippet} — rate {poster.username}", actor=poster)
            notify(poster, 'job_complete', f"Done on both sides: {snippet} — rate {hire.username}", actor=hire)
    else:
        wr.save()
        message = f'{user.username} marked "{snippet}" complete — confirm to close it out'
        if is_poster:
            for hire in hires:
                notify(hire, 'job_confirm', message, actor=user)
        else:
            notify(poster, 'job_review', message, actor=user)

    return JsonResponse({
        "message": "Job marked complete by both sides" if both_confirmed else "Marked complete — waiting for the other side",
        "status": wr.status,
        "completed_by_poster": wr.completed_by_poster,
        "completed_by_worker": wr.completed_by_worker,
    })


def send_work_proposal(request, receiver_id):
    if request.method == "POST":
        user, error = get_user_from_request(request)
        if error:
            return error

        guard = require_contact(user)
        if guard:
            return guard

        try:
            receiver = User.objects.get(id=receiver_id)

            if receiver.status != 'open_to_work':
                return JsonResponse({"error": "This user is not open to work"}, status=400)

            if user.id == receiver.id:
                return JsonResponse({"error": "You cannot send a proposal to yourself"}, status=400)

            description = request.POST.get("description", "").strip()
            payment_per_hour = request.POST.get("payment_per_hour", "").strip()
            payment_per_day = request.POST.get("payment_per_day", "").strip()

            if not description:
                return JsonResponse({"error": "Description is required"}, status=400)

            if not payment_per_hour and not payment_per_day:
                return JsonResponse({"error": "Either payment_per_hour or payment_per_day is required"}, status=400)

            proposal, created = WorkProposal.objects.get_or_create(
                sender=user,
                receiver=receiver,
                defaults={
                    "description": description,
                    "payment_per_hour": float(payment_per_hour) if payment_per_hour else None,
                    "payment_per_day": float(payment_per_day) if payment_per_day else None,
                }
            )

            if not created:
                return JsonResponse({"error": "You already sent a proposal to this user"}, status=400)

            from notifications.utils import notify
            notify(receiver, 'proposal', f"{user.username} sent you a work proposal", actor=user)

            return JsonResponse({"message": "Work proposal sent", "proposal_id": proposal.id}, status=201)

        except User.DoesNotExist:
            return JsonResponse({"error": "User not found"}, status=404)

    return JsonResponse({"error": "Method not allowed"}, status=405)


def respond_to_work_proposal(request, proposal_id):
    if request.method == "POST":
        user, error = get_user_from_request(request)
        if error:
            return error

        status = request.POST.get("status", "").strip().lower()
        if status not in ["accepted", "declined"]:
            return JsonResponse({"error": "status must be 'accepted' or 'declined'"}, status=400)

        if status == 'accepted':
            guard = require_contact(user)
            if guard:
                return guard

        try:
            proposal = WorkProposal.objects.get(id=proposal_id, receiver=user)

            if proposal.status != 'pending':
                return JsonResponse({"error": "Proposal already responded to"}, status=400)

            proposal.status = status
            proposal.save()

            from notifications.utils import notify
            ntype = 'proposal_accepted' if status == 'accepted' else 'proposal_declined'
            notify(proposal.sender, ntype,
                   f"{user.username} {status} your work proposal", actor=user)

            if status == 'accepted':
                # Same reuse logic as assign_work_request — don't fork a second
                # thread if these two already have a conversation going.
                conversation = next(
                    (c for c in Conversation.objects.filter(participants=user).filter(participants=proposal.sender)
                     if c.participants.count() == 2),
                    None,
                )
                if not conversation:
                    conversation = Conversation.objects.create(conversation_type='work')
                    conversation.participants.add(user, proposal.sender)
                return JsonResponse({
                    "message": "Proposal accepted — conversation started",
                    "conversation_id": conversation.id
                })

            return JsonResponse({"message": "Proposal declined"})

        except WorkProposal.DoesNotExist:
            return JsonResponse({"error": "Proposal not found or not yours"}, status=404)

    return JsonResponse({"error": "Method not allowed"}, status=405)


def get_my_proposals(request):
    if request.method == "GET":
        user, error = get_user_from_request(request)
        if error:
            return error

        proposals = WorkProposal.objects.filter(receiver=user).select_related("sender")
        data = [
            {
                "id": p.id,
                "from": p.sender.username,
                "description": p.description,
                "payment_per_hour": p.payment_per_hour,
                "payment_per_day": p.payment_per_day,
                "status": p.status,
                "created_at": str(p.created_at),
            }
            for p in proposals
        ]
        return JsonResponse({"proposals": data, "count": len(data)})

    return JsonResponse({"error": "Method not allowed"}, status=405)


def send_message(request, conversation_id):
    if request.method == "POST":
        user, error = get_user_from_request(request)
        if error:
            return error

        try:
            conversation = Conversation.objects.get(id=conversation_id)

            if not conversation.participants.filter(id=user.id).exists():
                return JsonResponse({"error": "You are not part of this conversation"}, status=403)

            # Cheap flood guard — scoped to this conversation (not globally
            # per-user) so replying quickly across two open threads doesn't
            # falsely trip it. 1s is imperceptible to a human sender but
            # blocks a script hammering this endpoint.
            recent_msg = Message.objects.filter(sender=user, conversation=conversation).order_by('-created_at').first()
            if recent_msg and recent_msg.created_at and (timezone.now() - recent_msg.created_at).total_seconds() < 1:
                return JsonResponse({"error": "Sending too fast — slow down a bit."}, status=429)

            from django.db.models import Q
            from users.models import Block
            others = list(conversation.participants.exclude(id=user.id))
            if others and Block.objects.filter(
                Q(blocker=user, blocked__in=others) | Q(blocker__in=others, blocked=user)
            ).exists():
                return JsonResponse({"error": "You can't message in this conversation"}, status=403)

            text = request.POST.get("text", "").strip()
            media_file = request.FILES.get("media")
            if not text and not media_file:
                return JsonResponse({"error": "Send some text or an attachment"}, status=400)

            media_url = ''
            media_type = ''
            if media_file:
                from users.views import validate_media_upload
                bad = validate_media_upload(media_file)
                if bad:
                    return JsonResponse({"error": bad}, status=400)
                ctype = (getattr(media_file, 'content_type', '') or '').lower()
                media_type = 'video' if ctype.startswith('video') else 'image'
                try:
                    import cloudinary, cloudinary.uploader
                    from django.conf import settings
                    cs = settings.CLOUDINARY_STORAGE
                    cloudinary.config(
                        cloud_name=cs.get('CLOUD_NAME'),
                        api_key=cs.get('API_KEY'),
                        api_secret=cs.get('API_SECRET'),
                    )
                    # resource_type='auto' handles both images and videos.
                    result = cloudinary.uploader.upload(
                        media_file, resource_type='auto', folder='messages'
                    )
                    media_url = result.get('secure_url', '')
                except Exception:
                    return JsonResponse({"error": "Couldn't upload that attachment"}, status=500)

            message = Message.objects.create(
                conversation=conversation, sender=user, text=text,
                media=media_url, media_type=media_type if media_url else '',
            )

            from notifications.utils import notify
            preview = text or ('sent a video' if media_type == 'video' else 'sent a photo')
            for other in others:
                notify(other, 'message', f"{user.username}: {preview[:40]}", actor=user)

            return JsonResponse({
                "message": "Message sent",
                "message_id": message.id,
                "media_url": message.media or None,
                "media_type": message.media_type or None,
                "created_at": str(message.created_at),
            }, status=201)

        except Conversation.DoesNotExist:
            return JsonResponse({"error": "Conversation not found"}, status=404)

    return JsonResponse({"error": "Method not allowed"}, status=405)


def get_messages(request, conversation_id):
    if request.method == "GET":
        user, error = get_user_from_request(request)
        if error:
            return error

        try:
            conversation = Conversation.objects.get(id=conversation_id)

            if not conversation.participants.filter(id=user.id).exists():
                return JsonResponse({"error": "You are not part of this conversation"}, status=403)

            # Mark anything sent TO this user as read now that they're
            # viewing the thread — powers the "seen" tick for the sender.
            Message.objects.filter(
                conversation=conversation, read_at__isnull=True
            ).exclude(sender=user).update(read_at=timezone.now())

            messages = Message.objects.filter(
                conversation=conversation
            ).select_related("sender").order_by("created_at")

            data = [
                {
                    "id": m.id,
                    "sender": m.sender.username,
                    "sender_avatar": request.build_absolute_uri(m.sender.profile_image.url) if m.sender.profile_image else None,
                    "text": m.text,
                    "media_url": m.media or None,
                    "media_type": m.media_type or None,
                    "created_at": str(m.created_at),
                    "read_at": str(m.read_at) if m.read_at else None,
                }
                for m in messages
            ]

            # Typing indicator — anyone else in this conversation who pinged
            # the typing endpoint in the last 4 seconds (frontend pings every
            # ~2s while the user is actively typing).
            typing_cutoff = timezone.now() - timedelta(seconds=4)
            typing_users = list(
                TypingStatus.objects.filter(conversation=conversation, updated_at__gte=typing_cutoff)
                .exclude(user=user).values_list('user__username', flat=True)
            )

            return JsonResponse({"messages": data, "count": len(data), "typing_users": typing_users})

        except Conversation.DoesNotExist:
            return JsonResponse({"error": "Conversation not found"}, status=404)

    return JsonResponse({"error": "Method not allowed"}, status=405)


def set_typing(request, conversation_id):
    if request.method == "POST":
        user, error = get_user_from_request(request)
        if error:
            return error

        try:
            conversation = Conversation.objects.get(id=conversation_id)
            if not conversation.participants.filter(id=user.id).exists():
                return JsonResponse({"error": "You are not part of this conversation"}, status=403)

            TypingStatus.objects.update_or_create(conversation=conversation, user=user)
            return JsonResponse({"ok": True})

        except Conversation.DoesNotExist:
            return JsonResponse({"error": "Conversation not found"}, status=404)

    return JsonResponse({"error": "Method not allowed"}, status=405)


def start_conversation(request, user_id):
    """Get-or-create a 1:1 direct conversation with another user. Only allowed
    once the two have actually worked together (an assigned freelance job, an
    accepted work proposal, or an accepted collab) — see the check below."""
    if request.method != "POST":
        return JsonResponse({"error": "Method not allowed"}, status=405)

    user, error = get_user_from_request(request)
    if error:
        return error

    if user.id == user_id:
        return JsonResponse({"error": "You can't message yourself"}, status=400)

    try:
        other = User.objects.get(id=user_id)
    except User.DoesNotExist:
        return JsonResponse({"error": "User not found"}, status=404)

    from users.models import Block
    from django.db.models import Q
    if Block.objects.filter(
        Q(blocker=user, blocked=other) | Q(blocker=other, blocked=user)
    ).exists():
        return JsonResponse({"error": "You can't message this user"}, status=403)

    # Reuse an existing 1:1 conversation if one already exists between the two.
    for c in Conversation.objects.filter(participants=user).filter(participants=other):
        if c.participants.count() == 2:
            return JsonResponse({"conversation_id": c.id})

    # No conversation yet — messaging is allowed either between friends, or
    # between people who've actually worked together (an assigned freelance job,
    # an accepted work proposal, or an accepted collab).
    from collab.models import CollabRequest
    from users.models import Friendship
    are_friends = Friendship.objects.filter(
        Q(requester=user, receiver=other) | Q(requester=other, receiver=user),
        status='accepted'
    ).exists()
    connected = are_friends or (
        WorkRequest.objects.filter(
            Q(created_by=user, assigned_to=other) | Q(created_by=other, assigned_to=user)
        ).exists()
        or WorkProposal.objects.filter(
            Q(sender=user, receiver=other) | Q(sender=other, receiver=user), status='accepted'
        ).exists()
        or CollabRequest.objects.filter(
            Q(applicant=user, collab_post__user=other) | Q(applicant=other, collab_post__user=user),
            status='accepted'
        ).exists()
    )
    if not connected:
        return JsonResponse({
            "error": "You can only message friends or people you've worked with — add them as a friend, or apply to their collab/freelance job first."
        }, status=403)

    convo = Conversation.objects.create(conversation_type='direct')
    convo.participants.add(user, other)
    return JsonResponse({"conversation_id": convo.id})


def _chat_work_context(conversation, user):
    """What a thread is about, so the inbox can say "Poster for the fest ·
    ₹800" instead of just a username. Conversation.work_request is a
    OneToOne, so on a gig hiring several people only the first chat carries
    the link; the rest fall back to no context rather than guessing."""
    wr = conversation.work_request
    if wr:
        return {
            "kind": "freelance",
            "id": wr.id,
            "title": (wr.description or "").strip()[:70],
            "payment_amount": wr.payment_amount,
            "status": wr.status,
            "is_poster": wr.created_by_id == user.id,
            "completed_by_poster": wr.completed_by_poster,
            "completed_by_worker": wr.completed_by_worker,
        }
    cp = conversation.collab_post
    if cp:
        return {
            "kind": "collab",
            "id": cp.id,
            "title": cp.title,
            "status": cp.status,
            "is_poster": cp.user_id == user.id,
        }
    return None


def get_my_conversations(request):
    if request.method == "GET":
        user, error = get_user_from_request(request)
        if error:
            return error

        # Chaining .order_by() onto a plain prefetch_related("messages") would
        # bypass Django's prefetch cache and issue a fresh query per
        # conversation for the "last message" lookup below — a real N+1 that
        # matters now that this endpoint is polled every 5s. Prefetch with an
        # explicit ordering so it's fetched once, grouped by conversation.
        conversations = Conversation.objects.filter(
            participants=user
        ).select_related("collab_post", "work_request").prefetch_related(
            "participants",
            Prefetch("messages", queryset=Message.objects.order_by("-created_at"), to_attr="_ordered_messages"),
        ).annotate(
            unread=Count(
                "messages",
                filter=Q(messages__read_at__isnull=True) & ~Q(messages__sender=user),
                distinct=True,
            )
        )

        data = []
        for c in conversations:
            last_message = c._ordered_messages[0] if c._ordered_messages else None
            activity_at = last_message.created_at if last_message else c.created_at
            others = list(c.participants.exclude(id=user.id))

            # A collab-team thread has an owner + every accepted applicant —
            # picking "the other participant" like the 1:1 cases below would
            # just show one arbitrary teammate and hide everyone else.
            if c.conversation_type == 'collab':
                entry = {
                    "id": c.id,
                    "type": c.conversation_type,
                    "is_group": True,
                    "with": c.collab_post.title if c.collab_post else "Collab team",
                    "with_id": None,
                    "with_avatar": None,
                    "collab_post_id": c.collab_post_id,
                    "is_collab_owner": bool(c.collab_post and c.collab_post.user_id == user.id),
                    "participants": [{"id": o.id, "username": o.username} for o in others],
                    "participant_count": len(others) + 1,
                }
            else:
                other = others[0] if others else None
                entry = {
                    "id": c.id,
                    "type": c.conversation_type,
                    "is_group": False,
                    "with": other.username if other else None,
                    "with_id": other.id if other else None,
                    "with_avatar": request.build_absolute_uri(other.profile_image.url) if other and other.profile_image else None,
                }

            entry["work"] = _chat_work_context(c, user)
            entry["unread"] = c.unread
            entry["last_message"] = last_message.text if last_message else None
            entry["last_message_at"] = str(last_message.created_at) if last_message else None
            entry["_activity_at"] = activity_at
            data.append(entry)

        # Most recently active conversation first — otherwise a chat from
        # weeks ago could sit above one with a message from 5 minutes ago.
        # (created_at/activity_at can be null on ancient rows, so those sort last.)
        data.sort(key=lambda d: (d["_activity_at"] is None, d["_activity_at"] and -d["_activity_at"].timestamp()))
        for d in data:
            del d["_activity_at"]

        return JsonResponse({"conversations": data, "count": len(data)})

    return JsonResponse({"error": "Method not allowed"}, status=405)

def get_my_applications(request):
    """Everything the logged-in user has applied to — freelance jobs and collab
    posts — with a simple status so they can track outcomes."""
    if request.method != "GET":
        return JsonResponse({"error": "Method not allowed"}, status=405)

    user, error = get_user_from_request(request)
    if error:
        return error

    from collab.models import CollabRequest

    apps = []

    from django.db.models import Count, Q
    now = timezone.now()

    # Freelance: WorkRequestResponse.user == applicant
    for r in WorkRequestResponse.objects.filter(user=user).select_related(
        'work_request', 'work_request__created_by'
    ):
        wr = r.work_request
        # Hiring flags each response; assigned_to is only the *first* hire,
        # kept for the 1:1 completion flow. Reading assigned_to alone told
        # hires #2-#5 they'd been passed over, and a declined applicant was
        # left on "pending" forever.
        hired = r.hired or wr.assigned_to_id == user.id
        expired = wr.expires_at is not None and wr.expires_at <= now
        if hired:
            status = 'accepted'
        elif r.rejected:
            status = 'declined'
        elif wr.status == 'assigned' or (wr.status == 'closed' and wr.assigned_to_id):
            status = 'filled'
        elif wr.status == 'closed' or expired:
            status = 'closed'
        else:
            status = 'pending'
        apps.append({
            'kind': 'freelance',
            'id': wr.id,
            'title': (wr.description or '').strip()[:70],
            'status': status,
            'wr_status': wr.status,   # raw open/assigned/closed — 'status' above is a display label
            'applied_at': str(r.created_at) if r.created_at else None,
            'posted_by': wr.created_by.username,
            'posted_by_id': wr.created_by.id,
            'payment_amount': wr.payment_amount,
            'completed_by_poster': wr.completed_by_poster,
            'completed_by_worker': wr.completed_by_worker,
            'people_needed': wr.people_needed or 1,
        })

    # Collab: CollabRequest.applicant == user
    collab_requests = (
        CollabRequest.objects.filter(applicant=user)
        .select_related('collab_post', 'collab_post__user')
        .annotate(team_filled=Count(
            'collab_post__requests',
            filter=Q(collab_post__requests__status='accepted'),
            distinct=True,
        ))
    )
    for cr in collab_requests:
        cp = cr.collab_post
        status = cr.status   # pending / accepted / declined
        # A request still pending on a post that has since filled up, been
        # closed, or run out of time will never be answered.
        if status == 'pending':
            if cr.team_filled >= (cp.people_needed or 1):
                status = 'filled'
            elif cp.status == 'closed' or (cp.expires_at and cp.expires_at <= now):
                status = 'closed'
        apps.append({
            'kind': 'collab',
            'id': cp.id,
            'title': cp.title,
            'status': status,
            'applied_at': str(cr.created_at) if cr.created_at else None,
            'posted_by': cp.user.username,
            'posted_by_id': cp.user.id,
            'collab_type': cp.collab_type,
            'people_needed': cp.people_needed or 1,
            'team_filled': cr.team_filled,
        })

    apps.sort(key=lambda a: a['applied_at'] or '', reverse=True)
    return JsonResponse({'applications': apps, 'count': len(apps)})
