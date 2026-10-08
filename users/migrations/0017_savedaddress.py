import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0016_remove_user_status"),
    ]

    operations = [
        migrations.CreateModel(
            name="SavedAddress",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("label", models.CharField(max_length=40)),
                ("address", models.CharField(blank=True, default="", max_length=200)),
                ("latitude", models.FloatField()),
                ("longitude", models.FloatField()),
                ("created_at", models.DateTimeField(auto_now_add=True, null=True)),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,
                                           related_name="addresses", to="users.user")),
            ],
            options={
                "ordering": ["-created_at"],
                "unique_together": {("user", "label")},
            },
        ),
    ]
