#!/usr/bin/env bash
# Entrypoint of the single-image deploy (root Dockerfile; what Railway runs).
#
# Runs three processes and supervises all of them:
#   - the Next.js standalone server on 127.0.0.1:3000 (internal only; the
#     backend proxies page requests to it, see api/app.py),
#   - the FastAPI backend (uvicorn) on 0.0.0.0:8000, the one exposed port, and
#   - the collection worker (python -m intel_platform.worker), which executes
#     the collection runs the API enqueues in collection_jobs.
#
# COLLECTION_WORKER_MODE defaults to `worker` here, so the API only enqueues
# and collection (Chromium, extraction) runs in the worker, not in the process
# serving requests. Set it to `inline` to run collection in the API process
# instead; the worker then finds nothing queued and idles.
#
# If any process exits, the others are stopped and this script exits
# non-zero, so the platform's restart policy brings the whole container back
# rather than leaving an API with no UI, a UI with no API, or collection runs
# queued with no worker to take them. SIGTERM and SIGINT are forwarded to all
# three for a clean shutdown (the worker fails the job in hand rather than
# leaving it running).
#
# The port is fixed at 8000: EXPOSE, the HEALTHCHECK and the Railway domain
# all target it, so a platform-injected PORT is deliberately not read.
# FRONTEND_DIR and BACKEND_DIR exist for testing this script outside the image.
set -u

FRONTEND_DIR=${FRONTEND_DIR:-/app/frontend-server}
BACKEND_DIR=${BACKEND_DIR:-/app}
export COLLECTION_WORKER_MODE="${COLLECTION_WORKER_MODE:-worker}"

cd "$FRONTEND_DIR" || exit 1
HOSTNAME=127.0.0.1 PORT=3000 node server.js &
frontend_pid=$!

cd "$BACKEND_DIR" || exit 1
uvicorn intel_platform.api.app:app --host 0.0.0.0 --port 8000 &
backend_pid=$!

python -m intel_platform.worker &
worker_pid=$!

stop_children() {
    kill -TERM "$frontend_pid" "$backend_pid" "$worker_pid" 2>/dev/null
    wait "$frontend_pid" "$backend_pid" "$worker_pid" 2>/dev/null
}

trap 'echo "start.sh: shutdown signal received; stopping frontend, backend and worker" >&2; stop_children; exit 143' TERM INT

# Block until the first child exits (bash >= 5.1: wait -n with pids).
wait -n "$frontend_pid" "$backend_pid" "$worker_pid"
status=$?

# The one that exited has been reaped, so it alone fails kill -0.
died=""
kill -0 "$frontend_pid" 2>/dev/null || died="${died:+$died, }frontend (next server.js)"
kill -0 "$backend_pid" 2>/dev/null || died="${died:+$died, }backend (uvicorn)"
kill -0 "$worker_pid" 2>/dev/null || died="${died:+$died, }collection worker"
echo "start.sh: ${died:-a child} exited with status $status; stopping the others" >&2
stop_children

# A child that exits 0 is still a failure here: none of them should ever stop.
if [ "$status" -eq 0 ]; then
    status=1
fi
exit "$status"
