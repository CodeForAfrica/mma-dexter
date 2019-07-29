FROM python:3.7.1

COPY . /app
WORKDIR /app

RUN pip install -r requirements.txt

CMD ["gunicorn","--workers", "3", "--worker-class", "gevent", "--timeout", "600", "--log-file", "-", "--access-logfile", "-", "-b", "0.0.0.0:8000", "app:app"]
