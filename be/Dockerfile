FROM python:3-alpine
ENV DJANGO_SETTINGS_MODULE levity.settings
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
RUN mkdir -p /app/static
RUN mkdir -p /var/www/html
RUN poetry run python manage.py collectstatic --noinput

