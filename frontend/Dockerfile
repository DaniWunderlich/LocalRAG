FROM python:3.14.7-slim-bookworm

COPY --from=ghcr.io/astral-sh/uv:0.13.7 /uv /usr/local/bin/uv
ENV UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    GRADIO_ANALYTICS_ENABLED=False \
    HF_HUB_DISABLE_TELEMETRY=1 \
    GRADIO_TEMP_DIR=/tmp/localrag-uploads
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev \
    && useradd --system --uid 10001 --create-home app
COPY . .
USER app
EXPOSE 7860
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "7860"]
