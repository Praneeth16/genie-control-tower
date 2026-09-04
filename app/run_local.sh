#!/usr/bin/env bash
# Local end-to-end run: build the frontend to static, then serve API + static via uvicorn.
# Auth is via the Databricks CLI profile (set in .env or the environment).
set -euo pipefail
cd "$(dirname "$0")"

export DATABRICKS_CONFIG_PROFILE="${DATABRICKS_CONFIG_PROFILE:-<your-profile>}"

echo "==> Building frontend (npm)…"
( cd frontend && npm install --silent && npm run build )

echo "==> Installing backend deps…"
pip3 install --quiet --user -r requirements.txt

echo "==> Starting uvicorn on http://localhost:8000 (profile: $DATABRICKS_CONFIG_PROFILE)"
cd backend
exec python3 -m uvicorn main:app --host 0.0.0.0 --port 8000
