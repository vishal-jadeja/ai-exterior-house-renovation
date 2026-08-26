#!/bin/sh
# Hugging Face Space: one free container runs migrations + seed, then API and worker together.
set -e
alembic upgrade head
python -m app.seed
python -m app.worker &
WORKER=$!
uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-7860}" &
API=$!
# If either process dies, exit non-zero so the Space restarts the container.
while kill -0 "$WORKER" 2>/dev/null && kill -0 "$API" 2>/dev/null; do sleep 5; done
kill "$WORKER" "$API" 2>/dev/null || true
exit 1
