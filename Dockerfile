# Frontend build stage
FROM node:20-slim AS frontend-build
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ .
RUN npm run build

# Backend stage
FROM python:3.12-slim

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy backend
COPY backend/pyproject.toml ./
COPY backend/src/ src/
RUN uv sync --no-dev
RUN uv run python -m spacy download en_core_web_sm

# Copy frontend build
COPY --from=frontend-build /app/frontend/out ./static

EXPOSE 8000

CMD ["uv", "run", "uvicorn", "intel_platform.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
