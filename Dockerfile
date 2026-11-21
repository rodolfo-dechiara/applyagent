# ApplyAgent — production image. Runtime deps stay Django-only in pyproject;
# gunicorn is installed into the venv at image build time only.
FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    VIRTUAL_ENV=/app/.venv \
    DJANGO_SETTINGS_MODULE=config.settings

WORKDIR /app

RUN pip install --no-cache-dir uv

# Dependency layer (cached unless pyproject/uv.lock change).
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project

COPY . .
RUN uv pip install --no-cache gunicorn \
    && chmod +x /app/entrypoint.sh

ENV PATH="/app/.venv/bin:$PATH"

# Migrations run on the app machine (the only one with the /data volume).
ENTRYPOINT ["/app/entrypoint.sh"]

EXPOSE 8080
# One worker: SQLite does not like multi-process writes. Threads for I/O.
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8080", "--workers", "1", "--threads", "4"]
