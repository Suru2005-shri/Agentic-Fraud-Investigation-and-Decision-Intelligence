#!/usr/bin/env bash
# Start ARGUS locally: creates a virtual environment, installs dependencies, runs the server.
set -e
cd "$(dirname "$0")"
[ -d .venv ] || python3 -m venv .venv
. .venv/bin/activate
pip install -q -r requirements.txt
exec uvicorn backend.main:app --host 0.0.0.0 --port "${PORT:-8000}"
