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
# `|| true` on migrate is deliberate — a bad migration must not take the
# service down — but a bare `|| true` also made a FAILING migrate invisible.
# It failed on every boot for weeks (tables applied by hand in the Supabase
# editor were never recorded, so migrate re-attempted and aborted), which
# silently meant no later migration could ever apply. The banner below makes
# that state greppable in Cloud Run logs and alertable.
CMD python manage.py migrate --noinput \
      || echo "!!! MIGRATE FAILED — schema may be behind the code. See sql/RECONCILE_MIGRATION_STATE_SUPABASE.sql !!!"; \
    python manage.py collectstatic --noinput || true; \
    python manage.py seed_categories --replace || true; \
    exec gunicorn social.wsgi --bind 0.0.0.0:${PORT:-8080} --log-file - --timeout 120 --workers 1 --threads 4
