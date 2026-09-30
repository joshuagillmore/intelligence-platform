#!/usr/bin/env bash
# Entrypoint of the single-image deploy (root Dockerfile; what Railway runs).
#
# Runs two processes and supervises both:
#   - the Next.js standalone server on 127.0.0.1:3000 (internal only; the
#     backend proxies page requests to it, see api/app.py), and
#   - the FastAPI backend (uvicorn) on 0.0.0.0:8000, the one exposed port.
#
# If either process exits, the other is stopped and this script exits
# non-zero, so the platform's restart policy brings the whole container back
# rather than leaving an API with no UI (or a UI with no API) running. SIGTERM
# and SIGINT are forwarded to both children for a clean shutdown.
#
# The port is fixed at 8000: EXPOSE, the HEALTHCHECK and the Railway domain
# all target it, so a platform-injected PORT is deliberately not read.
set -u

FRONTEND_DIR=/app/frontend-server
BACKEND_DIR=/app

cd "$FRONTEND_DIR"
HOSTNAME=127.0.0.1 PORT=3000 node server.js &
frontend_pid=$!

cd "$BACKEND_DIR"
uvicorn intel_platform.api.app:app --host 0.0.0.0 --port 8000 &
backend_pid=$!

stop_children() {
    kill -TERM "$frontend_pid" "$backend_pid" 2>/dev/null
    wait "$frontend_pid" "$backend_pid" 2>/dev/null
}

trap 'echo "start.sh: shutdown signal received; stopping frontend and backend" >&2; stop_children; exit 143' TERM INT

# Block until the first child exits (bash >= 5.1: wait -n with pids).
wait -n "$frontend_pid" "$backend_pid"
status=$?

if kill -0 "$frontend_pid" 2>/dev/null; then
    died="backend (uvicorn)"
else
    died="frontend (next server.js)"
fi
echo "start.sh: $died exited with status $status; stopping the other process" >&2
stop_children

# A child that exits 0 is still a failure here: neither should ever stop.
if [ "$status" -eq 0 ]; then
    status=1
fi
exit "$status"
