"""Feed search used to 500 on every query; these pin the fix."""
from django.test import TestCase


class SearchTests(TestCase):
    def test_a_real_query_returns_results_not_a_500(self):
        for q in ('design', 'web developer'):
            self.assertEqual(self.client.get('/feed/search/', {'q': q}).status_code, 200, q)

    def test_garbage_location_is_a_400(self):
        r = self.client.get('/feed/search/', {'q': 'design', 'radius': 'x', 'latitude': 'y', 'longitude': 'z'})
        self.assertEqual(r.status_code, 400)
