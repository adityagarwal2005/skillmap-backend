web: python manage.py migrate --noinput || true; python manage.py collectstatic --noinput || true; gunicorn social.wsgi --log-file - --timeout 120 --workers 1 --threads 4
