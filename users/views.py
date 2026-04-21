from django.http import JsonResponse
from django.contrib.auth.hashers import make_password, check_password
from rest_framework_simplejwt.tokens import RefreshToken
from .models import User, StudentProfile
from skills.models import Category, Skill
import math


def get_distance_km(lat1, lon1, lat2, lon2):
    R = 6371
    d_lat = math.radians(lat2 - lat1)
    d_lon = math.radians(lon2 - lon1)
    a = (math.sin(d_lat / 2) ** 2 +
         math.cos(math.radians(lat1)) *
         math.cos(math.radians(lat2)) *
         math.sin(d_lon / 2) ** 2)
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def get_tokens_for_user(user):
    refresh = RefreshToken()
    refresh['user_id'] = user.id
    refresh['username'] = user.username
    return {
        'refresh': str(refresh),
        'access': str(refresh.access_token),
    }


def get_user_from_token(request):
    auth_header = request.headers.get('Authorization', '')
    if not auth_header.startswith('Bearer '):
        return None, JsonResponse({"error": "Authorization token required"}, status=401)

    token = auth_header.split(' ')[1]
    try:
        from rest_framework_simplejwt.tokens import AccessToken
        decoded = AccessToken(token)
        user_id = decoded['user_id']
        user = User.objects.get(id=user_id)
        return user, None
    except Exception:
        return None, JsonResponse({"error": "Invalid or expired token"}, status=401)


def register(request):
    if request.method == "POST":
        username = request.POST.get("username", "").strip()
        email = request.POST.get("email", "").strip()
        password = request.POST.get("password", "").strip()
        category_id = request.POST.get("category_id", "").strip()
        latitude = request.POST.get("latitude", "").strip()
        longitude = request.POST.get("longitude", "").strip()

        if not username or not email or not password:
            return JsonResponse({"error": "All fields are required"}, status=400)

        if User.objects.filter(username=username).exists():
            return JsonResponse({"error": "Username already taken"}, status=400)

        if User.objects.filter(email=email).exists():
            return JsonResponse({"error": "Email already registered"}, status=400)

        category = None
        if category_id:
            try:
                category = Category.objects.get(id=category_id)
            except Category.DoesNotExist:
                return JsonResponse({"error": "Category not found"}, status=404)

        user = User.objects.create(
            username=username,
            email=email,
            password=make_password(password),
            category=category,
            latitude=float(latitude) if latitude else None,
            longitude=float(longitude) if longitude else None,
        )

        tokens = get_tokens_for_user(user)
        return JsonResponse({
            "message": "User registered successfully",
            "user_id": user.id,
            "access": tokens['access'],
            "refresh": tokens['refresh'],
        }, status=201)

    return JsonResponse({"error": "Method not allowed"}, status=405)


def login(request):
    if request.method == "POST":
        username = request.POST.get("username", "").strip()
        password = request.POST.get("password", "").strip()

        if not username or not password:
            return JsonResponse({"error": "Username and password required"}, status=400)

        try:
            user = User.objects.get(username=username)
            if check_password(password, user.password):
                tokens = get_tokens_for_user(user)
                return JsonResponse({
                    "message": f"Welcome, {user.username}!",
                    "user_id": user.id,
                    "username": user.username,
                    "access": tokens['access'],
                    "refresh": tokens['refresh'],
                })
            return JsonResponse({"error": "Invalid credentials"}, status=401)
        except User.DoesNotExist:
            return JsonResponse({"error": "Invalid credentials"}, status=401)

    return JsonResponse({"error": "Method not allowed"}, status=405)


def refresh_token(request):
    if request.method == "POST":
        refresh_token = request.POST.get("refresh", "").strip()
        if not refresh_token:
            return JsonResponse({"error": "Refresh token is required"}, status=400)

        try:
            refresh = RefreshToken(refresh_token)
            return JsonResponse({"access": str(refresh.access_token)})
        except Exception:
            return JsonResponse({"error": "Invalid or expired refresh token"}, status=401)

    return JsonResponse({"error": "Method not allowed"}, status=405)


def get_user(request, user_id):
    if request.method == "GET":
        try:
            user = User.objects.get(id=user_id)
            return JsonResponse({
                "id": user.id,
                "username": user.username,
                "email": user.email,
                "category": user.category.name if user.category else None,
                "skills": [s.name for s in user.skills.all()],
                "status": user.status,
                "rating": user.rating,
                "latitude": user.latitude,
                "longitude": user.longitude,
                "linkedin_url": user.linkedin_url,
                "github_url": user.github_url,
                "created_at": user.created_at,
            })
        except User.DoesNotExist:
            return JsonResponse({"error": "User not found"}, status=404)

    return JsonResponse({"error": "Method not allowed"}, status=405)


def edit_user(request, user_id):
    if request.method == "POST":
        user, error = get_user_from_token(request)
        if error:
            return error

        if user.id != user_id:
            return JsonResponse({"error": "You can only edit your own profile"}, status=403)

        username = request.POST.get("username", "").strip()
        email = request.POST.get("email", "").strip()
        password = request.POST.get("password", "").strip()
        latitude = request.POST.get("latitude", "").strip()
        longitude = request.POST.get("longitude", "").strip()
        category_id = request.POST.get("category_id", "").strip()
        linkedin_url = request.POST.get("linkedin_url", "").strip()
        github_url = request.POST.get("github_url", "").strip()

        if username:
            user.username = username
        if email:
            user.email = email
        if password:
            user.password = make_password(password)
        if latitude:
            user.latitude = float(latitude)
        if longitude:
            user.longitude = float(longitude)
        if linkedin_url:
            user.linkedin_url = linkedin_url
        if github_url:
            user.github_url = github_url
        if category_id:
            try:
                user.category = Category.objects.get(id=category_id)
            except Category.DoesNotExist:
                return JsonResponse({"error": "Category not found"}, status=404)

        user.save()
        return JsonResponse({"message": "User updated successfully"})

    return JsonResponse({"error": "Method not allowed"}, status=405)


def delete_user(request, user_id):
    if request.method == "DELETE":
        user, error = get_user_from_token(request)
        if error:
            return error

        if user.id != user_id:
            return JsonResponse({"error": "You can only delete your own account"}, status=403)

        user.delete()
        return JsonResponse({"message": "User deleted"})

    return JsonResponse({"error": "Method not allowed"}, status=405)


def update_status(request):
    if request.method == "POST":
        user, error = get_user_from_token(request)
        if error:
            return error

        status = request.POST.get("status", "").strip()
        valid = ['open_to_freelance', 'open_to_work', 'not_available']

        if status not in valid:
            return JsonResponse({
                "error": f"status must be one of: {', '.join(valid)}"
            }, status=400)

        user.status = status
        user.save()
        return JsonResponse({"message": f"Status updated to '{status}'"})

    return JsonResponse({"error": "Method not allowed"}, status=405)


def search_users(request):
    if request.method == "GET":
        category_id = request.GET.get("category_id", "").strip()
        skills = request.GET.get("skills", "").strip()
        radius_km = request.GET.get("radius", "10").strip()
        latitude = request.GET.get("latitude", "").strip()
        longitude = request.GET.get("longitude", "").strip()

        if not category_id:
            return JsonResponse({"error": "category_id is required"}, status=400)

        if not latitude or not longitude:
            return JsonResponse({"error": "latitude and longitude are required"}, status=400)

        try:
            category = Category.objects.get(id=category_id)
        except Category.DoesNotExist:
            return JsonResponse({"error": "Category not found"}, status=404)

        try:
            lat = float(latitude)
            lon = float(longitude)
            radius = float(radius_km)
        except ValueError:
            return JsonResponse({"error": "Invalid location or radius values"}, status=400)

        skill_list = []
        if skills:
            skill_list = [s.strip() for s in skills.split(",")]
            invalid_skills = []
            for skill_name in skill_list:
                if not Skill.objects.filter(name__iexact=skill_name).exists():
                    invalid_skills.append(skill_name)
            if invalid_skills:
                return JsonResponse({
                    "error": f"Invalid skill tags: {', '.join(invalid_skills)}. Use valid tags only."
                }, status=400)

        users = User.objects.filter(
            category=category
        ).select_related("category").prefetch_related("skills")

        if skill_list:
            users = users.filter(skills__name__in=skill_list).distinct()

        results = []
        for user in users:
            if user.latitude is None or user.longitude is None:
                continue
            distance = get_distance_km(lat, lon, user.latitude, user.longitude)
            if distance <= radius:
                results.append((user, round(distance, 2)))

        results.sort(key=lambda x: x[1])

        data = [
            {
                "id": user.id,
                "username": user.username,
                "category": user.category.name if user.category else None,
                "skills": [s.name for s in user.skills.all()],
                "rating": user.rating,
                "status": user.status,
                "distance_km": distance,
            }
            for user, distance in results
        ]

        return JsonResponse({"category": category.name, "results": data, "count": len(data)})

    return JsonResponse({"error": "Method not allowed"}, status=405)


def add_student_profile(request, user_id):
    if request.method == "POST":
        user, error = get_user_from_token(request)
        if error:
            return error

        if user.id != user_id:
            return JsonResponse({"error": "You can only add your own student profile"}, status=403)

        if not user.category or user.category.name.lower() != "student":
            return JsonResponse({"error": "User is not in Student category"}, status=400)

        if StudentProfile.objects.filter(user=user).exists():
            return JsonResponse({"error": "Student profile already exists"}, status=400)

        education_type = request.POST.get("education_type", "").strip().lower()
        if education_type not in ["school", "college"]:
            return JsonResponse({"error": "education_type must be 'school' or 'college'"}, status=400)

        if education_type == "college":
            degree_name = request.POST.get("degree_name", "").strip()
            current_year = request.POST.get("current_year", "").strip()
            if not degree_name or not current_year:
                return JsonResponse({"error": "degree_name and current_year are required"}, status=400)
            StudentProfile.objects.create(
                user=user,
                education_type="college",
                degree_name=degree_name,
                current_year=int(current_year),
            )
        else:
            current_class = request.POST.get("current_class", "").strip()
            if not current_class:
                return JsonResponse({"error": "current_class is required"}, status=400)
            StudentProfile.objects.create(
                user=user,
                education_type="school",
                current_class=int(current_class),
            )

        return JsonResponse({"message": "Student profile created successfully"}, status=201)

    return JsonResponse({"error": "Method not allowed"}, status=405)


def edit_student_profile(request, user_id):
    if request.method == "POST":
        user, error = get_user_from_token(request)
        if error:
            return error

        if user.id != user_id:
            return JsonResponse({"error": "You can only edit your own student profile"}, status=403)

        try:
            profile = StudentProfile.objects.get(user=user)
            degree_name = request.POST.get("degree_name", "").strip()
            current_year = request.POST.get("current_year", "").strip()
            current_class = request.POST.get("current_class", "").strip()

            if degree_name:
                profile.degree_name = degree_name
            if current_year:
                profile.current_year = int(current_year)
            if current_class:
                profile.current_class = int(current_class)

            profile.save()
            return JsonResponse({"message": "Student profile updated"})
        except StudentProfile.DoesNotExist:
            return JsonResponse({"error": "Student profile not found"}, status=404)

    return JsonResponse({"error": "Method not allowed"}, status=405)


def get_student_profile(request, user_id):
    if request.method == "GET":
        try:
            user = User.objects.get(id=user_id)
            profile = StudentProfile.objects.get(user=user)
            return JsonResponse({
                "username": user.username,
                "education_type": profile.education_type,
                "degree_name": profile.degree_name,
                "current_year": profile.current_year,
                "current_class": profile.current_class,
                "skills": [s.name for s in user.skills.all()],
            })
        except User.DoesNotExist:
            return JsonResponse({"error": "User not found"}, status=404)
        except StudentProfile.DoesNotExist:
            return JsonResponse({"error": "Student profile not found"}, status=404)

    return JsonResponse({"error": "Method not allowed"}, status=405)