# ── Stage 1: Frontend build ──
# Node 22 (active LTS). The runtime stage copies this same binary, so the
# Next.js server runs on exactly the Node it was built with.
FROM node:22-slim AS frontend-build
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci --legacy-peer-deps
COPY frontend/ .
RUN rm -f .env.local .env.production .env
RUN mkdir -p public
ENV NEXT_PUBLIC_API_URL=""
RUN npm run build

# ── Stage 2: Backend + Frontend on single port ──
# Python 3.11 matches backend/.python-version and the version CI tests on.
FROM python:3.11-slim

WORKDIR /app

# Node for the Next.js standalone server: the build stage's binary, not
# Debian's apt `nodejs` (an unpinned, different major from the one that built
# the app). curl is for the HEALTHCHECK.
COPY --from=frontend-build /usr/local/bin/node /usr/local/bin/node
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/* \
    && node --version

COPY --from=ghcr.io/astral-sh/uv:0.12.21 /uv /usr/local/bin/uv

# The app runs as this unprivileged user. It owns only what the app writes:
# its home (crawl4ai's ~/.crawl4ai) and /data/attack, where the ATT&CK and
# CWE/CAPEC downloads are cached (services/attack resolves that path from
# the source tree, which puts it at /data/attack in this image). The code and
# the virtualenv stay root-owned and read-only to it.
RUN useradd --create-home --uid 10001 --shell /usr/sbin/nologin app \
    && mkdir -p /data/attack && chown app:app /data/attack

# Install backend. uv.lock ships with pyproject.toml so the production image
# installs the exact versions the test suite ran against; without it `uv sync`
# re-resolves the ranges at build time and the deployed dependency set drifts
# from the tested one (measured: 67 of 167 packages). --locked makes a stale
# lock a build failure instead of a silent re-resolve.
COPY backend/pyproject.toml backend/uv.lock ./
COPY backend/src/ src/
# Alembic migrations: init_db runs `alembic upgrade head` at boot, reading
# alembic.ini and the versions from /app, the layout `uv run` expects.
COPY backend/alembic/ alembic/
COPY backend/alembic.ini alembic.ini
RUN uv sync --no-dev --locked
# Must follow `uv sync`, and nothing may sync again after it: the model is
# installed by URL and is deliberately not in uv.lock, so a later `uv sync`
# prunes it. UV_NO_SYNC below stops `uv run` from syncing at all.
RUN uv pip install --python .venv/bin/python https://github.com/explosion/spacy-models/releases/download/en_core_web_sm-3.8.0/en_core_web_sm-3.8.0-py3-none-any.whl

# Chromium for crawl4ai's headless crawler (collection/crawler.py). Without it
# every crawl fails at browser launch. Installed explicitly through playwright
# so a failed download fails the build: crawl4ai-setup catches the error from
# its own playwright call and only logs a warning, so on its own it can exit 0
# with no browser. PLAYWRIGHT_BROWSERS_PATH is a shared location rather than
# root's ~/.cache, and is read again at runtime to find the browser.
ENV PLAYWRIGHT_BROWSERS_PATH=/opt/ms-playwright
RUN .venv/bin/playwright install --with-deps chromium

# Copy frontend standalone build (owned by the app user: Next writes .next/cache)
COPY --from=frontend-build --chown=app:app /app/frontend/.next/standalone /app/frontend-server
COPY --from=frontend-build --chown=app:app /app/frontend/.next/static /app/frontend-server/.next/static

COPY start.sh /app/start.sh
RUN chmod 0755 /app/start.sh

# The venv's binaries (uvicorn, python) first on PATH; `uv run` in this image
# uses the installed environment as-is and never re-syncs it.
ENV PATH="/app/.venv/bin:${PATH}" \
    UV_NO_SYNC=1

USER app

# crawl4ai's home-directory and database init, as the user that will use it.
# CRAWL4AI_MODE=api skips setup's own (--force) chromium download and its
# patchright install: the browser is already installed above, and the crawler
# never uses undetected mode.
RUN CRAWL4AI_MODE=api crawl4ai-setup

EXPOSE 8000

# Liveness: /health answers 200 whenever uvicorn is serving (its body reports
# "degraded" when Neo4j or a configured Ollama is down).
HEALTHCHECK --interval=30s --timeout=10s --start-period=90s --retries=3 \
    CMD curl -fsS -o /dev/null http://127.0.0.1:8000/health || exit 1

# start.sh runs the Next.js server (internal 127.0.0.1:3000), uvicorn
# (0.0.0.0:8000, the port Railway exposes; it proxies page requests to Next)
# and the collection worker (python -m intel_platform.worker), and exits
# non-zero as soon as any of them dies, so the platform restarts the container
# instead of serving part of an app.
ENTRYPOINT ["/app/start.sh"]
