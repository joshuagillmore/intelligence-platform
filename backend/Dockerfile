FROM python:3.12-slim

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Build context is the repo root (Railway default), so prefix paths with backend/.
COPY backend/pyproject.toml .
COPY backend/src/ src/

RUN uv sync --no-dev
RUN uv pip install --python .venv/bin/python https://github.com/explosion/spacy-models/releases/download/en_core_web_sm-3.8.0/en_core_web_sm-3.8.0-py3-none-any.whl

# Install Chromium + its OS-level dependencies for crawl4ai's headless browser.
# Runs as root (no unprivileged USER), so apt-based install-deps works. crawl4ai-setup
# alone can silently skip the actual browser binary download, so install explicitly
# (the lesson learned deploying Quarry).
RUN uv run playwright install-deps chromium \
    && uv run playwright install chromium \
    && uv run crawl4ai-setup

EXPOSE 8000

# Shell form so Railway's injected $PORT is honored (falls back to 8000 locally).
CMD uv run uvicorn intel_platform.api.app:app --host 0.0.0.0 --port ${PORT:-8000}
