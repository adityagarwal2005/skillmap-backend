from django.http import JsonResponse
from django.contrib.auth.hashers import make_password, check_password
from rest_framework_simplejwt.tokens import RefreshToken
from .models import User, StudentProfile
from skills.models import Category, Skill
import math

from django.core.mail import send_mail
from .models import OTPVerification
import random

from django.core.mail import send_mail
from smtplib import SMTPException


import threading
from django.core.mail import send_mail

import resend
import os

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




def send_otp_email(username, email, otp):
    resend.api_key = os.environ.get('RESEND_API_KEY')
    try:
        resend.Emails.send({
            "from": "SkillMap <noreply@doithere.in>",
            "to": [email],
            "subject": "Your SkillMap verification code",
            "text": f"Hi {username},\n\nYour SkillMap verification code is:\n\n{otp}\n\nThis code expires in 10 minutes.\n\n— SkillMap Team"
        })
        print(f"=== OTP EMAIL SENT TO {email} ===")
    except Exception as e:
        print(f"=== RESEND ERROR: {e} ===")

def send_otp(request):
    if request.method == 'POST':
        email    = request.POST.get('email')
        username = request.POST.get('username')

        if User.objects.filter(username=username).exists():
            return JsonResponse({'error': 'Username already taken'}, status=400)

        if User.objects.filter(email=email).exists():
            return JsonResponse({'error': 'Email already registered. Please login.'}, status=400)

        otp = str(random.randint(100000, 999999))

        OTPVerification.objects.filter(email=email).delete()
        OTPVerification.objects.create(email=email, otp=otp)


        import os
        if os.environ.get('DEBUG') == 'True':
            print(f"=== LOCAL OTP FOR {email}: {otp} ===")       

        # Send email in background thread so it doesn't block
        thread = threading.Thread(
            target=send_otp_email,
            args=(username, email, otp)
        )
        thread.daemon = True
        thread.start()

        return JsonResponse({'message': 'OTP sent to your email'})

    return JsonResponse({'error': 'Method not allowed'}, status=405)

def verify_otp_and_register(request):
    if request.method == 'POST':
        username  = request.POST.get('username')
        email     = request.POST.get('email')
        password  = request.POST.get('password')
        otp       = request.POST.get('otp')
        latitude  = request.POST.get('latitude')
        longitude = request.POST.get('longitude')

        try:
            otp_obj = OTPVerification.objects.filter(
                email=email, otp=otp, is_used=False
            ).latest('created_at')
        except OTPVerification.DoesNotExist:
            return JsonResponse({'error': 'Invalid OTP. Please try again.'}, status=400)

        if otp_obj.is_expired():
            return JsonResponse({'error': 'OTP expired. Please request a new one.'}, status=400)

        otp_obj.is_used = True
        otp_obj.save()

        if User.objects.filter(username=username).exists():
            return JsonResponse({'error': 'This username is already taken.'}, status=400)

        user = User.objects.create(
            username=username,
            email=email,
            password=make_password(password),
            latitude=float(latitude) if latitude else None,
            longitude=float(longitude) if longitude else None,
        )

        tokens = get_tokens_for_user(user)
        return JsonResponse({
            'message': f'Welcome to SkillMap, {username}!',
            'user_id': user.id,
            'username': user.username,
            'access':  tokens['access'],
            'refresh': tokens['refresh'],
        }, status=201)


def login(request):
    if request.method == 'POST':
        identifier = request.POST.get('username') or request.POST.get('identifier')
        password   = request.POST.get('password')

        # Try username first, then email
        user = None
        try:
            user = User.objects.get(username=identifier)
        except User.DoesNotExist:
            try:
                user = User.objects.get(email=identifier)
            except User.DoesNotExist:
                return JsonResponse({
                    'error': 'No account found with this username or email.'
                }, status=404)

        if not check_password(password, user.password):
            return JsonResponse({
                'error': 'Incorrect password. Please try again.'
            }, status=401)

        tokens = get_tokens_for_user(user)
        return JsonResponse({
            'message': f'Welcome, {user.username}!',
            'user_id': user.id,
            'username': user.username,
            'access':  tokens['access'],
            'refresh': tokens['refresh'],
        })

    return JsonResponse({'error': 'Method not allowed'}, status=405)

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
                "instagram_url": user.instagram_url,
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
        instagram_url = request.POST.get("instagram_url", "").strip()

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
        if instagram_url:
            user.instagram_url = instagram_url
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
    if request.method == 'GET':
        category_id = request.GET.get('category_id')
        latitude    = request.GET.get('latitude')
        longitude   = request.GET.get('longitude')
        radius_km   = float(request.GET.get('radius', 50))
        skills      = request.GET.get('skills', '').strip()

        if not category_id:
            return JsonResponse({'error': 'Category is required'}, status=400)

        users = User.objects.filter(category_id=category_id)

        # skill filter
        if skills:
            skill_list = [s.strip().lower() for s in skills.split(',')]
            for skill in skill_list:
                users = users.filter(skills__name__icontains=skill)

        results = []
        for u in users:
            # location filter — only apply if both user and searcher have location
            if latitude and longitude and u.latitude and u.longitude:
                distance = get_distance_km(
                    float(latitude), float(longitude),
                    u.latitude, u.longitude
                )
                if distance > radius_km:
                    continue
                dist_display = round(distance, 1)
            else:
                dist_display = None

            results.append({
                'id':       u.id,
                'username': u.username,
                'category': u.category.name if u.category else None,
                'skills':   [s.name for s in u.skills.all()],
                'rating':   u.rating,
                'status':   u.status,
                'distance_km': dist_display,
                'latitude': u.latitude,
                'longitude': u.longitude,
            })

        return JsonResponse({'results': results})

    return JsonResponse({'error': 'Method not allowed'}, status=405)


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



def test_email(request):
    import threading
    import os

    def _send():
        from django.core.mail import send_mail
        try:
            send_mail(
                subject='SkillMap Test',
                message='Test email',
                from_email=None,
                recipient_list=[os.environ.get('EMAIL_HOST_USER')],
                fail_silently=False,
            )
        except Exception as e:
            print(f"Email error: {e}")

    thread = threading.Thread(target=_send)
    thread.daemon = True
    thread.start()

    return JsonResponse({'message': 'Email sending in background - check inbox in 30 seconds'})

def health(request):
    return JsonResponse({'status': 'ok'})


def register(request):
    if request.method == 'POST':
        username  = request.POST.get('username')
        email     = request.POST.get('email')
        password  = request.POST.get('password')
        latitude  = request.POST.get('latitude')
        longitude = request.POST.get('longitude')

        if User.objects.filter(username=username).exists():
            return JsonResponse({'error': 'This username is already taken. Please choose another.'}, status=400)

        if User.objects.filter(email=email).exists():
            return JsonResponse({'error': 'This email is already registered. Please login instead.'}, status=400)

        user = User.objects.create(
            username=username,
            email=email,
            password=make_password(password),
            latitude=float(latitude) if latitude else None,
            longitude=float(longitude) if longitude else None,
        )

        tokens = get_tokens_for_user(user)
        return JsonResponse({
            'message': f'Welcome to SkillMap, {username}!',
            'user_id': user.id,
            'username': user.username,
            'access':  tokens['access'],
            'refresh': tokens['refresh'],
        }, status=201)