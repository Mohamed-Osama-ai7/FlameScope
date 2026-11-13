# FlameScope API / loader image. Build context: backend/
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /srv/backend

# Dependencies first (cached layer): a code change does not re-download them.
COPY pyproject.toml ./
RUN mkdir app && touch app/__init__.py && pip install . && useradd --create-home --uid 10001 flamescope

COPY app ./app
COPY scripts ./scripts
COPY alembic.ini ./
RUN pip install --no-deps --force-reinstall .

# /srv/data is mounted read-only at runtime (see docker-compose.yml)
USER flamescope
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
