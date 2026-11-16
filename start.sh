#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "=================================================================="
echo " CourtVision AI: NCAA Broadcast Editor Intelligence & Agents"
echo "=================================================================="
echo "Project Directory: ${ROOT_DIR}"

# Clean up any stale or suspended (Ctrl+Z) processes occupying ports 8000 or 5173-5175
STALE_PIDS="$(lsof -ti :8000,:5173,:5174,:5175 2>/dev/null || true)"
if [ -n "${STALE_PIDS}" ]; then
  echo "Cleaning up stale processes on ports 8000/5173..."
  echo "${STALE_PIDS}" | xargs kill -9 2>/dev/null || true
  sleep 0.5
fi

if ! "${ROOT_DIR}/backend/.venv/bin/uvicorn" --version >/dev/null 2>&1; then
  echo "[1/3] Setting up Python virtual environment in backend/.venv..."
  python3 -m venv --clear "${ROOT_DIR}/backend/.venv"
  "${ROOT_DIR}/backend/.venv/bin/pip" install --upgrade pip
  "${ROOT_DIR}/backend/.venv/bin/pip" install -r "${ROOT_DIR}/backend/requirements.txt"
fi

if [ ! -d "${ROOT_DIR}/frontend/node_modules" ]; then
  echo "[2/3] Installing frontend dependencies..."
  (cd "${ROOT_DIR}/frontend" && NPM_CONFIG_CACHE=/tmp/npm-cache npm install)
fi

echo "[3/3] Starting FastAPI Backend (http://127.0.0.1:8000) and Vite Studio UI (http://127.0.0.1:5173)..."

trap 'kill 0' EXIT

(
  cd "${ROOT_DIR}/backend"
  ./.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
) &

(
  cd "${ROOT_DIR}/frontend"
  npm run dev -- --host 127.0.0.1 --port 5173 --strictPort
) &

wait
