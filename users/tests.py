"""Account safety: what a profile reveals, and the signup path."""
import datetime
from unittest import mock

from django.test import RequestFactory
from django.utils import timezone

from users import views as users_views

from skills.utils import get_or_create_skill
from social.testing import ApiTestCase, make_user
from users.models import OTPVerification, PhoneOTPVerification, SavedAddress, User


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


class SeoProfileListTests(ApiTestCase):
    """The sitemap feeds on this, so an empty profile must never reach it —
    a sitemap full of thin, near-identical pages costs a domain more than
    the extra URLs are worth."""

    def get(self):
        return self.client.get('/seo/profiles/')

    def test_profile_with_a_headline_is_listed(self):
        make_user('has_headline', headline='Backend engineer')
        names = [r['username'] for r in self.get().json()['results']]
        self.assertIn('has_headline', names)

    def test_profile_with_only_a_skill_is_listed(self):
        u = make_user('has_skill')
        u.skills.add(get_or_create_skill('Python'))
        names = [r['username'] for r in self.get().json()['results']]
        self.assertIn('has_skill', names)

    def test_empty_profile_is_left_out(self):
        make_user('blank_slate')
        names = [r['username'] for r in self.get().json()['results']]
        self.assertNotIn('blank_slate', names)

    def test_whitespace_only_headline_does_not_count_as_content(self):
        make_user('spacey', headline='   ', bio='  ')
        names = [r['username'] for r in self.get().json()['results']]
        self.assertNotIn('spacey', names)

    def test_readable_without_a_token(self):
        make_user('anon_visible', bio='Real bio here')
        res = self.get()
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()['count'], len(res.json()['results']))


class SavedAddressTests(ApiTestCase):
    """Switching the feed between saved places (see users.models.SavedAddress)."""

    def setUp(self):
        self.user = make_user('nomad')
        self.home = {'label': 'Home', 'latitude': '30.73', 'longitude': '76.77',
                     'address': 'Sector 34, Chandigarh'}

    def test_saving_and_listing_a_place(self):
        r = self.post_as(self.user, '/users/addresses/', self.home)
        self.assertEqual(r.status_code, 201)
        saved = self.get_as(self.user, '/users/addresses/').json()['addresses']
        self.assertEqual([a['label'] for a in saved], ['Home'])
        self.assertEqual(saved[0]['latitude'], 30.73)

    def test_anonymous_callers_get_nothing(self):
        self.assertEqual(self.client.get('/users/addresses/').status_code, 401)

    def test_a_place_is_private_to_its_owner(self):
        self.post_as(self.user, '/users/addresses/', self.home)
        other = self.get_as(make_user('stranger'), '/users/addresses/').json()
        self.assertEqual(other['addresses'], [])

    def test_impossible_coordinates_are_refused(self):
        r = self.post_as(self.user, '/users/addresses/',
                         {**self.home, 'latitude': '999'})
        self.assertEqual(r.status_code, 400)

    def test_an_unnamed_place_is_refused(self):
        r = self.post_as(self.user, '/users/addresses/', {**self.home, 'label': '  '})
        self.assertEqual(r.status_code, 400)

    def test_reusing_a_name_moves_that_place_instead_of_erroring(self):
        """Moving flats is the common case; unique_together would otherwise
        surface as a 500."""
        self.post_as(self.user, '/users/addresses/', self.home)
        r = self.post_as(self.user, '/users/addresses/',
                         {**self.home, 'latitude': '28.61', 'longitude': '77.21'})
        self.assertEqual(r.status_code, 200)
        saved = self.get_as(self.user, '/users/addresses/').json()['addresses']
        self.assertEqual(len(saved), 1)
        self.assertEqual(saved[0]['latitude'], 28.61)

    def test_the_cap_holds(self):
        for i in range(SavedAddress.MAX_PER_USER):
            self.assertEqual(
                self.post_as(self.user, '/users/addresses/',
                             {**self.home, 'label': f'Place {i}'}).status_code, 201)
        r = self.post_as(self.user, '/users/addresses/', {**self.home, 'label': 'One more'})
        self.assertEqual(r.status_code, 400)

    def test_removing_a_place(self):
        made = self.post_as(self.user, '/users/addresses/', self.home).json()['address']
        r = self.client.delete(f"/users/addresses/{made['id']}/delete/", **self.auth(self.user))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.get_as(self.user, '/users/addresses/').json()['addresses'], [])

    def test_you_cannot_remove_someone_else_s_place(self):
        made = self.post_as(self.user, '/users/addresses/', self.home).json()['address']
        r = self.client.delete(f"/users/addresses/{made['id']}/delete/",
                               **self.auth(make_user('stranger')))
        self.assertEqual(r.status_code, 404)
        self.assertEqual(len(self.get_as(self.user, '/users/addresses/').json()['addresses']), 1)


class AvailabilityStatusGoneTests(ApiTestCase):
    """The self-declared "Open to work" flag was removed — see migration
    users/0016. A stale profile field cannot be trusted, and its default
    ('not_available') silently told every visitor the person did not want
    work."""

    def test_the_update_endpoint_is_gone(self):
        user = make_user('someone')
        r = self.post_as(user, '/users/status/update/', {'status': 'open_to_work'})
        self.assertEqual(r.status_code, 404)

    def test_a_profile_no_longer_carries_a_status(self):
        user = make_user('someone')
        self.assertNotIn('status', self.get_as(user, f'/users/{user.id}/').json())

    def test_a_proposal_no_longer_depends_on_a_flag(self):
        """This gate made proposals impossible to send to anyone who had never
        opened Settings."""
        sender = make_user('sender', contact=True)
        receiver = make_user('receiver')
        r = self.post_as(sender, f'/work/proposals/send/{receiver.id}/',
                         {'description': 'Shoot on Sunday', 'payment_per_day': '2000'})
        self.assertEqual(r.status_code, 201)


class GeocodeSearchTests(ApiTestCase):
    """Typed-address lookup, which is what lets someone save a place they are
    not currently standing in."""

    def setUp(self):
        self.user = make_user('nomad')
        from django.core.cache import cache
        cache.clear()

    def test_it_needs_a_login(self):
        self.assertEqual(self.client.get('/users/geocode/', {'q': 'chandigarh'}).status_code, 401)

    def test_a_short_query_asks_nobody(self):
        with mock.patch('users.views.requests.get') as get:
            r = self.get_as(self.user, '/users/geocode/', {'q': 'ch'})
        self.assertEqual(r.json()['results'], [])
        get.assert_not_called()

    def test_results_are_flattened_to_what_a_saved_place_needs(self):
        payload = [{'lat': '30.7333', 'lon': '76.7794',
                    'display_name': 'Sector 34, Chandigarh, 160022, India'}]
        with mock.patch('users.views.requests.get') as get:
            get.return_value = mock.Mock(status_code=200, json=lambda: payload)
            results = self.get_as(self.user, '/users/geocode/', {'q': 'sector 34'}).json()['results']
        self.assertEqual(results, [{
            'label': 'Sector 34',
            'address': 'Sector 34, Chandigarh, 160022, India',
            'latitude': 30.7333,
            'longitude': 76.7794,
        }])

    def test_unusable_coordinates_are_dropped_not_served(self):
        payload = [{'lat': 'north-ish', 'lon': '76.7794', 'display_name': 'Nowhere'}]
        with mock.patch('users.views.requests.get') as get:
            get.return_value = mock.Mock(status_code=200, json=lambda: payload)
            results = self.get_as(self.user, '/users/geocode/', {'q': 'nowhere'}).json()['results']
        self.assertEqual(results, [])

    def test_a_repeat_query_is_served_from_cache(self):
        payload = [{'lat': '30.73', 'lon': '76.77', 'display_name': 'Chandigarh, India'}]
        with mock.patch('users.views.requests.get') as get:
            get.return_value = mock.Mock(status_code=200, json=lambda: payload)
            self.get_as(self.user, '/users/geocode/', {'q': 'chandigarh'})
            self.get_as(self.user, '/users/geocode/', {'q': 'Chandigarh'})
            self.assertEqual(get.call_count, 1)

    def test_a_dead_third_party_degrades_instead_of_500ing(self):
        with mock.patch('users.views.requests.get', side_effect=OSError('down')):
            r = self.get_as(self.user, '/users/geocode/', {'q': 'chandigarh'})
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()['unavailable'])
        self.assertEqual(r.json()['results'], [])
