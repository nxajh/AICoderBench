#!/bin/bash
set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"
mkdir -p data results
echo "Starting AICoderBench on :8000 ..."
exec python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload "$@"
