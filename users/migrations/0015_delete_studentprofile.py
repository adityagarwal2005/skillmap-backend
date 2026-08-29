from django.db import migrations


class Migration(migrations.Migration):
    """Drop StudentProfile.

    The degree/year/class data it held was never surfaced in the app (the
    frontend never called any of its three endpoints), and its read endpoint
    was unauthenticated — so it was pure exposure with no product value.
    """

    dependencies = [
        ('users', '0014_phoneotpverification_user_phone_verified'),
    ]

    operations = [
        migrations.DeleteModel(name='StudentProfile'),
    ]
