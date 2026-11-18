#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

cleanup() {
  echo ""
  echo "Stopping FretFlow servers..."
  kill "${BACKEND_PID:-}" "${FRONTEND_PID:-}" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

if [ ! -x "$ROOT_DIR/backend/.venv/bin/uvicorn" ]; then
  echo "📦 Installing Python backend dependencies with uv..."
  (cd "$ROOT_DIR/backend" && uv sync)
fi

if [ ! -d "$ROOT_DIR/frontend/node_modules" ]; then
  echo "📦 Installing Frontend dependencies with pnpm..."
  (cd "$ROOT_DIR/frontend" && pnpm install)
fi

echo "🎸 Starting FretFlow Backend on http://127.0.0.1:8000 ..."
(
  cd "$ROOT_DIR/backend"
  exec ./.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
) &
BACKEND_PID=$!

echo "🎤 Starting FretFlow Studio UI on http://127.0.0.1:5173 (http://localhost:5173) ..."
(
  cd "$ROOT_DIR/frontend"
  exec pnpm dev --host 127.0.0.1
) &
FRONTEND_PID=$!

wait
