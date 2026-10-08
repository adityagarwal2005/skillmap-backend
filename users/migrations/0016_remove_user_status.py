from django.db import migrations


class Migration(migrations.Migration):
    """Drop the self-declared availability flag.

    A profile that says "Open to work" is only true for as long as someone
    remembers to change it back, so in practice it decayed into noise: the
    default was 'not_available', which quietly told every visitor the person
    did not want work. DoitHere already answers the same question with
    something that cannot go stale — whether you have an open listing, and
    whether you apply to things.

    It also gated send_work_proposal, so proposals were silently impossible
    to send to anyone who had never visited Settings.
    """

    dependencies = [
        ("users", "0015_delete_studentprofile"),
    ]

    operations = [
        migrations.RemoveField(model_name="user", name="status"),
    ]
