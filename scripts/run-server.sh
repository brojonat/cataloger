#!/usr/bin/env bash
# Run the Cataloger server

set -e

# Check if .env.server exists
if [ ! -f ".env.server" ]; then
    echo "Error: .env.server not found"
    echo "Run: ./scripts/setup-env.sh"
    exit 1
fi

# Source environment
set -a
source .env.server
set +a

echo "Starting Cataloger server..."
echo "API: http://localhost:${PORT:-8000}"
echo "UI:  http://localhost:${PORT:-8000}/"
echo ""

uv run uvicorn server.main:app --host "${HOST:-0.0.0.0}" --port "${PORT:-8000}" --reload
