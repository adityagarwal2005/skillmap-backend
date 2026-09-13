"""Account safety: what a profile reveals, and the signup path."""
import datetime

from skills.utils import get_or_create_skill
from social.testing import ApiTestCase, make_user


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
