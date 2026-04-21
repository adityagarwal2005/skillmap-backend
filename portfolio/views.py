from django.http import JsonResponse
from .models import PortfolioItem, Media, Reaction, Comment
from users.models import User
from skills.models import Skill, Tag
from users.views import get_user_from_token


def get_user_from_request(request):
    return get_user_from_token(request)


def create_portfolio_item(request):
    if request.method == "POST":
        user, error = get_user_from_request(request)
        if error:
            return error

        title = request.POST.get("title", "").strip()
        description = request.POST.get("description", "").strip()
        portfolio_type = request.POST.get("portfolio_type", "project").strip()
        skills_input = request.POST.get("skills", "").strip()
        tags_input = request.POST.get("tags", "").strip()

        if not title or not description:
            return JsonResponse({"error": "title and description are required"}, status=400)

        valid_types = ['project', 'design', 'photo', 'baked_good', 'artwork', 'video', 'other']
        if portfolio_type not in valid_types:
            return JsonResponse({"error": f"portfolio_type must be one of: {', '.join(valid_types)}"}, status=400)

        latitude = request.POST.get("latitude", "").strip()
        longitude = request.POST.get("longitude", "").strip()
        item = PortfolioItem.objects.create(
            user=user,
            title=title,
            description=description,
            portfolio_type=portfolio_type,
            latitude=float(latitude) if latitude else None,
            longitude=float(longitude) if longitude else None,
        )

        # add skills (optional)
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
                item.delete()
                return JsonResponse({"error": f"Invalid skills: {', '.join(invalid)}"}, status=400)
            item.skills.set(skill_objects)

        # add tags (optional)
        if tags_input:
            tag_list = [t.strip() for t in tags_input.split(",")]
            tag_objects = []
            for tag_name in tag_list:
                tag, _ = Tag.objects.get_or_create(name=tag_name)
                tag_objects.append(tag)
            item.tags.set(tag_objects)

        return JsonResponse({
            "message": "Portfolio item created",
            "item_id": item.id,
            "title": item.title,
            "portfolio_type": item.portfolio_type,
            "skills": [s.name for s in item.skills.all()],
            "tags": [t.name for t in item.tags.all()],
        }, status=201)

    return JsonResponse({"error": "Method not allowed"}, status=405)


def show_portfolio_items(request):
    """Show all portfolio items — public feed"""
    if request.method == "GET":
        portfolio_type = request.GET.get("type", "").strip()

        items = PortfolioItem.objects.select_related("user").prefetch_related(
            "skills", "tags", "media", "reactions", "comments"
        ).order_by("-created_at")

        if portfolio_type:
            items = items.filter(portfolio_type=portfolio_type)

        data = [
            {
                "id": i.id,
                "username": i.user.username,
                "title": i.title,
                "description": i.description,
                "portfolio_type": i.portfolio_type,
                "skills": [s.name for s in i.skills.all()],
                "tags": [t.name for t in i.tags.all()],
                "media": [
                    {
                        "id": m.id,
                        "media_type": m.media_type,
                        "url": m.url if m.url else request.build_absolute_uri(m.file.url) if m.file else None,
                        "order": m.order,
                    }
                    for m in i.media.all()
                ],
                "reactions": i.reactions.count(),
                "comments": i.comments.count(),
                "created_at": i.created_at,
            }
            for i in items
        ]
        return JsonResponse({"items": data, "count": len(data)})

    return JsonResponse({"error": "Method not allowed"}, status=405)


def show_user_portfolio(request, user_id):
    """Show a user's portfolio with optional skill/tag filtering"""
    if request.method == "GET":
        try:
            user = User.objects.get(id=user_id)
            skills_filter = request.GET.get("skills", "").strip()
            tags_filter = request.GET.get("tags", "").strip()
            type_filter = request.GET.get("type", "").strip()

            items = PortfolioItem.objects.filter(user=user).prefetch_related(
                "skills", "tags", "media", "reactions", "comments"
            ).order_by("-created_at")

            if type_filter:
                items = items.filter(portfolio_type=type_filter)

            if skills_filter:
                for skill_name in [s.strip() for s in skills_filter.split(",")]:
                    items = items.filter(skills__name__iexact=skill_name)
                items = items.distinct()

            if tags_filter:
                for tag_name in [t.strip() for t in tags_filter.split(",")]:
                    items = items.filter(tags__name__iexact=tag_name)
                items = items.distinct()

            data = [
                {
                    "id": i.id,
                    "title": i.title,
                    "description": i.description,
                    "portfolio_type": i.portfolio_type,
                    "skills": [s.name for s in i.skills.all()],
                    "tags": [t.name for t in i.tags.all()],
                    "media": [
                        {
                            "id": m.id,
                            "media_type": m.media_type,
                            "url": m.url if m.url else request.build_absolute_uri(m.file.url) if m.file else None,
                            "order": m.order,
                        }
                        for m in i.media.all()
                    ],
                    "reactions": i.reactions.count(),
                    "comments": i.comments.count(),
                    "latitude": i.latitude,      # add this
                    "longitude": i.longitude, 
                    "created_at": i.created_at,
                }
                for i in items
            ]
            return JsonResponse({"items": data, "count": len(data)})
        except User.DoesNotExist:
            return JsonResponse({"error": "User not found"}, status=404)

    return JsonResponse({"error": "Method not allowed"}, status=405)


def edit_portfolio_item(request, item_id):
    if request.method == "POST":
        user, error = get_user_from_request(request)
        if error:
            return error

        try:
            item = PortfolioItem.objects.get(id=item_id, user=user)

            title = request.POST.get("title", "").strip()
            description = request.POST.get("description", "").strip()
            portfolio_type = request.POST.get("portfolio_type", "").strip()
            skills_input = request.POST.get("skills", "").strip()
            tags_input = request.POST.get("tags", "").strip()

            if title:
                item.title = title
            if description:
                item.description = description
            if portfolio_type:
                item.portfolio_type = portfolio_type

            if skills_input:
                skill_list = [s.strip() for s in skills_input.split(",")]
                skill_objects = []
                for skill_name in skill_list:
                    try:
                        skill = Skill.objects.get(name__iexact=skill_name)
                        skill_objects.append(skill)
                    except Skill.DoesNotExist:
                        return JsonResponse({"error": f"Skill '{skill_name}' not found"}, status=400)
                item.skills.set(skill_objects)

            if tags_input:
                tag_list = [t.strip() for t in tags_input.split(",")]
                tag_objects = []
                for tag_name in tag_list:
                    tag, _ = Tag.objects.get_or_create(name=tag_name)
                    tag_objects.append(tag)
                item.tags.set(tag_objects)

            item.save()
            return JsonResponse({"message": "Portfolio item updated"})
        except PortfolioItem.DoesNotExist:
            return JsonResponse({"error": "Item not found or not yours"}, status=404)

    return JsonResponse({"error": "Method not allowed"}, status=405)


def delete_portfolio_item(request, item_id):
    if request.method == "DELETE":
        user, error = get_user_from_request(request)
        if error:
            return error

        try:
            item = PortfolioItem.objects.get(id=item_id, user=user)
            item.delete()
            return JsonResponse({"message": "Portfolio item deleted"})
        except PortfolioItem.DoesNotExist:
            return JsonResponse({"error": "Item not found or not yours"}, status=404)

    return JsonResponse({"error": "Method not allowed"}, status=405)


def add_media(request, item_id):
    if request.method == "POST":
        user, error = get_user_from_request(request)
        if error:
            return error

        try:
            item = PortfolioItem.objects.get(id=item_id, user=user)

            media_type = request.POST.get("media_type", "").strip()
            url = request.POST.get("url", "").strip()
            file = request.FILES.get("file")
            order = request.POST.get("order", 0)

            if media_type not in ["image", "video", "link"]:
                return JsonResponse({"error": "media_type must be image, video or link"}, status=400)

            if not file and not url:
                return JsonResponse({"error": "Either file or url is required"}, status=400)

            media = Media.objects.create(
                portfolio_item=item,
                media_type=media_type,
                url=url if url else None,
                file=file if file else None,
                order=int(order),
            )

            return JsonResponse({
                "message": "Media added",
                "media_id": media.id,
                "url": media.url if media.url else request.build_absolute_uri(media.file.url) if media.file else None,
            }, status=201)

        except PortfolioItem.DoesNotExist:
            return JsonResponse({"error": "Item not found or not yours"}, status=404)

    return JsonResponse({"error": "Method not allowed"}, status=405)


def react_to_item(request, item_id):
    """Like/love/fire a portfolio item — or remove reaction if same type"""
    if request.method == "POST":
        user, error = get_user_from_request(request)
        if error:
            return error

        reaction_type = request.POST.get("reaction_type", "like").strip()
        if reaction_type not in ["like", "love", "fire"]:
            return JsonResponse({"error": "reaction_type must be like, love or fire"}, status=400)

        try:
            item = PortfolioItem.objects.get(id=item_id)
            existing = Reaction.objects.filter(portfolio_item=item, user=user).first()

            if existing:
                if existing.reaction_type == reaction_type:
                    existing.delete()
                    return JsonResponse({"message": f"Reaction removed"})
                else:
                    existing.reaction_type = reaction_type
                    existing.save()
                    return JsonResponse({"message": f"Reaction updated to {reaction_type}"})
            else:
                Reaction.objects.create(
                    portfolio_item=item,
                    user=user,
                    reaction_type=reaction_type
                )
                return JsonResponse({"message": f"Reacted with {reaction_type}"})

        except PortfolioItem.DoesNotExist:
            return JsonResponse({"error": "Item not found"}, status=404)

    return JsonResponse({"error": "Method not allowed"}, status=405)


def add_comment(request, item_id):
    if request.method == "POST":
        user, error = get_user_from_request(request)
        if error:
            return error

        try:
            item = PortfolioItem.objects.get(id=item_id)
            text = request.POST.get("text", "").strip()
            if not text:
                return JsonResponse({"error": "Comment text is required"}, status=400)

            comment = Comment.objects.create(portfolio_item=item, user=user, text=text)
            return JsonResponse({"message": "Comment added", "comment_id": comment.id}, status=201)
        except PortfolioItem.DoesNotExist:
            return JsonResponse({"error": "Item not found"}, status=404)

    return JsonResponse({"error": "Method not allowed"}, status=405)


def show_item_comments(request, item_id):
    if request.method == "GET":
        try:
            item = PortfolioItem.objects.get(id=item_id)
            comments = Comment.objects.filter(portfolio_item=item).select_related("user")
            data = [
                {
                    "id": c.id,
                    "username": c.user.username,
                    "text": c.text,
                    "created_at": c.created_at,
                }
                for c in comments
            ]
            return JsonResponse({"comments": data, "count": len(data)})
        except PortfolioItem.DoesNotExist:
            return JsonResponse({"error": "Item not found"}, status=404)

    return JsonResponse({"error": "Method not allowed"}, status=405)


def edit_comment(request, comment_id):
    if request.method == "POST":
        user, error = get_user_from_request(request)
        if error:
            return error

        try:
            comment = Comment.objects.get(id=comment_id, user=user)
            new_text = request.POST.get("text", "").strip()
            if not new_text:
                return JsonResponse({"error": "Text is required"}, status=400)

            comment.text = new_text
            comment.save()
            return JsonResponse({"message": "Comment updated"})
        except Comment.DoesNotExist:
            return JsonResponse({"error": "Comment not found or not yours"}, status=404)

    return JsonResponse({"error": "Method not allowed"}, status=405)


def remove_comment(request, comment_id):
    if request.method == "DELETE":
        user, error = get_user_from_request(request)
        if error:
            return error

        try:
            comment = Comment.objects.get(id=comment_id, user=user)
            comment.delete()
            return JsonResponse({"message": "Comment removed"})
        except Comment.DoesNotExist:
            return JsonResponse({"error": "Comment not found or not yours"}, status=404)

    return JsonResponse({"error": "Method not allowed"}, status=405)