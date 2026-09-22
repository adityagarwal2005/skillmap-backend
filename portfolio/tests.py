"""A project has its own page; it used to be looked for in the feed."""
from portfolio.models import PortfolioItem
from social.testing import ApiTestCase, make_user


class ProjectDetailTests(ApiTestCase):
    def setUp(self):
        self.owner = make_user('owner')
        self.item = PortfolioItem.objects.create(
            user=self.owner, title='Cafe menu card',
            description='Menu and poster set', portfolio_type='design')

    def test_a_project_can_be_fetched_on_its_own(self):
        r = self.client.get(f'/portfolio/{self.item.id}/')
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body['title'], 'Cafe menu card')
        self.assertEqual(body['user']['username'], 'owner')
        self.assertEqual(body['reactions'], 0)

    def test_an_unknown_project_is_a_404_not_a_500(self):
        self.assertEqual(self.client.get('/portfolio/999999/').status_code, 404)

    def test_the_route_does_not_swallow_the_user_portfolio_route(self):
        r = self.client.get(f'/portfolio/user/{self.owner.id}/')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(r.json()['items']), 1)
