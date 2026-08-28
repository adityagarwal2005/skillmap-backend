from .models import Skill


def find_skill(name):
    """Case-insensitive skill lookup, tolerant of duplicate case variants.

    Skill.name is unique=True, but Postgres uniqueness is case-SENSITIVE, so
    the table happily holds both "React" and "react". Any `.get(name__iexact=)`
    against those raises MultipleObjectsReturned — which surfaced as a 500
    ("Failed to post") when creating a job whose skills hit a duplicated name.

    Returns the oldest matching row, or None.
    """
    name = (name or '').strip()
    if not name:
        return None
    return Skill.objects.filter(name__iexact=name).order_by('id').first()


def get_or_create_skill(name):
    """find_skill(), creating the skill if no case-variant exists yet."""
    name = (name or '').strip()
    if not name:
        return None
    return find_skill(name) or Skill.objects.create(name=name)
