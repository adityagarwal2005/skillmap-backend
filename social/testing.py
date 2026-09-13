"""Shared helpers for the test suites.

Named so Django's test discovery (test*.py) doesn't pick it up. Run the
suites against sqlite so they never touch the real database:

    DJANGO_SETTINGS_MODULE=social.local_test_settings python manage.py test
"""
import datetime

from django.contrib.auth.hashers import make_password
from django.test import TestCase
from django.utils import timezone

from users.models import User
from users.views import get_tokens_for_user


def make_user(username, contact=False, **fields):
    """A user; contact=True adds the verified WhatsApp that posting requires."""
    if contact:
        fields.setdefault('whatsapp', '9876543210')
        fields.setdefault('phone_verified', True)
    return User.objects.create(
        username=username,
        email=f'{username}@test.local',
        password=make_password('Str0ng!Passw0rd'),
        **fields,
    )


def in_hours(hours):
    return timezone.now() + datetime.timedelta(hours=hours)


class ApiTestCase(TestCase):
    def auth(self, user):
        return {'HTTP_AUTHORIZATION': f"Bearer {get_tokens_for_user(user)['access']}"}

    def get_as(self, user, url, data=None):
        return self.client.get(url, data or {}, **self.auth(user))

    def post_as(self, user, url, data=None):
        return self.client.post(url, data or {}, **self.auth(user))
