#!/bin/bash

# Get the directory of this script
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$SCRIPT_DIR/backend"

echo "Checking for any processes listening on port 8000..."
if command -v fuser >/dev/null 2>&1; then
    fuser -k 8000/tcp 2>/dev/null && echo "Killed existing process on port 8000 using fuser." || true
elif command -v lsof >/dev/null 2>&1; then
    lsof -t -i:8000 | xargs kill -9 2>/dev/null && echo "Killed existing process on port 8000 using lsof." || true
fi

# Check if the virtual environment exists
if [ -d "$BACKEND_DIR/venv" ]; then
    echo "Activating virtual environment and starting server..."
    cd "$BACKEND_DIR"
    exec ./venv/bin/python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
else
    echo "Virtual environment not found at $BACKEND_DIR/venv"
    echo "Attempting to run using system python/uvicorn..."
    cd "$BACKEND_DIR"
    exec uvicorn main:app --host 0.0.0.0 --port 8000 --reload
fi
