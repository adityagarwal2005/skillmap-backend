"""Remove listings that can never appear on the board again.

Run from the repo root:

    venv/bin/python clear_dead_listings.py

What goes:
  - freelance gigs whose window has closed, or that are marked closed
  - collab posts the same, plus legacy ones with no expiry at all: those
    predate the visibility window and so can never close themselves

What stays:
  - every user account
  - every review and rating. Review.work_request is SET_NULL, so a rating
    outlives the listing it came from
  - anything still live

Applicant rows cascade with their listing, which is correct: an application
to a removed gig has nothing left to point at.

A timestamped fixture is written to backups/ before anything is removed, and
the whole thing runs in one transaction. To restore:

    venv/bin/python manage.py loaddata backups/<file>.json
"""
import datetime
import os
import pathlib
import sys

import django

ROOT = pathlib.Path(__file__).resolve().parent

# The production connection string lives in .env, same as the app reads it.
env = ROOT / '.env'
if env.exists():
    for line in env.read_text().splitlines():
        if line.strip() and not line.startswith('#') and '=' in line:
            key, value = line.split('=', 1)
            os.environ.setdefault(key.strip(), value.strip())
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'social.settings')
django.setup()

from django.core import serializers                      # noqa: E402
from django.db import transaction                        # noqa: E402
from django.utils import timezone                        # noqa: E402

from collab.models import CollabPost, CollabRequest      # noqa: E402
from reviews.models import Review                        # noqa: E402
from users.models import User                            # noqa: E402
from work.models import WorkRequest, WorkRequestResponse  # noqa: E402

now = timezone.now()

gigs = [g for g in WorkRequest.objects.select_related('created_by')
        if (g.expires_at and g.expires_at <= now) or g.status == 'closed']

# `expires_at is None` catches the legacy rows: posted before listings had a
# visibility window, so nothing will ever retire them on its own.
collabs = [c for c in CollabPost.objects.select_related('user')
           if c.expires_at is None or c.expires_at <= now or c.status == 'closed']

if not gigs and not collabs:
    print("Nothing dead to clear.")
    sys.exit(0)

print(f"Will remove {len(gigs)} gig(s) and {len(collabs)} collab post(s):\n")
for g in gigs:
    print(f"  gig#{g.id:<4} Rs{g.payment_amount:<9} "
          f"{str(g.description)[:44]!r}  @{g.created_by.username}")
for c in collabs:
    print(f"  col#{c.id:<4} {str(c.title)[:44]!r}  @{c.user.username}")

users_before = User.objects.count()
reviews_before = Review.objects.count()

rows = (gigs + collabs
        + list(WorkRequestResponse.objects.filter(work_request__in=gigs))
        + list(CollabRequest.objects.filter(collab_post__in=collabs)))

(ROOT / 'backups').mkdir(exist_ok=True)
stamp = datetime.datetime.now().strftime('%Y%m%d-%H%M%S')
backup = ROOT / 'backups' / f'dead-listings-{stamp}.json'
backup.write_text(serializers.serialize('json', rows, indent=1))
print(f"\nBacked up {len(rows)} rows -> {backup.relative_to(ROOT)}")

if input("\nType DELETE to confirm: ").strip() != 'DELETE':
    print("Aborted. Nothing was removed.")
    sys.exit(1)

with transaction.atomic():
    WorkRequest.objects.filter(id__in=[g.id for g in gigs]).delete()
    CollabPost.objects.filter(id__in=[c.id for c in collabs]).delete()

print(f"\nDone. users {users_before} -> {User.objects.count()}, "
      f"reviews {reviews_before} -> {Review.objects.count()}")
print(f"Remaining: {WorkRequest.objects.count()} gig(s), "
      f"{CollabPost.objects.count()} collab post(s)")
