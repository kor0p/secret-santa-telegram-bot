release: python manage.py migrate
web: gunicorn bot.wsgi -b 0.0.0.0:$PORT
