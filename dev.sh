#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

cleanup() {
  echo ""
  echo "Stopping FretFlow servers..."
  kill "${BACKEND_PID:-}" "${FRONTEND_PID:-}" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

echo "🎸 Starting FretFlow Backend on http://127.0.0.1:8000 ..."
(
  cd "$ROOT_DIR/backend"
  exec ./.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
) &
BACKEND_PID=$!

echo "🎤 Starting FretFlow Studio UI on http://localhost:5173 ..."
(
  cd "$ROOT_DIR/frontend"
  exec pnpm dev --host 127.0.0.1 --port 5173
) &
FRONTEND_PID=$!

wait
