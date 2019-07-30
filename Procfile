web: gunicorn --workers 3 --worker-class gevent --timeout 600 --log-file - --access-logfile - -b 0.0.0.0:5000 app:app
worker: celery worker --app dexter.tasks --beat --concurrency 1 --loglevel info
