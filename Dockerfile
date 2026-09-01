FROM python:3.13-slim

# psycopg2-binary and Pillow ship compiled wheels for most platforms, but
# libpq (Postgres client lib) still needs to be present at runtime for
# psycopg2-binary to actually load.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Cloud Run injects PORT (defaults to 8080) and expects the container to
# listen on it — everything else here mirrors the existing Procfile exactly
# (same migrate/collectstatic/seed-then-serve sequence Render already runs),
# so behavior doesn't change just because the host did.
# migrate_safe, not migrate: schema here is sometimes applied by hand in the
# Supabase editor, which makes plain `migrate` abort on "already exists" and
# silently skip every migration behind it. migrate_safe records those and
# carries on, while still failing loudly on a genuinely broken migration.
# The `|| echo` keeps a bad migration from taking the service down, while
# leaving a greppable, alertable banner in the logs (a bare `|| true` hid it).
CMD python manage.py migrate_safe \
      || echo "!!! MIGRATE FAILED — schema may be behind the code !!!"; \
    python manage.py collectstatic --noinput || true; \
    python manage.py seed_categories --replace || true; \
    exec gunicorn social.wsgi --bind 0.0.0.0:${PORT:-8080} --log-file - --timeout 120 --workers 1 --threads 8
