"""What does and does not earn a row in the notifications list."""
from notifications.models import Notification
from social.testing import ApiTestCase, make_user
from users.models import Friendship


class MessagesDoNotNotifyTests(ApiTestCase):
    """A message pushes to the device and raises the Messages badge, but it
    no longer creates a notification row. One row per message turned the list
    into a chat transcript and buried everything that needs a decision."""

    def setUp(self):
        self.ana = make_user('ana', contact=True)
        self.ben = make_user('ben', contact=True)
        # Messaging needs an existing connection — created directly so the
        # friend-request notification doesn't muddy the counts below.
        Friendship.objects.create(requester=self.ana, receiver=self.ben, status='accepted')
        convo = self.post_as(self.ana, f'/conversations/start/{self.ben.id}/')
        self.convo_id = convo.json()['conversation_id']

    def send(self, text):
        return self.post_as(self.ana, f'/conversations/{self.convo_id}/send/', {'text': text})

    def test_a_message_creates_no_notification_row(self):
        self.assertEqual(self.send('hi').status_code, 201)
        self.assertEqual(Notification.objects.filter(user=self.ben).count(), 0)

    def test_a_chat_leaves_the_notifications_list_empty(self):
        for line in ('hi', 'how are you', 'you there?'):
            self.send(line)
        listed = self.get_as(self.ben, '/notifications/').json()
        self.assertEqual(listed['count'], 0)
        self.assertEqual(self.get_as(self.ben, '/notifications/unread/').json()['unread_count'], 0)

    def test_rows_already_sitting_in_an_account_are_hidden_too(self):
        """Existing accounts are full of them; they are hidden rather than
        deleted so the history stays auditable in admin."""
        Notification.objects.create(user=self.ben, notification_type='message',
                                    message='ana: hi', actor=self.ana)
        Notification.objects.create(user=self.ben, notification_type='friend_request',
                                    message='ana sent you a friend request', actor=self.ana)
        listed = self.get_as(self.ben, '/notifications/').json()
        self.assertEqual([n['type'] for n in listed['notifications']], ['friend_request'])
        self.assertEqual(self.get_as(self.ben, '/notifications/unread/').json()['unread_count'], 1)


class FriendRequestsStillNotifyTests(ApiTestCase):
    def test_a_friend_request_still_lands_in_the_list(self):
        ana, ben = make_user('ana'), make_user('ben')
        self.post_as(ana, f'/users/{ben.id}/friend/')
        listed = self.get_as(ben, '/notifications/').json()['notifications']
        self.assertEqual([n['type'] for n in listed], ['friend_request'])
