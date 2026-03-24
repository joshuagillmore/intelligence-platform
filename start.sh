#!/bin/sh
# Start frontend on internal port 3000 in background
cd /app/frontend-server && HOSTNAME=0.0.0.0 PORT=3000 node server.js &

# Start backend on Railway's PORT (or default 8000)
cd /app
exec uv run uvicorn intel_platform.api.app:app --host 0.0.0.0 --port "${PORT:-8000}"
