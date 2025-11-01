#!/bin/bash
#
# Stop local development services
#
# Usage:
#   ./scripts/stop-dev-services.sh [--clean]
#
# Options:
#   --clean    Remove volumes (deletes all stored data)

set -e

cd "$(dirname "$0")/.."

CLEAN=false
if [ "$1" = "--clean" ]; then
    CLEAN=true
fi

echo "🛑 Stopping local development services..."
echo

# Use 'docker compose' (v2) if available, otherwise 'docker-compose' (v1)
if docker compose version &> /dev/null 2>&1; then
    COMPOSE_CMD="docker compose"
else
    COMPOSE_CMD="docker-compose"
fi

# Stop services
$COMPOSE_CMD -f docker-compose.dev.yaml down

if [ "$CLEAN" = true ]; then
    echo "🧹 Removing volumes (data will be deleted)..."
    $COMPOSE_CMD -f docker-compose.dev.yaml down -v
    echo "✅ Volumes removed"
else
    echo "💾 Volumes preserved (use --clean to remove data)"
fi

echo
echo "✅ Development services stopped"
