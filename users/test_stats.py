"""Founder dashboard stats endpoint: gating + a few representative counts."""
from django.test import override_settings

from social.testing import ApiTestCase, make_user
from work.models import WorkRequest
from portfolio.models import Video


@override_settings(FOUNDER_EMAILS=['boss@test.local'])   # the email make_user('boss') generates
class FounderStatsTests(ApiTestCase):
    def setUp(self):
        self.boss = make_user('boss')
        self.alice = make_user('alice')
        self.bob = make_user('bob')
        WorkRequest.objects.create(
            created_by=self.alice, description='Need a poster',
            payment_amount=500, time_limit_hours=24, status='open')
        Video.objects.create(user=self.bob, url='https://cdn/x.mp4', caption='reel')

    def test_founder_sees_the_numbers(self):
        r = self.get_as(self.boss, '/founder/stats/')
        self.assertEqual(r.status_code, 200)
        d = r.json()
        self.assertEqual(d['users']['total'], 3)        # boss, alice, bob
        self.assertEqual(d['users']['today'], 3)        # all just created
        self.assertEqual(len(d['users']['trend']), 14)
        self.assertEqual(d['users']['trend'][-1]['count'], 3)   # today is the last bucket
        self.assertEqual(d['gigs']['total'], 1)
        self.assertEqual(d['gigs']['active'], 1)
        self.assertEqual(d['videos']['total'], 1)
        self.assertTrue(any(s['username'] == 'bob' for s in d['recent_signups']))

    def test_a_normal_user_is_forbidden(self):
        self.assertEqual(self.get_as(self.alice, '/founder/stats/').status_code, 403)

    def test_anonymous_is_unauthorised(self):
        self.assertEqual(self.client.get('/founder/stats/').status_code, 401)
