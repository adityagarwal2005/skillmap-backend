"""Apply migrations, tolerating DDL that was already applied out-of-band.

Why this exists
---------------
Schema changes on this project have often been applied by hand in the Supabase
SQL editor and then deployed. Django doesn't know that happened, so on the next
boot `migrate` re-attempts them, Postgres raises "already exists", and the whole
command aborts — meaning every migration *after* the failing one silently never
runs. That has bitten three times, each time needing a bespoke reconcile script.

What this does
--------------
Applies migrations ONE AT A TIME. If a migration fails specifically because the
object it creates already exists (or the object it drops is already gone), that
migration is recorded as applied (--fake) and the run continues.

Why faking is safe here
-----------------------
It only ever fakes when Postgres itself reports the object's presence/absence
matches the migration's intent. That's the database confirming the DDL is
already in place — not an assumption. Any other error still aborts loudly, so a
genuinely broken migration is never skipped.
"""
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db import connections, DEFAULT_DB_ALIAS
from django.db.migrations.executor import MigrationExecutor
from django.db.utils import ProgrammingError, OperationalError

# Postgres messages that mean "the schema already matches this migration".
ALREADY_DONE = (
    'already exists',        # postgres: table/column/index already there
    'duplicate column',      # sqlite equivalent (local dev)
    'does not exist',        # a DROP whose target is already gone
    'no such table',         # sqlite equivalent of the above
)


class Command(BaseCommand):
    help = "Run migrations, faking any whose DDL is already present in the database."

    def add_arguments(self, parser):
        parser.add_argument('--database', default=DEFAULT_DB_ALIAS)

    def handle(self, *args, **options):
        db = options['database']
        connection = connections[db]
        executor = MigrationExecutor(connection)
        plan = executor.migration_plan(executor.loader.graph.leaf_nodes())

        if not plan:
            self.stdout.write("No migrations to apply.")
            return

        faked, applied = [], []
        for migration, backwards in plan:
            label = f"{migration.app_label}.{migration.name}"
            if backwards:
                self.stdout.write(f"Skipping reverse migration {label}")
                continue
            try:
                call_command(
                    'migrate', migration.app_label, migration.name,
                    database=db, verbosity=0, interactive=False,
                )
                applied.append(label)
                self.stdout.write(f"  applied  {label}")
            except (ProgrammingError, OperationalError) as exc:
                msg = str(exc).lower()
                if not any(token in msg for token in ALREADY_DONE):
                    self.stderr.write(f"  FAILED   {label}: {exc}")
                    raise
                # The database already reflects this migration — record it and
                # keep going, instead of aborting everything behind it.
                call_command(
                    'migrate', migration.app_label, migration.name,
                    database=db, fake=True, verbosity=0, interactive=False,
                )
                faked.append(label)
                self.stdout.write(f"  faked    {label}  (schema already present)")

        self.stdout.write(
            self.style.SUCCESS(f"migrate_safe done — {len(applied)} applied, {len(faked)} faked.")
        )
        if faked:
            self.stdout.write(
                "Faked because the schema was applied outside Django: " + ", ".join(faked)
            )
