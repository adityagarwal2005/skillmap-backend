"""Gig lifecycle: posting, hiring against capacity, declining, closing, mutual
completion, and what applicants see about each of those."""
from notifications.models import Notification
from portfolio.models import PortfolioItem
from social.testing import ApiTestCase, in_hours, make_user
from work.models import Conversation, WorkRequest, WorkRequestResponse


def make_gig(poster, people_needed=1, **fields):
    fields.setdefault('status', 'open')
    fields.setdefault('expires_at', in_hours(24))
    return WorkRequest.objects.create(
        created_by=poster, description='Design a poster for the fest', payment_amount=800,
        time_limit_hours=24, people_needed=people_needed, **fields,
    )


def apply(gig, user, **flags):
    return WorkRequestResponse.objects.create(
        work_request=gig, user=user, status='accepted', message='I can do this', **flags)


class PostingTests(ApiTestCase):
    def setUp(self):
        self.poster = make_user('poster', contact=True)

    def create(self, **overrides):
        data = {'description': 'Edit a reel', 'payment_amount': '500',
                'time_limit_hours': '24', 'skills': 'Video editing', **overrides}
        return self.post_as(self.poster, '/work/requests/create/', data)

    def test_visibility_window_is_capped_at_48_hours(self):
        self.assertEqual(self.create(time_limit_hours='500').status_code, 201)
        self.assertEqual(WorkRequest.objects.get().time_limit_hours, 48)

    def test_capacity_is_clamped_to_five(self):
        self.create(people_needed='99')
        self.assertEqual(WorkRequest.objects.get().people_needed, 5)

    def test_non_numeric_budget_is_a_400_not_a_500(self):
        self.assertEqual(self.create(payment_amount='abc').status_code, 400)

    def test_negative_budget_is_rejected(self):
        self.assertEqual(self.create(payment_amount='-10').status_code, 400)


class HiringTests(ApiTestCase):
    def setUp(self):
        self.poster = make_user('poster', contact=True)
        self.ana, self.ben, self.cal = make_user('ana'), make_user('ben'), make_user('cal')
        self.gig = make_gig(self.poster, people_needed=2)
        for person in (self.ana, self.ben, self.cal):
            apply(self.gig, person)

    def hire(self, person, as_user=None):
        return self.post_as(as_user or self.poster, f'/work/requests/{self.gig.id}/assign/',
                            {'assignee_id': person.id})

    def test_gig_stays_open_until_every_spot_is_filled(self):
        self.assertEqual(self.hire(self.ana).status_code, 200)
        self.gig.refresh_from_db()
        self.assertEqual(self.gig.status, 'open')
        self.assertEqual(self.hire(self.ben).status_code, 200)
        self.gig.refresh_from_db()
        self.assertEqual(self.gig.status, 'assigned')

    def test_no_hiring_past_capacity(self):
        self.hire(self.ana)
        self.hire(self.ben)
        self.assertEqual(self.hire(self.cal).status_code, 400)
        self.assertFalse(WorkRequestResponse.objects.get(user=self.cal).hired)

    def test_every_hire_gets_their_own_chat_with_the_poster(self):
        first = self.hire(self.ana).json()['conversation_id']
        second = self.hire(self.ben).json()['conversation_id']
        self.assertNotEqual(first, second)
        for conv_id, person in ((first, self.ana), (second, self.ben)):
            members = set(Conversation.objects.get(id=conv_id).participants.values_list('username', flat=True))
            self.assertEqual(members, {'poster', person.username})

    def test_only_the_poster_can_hire(self):
        intruder = make_user('intruder', contact=True)
        self.assertEqual(self.hire(self.ana, as_user=intruder).status_code, 404)

    def test_decline_is_permanent_and_the_applicant_is_told(self):
        r = self.post_as(self.poster, f'/work/requests/{self.gig.id}/reject/', {'applicant_id': self.cal.id})
        self.assertEqual(r.status_code, 200)
        self.assertTrue(WorkRequestResponse.objects.get(user=self.cal).rejected)
        self.assertTrue(Notification.objects.filter(user=self.cal, notification_type='proposal_declined').exists())

    def test_cannot_decline_someone_already_hired(self):
        self.hire(self.ana)
        r = self.post_as(self.poster, f'/work/requests/{self.gig.id}/reject/', {'applicant_id': self.ana.id})
        self.assertEqual(r.status_code, 400)

    def test_applicant_list_is_private_to_the_poster(self):
        url = f'/work/requests/{self.gig.id}/responses/'
        self.assertEqual(self.client.get(url).status_code, 401)
        self.assertIn(self.get_as(self.ana, url).status_code, (403, 404))
        self.assertEqual(self.get_as(self.poster, url).status_code, 200)

    def test_posting_history_is_self_only(self):
        url = f'/work/requests/user/{self.poster.id}/'
        self.assertEqual(self.get_as(self.ana, url).status_code, 403)
        self.assertEqual(self.get_as(self.poster, url).status_code, 200)


class CompletionTests(ApiTestCase):
    def setUp(self):
        self.poster = make_user('poster', contact=True)
        self.ana, self.ben = make_user('ana'), make_user('ben')
        self.gig = make_gig(self.poster, people_needed=2, status='assigned', assigned_to=self.ana)
        apply(self.gig, self.ana, hired=True)
        apply(self.gig, self.ben, hired=True)

    def complete(self, user, gig=None):
        return self.post_as(user, f'/work/requests/{(gig or self.gig).id}/complete/')

    def test_any_hire_can_confirm_not_just_the_first(self):
        self.assertEqual(self.complete(self.ben).status_code, 200)
        self.gig.refresh_from_db()
        self.assertTrue(self.gig.completed_by_worker)
        self.assertEqual(self.gig.status, 'assigned')
        self.assertTrue(Notification.objects.filter(user=self.poster, notification_type='job_review').exists())

    def test_poster_marking_done_asks_every_hire_to_confirm(self):
        self.complete(self.poster)
        for hire in (self.ana, self.ben):
            self.assertTrue(Notification.objects.filter(user=hire, notification_type='job_confirm').exists())

    def test_mutual_completion_closes_and_verifies_every_hire(self):
        self.complete(self.poster)
        self.complete(self.ben)
        self.gig.refresh_from_db()
        self.assertEqual(self.gig.status, 'closed')
        verified = PortfolioItem.objects.filter(verified_via_work=self.gig, verified=True)
        self.assertEqual(sorted(verified.values_list('user__username', flat=True)), ['ana', 'ben'])
        rate_prompts = Notification.objects.filter(user=self.poster, notification_type='job_complete')
        self.assertEqual(sorted(rate_prompts.values_list('actor__username', flat=True)), ['ana', 'ben'])

    def test_a_closed_gig_cannot_be_completed_again(self):
        self.complete(self.poster)
        self.complete(self.ana)
        self.assertEqual(self.complete(self.poster).status_code, 400)
        self.assertEqual(PortfolioItem.objects.filter(verified_via_work=self.gig).count(), 2)

    def test_partly_staffed_gig_can_still_finish(self):
        gig = make_gig(self.poster, people_needed=3)
        apply(gig, self.ana, hired=True)
        self.assertEqual(self.complete(self.poster, gig).status_code, 200)
        self.assertEqual(self.complete(self.ana, gig).status_code, 200)
        gig.refresh_from_db()
        self.assertEqual(gig.status, 'closed')

    def test_nothing_to_complete_before_anyone_is_hired(self):
        gig = make_gig(self.poster)
        self.assertEqual(self.complete(self.poster, gig).status_code, 400)

    def test_outsiders_cannot_complete(self):
        self.assertEqual(self.complete(make_user('stranger')).status_code, 403)


class ClosingTests(ApiTestCase):
    def setUp(self):
        self.poster = make_user('poster', contact=True)
        self.ana = make_user('ana')
        self.gig = make_gig(self.poster, status='assigned', assigned_to=self.ana)
        apply(self.gig, self.ana, hired=True)

    def test_closing_early_awards_no_verified_project(self):
        r = self.post_as(self.poster, f'/work/requests/{self.gig.id}/close/')
        self.assertEqual(r.status_code, 200)
        self.gig.refresh_from_db()
        self.assertEqual(self.gig.status, 'closed')
        self.assertFalse(PortfolioItem.objects.filter(user=self.ana).exists())

    def test_only_the_poster_can_close(self):
        r = self.post_as(self.ana, f'/work/requests/{self.gig.id}/close/')
        self.assertEqual(r.status_code, 404)


class ApplicationStatusTests(ApiTestCase):
    """What /my-applications/ tells an applicant about where they stand."""

    def status_for(self, user, gig):
        apps = self.get_as(user, '/my-applications/').json()['applications']
        return next(a['status'] for a in apps if a['kind'] == 'freelance' and a['id'] == gig.id)

    def setUp(self):
        self.poster = make_user('poster', contact=True)

    def test_every_hire_is_accepted_not_only_the_first(self):
        ana, ben = make_user('ana'), make_user('ben')
        gig = make_gig(self.poster, people_needed=2, status='assigned', assigned_to=ana)
        apply(gig, ana, hired=True)
        apply(gig, ben, hired=True)
        self.assertEqual(self.status_for(ben, gig), 'accepted')

    def test_declined_is_reported(self):
        cal = make_user('cal')
        gig = make_gig(self.poster)
        apply(gig, cal, rejected=True)
        self.assertEqual(self.status_for(cal, gig), 'declined')

    def test_full_gig_reads_filled_for_those_not_picked(self):
        ana, dee = make_user('ana'), make_user('dee')
        gig = make_gig(self.poster, status='assigned', assigned_to=ana)
        apply(gig, ana, hired=True)
        apply(gig, dee)
        self.assertEqual(self.status_for(dee, gig), 'filled')

    def test_expired_without_an_answer_reads_closed(self):
        eve = make_user('eve')
        gig = make_gig(self.poster, expires_at=in_hours(-1))
        apply(gig, eve)
        self.assertEqual(self.status_for(eve, gig), 'closed')
