FROM python:3.12-slim

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

COPY pyproject.toml .
COPY src/ src/

RUN uv sync --no-dev
RUN uv pip install --python .venv/bin/python https://github.com/explosion/spacy-models/releases/download/en_core_web_sm-3.8.0/en_core_web_sm-3.8.0-py3-none-any.whl

# Install Chromium for crawl4ai headless browser
RUN uv run crawl4ai-setup

EXPOSE 8000

CMD ["uv", "run", "uvicorn", "intel_platform.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
