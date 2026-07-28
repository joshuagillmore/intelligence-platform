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

# --locked asserts uv.lock is current: add a dependency to pyproject.toml and
# forget `uv lock`, and the build fails here rather than shipping an image that
# silently lacks the package. (--frozen would only skip re-resolution, not check
# staleness — that reintroduces the exact drift this block exists to prevent.)
RUN uv sync --no-dev --locked
# Must come after `uv sync`, and nothing may `uv sync` again afterwards: the
# model is installed by URL and is deliberately absent from uv.lock, so a later
# sync prunes it as an unlocked package and NLP extraction silently loses its
# spaCy model. `uv run` (the CMD, and start.sh) does not prune — verified.
RUN uv pip install --python .venv/bin/python https://github.com/explosion/spacy-models/releases/download/en_core_web_sm-3.8.0/en_core_web_sm-3.8.0-py3-none-any.whl

# Install Chromium for crawl4ai headless browser
RUN uv run crawl4ai-setup

EXPOSE 8000

CMD ["uv", "run", "uvicorn", "intel_platform.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
