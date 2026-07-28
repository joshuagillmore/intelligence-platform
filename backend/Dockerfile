FROM python:3.12-slim

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# uv.lock must be copied alongside pyproject.toml: without it `uv sync` resolves
# the dependency ranges afresh at build time, so the image gets whatever is
# newest that day rather than what the test suite ran against. Measured on a
# real build, 67 of 167 packages drifted from the lock — pydantic 2.12.5→2.13.4,
# cryptography 46→49, openai 2.29→2.49 — and every rebuild could differ again.
COPY pyproject.toml uv.lock ./
COPY src/ src/

# --frozen fails the build if uv.lock is stale rather than quietly re-resolving,
# so a lockfile that drifts from pyproject.toml is caught here, not in prod.
RUN uv sync --no-dev --frozen
RUN uv pip install --python .venv/bin/python https://github.com/explosion/spacy-models/releases/download/en_core_web_sm-3.8.0/en_core_web_sm-3.8.0-py3-none-any.whl

# Install Chromium for crawl4ai headless browser
RUN uv run crawl4ai-setup

EXPOSE 8000

CMD ["uv", "run", "uvicorn", "intel_platform.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
