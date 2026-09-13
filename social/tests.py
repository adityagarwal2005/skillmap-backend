from django.test import SimpleTestCase

from social.validators import MAX_VISIBILITY_HOURS, parse_float, parse_lat, parse_lon


class ValidatorTests(SimpleTestCase):
    def test_coordinates_parse_or_come_back_empty(self):
        self.assertEqual(parse_lat('30.73'), 30.73)
        self.assertEqual(parse_lon('-122.4'), -122.4)
        for bad in ('', None, 'abc', 'NaN', '1e999'):
            self.assertIsNone(parse_lat(bad), bad)

    def test_impossible_coordinates_are_rejected(self):
        self.assertIsNone(parse_lat('91'))
        self.assertIsNone(parse_lon('181'))

    def test_floats_fall_back_and_clamp(self):
        self.assertEqual(parse_float('abc', 50), 50)
        self.assertEqual(parse_float('-5', 50, minimum=0), 0)
        self.assertEqual(parse_float('900', 50, maximum=100), 100)

    def test_visibility_cap(self):
        self.assertEqual(MAX_VISIBILITY_HOURS, 48)
