FROM python:3-alpine
WORKDIR /app
COPY poetry.lock .
COPY pyproject.toml .
RUN pip install poetry && \
    poetry install --no-root && \
    rm -rf ~/.cache/pip && \
    rm -rf ~/.cache/pypoetry/{cache,artifacts} && \
    find ~/.cache/pypoetry/virtualenvs -name '*.pyc' -exec rm -rf '{}' \;
COPY . .
CMD poetry run python main.py
