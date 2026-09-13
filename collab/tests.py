"""Collab capacity and who gets to see a team once they've been turned down."""
from collab.models import CollabPost, CollabRequest
from social.testing import ApiTestCase, in_hours, make_user


def listed_ids(payload):
    """Every object id with a title anywhere in a response, whatever its shape."""
    found = set()
    if isinstance(payload, dict):
        if 'id' in payload and 'title' in payload:
            found.add(payload['id'])
        for value in payload.values():
            found |= listed_ids(value)
    elif isinstance(payload, list):
        for value in payload:
            found |= listed_ids(value)
    return found


class CollabCapacityTests(ApiTestCase):
    def setUp(self):
        self.host = make_user('host', contact=True)
        self.ana, self.ben, self.cal = make_user('ana'), make_user('ben'), make_user('cal')
        self.post = CollabPost.objects.create(
            user=self.host, title='Hackathon team', description='Need two devs',
            collab_type='experience', people_needed=2, status='open', expires_at=in_hours(24),
        )
        self.requests = {
            person.username: CollabRequest.objects.create(collab_post=self.post, applicant=person, status='pending')
            for person in (self.ana, self.ben, self.cal)
        }

    def respond(self, username, status, as_user=None):
        req = self.requests[username]
        return self.post_as(as_user or self.host, f'/collab/requests/{req.id}/respond/', {'status': status})

    def test_filling_every_seat_closes_the_post(self):
        self.assertEqual(self.respond('ana', 'accepted').status_code, 200)
        self.post.refresh_from_db()
        self.assertEqual(self.post.status, 'open')
        self.assertEqual(self.respond('ben', 'accepted').status_code, 200)
        self.post.refresh_from_db()
        self.assertEqual(self.post.status, 'closed')

    def test_no_accepting_past_capacity(self):
        self.respond('ana', 'accepted')
        self.respond('ben', 'accepted')
        self.assertEqual(self.respond('cal', 'accepted').status_code, 400)

    def test_only_the_host_can_respond(self):
        self.assertIn(self.respond('ben', 'accepted', as_user=self.ana).status_code, (403, 404))

    def test_declined_applicant_stops_seeing_the_post(self):
        self.assertIn(self.post.id, listed_ids(self.get_as(self.cal, '/collab/').json()))
        self.respond('cal', 'declined')
        self.assertNotIn(self.post.id, listed_ids(self.get_as(self.cal, '/collab/').json()))

    def test_applicant_list_is_private_to_the_host(self):
        url = f'/collab/{self.post.id}/applicants/'
        self.assertIn(self.get_as(self.ana, url).status_code, (403, 404))
        self.assertEqual(self.get_as(self.host, url).status_code, 200)
