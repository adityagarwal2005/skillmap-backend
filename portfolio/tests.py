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



from unittest.mock import patch
from django.core.files.uploadedfile import SimpleUploadedFile
from portfolio.models import Video, VideoLike


class VideoFeedTests(ApiTestCase):
    def setUp(self):
        self.a = make_user('vida', contact=True)
        self.b = make_user('vidb')
        self.v1 = Video.objects.create(user=self.b, url='https://cdn/x1.mp4', caption='my reel')
        self.v2 = Video.objects.create(user=self.b, url='https://cdn/x2.mp4', caption='another')

    def test_feed_lists_newest_first(self):
        r = self.get_as(self.a, '/videos/')
        self.assertEqual(r.status_code, 200)
        ids = [v['id'] for v in r.json()['videos']]
        self.assertEqual(ids, [self.v2.id, self.v1.id])
        self.assertEqual(r.json()['videos'][0]['user']['username'], 'vidb')

    def test_anonymous_cannot_read_the_feed(self):
        self.assertEqual(self.client.get('/videos/').status_code, 401)

    @patch('portfolio.views.upload_media_file', return_value=('https://cdn/new.mp4', 'video'))
    def test_posting_a_video(self, _up):
        f = SimpleUploadedFile('clip.mp4', b'fakebytes', content_type='video/mp4')
        r = self.post_as(self.a, '/videos/create/', {'video': f, 'caption': 'fresh cut'})
        self.assertEqual(r.status_code, 201)
        self.assertEqual(Video.objects.filter(user=self.a).count(), 1)
        self.assertEqual(r.json()['video']['caption'], 'fresh cut')

    def test_posting_needs_a_file(self):
        self.assertEqual(self.post_as(self.a, '/videos/create/', {'caption': 'x'}).status_code, 400)

    @patch('portfolio.views.upload_media_file', return_value=('', ''))
    def test_a_failed_upload_is_a_400(self, _up):
        f = SimpleUploadedFile('clip.mp4', b'x', content_type='video/mp4')
        self.assertEqual(self.post_as(self.a, '/videos/create/', {'video': f}).status_code, 400)

    def test_like_toggles(self):
        r1 = self.post_as(self.a, f'/videos/{self.v1.id}/like/', {})
        self.assertTrue(r1.json()['liked']); self.assertEqual(r1.json()['likes'], 1)
        r2 = self.post_as(self.a, f'/videos/{self.v1.id}/like/', {})
        self.assertFalse(r2.json()['liked']); self.assertEqual(r2.json()['likes'], 0)

    def test_feed_reports_my_like(self):
        VideoLike.objects.create(video=self.v1, user=self.a)
        feed = {v['id']: v for v in self.get_as(self.a, '/videos/').json()['videos']}
        self.assertTrue(feed[self.v1.id]['liked'])
        self.assertFalse(feed[self.v2.id]['liked'])

    def test_user_videos_shelf(self):
        r = self.get_as(self.a, f'/videos/user/{self.b.id}/')
        self.assertEqual(r.json()['count'], 2)

    def test_delete_only_your_own(self):
        mine = Video.objects.create(user=self.a, url='https://cdn/mine.mp4')
        self.assertEqual(self.post_as(self.a, f'/videos/{mine.id}/delete/', {}).status_code, 200)
        self.assertEqual(self.post_as(self.a, f'/videos/{self.v1.id}/delete/', {}).status_code, 404)

    def test_view_count_increments(self):
        self.post_as(self.a, f'/videos/{self.v1.id}/view/', {})
        self.v1.refresh_from_db()
        self.assertEqual(self.v1.views, 1)
