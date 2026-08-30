from django.http import JsonResponse
from django.db.models import Prefetch
from django.utils import timezone
from datetime import timedelta
from .models import WorkRequest, WorkRequestResponse, WorkProposal, Conversation, Message, TypingStatus
from users.models import User
# Skill/Category are reached via skills.utils now (see create_work_request).
from users.views import get_user_from_token, require_contact


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
            expires_at = timezone.now() + timedelta(hours=int(time_limit_hours))
        except ValueError:
            return JsonResponse({"error": "time_limit_hours must be a number"}, status=400)

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
            payment_amount=float(payment_amount),
            time_limit_hours=int(time_limit_hours),
            gender_preference=gender_preference,
            people_needed=people_needed,
            expires_at=expires_at,
            status='open',
            latitude=float(latitude) if latitude else None,
            longitude=float(longitude) if longitude else None,
            range_km=float(range_km) if range_km else None,
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
    radius_km    = float(request.GET.get('radius', 50))
    latitude     = request.GET.get('latitude')
    longitude    = request.GET.get('longitude')

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
        if latitude and longitude:
            if job_lat is not None and job_lon is not None:
                distance = get_distance_km(
                    float(latitude), float(longitude),
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
            if conversation:
                if conversation.work_request_id is None:
                    conversation.work_request = work_request
                    conversation.save(update_fields=['work_request'])
            else:
                conversation = Conversation.objects.create(
                    work_request=work_request,
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
    """Post owner declines an applicant. Deletes their WorkRequestResponse so
    the applicant is removed and is free to apply to the same job again."""
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
    return JsonResponse({"message": "Applicant declined"})


def close_work_request(request, work_request_id):
    if request.method == "POST":
        user, error = get_user_from_request(request)
        if error:
            return error

        try:
            work_request = WorkRequest.objects.get(id=work_request_id, created_by=user)
            work_request.status = 'closed'
            work_request.save()

            if work_request.assigned_to:
                from portfolio.models import PortfolioItem
                item = PortfolioItem.objects.create(
                    user=work_request.assigned_to,
                    title=f"Completed: {work_request.description[:80]}",
                    description="Completed work for a client. Verified on DoitHere.",
                    portfolio_type='project',
                    verified=True,
                    verified_via_work=work_request,
                )
                item.skills.set(work_request.required_skills.all())
                return JsonResponse({
                    "message": "Work request closed",
                    "portfolio_item_created": True,
                    "portfolio_item_id": item.id,
                })

            return JsonResponse({"message": "Work request closed"})

        except WorkRequest.DoesNotExist:
            return JsonResponse({"error": "Work request not found or not yours"}, status=404)

    return JsonResponse({"error": "Method not allowed"}, status=405)


def complete_work_request(request, work_request_id):
    """Mutual completion: both the poster and the hired worker must confirm
    before a job actually closes. Prevents one side unilaterally declaring a
    job 'done' and lets us prompt both to rate each other once it's final."""
    if request.method != "POST":
        return JsonResponse({"error": "Method not allowed"}, status=405)

    user, error = get_user_from_request(request)
    if error:
        return error

    try:
        wr = WorkRequest.objects.get(id=work_request_id)
    except WorkRequest.DoesNotExist:
        return JsonResponse({"error": "Job not found"}, status=404)

    is_poster = user.id == wr.created_by_id
    is_worker = wr.assigned_to_id is not None and user.id == wr.assigned_to_id
    if not (is_poster or is_worker):
        return JsonResponse({"error": "You're not part of this job"}, status=403)

    if wr.status != 'assigned':
        return JsonResponse({"error": "This job isn't in progress"}, status=400)

    from notifications.utils import notify

    if is_poster:
        wr.completed_by_poster = True
    else:
        wr.completed_by_worker = True

    both_confirmed = wr.completed_by_poster and wr.completed_by_worker

    if both_confirmed:
        from django.utils import timezone
        wr.status = 'closed'
        wr.completed_at = timezone.now()
        wr.save()

        from portfolio.models import PortfolioItem
        if not PortfolioItem.objects.filter(verified_via_work=wr).exists():
            item = PortfolioItem.objects.create(
                user=wr.assigned_to,
                title=f"Completed: {wr.description[:80]}",
                description="Completed work for a client. Verified on DoitHere.",
                portfolio_type='project',
                verified=True,
                verified_via_work=wr,
            )
            item.skills.set(wr.required_skills.all())

        notify(wr.created_by, 'job_complete', "Job complete on both sides — rate each other!", actor=None)
        notify(wr.assigned_to, 'job_complete', "Job complete on both sides — rate each other!", actor=None)
    else:
        wr.save()
        other = wr.assigned_to if is_poster else wr.created_by
        notify(other, 'job_complete', f"{user.username} marked the job complete — confirm to close it out", actor=user)

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
        ).select_related("collab_post").prefetch_related(
            "participants",
            Prefetch("messages", queryset=Message.objects.order_by("-created_at"), to_attr="_ordered_messages"),
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

    # Freelance: WorkRequestResponse.user == applicant
    for r in WorkRequestResponse.objects.filter(user=user).select_related(
        'work_request', 'work_request__created_by'
    ):
        wr = r.work_request
        if wr.assigned_to_id == user.id:
            status = 'accepted'
        elif wr.status in ('assigned', 'closed'):
            status = 'filled'      # someone else was picked
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
        })

    # Collab: CollabRequest.applicant == user
    for cr in CollabRequest.objects.filter(applicant=user).select_related(
        'collab_post', 'collab_post__user'
    ):
        cp = cr.collab_post
        apps.append({
            'kind': 'collab',
            'id': cp.id,
            'title': cp.title,
            'status': cr.status,   # pending / accepted / declined
            'applied_at': str(cr.created_at) if cr.created_at else None,
            'posted_by': cp.user.username,
            'posted_by_id': cp.user.id,
            'collab_type': cp.collab_type,
        })

    apps.sort(key=lambda a: a['applied_at'] or '', reverse=True)
    return JsonResponse({'applications': apps, 'count': len(apps)})
