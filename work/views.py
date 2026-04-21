from django.http import JsonResponse
from django.utils import timezone
from datetime import timedelta
from .models import WorkRequest, WorkRequestResponse, WorkProposal, Conversation, Message
from users.models import User
from skills.models import Skill
from users.views import get_user_from_token


def get_user_from_request(request):
    return get_user_from_token(request)


def create_work_request(request):
    if request.method == "POST":
        user, error = get_user_from_request(request)
        if error:
            return error

        description = request.POST.get("description", "").strip()
        payment_amount = request.POST.get("payment_amount", "").strip()
        time_limit_hours = request.POST.get("time_limit_hours", "").strip()
        skills = request.POST.get("skills", "").strip()

        if not description or not payment_amount or not time_limit_hours or not skills:
            return JsonResponse({"error": "description, payment_amount, time_limit_hours and skills are required"}, status=400)

        skill_list = [s.strip() for s in skills.split(",")]
        skill_objects = []
        for skill_name in skill_list:
            try:
                skill = Skill.objects.get(name__iexact=skill_name)
                skill_objects.append(skill)
            except Skill.DoesNotExist:
                return JsonResponse({"error": f"Skill '{skill_name}' not found. Add it first."}, status=400)

        expires_at = timezone.now() + timedelta(hours=int(time_limit_hours))
        work_request = WorkRequest.objects.create(
            created_by=user,
            description=description,
            payment_amount=float(payment_amount),
            time_limit_hours=int(time_limit_hours),
            expires_at=expires_at,
        )
        work_request.required_skills.set(skill_objects)

        return JsonResponse({
            "message": "Work request created",
            "work_request_id": work_request.id,
            "expires_at": work_request.expires_at,
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
                    "expires_at": wr.expires_at,
                    "responses_count": wr.responses.count(),
                    "created_at": wr.created_at,
                }
                for wr in requests
            ]
            return JsonResponse({"work_requests": data, "count": len(data)})
        except User.DoesNotExist:
            return JsonResponse({"error": "User not found"}, status=404)

    return JsonResponse({"error": "Method not allowed"}, status=405)


def get_available_work_requests(request, user_id):
    if request.method == "GET":
        try:
            user = User.objects.get(id=user_id)
            user_skills = user.skills.all()

            if not user_skills:
                return JsonResponse({"error": "Add skills to your profile to see matching requests"}, status=400)

            work_requests = WorkRequest.objects.filter(
                status='open',
                required_skills__in=user_skills,
                expires_at__gt=timezone.now(),
            ).exclude(created_by=user).distinct().order_by("-created_at")

            data = [
                {
                    "id": wr.id,
                    "created_by": wr.created_by.username,
                    "description": wr.description,
                    "skills": [s.name for s in wr.required_skills.all()],
                    "payment_amount": wr.payment_amount,
                    "time_limit_hours": wr.time_limit_hours,
                    "expires_at": wr.expires_at,
                    "created_at": wr.created_at,
                }
                for wr in work_requests
            ]
            return JsonResponse({"work_requests": data, "count": len(data)})
        except User.DoesNotExist:
            return JsonResponse({"error": "User not found"}, status=404)

    return JsonResponse({"error": "Method not allowed"}, status=405)


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
                    "responded_at": r.created_at,
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

            # auto create verified portfolio item for assignee
            if work_request.assigned_to:
                from portfolio.models import PortfolioItem
                item = PortfolioItem.objects.create(
                    user=work_request.assigned_to,
                    title=f"Completed: {work_request.description[:80]}",
                    description=f"Completed work for a client. Verified on SkillMap.",
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

        try:
            proposal = WorkProposal.objects.get(id=proposal_id, receiver=user)

            if proposal.status != 'pending':
                return JsonResponse({"error": "Proposal already responded to"}, status=400)

            proposal.status = status
            proposal.save()

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
                "created_at": p.created_at,
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

            text = request.POST.get("text", "").strip()
            if not text:
                return JsonResponse({"error": "Message text is required"}, status=400)

            message = Message.objects.create(conversation=conversation, sender=user, text=text)
            return JsonResponse({
                "message": "Message sent",
                "message_id": message.id,
                "created_at": message.created_at,
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
                    "text": m.text,
                    "created_at": m.created_at,
                }
                for m in messages
            ]
            return JsonResponse({"messages": data, "count": len(data)})

        except Conversation.DoesNotExist:
            return JsonResponse({"error": "Conversation not found"}, status=404)

    return JsonResponse({"error": "Method not allowed"}, status=405)


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
                "last_message": last_message.text if last_message else None,
                "last_message_at": last_message.created_at if last_message else None,
            })

        return JsonResponse({"conversations": data, "count": len(data)})

    return JsonResponse({"error": "Method not allowed"}, status=405)