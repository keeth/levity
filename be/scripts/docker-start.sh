#!/bin/sh
set -e
cp -rfv /app/static /var/www/html
poetry run gunicorn -b :8000 --workers 3 --threads 5 levity.wsgi
