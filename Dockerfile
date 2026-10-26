# syntax=docker/dockerfile:1
FROM python:3.12-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install . && python -c "import t2sql"

COPY examples ./examples
RUN python -c "import sqlite3,pathlib; c=sqlite3.connect('examples/university.sqlite'); c.executescript(pathlib.Path('examples/university.sql').read_text()); c.commit()"

# Run as an unprivileged user; databases are mounted read-only in compose anyway.
RUN useradd --create-home --uid 10001 app && mkdir -p /app/.cache && chown -R app /app/.cache
USER app

# No LLM base URL here: it would override T2SQL_LLM_PROVIDER. docker-compose sets Ollama's.
ENV T2SQL_DATABASES_DIR=/app/examples \
    PORT=8000
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s CMD python -c "import os, urllib.request; urllib.request.urlopen(f'http://127.0.0.1:{os.environ[\"PORT\"]}/health')"
# Cloud Run sets $PORT. --proxy-headers makes the client IP (used by the rate limiter) the
# caller's, not the load balancer's.
CMD ["sh", "-c", "exec uvicorn t2sql.api.app:app --host 0.0.0.0 --port ${PORT} --proxy-headers --forwarded-allow-ips='*'"]
