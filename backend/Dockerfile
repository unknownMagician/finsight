FROM python:3.13-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

COPY pyproject.toml ./
COPY app/__init__.py app/__init__.py
RUN pip install .

COPY . .
RUN pip install --no-deps . \
    && useradd --create-home --uid 10001 finsight
USER finsight

EXPOSE 8000

# Apply migrations, then serve. Keep a single worker per container; scale with replicas.
# FORWARDED_ALLOW_IPS (read by uvicorn) controls which peers may set X-Forwarded-For, which
# per-IP rate limits rely on. Restrict it to your reverse proxy in production.
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers"]
