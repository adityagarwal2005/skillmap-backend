from django.http import JsonResponse
from django.utils import timezone
from datetime import timedelta
from .models import WorkRequest, WorkRequestResponse, WorkProposal, Conversation, Message
from users.models import User
from skills.models import Skill, Category
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

        description = request.POST.get("description", "").strip()
        payment_amount = request.POST.get("payment_amount", "").strip()
        time_limit_hours = request.POST.get("time_limit_hours", "").strip()
        skills = request.POST.get("skills", "").strip()

        if not description or not payment_amount or not time_limit_hours or not skills:
            return JsonResponse({"error": "description, payment_amount, time_limit_hours and skills are required"}, status=400)

        skill_list = [s.strip() for s in skills.split(",") if s.strip()]
        skill_objects = []
        for skill_name in skill_list:
            skill, _ = Skill.objects.get_or_create(name__iexact=skill_name, defaults={"name": skill_name})
            skill_objects.append(skill)

        try:
            expires_at = timezone.now() + timedelta(hours=int(time_limit_hours))
        except ValueError:
            return JsonResponse({"error": "time_limit_hours must be a number"}, status=400)

        latitude = request.POST.get("latitude", "").strip()
        longitude = request.POST.get("longitude", "").strip()
        work_request = WorkRequest.objects.create(
            created_by=user,
            description=description,
            payment_amount=float(payment_amount),
            time_limit_hours=int(time_limit_hours),
            expires_at=expires_at,
            status='open',
            latitude=float(latitude) if latitude else None,
            longitude=float(longitude) if longitude else None,
        )
        work_request.required_skills.set(skill_objects)

        return JsonResponse({
            "message": "Work request created",
            "work_request_id": work_request.id,
            "expires_at": str(work_request.expires_at),
        }, status=201)

    return JsonResponse({"error": "Method not allowed"}, status=405)


def get_my_work_requests(request, user_id):
    if request.method == "GET":
        try:
            user = User.objects.get(id=user_id)
            requests = WorkRequest.objects.filter(created_by=user).order_by("-created_at")
            data = [
                {
                    "id": wr.id,
                    "description": wr.description,
                    "skills": [s.name for s in wr.required_skills.all()],
                    "payment_amount": wr.payment_amount,
                    "time_limit_hours": wr.time_limit_hours,
                    "status": wr.status,
                    "assigned_to": wr.assigned_to.username if wr.assigned_to else None,
                    "expires_at": str(wr.expires_at),
                    "responses_count": wr.responses.count(),
                    "created_at": str(wr.created_at),
                }
                for wr in requests
            ]
            return JsonResponse({"work_requests": data, "count": len(data)})
        except User.DoesNotExist:
            return JsonResponse({"error": "User not found"}, status=404)

    return JsonResponse({"error": "Method not allowed"}, status=405)


def get_available_work_requests(request, user_id):
    user, error = get_user_from_request(request)
    if error:
        return error

    skill_filter = request.GET.get('skill', '').strip().lower()
    radius_km    = float(request.GET.get('radius', 50))
    latitude     = request.GET.get('latitude')
    longitude    = request.GET.get('longitude')

    # Newest first — this is a live job board.
    work_requests = WorkRequest.objects.filter(status='open').order_by('-created_at')

    results = []
    for wr in work_requests:
        if wr.created_by.id == user.id:
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
                if distance > radius_km:
                    continue
                dist_display = round(distance, 1)
            else:
                continue

        results.append({
            'id':               wr.id,
            'description':      wr.description,
            'payment_amount':   wr.payment_amount,
            'time_limit_hours': wr.time_limit_hours,
            'status':           wr.status,
            'created_by':       wr.created_by.username,
            'skills':           [s.name for s in wr.required_skills.all()],
            'expires_at':       str(wr.expires_at) if wr.expires_at else None,
            'created_at':       str(wr.created_at) if wr.created_at else None,
            'distance_km':      dist_display,
            'responses_count':  wr.responses.count(),
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

            WorkRequestResponse.objects.create(
                work_request=work_request,
                user=user,
                status=status,
                message=message if message else None,
            )
            return JsonResponse({"message": f"Response '{status}' submitted successfully"})

        except WorkRequest.DoesNotExist:
            return JsonResponse({"error": "Work request not found"}, status=404)

    return JsonResponse({"error": "Method not allowed"}, status=405)


def get_work_request_responses(request, work_request_id):
    if request.method == "GET":
        try:
            work_request = WorkRequest.objects.get(id=work_request_id)
            responses = WorkRequestResponse.objects.filter(
                work_request=work_request, status='accepted'
            ).select_related("user")

            data = [
                {
                    "user_id": r.user.id,
                    "username": r.user.username,
                    "skills": [s.name for s in r.user.skills.all()],
                    "rating": r.user.rating,
                    "message": r.message,
                    "responded_at": str(r.created_at),
                }
                for r in responses
            ]
            return JsonResponse({"applicants": data, "count": len(data)})
        except WorkRequest.DoesNotExist:
            return JsonResponse({"error": "Work request not found"}, status=404)

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

            if not WorkRequestResponse.objects.filter(
                work_request=work_request, user=assignee, status='accepted'
            ).exists():
                return JsonResponse({"error": "This user has not accepted the request"}, status=400)

            work_request.assigned_to = assignee
            work_request.status = 'assigned'
            work_request.save()

            conversation = Conversation.objects.create(
                work_request=work_request,
                conversation_type='freelance'
            )
            conversation.participants.add(user, assignee)

            return JsonResponse({
                "message": f"Work assigned to {assignee.username} successfully",
                "conversation_id": conversation.id
            })

        except WorkRequest.DoesNotExist:
            return JsonResponse({"error": "Work request not found or not yours"}, status=404)
        except User.DoesNotExist:
            return JsonResponse({"error": "Assignee not found"}, status=404)

    return JsonResponse({"error": "Method not allowed"}, status=405)


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
                    description="Completed work for a client. Verified on SkillMap.",
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

            from django.db.models import Q
            from users.models import Block
            other = conversation.participants.exclude(id=user.id).first()
            if other and Block.objects.filter(
                Q(blocker=user, blocked=other) | Q(blocker=other, blocked=user)
            ).exists():
                return JsonResponse({"error": "You can't message this user"}, status=403)

            text = request.POST.get("text", "").strip()
            media_file = request.FILES.get("media")
            if not text and not media_file:
                return JsonResponse({"error": "Send some text or an attachment"}, status=400)

            media_url = ''
            media_type = ''
            if media_file:
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
                }
                for m in messages
            ]
            return JsonResponse({"messages": data, "count": len(data)})

        except Conversation.DoesNotExist:
            return JsonResponse({"error": "Conversation not found"}, status=404)

    return JsonResponse({"error": "Method not allowed"}, status=405)


def start_conversation(request, user_id):
    """Get-or-create a 1:1 direct conversation with another user, so anyone can
    message anyone (not only after a proposal/collab is accepted)."""
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

    # No conversation yet — messaging is only allowed between people who have
    # actually worked together: an accepted freelance job or collab.
    from collab.models import CollabRequest
    connected = (
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
            "error": "You can only message people you've worked with — apply to their collab or freelance job (or accept theirs) first."
        }, status=403)

    convo = Conversation.objects.create(conversation_type='direct')
    convo.participants.add(user, other)
    return JsonResponse({"conversation_id": convo.id})


def get_my_conversations(request):
    if request.method == "GET":
        user, error = get_user_from_request(request)
        if error:
            return error

        conversations = Conversation.objects.filter(
            participants=user
        ).prefetch_related("participants", "messages")

        data = []
        for c in conversations:
            other = c.participants.exclude(id=user.id).first()
            last_message = c.messages.order_by("-created_at").first()
            data.append({
                "id": c.id,
                "type": c.conversation_type,
                "with": other.username if other else None,
                "with_id": other.id if other else None,
                "with_avatar": request.build_absolute_uri(other.profile_image.url) if other and other.profile_image else None,
                "last_message": last_message.text if last_message else None,
                "last_message_at": str(last_message.created_at) if last_message else None,
            })

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
            'applied_at': str(r.created_at) if r.created_at else None,
            'posted_by': wr.created_by.username,
            'posted_by_id': wr.created_by.id,
            'payment_amount': wr.payment_amount,
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
