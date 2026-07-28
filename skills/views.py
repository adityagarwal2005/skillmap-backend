from django.http import JsonResponse
from django.db.models import Q
from .models import Category, Skill, UserSkill
from users.models import User
from users.views import get_user_from_token
import math


def add_category(request):
    if request.method == "POST":
        # Not called anywhere by the frontend — categories are seeded/managed
        # via the admin. It had no auth check at all, so anyone could spam
        # arbitrary rows into this table; require login at minimum.
        user, error = get_user_from_token(request)
        if error:
            return error

        name = request.POST.get("name", "").strip()
        if not name:
            return JsonResponse({"error": "Category name is required"}, status=400)

        category, created = Category.objects.get_or_create(name=name)
        if not created:
            return JsonResponse({"error": "Category already exists"}, status=400)
        return JsonResponse({"message": "Category created", "category_id": category.id}, status=201)

    return JsonResponse({"error": "Method not allowed"}, status=405)


def show_categories(request):
    if request.method == "GET":
        categories = Category.objects.all()
        data = [{"id": c.id, "name": c.name} for c in categories]
        return JsonResponse({"categories": data})

    return JsonResponse({"error": "Method not allowed"}, status=405)


def get_category_skills(request, category_id):
    if request.method == "GET":
        try:
            category = Category.objects.get(id=category_id)
            # Skills seeded onto the category itself, plus any skills real users
            # in this category actually have — so the filter is useful even for
            # a brand-new campus category with no members yet.
            skills = Skill.objects.filter(
                Q(category=category) | Q(userskill__user__category=category)
            ).distinct()
            data = [{"id": s.id, "name": s.name} for s in skills]
            return JsonResponse({"category": category.name, "skills": data})
        except Category.DoesNotExist:
            return JsonResponse({"error": "Category not found"}, status=404)

    return JsonResponse({"error": "Method not allowed"}, status=405)


def add_skill(request, user_id):
    if request.method == "POST":
        user, error = get_user_from_token(request)
        if error:
            return error

        if user.id != user_id:
            return JsonResponse({"error": "You can only add skills to your own profile"}, status=403)

        skill_name = request.POST.get("skill", "").strip()
        if not skill_name:
            return JsonResponse({"error": "Skill name is required"}, status=400)

        skill, _ = Skill.objects.get_or_create(name=skill_name)
        UserSkill.objects.get_or_create(user=user, skill=skill)
        return JsonResponse({"message": f"Skill '{skill_name}' added"})

    return JsonResponse({"error": "Method not allowed"}, status=405)


def remove_skill(request, user_id):
    if request.method == "DELETE":
        user, error = get_user_from_token(request)
        if error:
            return error

        if user.id != user_id:
            return JsonResponse({"error": "You can only remove your own skills"}, status=403)

        skill_name = request.POST.get("skill", "").strip()
        if not skill_name:
            return JsonResponse({"error": "Skill name is required"}, status=400)

        try:
            skill = Skill.objects.get(name=skill_name)
            UserSkill.objects.filter(user=user, skill=skill).delete()
            return JsonResponse({"message": f"Skill '{skill_name}' removed"})
        except Skill.DoesNotExist:
            return JsonResponse({"error": "Skill not found"}, status=404)

    return JsonResponse({"error": "Method not allowed"}, status=405)


