# ── Stage 1: Frontend build ──
FROM node:20-slim AS frontend-build
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci --legacy-peer-deps
COPY frontend/ .
RUN rm -f .env.local .env.production .env
RUN mkdir -p public
ENV NEXT_PUBLIC_API_URL=""
RUN npm run build

# ── Stage 2: Backend + Frontend on single port ──
FROM python:3.12-slim

WORKDIR /app

# Install Node.js first (needed for frontend server)
RUN apt-get update && apt-get install -y --no-install-recommends nodejs curl && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Install backend
COPY backend/pyproject.toml ./
COPY backend/src/ src/
RUN uv sync --no-dev
RUN uv pip install --python .venv/bin/python https://github.com/explosion/spacy-models/releases/download/en_core_web_sm-3.8.0/en_core_web_sm-3.8.0-py3-none-any.whl

# Copy frontend standalone build
COPY --from=frontend-build /app/frontend/.next/standalone /app/frontend-server
COPY --from=frontend-build /app/frontend/.next/static /app/frontend-server/.next/static

COPY start.sh /app/start.sh
RUN chmod +x /app/start.sh

EXPOSE ${PORT:-8000}

ENTRYPOINT ["/app/start.sh"]
