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

EXPOSE 8000

# Start both: frontend on internal port 3000, backend on 8000
# Railway exposes 8000 via the domain
ENTRYPOINT ["sh", "-c", "cd /app/frontend-server && HOSTNAME=0.0.0.0 PORT=3000 node server.js & cd /app && exec uv run uvicorn intel_platform.api.app:app --host 0.0.0.0 --port 8000"]
