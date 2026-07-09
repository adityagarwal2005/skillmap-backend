from django.http import JsonResponse
from django.contrib.auth.hashers import make_password, check_password
from django.core.mail import send_mail
from rest_framework_simplejwt.tokens import RefreshToken
from smtplib import SMTPException
from .models import User, StudentProfile, OTPVerification, Block, Report, SkillEndorsement
from skills.models import Category, Skill
import math
import random
import threading
import resend
import os
import logging

logger = logging.getLogger(__name__)

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




def block_user(request, user_id):
    """Block another user: hides their posts from your feed and stops messaging."""
    if request.method != "POST":
        return JsonResponse({"error": "Method not allowed"}, status=405)

    user, error = get_user_from_token(request)
    if error:
        return error

    if user.id == user_id:
        return JsonResponse({"error": "You can't block yourself"}, status=400)

    try:
        target = User.objects.get(id=user_id)
    except User.DoesNotExist:
        return JsonResponse({"error": "User not found"}, status=404)

    Block.objects.get_or_create(blocker=user, blocked=target)
    return JsonResponse({"message": f"Blocked {target.username}"})


def unblock_user(request, user_id):
    if request.method != "POST":
        return JsonResponse({"error": "Method not allowed"}, status=405)

    user, error = get_user_from_token(request)
    if error:
        return error

    Block.objects.filter(blocker=user, blocked_id=user_id).delete()
    return JsonResponse({"message": "Unblocked"})


def get_blocked_users(request):
    if request.method != "GET":
        return JsonResponse({"error": "Method not allowed"}, status=405)

    user, error = get_user_from_token(request)
    if error:
        return error

    blocks = Block.objects.filter(blocker=user).select_related('blocked')
    data = [
        {"id": b.blocked.id, "username": b.blocked.username, "blocked_at": b.created_at}
        for b in blocks
    ]
    return JsonResponse({"blocked_users": data, "count": len(data)})


def report_content(request):
    """Report a user or a post. report_type: 'user' or 'post'; target_id; reason; details (optional)."""
    if request.method != "POST":
        return JsonResponse({"error": "Method not allowed"}, status=405)

    user, error = get_user_from_token(request)
    if error:
        return error

    report_type = request.POST.get("report_type", "").strip()
    target_id = request.POST.get("target_id", "").strip()
    reason = request.POST.get("reason", "").strip()
    details = request.POST.get("details", "").strip()

    valid_reasons = [c[0] for c in Report.REASON_CHOICES]
    if report_type not in ("user", "post"):
        return JsonResponse({"error": "report_type must be 'user' or 'post'"}, status=400)
    if reason not in valid_reasons:
        return JsonResponse({"error": f"reason must be one of: {', '.join(valid_reasons)}"}, status=400)
    if not target_id:
        return JsonResponse({"error": "target_id is required"}, status=400)

    report = Report(reporter=user, report_type=report_type, reason=reason, details=details)

    if report_type == "user":
        try:
            reported_user = User.objects.get(id=target_id)
        except User.DoesNotExist:
            return JsonResponse({"error": "User not found"}, status=404)
        if reported_user.id == user.id:
            return JsonResponse({"error": "You can't report yourself"}, status=400)
        report.reported_user = reported_user
    else:
        from portfolio.models import PortfolioItem
        try:
            report.reported_post = PortfolioItem.objects.get(id=target_id)
        except PortfolioItem.DoesNotExist:
            return JsonResponse({"error": "Post not found"}, status=404)

    report.save()
    return JsonResponse({"message": "Report submitted. Thanks for helping keep SkillMap safe."})


def send_otp_email(username, email, otp):
    resend.api_key = os.environ.get('RESEND_API_KEY')
    try:
        resend.Emails.send({
            "from": "SkillMap <noreply@doithere.in>",
            "to": [email],
            "subject": "Your SkillMap verification code",
            "text": f"Hi {username},\n\nYour SkillMap verification code is:\n\n{otp}\n\nThis code expires in 10 minutes.\n\n— SkillMap Team"
        })
        logger.info("OTP email sent to %s", email)
    except Exception as e:
        logger.error("Resend error sending OTP to %s: %s", email, e)

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


        if os.environ.get('DEBUG') == 'True':
            logger.info("Local OTP for %s: %s", email, otp)

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


def change_password(request, user_id):
    """Change password after verifying the current one."""
    if request.method == "POST":
        user, error = get_user_from_token(request)
        if error:
            return error
        if user.id != user_id:
            return JsonResponse({"error": "You can only change your own password"}, status=403)

        current = request.POST.get("current_password", "")
        new = request.POST.get("new_password", "")

        if not new:
            return JsonResponse({"error": "New password is required"}, status=400)
        if len(new) < 6:
            return JsonResponse({"error": "New password must be at least 6 characters"}, status=400)
        if not check_password(current, user.password):
            return JsonResponse({"error": "Current password is incorrect"}, status=400)

        user.password = make_password(new)
        user.save()
        return JsonResponse({"message": "Password updated"})

    return JsonResponse({"error": "Method not allowed"}, status=405)


def send_login_otp(request):
    """Send a one-time login code to an EXISTING account's email."""
    if request.method == 'POST':
        email = request.POST.get('email', '').strip()
        if not email:
            return JsonResponse({'error': 'Email is required'}, status=400)

        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            return JsonResponse(
                {'error': 'No account found with this email. Please register.'},
                status=404,
            )

        otp = str(random.randint(100000, 999999))
        OTPVerification.objects.filter(email=email).delete()
        OTPVerification.objects.create(email=email, otp=otp)

        if os.environ.get('DEBUG') == 'True':
            logger.info("Login OTP for %s: %s", email, otp)

        thread = threading.Thread(
            target=send_otp_email, args=(user.username, email, otp)
        )
        thread.daemon = True
        thread.start()

        return JsonResponse({'message': 'Login code sent to your email'})

    return JsonResponse({'error': 'Method not allowed'}, status=405)


def verify_login_otp(request):
    """Verify a login code and sign the existing user in (no account created)."""
    if request.method == 'POST':
        email = request.POST.get('email', '').strip()
        otp   = request.POST.get('otp', '').strip()

        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            return JsonResponse({'error': 'No account found with this email.'}, status=404)

        try:
            otp_obj = OTPVerification.objects.filter(
                email=email, otp=otp, is_used=False
            ).latest('created_at')
        except OTPVerification.DoesNotExist:
            return JsonResponse({'error': 'Invalid code. Please try again.'}, status=400)

        if otp_obj.is_expired():
            return JsonResponse({'error': 'Code expired. Please request a new one.'}, status=400)

        otp_obj.is_used = True
        otp_obj.save()

        tokens = get_tokens_for_user(user)
        return JsonResponse({
            'message': f'Welcome back, {user.username}!',
            'user_id': user.id,
            'username': user.username,
            'access':  tokens['access'],
            'refresh': tokens['refresh'],
        })

    return JsonResponse({'error': 'Method not allowed'}, status=405)


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
        from django.db.models import F, Count
        try:
            user = User.objects.get(id=user_id)

            # Count a profile view when a *different* logged-in user opens it.
            viewer, _ = get_user_from_token(request)
            if viewer and viewer.id != user.id:
                User.objects.filter(id=user.id).update(profile_views=F('profile_views') + 1)
                user.profile_views += 1

            # Endorsement counts per skill + whether the viewer endorsed each.
            counts = {
                row['skill']: row['n']
                for row in SkillEndorsement.objects.filter(user=user)
                .values('skill').annotate(n=Count('id'))
            }
            my_endorsements = set()
            if viewer and viewer.id != user.id:
                my_endorsements = set(
                    SkillEndorsement.objects.filter(user=user, endorser=viewer)
                    .values_list('skill', flat=True)
                )
            skills = [{
                'name': s.name,
                'endorsements': counts.get(s.name, 0),
                'endorsed_by_me': s.name in my_endorsements,
            } for s in user.skills.all()]

            return JsonResponse({
                "id": user.id,
                "username": user.username,
                "email": user.email,
                "category": user.category.name if user.category else None,
                "skills": [s['name'] for s in skills],       # back-compat: list of names
                "skills_detail": skills,                      # names + endorsement counts
                "status": user.status,
                "rating": user.rating,
                "profile_views": user.profile_views,
                "latitude": user.latitude,
                "longitude": user.longitude,
                "linkedin_url": user.linkedin_url,
                "github_url": user.github_url,
                "instagram_url": user.instagram_url,
                "dob": user.dob,
                "headline": user.headline,
                "bio": user.bio,
                "profile_image": request.build_absolute_uri(user.profile_image.url) if user.profile_image else None,
                "created_at": user.created_at,
            })
        except User.DoesNotExist:
            return JsonResponse({"error": "User not found"}, status=404)

    return JsonResponse({"error": "Method not allowed"}, status=405)


def endorse_skill(request, user_id):
    """Toggle the current user's endorsement of one of `user_id`'s skills."""
    if request.method != "POST":
        return JsonResponse({"error": "Method not allowed"}, status=405)

    endorser, error = get_user_from_token(request)
    if error:
        return error
    if endorser.id == user_id:
        return JsonResponse({"error": "You can't endorse your own skills"}, status=400)

    try:
        target = User.objects.get(id=user_id)
    except User.DoesNotExist:
        return JsonResponse({"error": "User not found"}, status=404)

    skill = request.POST.get("skill", "").strip()
    if not skill:
        return JsonResponse({"error": "Skill is required"}, status=400)

    existing = SkillEndorsement.objects.filter(user=target, endorser=endorser, skill=skill).first()
    if existing:
        existing.delete()
        endorsed = False
    else:
        SkillEndorsement.objects.create(user=target, endorser=endorser, skill=skill)
        endorsed = True

    from notifications.utils import notify
    if endorsed:
        notify(target, 'reaction', f"{endorser.username} endorsed your {skill} skill", actor=endorser)

    count = SkillEndorsement.objects.filter(user=target, skill=skill).count()
    return JsonResponse({"endorsed": endorsed, "count": count})


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
        dob = request.POST.get("dob", "").strip()

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
        if dob:
            user.dob = dob
        # headline/bio: set whenever the field is present (allows clearing them)
        headline = request.POST.get("headline", None)
        if headline is not None:
            user.headline = headline.strip()[:120]
        bio = request.POST.get("bio", None)
        if bio is not None:
            user.bio = bio.strip()
        profile_image = request.FILES.get("profile_image")
        if profile_image:
            user.profile_image = profile_image
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
        from django.db.models import Q

        category_id = request.GET.get('category_id')
        latitude    = request.GET.get('latitude')
        longitude   = request.GET.get('longitude')
        radius_km   = float(request.GET.get('radius', 50))
        skills      = request.GET.get('skills', '').strip()
        query       = request.GET.get('q', '').strip()

        # A search needs at least one narrowing filter so we never dump the
        # whole user table. Category, a free-text query, or skills all qualify.
        if not (category_id or query or skills):
            return JsonResponse({'error': 'Enter a search term or pick a category'}, status=400)

        users = User.objects.all()

        if category_id:
            users = users.filter(category_id=category_id)

        # free-text search across name, category, and skills
        if query:
            users = users.filter(
                Q(username__icontains=query) |
                Q(category__name__icontains=query) |
                Q(skills__name__icontains=query)
            )

        # explicit skill-chip filter
        if skills:
            skill_list = [s.strip().lower() for s in skills.split(',')]
            for skill in skill_list:
                users = users.filter(skills__name__icontains=skill)

        users = users.distinct()

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
                'headline': u.headline,
                'profile_image': request.build_absolute_uri(u.profile_image.url) if u.profile_image else None,
                'skills':   [s.name for s in u.skills.all()],
                'rating':   u.rating,
                'status':   u.status,
                'distance_km': dist_display,
                'latitude': u.latitude,
                'longitude': u.longitude,
            })

        total = len(results)
        try:
            limit = max(1, min(int(request.GET.get('limit', 20)), 50))
        except (TypeError, ValueError):
            limit = 20
        try:
            offset = max(0, int(request.GET.get('offset', 0)))
        except (TypeError, ValueError):
            offset = 0
        page = results[offset:offset + limit]

        return JsonResponse({'results': page, 'count': total, 'has_more': offset + limit < total})

    return JsonResponse({'error': 'Method not allowed'}, status=405)


def discover_users(request):
    """A few people to surface on the feed so a fresh install never looks empty.
    Newest members first, excluding yourself and anyone blocked either way."""
    if request.method != 'GET':
        return JsonResponse({'error': 'Method not allowed'}, status=405)

    me, _ = get_user_from_token(request)  # optional — page is authed anyway

    qs = User.objects.all().order_by('-created_at')
    if me:
        qs = qs.exclude(id=me.id)
        blocked = set(Block.objects.filter(blocker=me).values_list('blocked_id', flat=True))
        blocked_by = set(Block.objects.filter(blocked=me).values_list('blocker_id', flat=True))
        exclude_ids = blocked | blocked_by
        if exclude_ids:
            qs = qs.exclude(id__in=exclude_ids)

    try:
        limit = max(1, min(int(request.GET.get('limit', 12)), 30))
    except (TypeError, ValueError):
        limit = 12

    results = [{
        'id': u.id,
        'username': u.username,
        'category': u.category.name if u.category else None,
        'headline': u.headline,
        'profile_image': request.build_absolute_uri(u.profile_image.url) if u.profile_image else None,
        'skills': [s.name for s in u.skills.all()][:4],
        'status': u.status,
    } for u in qs[:limit]]

    return JsonResponse({'results': results})


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
            logger.error("Email error: %s", e)

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