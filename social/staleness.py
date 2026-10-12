"""What is still worth showing someone about their own activity.

Listings on DoitHere are perishable by design — they run on a timer and
vanish from the board when it closes. The screens that show you your *own*
history never got that memo: "my posts" returned every gig you had ever
written, and notifications returned every row ever created, so an account a
month old opened on a wall of dead posts and "28 days ago" alerts about
things that resolved themselves long before.

Nothing is deleted. These are read filters, so the data is still there for
the admin, for reviews that hang off a hire, and for anything we want to
show deliberately later.
"""
from datetime import timedelta

# A closed post stays visible for a fortnight: long enough to see how it went
# and leave a rating, short enough that the page is about now.
RECENTLY_CLOSED_DAYS = 14

# A notification nobody acted on in a month is not going to be acted on.
NOTIFICATION_DAYS = 30


def post_still_matters(*, is_open, expires_at, closed_at, has_unfinished_hire, now):
    """Whether one of the user's own posts belongs on their Post screen.

    Kept while it is live, while work from it is still in flight, and for
    RECENTLY_CLOSED_DAYS after its window shut.
    """
    expired = expires_at is not None and expires_at <= now
    if is_open and not expired:
        return True
    if has_unfinished_hire:
        return True
    reference = expires_at or closed_at
    if reference is None:
        return True          # no dates to judge by — do not hide it
    return reference >= now - timedelta(days=RECENTLY_CLOSED_DAYS)


def notification_cutoff(now):
    return now - timedelta(days=NOTIFICATION_DAYS)
