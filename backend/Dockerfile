FROM python:3.14.7-slim-bookworm

COPY --from=ghcr.io/astral-sh/uv:0.13.7 /uv /usr/local/bin/uv
ENV UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY src/ ./src/
RUN uv sync --frozen --no-dev --no-editable \
    && useradd --system --uid 10001 --create-home app \
    && mkdir -p /app/data/documents \
    && chown -R app:app /app/data
USER app
EXPOSE 8000
CMD ["uvicorn", "rag.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
