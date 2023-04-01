FROM python:3-alpine
ENV DJANGO_SETTINGS_MODULE levity.settings
ENV PORT 8000
ENV NUM_WORKERS 3
ENV NUM_THREADS 5
WORKDIR /app
COPY poetry.lock .
COPY pyproject.toml .
RUN apk --no-cache add libpq && \
    pip install poetry && \
    poetry install --no-root && \
    rm -rf ~/.cache/pip && \
    rm -rf ~/.cache/pypoetry/{cache,artifacts} && \
    find ~/.cache/pypoetry/virtualenvs -name '*.pyc' -exec rm -rf '{}' \;
COPY . .
CMD poetry run gunicorn -b :$PORT --workers $NUM_WORKERS --threads $NUM_THREADS levity.wsgi
