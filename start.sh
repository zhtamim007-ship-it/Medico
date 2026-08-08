#!/usr/bin/env bash
# Start the AI YouTube Transcriber.
# Usage:
#   ./start.sh           # installs deps on first run, then starts
#   PORT=9000 ./start.sh # custom port

set -euo pipefail
cd "$(dirname "$0")"

PORT="${PORT:-8000}"
HOST="${HOST:-0.0.0.0}"

# 1. python venv
if [ ! -d ".venv" ]; then
  echo "→ Creating Python virtual env (.venv)"
  python3 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate

# 2. install backend deps
echo "→ Installing backend dependencies"
pip install --quiet --upgrade pip
pip install --quiet -r backend/requirements.txt

# 3. .env
if [ ! -f "backend/.env" ]; then
  echo "→ backend/.env not found, copying from .env.example"
  cp backend/.env.example backend/.env
  echo "  ⚠️  Edit backend/.env and add your OPENAI_API_KEY, then re-run this script."
  exit 1
fi

# 4. ffmpeg check
if ! command -v ffmpeg >/dev/null 2>&1; then
  echo "✗ ffmpeg not found. Install it first (apt: sudo apt install ffmpeg / brew: brew install ffmpeg)."
  exit 1
fi

# 5. run
echo "→ Starting server on http://${HOST}:${PORT}"
exec uvicorn backend.main:app --host "${HOST}" --port "${PORT}" --app-dir . --reload
