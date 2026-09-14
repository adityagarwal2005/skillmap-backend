"""The feed shows only what's near the viewer and still inside its window."""
from unittest import mock

from django.test import TestCase

from collab.models import CollabPost
from social.testing import ApiTestCase, in_hours, make_user
from work.models import WorkRequest

# A viewer in Chandigarh, and points about 1 km, 8 km and 1,700 km away.
HOME = (30.7412, 76.7788)
ONE_KM = (30.7502, 76.7788)
EIGHT_KM = (30.8131, 76.7788)
BANGALORE = (12.9716, 77.5946)


def gig(poster, where=(None, None), **fields):
    fields.setdefault('status', 'open')
    fields.setdefault('expires_at', in_hours(12))
    return WorkRequest.objects.create(
        created_by=poster, description='Shoot a reel', payment_amount=500, time_limit_hours=24,
        latitude=where[0], longitude=where[1], **fields)


def collab(host, where=(None, None), **fields):
    fields.setdefault('status', 'open')
    fields.setdefault('expires_at', in_hours(12))
    return CollabPost.objects.create(
        user=host, title='Hackathon team', description='Need a dev', collab_type='experience',
        latitude=where[0], longitude=where[1], **fields)


class FeedTestCase(ApiTestCase):
    def setUp(self):
        self.viewer = make_user('viewer', latitude=HOME[0], longitude=HOME[1])
        self.poster = make_user('poster')

    def feed(self, user=None, **params):
        r = self.get_as(user or self.viewer, '/feed/', params)
        self.assertEqual(r.status_code, 200)
        return r.json()

    def ids(self, **params):
        return {(it['kind'], it['id']) for it in self.feed(**params)['feed']}


class FeedRangeTests(FeedTestCase):
    def test_only_listings_inside_the_radius_show(self):
        near, mid = gig(self.poster, ONE_KM), gig(self.poster, EIGHT_KM)
        gig(self.poster, BANGALORE)
        self.assertEqual(self.ids(radius=5), {('freelance', near.id)})
        self.assertEqual(self.ids(radius=10), {('freelance', near.id), ('freelance', mid.id)})
        self.assertEqual(self.ids(radius=50), {('freelance', near.id), ('freelance', mid.id)})

    def test_every_item_carries_its_distance(self):
        gig(self.poster, ONE_KM)
        [item] = self.feed(radius=5)['feed']
        self.assertAlmostEqual(item['distance_km'], 1.0, delta=0.1)

    def test_a_listing_without_a_pin_is_placed_at_its_poster(self):
        near = collab(make_user('nearby', latitude=ONE_KM[0], longitude=ONE_KM[1]))
        collab(make_user('faraway', latitude=BANGALORE[0], longitude=BANGALORE[1]))
        self.assertEqual(self.ids(radius=5), {('collab', near.id)})

    def test_a_listing_with_no_location_at_all_is_left_out(self):
        gig(self.poster)
        collab(self.poster)
        self.assertEqual(self.ids(radius=50), set())

    def test_device_location_overrides_the_profile(self):
        there = gig(self.poster, BANGALORE)
        gig(self.poster, ONE_KM)
        self.assertEqual(self.ids(radius=5, lat=BANGALORE[0], lon=BANGALORE[1]), {('freelance', there.id)})

    def test_garbage_parameters_fall_back_to_defaults(self):
        near = gig(self.poster, ONE_KM)
        gig(self.poster, EIGHT_KM)
        payload = self.feed(radius='abc', lat='x', lon='999')
        self.assertEqual(payload['radius_km'], 5.0)
        self.assertEqual({it['id'] for it in payload['feed']}, {near.id})

    def test_no_location_anywhere_asks_for_one(self):
        gig(self.poster, ONE_KM)
        payload = self.feed(user=make_user('stranger'))
        self.assertTrue(payload['location_required'])
        self.assertEqual(payload['feed'], [])

    def test_nearby_posts_survive_the_candidate_cap(self):
        near = gig(self.poster, ONE_KM)
        for _ in range(3):
            gig(self.poster, BANGALORE)   # newer, but nowhere near
        with mock.patch('feed.views.FEED_CANDIDATE_CAP', 2):
            self.assertEqual(self.ids(radius=5), {('freelance', near.id)})


class FeedWindowTests(FeedTestCase):
    def test_expired_listings_are_gone(self):
        live = gig(self.poster, ONE_KM)
        gig(self.poster, ONE_KM, expires_at=in_hours(-1))
        collab(self.poster, ONE_KM, expires_at=in_hours(-1))
        self.assertEqual(self.ids(radius=5), {('freelance', live.id)})

    def test_a_listing_with_no_window_is_left_out(self):
        gig(self.poster, ONE_KM, expires_at=None)
        collab(self.poster, ONE_KM, expires_at=None)
        self.assertEqual(self.ids(radius=5), set())

    def test_closed_and_own_listings_are_left_out(self):
        gig(self.poster, ONE_KM, status='closed')
        gig(self.viewer, ONE_KM)
        collab(self.viewer, ONE_KM)
        self.assertEqual(self.ids(radius=5), set())

    def test_every_item_says_when_it_closes(self):
        gig(self.poster, ONE_KM)
        [item] = self.feed(radius=5)['feed']
        self.assertIsNotNone(item['expires_at'])


class SearchTests(TestCase):
    """Feed search used to 500 on every query; these pin the fix."""

    def test_a_real_query_returns_results_not_a_500(self):
        for q in ('design', 'web developer'):
            self.assertEqual(self.client.get('/feed/search/', {'q': q}).status_code, 200, q)

    def test_garbage_location_is_a_400(self):
        r = self.client.get('/feed/search/', {'q': 'design', 'radius': 'x', 'latitude': 'y', 'longitude': 'z'})
        self.assertEqual(r.status_code, 400)
