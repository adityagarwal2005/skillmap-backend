from django.http import JsonResponse
from .models import Category, Skill, UserSkill, Certificate
from users.models import User
from users.views import get_user_from_token
import math


def add_category(request):
    if request.method == "POST":
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
            skills = Skill.objects.filter(
                userskill__user__category=category
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


def add_certificate(request):
    if request.method == "POST":
        user, error = get_user_from_token(request)
        if error:
            return error

        title = request.POST.get("title", "").strip()
        issued_by = request.POST.get("issued_by", "").strip()
        issued_date = request.POST.get("issued_date", "").strip()
        certificate_url = request.POST.get("certificate_url", "").strip()
        image = request.FILES.get("image")

        if not title or not issued_by:
            return JsonResponse({"error": "Title and issued_by are required"}, status=400)

        certificate = Certificate.objects.create(
            user=user,
            title=title,
            issued_by=issued_by,
            issued_date=issued_date if issued_date else None,
            certificate_url=certificate_url if certificate_url else None,
            image=image if image else None,
        )
        return JsonResponse({
            "message": "Certificate added",
            "certificate_id": certificate.id,
            "image_url": request.build_absolute_uri(certificate.image.url) if certificate.image else None,
        }, status=201)

    return JsonResponse({"error": "Method not allowed"}, status=405)


def remove_certificate(request, certificate_id):
    if request.method == "DELETE":
        user, error = get_user_from_token(request)
        if error:
            return error

        try:
            certificate = Certificate.objects.get(id=certificate_id, user=user)
            certificate.delete()
            return JsonResponse({"message": "Certificate removed"})
        except Certificate.DoesNotExist:
            return JsonResponse({"error": "Certificate not found or not yours"}, status=404)

    return JsonResponse({"error": "Method not allowed"}, status=405)


def show_certificates(request, user_id):
    if request.method == "GET":
        try:
            user = User.objects.get(id=user_id)
            certificates = Certificate.objects.filter(user=user)
            data = [
                {
                    "id": c.id,
                    "title": c.title,
                    "issued_by": c.issued_by,
                    "issued_date": c.issued_date,
                    "certificate_url": c.certificate_url,
                    "image_url": request.build_absolute_uri(c.image.url) if c.image else None,
                    "created_at": c.created_at,
                }
                for c in certificates
            ]
            return JsonResponse({"certificates": data})
        except User.DoesNotExist:
            return JsonResponse({"error": "User not found"}, status=404)

    return JsonResponse({"error": "Method not allowed"}, status=405)