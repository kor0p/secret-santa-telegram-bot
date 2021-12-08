release: python manage.py migrate && python manage.py compilemessages --ignore .heroku
web: gunicorn bot.wsgi -b 0.0.0.0:$PORT
