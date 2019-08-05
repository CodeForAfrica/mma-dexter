FROM python:3.7.1

COPY . /app
WORKDIR /app

RUN apt-get -qq update && apt-get -qq install -y --no-install-recommends apt-utils ghostscript \
    && pip install -r requirements.txt

CMD ["gunicorn","--workers", "3", "--worker-class", "gevent", "--timeout", "216000", "--log-file", "-", "--access-logfile", "-", "-b", "0.0.0.0:5000", "app:app"]
