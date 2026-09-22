"""A project has its own page; it used to be looked for in the feed."""
from portfolio.models import PortfolioItem, Reaction
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

    def test_it_reports_each_reaction_type_and_which_one_is_mine(self):
        fan, other = make_user('fan'), make_user('other')
        Reaction.objects.create(portfolio_item=self.item, user=fan, reaction_type='love')
        Reaction.objects.create(portfolio_item=self.item, user=other, reaction_type='fire')

        anon = self.client.get(f'/portfolio/{self.item.id}/').json()
        self.assertEqual(anon['reaction_counts'], {'fire': 1, 'love': 1, 'like': 0})
        self.assertIsNone(anon['my_reaction'])

        mine = self.get_as(fan, f'/portfolio/{self.item.id}/').json()
        self.assertEqual(mine['my_reaction'], 'love')

