import os
from pathlib import Path
from datetime import timedelta
from dotenv import load_dotenv
import dj_database_url

# Load .env only in local (safe)
load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

# SECURITY
DEBUG = os.environ.get('DEBUG', 'False') == 'True'

SECRET_KEY = os.environ.get('SECRET_KEY')
if not SECRET_KEY:
    if DEBUG:
        SECRET_KEY = 'dev-secret-key-change-in-prod'
    else:
        # Silently falling back to a well-known string in production would let
        # anyone forge valid JWTs/session data — a misconfigured deploy must
        # fail loudly instead of degrading into a spoofable secret.
        raise RuntimeError(
            'SECRET_KEY environment variable must be set when DEBUG=False.'
        )

ALLOWED_HOSTS = [
    host.strip()
    for host in os.environ.get(
        'ALLOWED_HOSTS',
        'localhost,127.0.0.1,0.0.0.0'
    ).split(',')
    if host.strip()
]

# APPS
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    'cloudinary_storage',
    'cloudinary',
    'corsheaders',
    'rest_framework',
    'rest_framework_simplejwt',

    'users',
    'portfolio',
    'notifications',
    'reviews',
    'skills',
    'feed',
    'collab',
    'work',
]

# MIDDLEWARE
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',

    'corsheaders.middleware.CorsMiddleware',

    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'social.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'social.wsgi.application'

# ✅ FIXED DATABASE CONFIG (IMPORTANT)
DATABASES = {
    'default': dj_database_url.config(
        default=os.environ.get("DATABASE_URL"),
        conn_max_age=600,
        ssl_require=True
    )
}

# PASSWORD VALIDATORS
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# INTERNATIONALIZATION
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Asia/Kolkata'
USE_I18N = True
USE_TZ = True

# STATIC FILES
STATIC_URL = '/static/'
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')

# MEDIA + STATIC storage backends.
# Django 5.1+ (we're on 6.0) ignores the legacy DEFAULT_FILE_STORAGE /
# STATICFILES_STORAGE settings entirely — STORAGES is the only thing that
# takes effect. Without this dict, uploads silently fell back to local disk
# (ephemeral on Render) instead of Cloudinary, saving relative /media/ URLs
# that 404 on the frontend domain.
STORAGES = {
    'default': {
        'BACKEND': 'cloudinary_storage.storage.MediaCloudinaryStorage',
    },
    # CompressedManifestStaticFilesStorage is STRICT: it hard-crashes (500) on
    # any {% static %} reference not found in its manifest. That's exactly
    # what broke /admin/login/ — Django admin's own CSS/JS were never
    # collected (no admin.py was ever registered before, so nobody had ever
    # rendered an admin page here to notice). CompressedStaticFilesStorage is
    # the same whitenoise compression, just without the strict manifest
    # lookup, so a missing/never-collected file degrades gracefully instead
    # of crashing the page.
    'staticfiles': {
        'BACKEND': 'whitenoise.storage.CompressedStaticFilesStorage',
    },
}

# Serve static files straight from each app's static/ directory via Django's
# staticfiles finders, so this works even if `collectstatic` is never run as
# part of deploy (Render's free tier has no shell, and the user's Start
# Command doesn't currently include it).
WHITENOISE_USE_FINDERS = True

CLOUDINARY_STORAGE = {
    'CLOUD_NAME': os.environ.get('CLOUDINARY_CLOUD_NAME'),
    'API_KEY':    os.environ.get('CLOUDINARY_API_KEY'),
    'API_SECRET': os.environ.get('CLOUDINARY_API_SECRET'),
}

MEDIA_URL = '/media/'

# CORS — allow local dev, the production domain, all Vercel deploys, plus any
# origins listed in the CORS_ALLOWED_ORIGINS env var. No longer wide-open.
CORS_ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.environ.get('CORS_ALLOWED_ORIGINS', '').split(',')
    if origin.strip()
]

# Always trust these, regardless of env config, so the live site can't break.
for _origin in [
    'http://localhost:3000',
    'http://127.0.0.1:3000',
    'https://doithere.in',
    'https://www.doithere.in',
]:
    if _origin not in CORS_ALLOWED_ORIGINS:
        CORS_ALLOWED_ORIGINS.append(_origin)

# Any Vercel preview/production deployment (*.vercel.app)
CORS_ALLOWED_ORIGIN_REGEXES = [r"^https://.*\.vercel\.app$"]

# Django needs these to trust the domain for admin/CSRF over HTTPS.
CSRF_TRUSTED_ORIGINS = [
    'https://doithere.in',
    'https://www.doithere.in',
    'https://api.doithere.in',
    'https://skillmap-backend-498t.onrender.com',
]

# JWT
SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(days=1),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=7),
    'AUTH_HEADER_TYPES': ('Bearer',),
}

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ),
}

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'

# ── Production security hardening ──
# Kicks in automatically once DEBUG is False (set DEBUG=False in Render env).
if not DEBUG:
    # Render terminates TLS at its proxy and forwards this header; it also
    # already redirects HTTP->HTTPS at the edge, so we don't set
    # SECURE_SSL_REDIRECT (that can break Render's internal health checks).
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = 31536000          # 1 year
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    X_FRAME_OPTIONS = 'DENY'
EMAIL_HOST = os.environ.get('EMAIL_HOST', 'smtp.gmail.com')
EMAIL_PORT = int(os.environ.get('EMAIL_PORT', 587))
EMAIL_HOST_USER = os.environ.get('EMAIL_HOST_USER')
EMAIL_HOST_PASSWORD = os.environ.get('EMAIL_HOST_PASSWORD')
EMAIL_USE_TLS = True
DEFAULT_FROM_EMAIL = os.environ.get('EMAIL_HOST_USER')

# ── Error alerting ──
# Any unhandled 500 gets emailed here via Django's built-in AdminEmailHandler,
# reusing the SMTP account above (no new service to wire up). Set
# ADMIN_ALERT_EMAIL in Render's env to a different inbox if you don't want
# alerts going to the same address that sends OTP/notification mail;
# otherwise it defaults to EMAIL_HOST_USER.
_admin_alert_email = os.environ.get('ADMIN_ALERT_EMAIL') or EMAIL_HOST_USER
ADMINS = [('SkillMap Admin', _admin_alert_email)] if _admin_alert_email else []
# Gmail (and most SMTP providers) reject mail whose From header doesn't match
# the authenticated account, so this must be EMAIL_HOST_USER, not a made-up
# address — the legacy 'root@localhost' default would silently fail to send.
SERVER_EMAIL = EMAIL_HOST_USER or 'root@localhost'

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'filters': {
        'require_debug_false': {'()': 'django.utils.log.RequireDebugFalse'},
    },
    'handlers': {
        'console': {'class': 'logging.StreamHandler', 'level': 'INFO'},
        'mail_admins': {
            'class': 'django.utils.log.AdminEmailHandler',
            'level': 'ERROR',
            # Only mails in production — DEBUG=True shows the error page directly.
            'filters': ['require_debug_false'],
        },
    },
    'loggers': {
        'django': {'handlers': ['console'], 'level': 'INFO'},
        # Every uncaught exception in a view (including the raw JsonResponse
        # views that don't go through DRF) surfaces here via Django's request
        # handling — this is the one place that catches all of them.
        'django.request': {
            'handlers': ['console', 'mail_admins'],
            'level': 'ERROR',
            'propagate': False,
        },
    },
}
# ── Web Push (VAPID) ──
VAPID_PUBLIC_KEY = os.environ.get('VAPID_PUBLIC_KEY', '')
VAPID_PRIVATE_KEY = os.environ.get('VAPID_PRIVATE_KEY', '')
VAPID_CLAIMS_EMAIL = os.environ.get('VAPID_CLAIMS_EMAIL', 'mailto:admin@doithere.in')
