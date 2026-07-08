web: python manage.py migrate --noinput && python manage.py collectstatic --noinput && gunicorn social.wsgi --log-file - --timeout 120 --workers 1 --threads 4
