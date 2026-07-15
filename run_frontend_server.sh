#!/bin/bash

# Get the directory of this script
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FRONTEND_DIR="$SCRIPT_DIR/frontend"

echo "Checking for any processes listening on port 5173..."
if command -v fuser >/dev/null 2>&1; then
    fuser -k 5173/tcp 2>/dev/null && echo "Killed existing process on port 5173 using fuser." || true
elif command -v lsof >/dev/null 2>&1; then
    lsof -t -i:5173 | xargs kill -9 2>/dev/null && echo "Killed existing process on port 5173 using lsof." || true
fi

echo "Starting PodPilot frontend server..."

# Load NVM and use Node v22
export NVM_DIR="$HOME/.nvm"
if [ -s "$NVM_DIR/nvm.sh" ]; then
    . "$NVM_DIR/nvm.sh"
    nvm use 22 >/dev/null
fi

# Check if node_modules exists, if not install dependencies
if [ ! -d "$FRONTEND_DIR/node_modules" ]; then
    echo "node_modules not found in $FRONTEND_DIR. Installing dependencies..."
    cd "$FRONTEND_DIR"
    npm install
else
    cd "$FRONTEND_DIR"
fi

# Run the dev server
exec npm run dev
