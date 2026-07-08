"""
Seed the SkillMap categories (and starter skills) for a college-campus launch.

Usage:
    python manage.py seed_categories            # add/ensure the campus set, keep others
    python manage.py seed_categories --replace  # ALSO delete any non-campus categories

Idempotent: safe to run repeatedly. `--replace` removes categories that aren't in
the campus set; because User.category is on_delete=SET_NULL, affected users keep
their accounts and simply lose their category tag (they re-pick one in onboarding).
"""
from django.core.management.base import BaseCommand
from django.db import transaction

from skills.models import Category, Skill


# Category name -> starter skills. Tweak freely for your campus.
CAMPUS_CATEGORIES = {
    "Code / Software": [
        "Python", "JavaScript", "React", "Node.js", "Java", "C++",
        "Flutter", "Android", "Machine Learning", "Web Development",
    ],
    "IoT & Hardware": [
        "Arduino", "Raspberry Pi", "Embedded C", "PCB Design",
        "Robotics", "Sensors", "ESP32", "3D Printing",
    ],
    "Notes & Study Material": [
        "Handwritten Notes", "Assignment Help", "Exam Prep",
        "Lab Records", "Presentations", "Research Papers",
    ],
    "Design & Media": [
        "UI/UX", "Figma", "Graphic Design", "Logo Design",
        "Poster Design", "Canva", "Illustration",
    ],
    "Content & Writing": [
        "Blog Writing", "Technical Writing", "Copywriting",
        "Resume Writing", "Editing", "Scriptwriting",
    ],
    "Photography & Video": [
        "Photography", "Video Editing", "Reels", "Event Coverage",
        "Portrait", "Premiere Pro", "Photoshop",
    ],
    "Events & Management": [
        "Event Planning", "Anchoring", "Volunteering",
        "Sponsorship", "Logistics", "Hosting",
    ],
    "Business & Marketing": [
        "Social Media", "Digital Marketing", "SEO",
        "Branding", "Sales", "Public Speaking",
    ],
    "Tutoring & Academics": [
        "Maths", "Physics", "Chemistry", "Coding Help",
        "Doubt Solving", "Subject Tutoring",
    ],
    "Music & Performance": [
        "Singing", "Guitar", "Keyboard", "Dance", "DJ", "Music Production",
    ],
    "Sports & Fitness": [
        "Gym Training", "Cricket", "Football", "Yoga", "Athletics", "Nutrition",
    ],
    "Art & Craft": [
        "Painting", "Sketching", "Handmade Crafts",
        "Calligraphy", "Resin Art", "Origami",
    ],
    "Gaming & Esports": [
        "Game Development", "Streaming", "Esports",
        "Unity", "Level Design", "Game Art",
    ],
    # Catch-all bucket — no preset skills; users add their own.
    "Other": [],
}


class Command(BaseCommand):
    help = "Seed campus-launch categories and their starter skills."

    def add_arguments(self, parser):
        parser.add_argument(
            "--replace",
            action="store_true",
            help="Delete categories that are not in the campus set "
                 "(users on them keep their account but lose the category tag).",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        created = 0
        for cat_name, skill_names in CAMPUS_CATEGORIES.items():
            category, was_created = Category.objects.get_or_create(name=cat_name)
            if was_created:
                created += 1
            for skill_name in skill_names:
                skill, _ = Skill.objects.get_or_create(name=skill_name)
                # Only set the category if the skill isn't already linked to one,
                # so we never steal a skill from an existing category.
                if skill.category_id is None:
                    skill.category = category
                    skill.save(update_fields=["category"])

        self.stdout.write(self.style.SUCCESS(
            f"Ensured {len(CAMPUS_CATEGORIES)} campus categories "
            f"({created} newly created)."
        ))

        if options["replace"]:
            stale = Category.objects.exclude(name__in=CAMPUS_CATEGORIES.keys())
            stale_names = list(stale.values_list("name", flat=True))
            if stale_names:
                stale.delete()
                self.stdout.write(self.style.WARNING(
                    f"Removed {len(stale_names)} non-campus categories: "
                    f"{', '.join(stale_names)}"
                ))
            else:
                self.stdout.write("No non-campus categories to remove.")
        else:
            self.stdout.write(
                "Kept existing categories. Re-run with --replace to remove "
                "the generic ones."
            )
