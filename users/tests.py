"""Account safety: what a profile reveals, and the signup path."""
import datetime

from django.test import RequestFactory
from django.utils import timezone

from users import views as users_views

from skills.utils import get_or_create_skill
from social.testing import ApiTestCase, make_user
from users.models import OTPVerification, PhoneOTPVerification, User


class ProfilePrivacyTests(ApiTestCase):
    def setUp(self):
        self.owner = make_user('owner', latitude=30.73, longitude=76.77, dob=datetime.date(2000, 1, 1))

    def test_strangers_do_not_see_email_location_or_birthday(self):
        profile = self.client.get(f'/users/{self.owner.id}/').json()
        self.assertEqual(profile['username'], 'owner')
        for private in ('email', 'latitude', 'longitude', 'dob'):
            self.assertIsNone(profile[private], private)

    def test_logged_in_strangers_do_not_either(self):
        profile = self.get_as(make_user('other'), f'/users/{self.owner.id}/').json()
        self.assertIsNone(profile['latitude'])
        self.assertIsNone(profile['email'])

    def test_owner_still_sees_their_own_details(self):
        profile = self.get_as(self.owner, f'/users/{self.owner.id}/').json()
        self.assertEqual(profile['email'], 'owner@test.local')
        self.assertEqual(profile['latitude'], 30.73)


class SignupTests(ApiTestCase):
    def test_the_otp_bypass_route_is_gone(self):
        r = self.client.post('/users/register/', {
            'username': 'sneaky', 'email': 'sneaky@test.local', 'password': 'Str0ng!Passw0rd'})
        self.assertEqual(r.status_code, 404)

    def test_verify_register_rejects_get_cleanly(self):
        self.assertEqual(self.client.get('/users/verify-register/').status_code, 405)

    def test_verify_register_requires_every_field(self):
        self.assertEqual(self.client.post('/users/verify-register/', {}).status_code, 400)

    # is_expired() called timezone.now() in a module that had stopped
    # importing timezone, so every code check raised NameError and the last
    # step of email signup was a 500. These cover both sides of that check.
    def register(self, otp='552066', **overrides):
        data = {'username': 'ashish', 'email': 'ashish@test.local',
                'password': 'Str0ng!Passw0rd', 'otp': otp, **overrides}
        return self.client.post('/users/verify-register/', data)

    def test_a_valid_code_actually_creates_the_account(self):
        OTPVerification.objects.create(email='ashish@test.local', otp='552066')
        r = self.register()
        self.assertIn(r.status_code, (200, 201), r.content)
        self.assertTrue(User.objects.filter(username='ashish').exists())

    def test_an_expired_code_is_refused_not_a_500(self):
        otp = OTPVerification.objects.create(email='ashish@test.local', otp='552066')
        # created_at is auto_now_add, so age it after the fact.
        OTPVerification.objects.filter(pk=otp.pk).update(
            created_at=timezone.now() - datetime.timedelta(minutes=11))
        r = self.register()
        self.assertEqual(r.status_code, 400, r.content)
        self.assertIn('expired', r.json()['error'].lower())
        self.assertFalse(User.objects.filter(username='ashish').exists())

    def test_an_expired_phone_code_is_refused_not_a_500(self):
        user = make_user('phoner')
        otp = PhoneOTPVerification.objects.create(phone='9876543210', otp='121212')
        PhoneOTPVerification.objects.filter(pk=otp.pk).update(
            created_at=timezone.now() - datetime.timedelta(minutes=11))
        r = self.post_as(user, '/users/phone/verify-otp/',
                         {'phone': '9876543210', 'otp': '121212'})
        self.assertEqual(r.status_code, 400, r.content)


class ErrorReportPrivacyTests(ApiTestCase):
    """Django emails ADMINS a full traceback on a 500, including the POST
    body — which meant a real signup mailed out the password someone had
    just typed. Marking the view's parameters replaces them with ********."""

    def sensitive_for(self, view, path, data):
        request = RequestFactory().post(path, data)
        view(request)
        return getattr(request, 'sensitive_post_parameters', ())

    def test_signup_hides_the_password_and_code(self):
        marked = self.sensitive_for(
            users_views.verify_otp_and_register, '/users/verify-register/',
            {'username': 'x', 'email': 'x@test.local', 'password': 'p', 'otp': '1'})
        self.assertIn('password', marked)
        self.assertIn('otp', marked)

    def test_login_hides_the_password(self):
        marked = self.sensitive_for(
            users_views.login, '/users/login/', {'username': 'x', 'password': 'p'})
        self.assertIn('password', marked)


class EndorsementTests(ApiTestCase):
    def setUp(self):
        self.target = make_user('target')
        self.fan = make_user('fan')
        self.target.skills.add(get_or_create_skill('Python'))

    def endorse(self, skill, user=None, target=None):
        return self.post_as(user or self.fan, f'/users/{(target or self.target).id}/endorse/', {'skill': skill})

    def test_endorsing_a_listed_skill_works_and_toggles(self):
        self.assertTrue(self.endorse('Python').json()['endorsed'])
        self.assertFalse(self.endorse('Python').json()['endorsed'])

    def test_unlisted_skills_cannot_be_endorsed(self):
        self.assertEqual(self.endorse('Underwater basket weaving').status_code, 400)

    def test_no_self_endorsement(self):
        self.assertEqual(self.endorse('Python', user=self.target).status_code, 400)
