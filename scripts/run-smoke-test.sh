#!/bin/bash
#
# Run smoke tests for Cataloger service
#
# Usage:
#   ./scripts/run-smoke-test.sh
#
# Environment:
#   CATALOGER_API_URL - Service URL (default: http://localhost:8000)
#   AUTH_SECRET - Will be loaded from .env.server if not set
#   DB_PATH - Test database (default: data/sample_ecommerce.duckdb)

set -e

# Change to project root
cd "$(dirname "$0")/.."

echo "🧪 Cataloger Smoke Test"
echo "======================="
echo

# Check if database exists
DB_PATH="${DB_PATH:-data/sample_ecommerce.duckdb}"
if [ ! -f "$DB_PATH" ]; then
    echo "❌ Database not found: $DB_PATH"
    echo "   Creating sample database..."
    ./scripts/bootstrap-db.sh
    echo
fi

# Check if server is running
API_URL="${CATALOGER_API_URL:-http://localhost:8000}"
echo "🔍 Checking if server is running at $API_URL..."

if ! curl -s -f "$API_URL/healthz" > /dev/null 2>&1; then
    echo "❌ Server not responding at $API_URL"
    echo "   Start the server first:"
    echo "   ./scripts/run-server.sh"
    exit 1
fi

echo "✅ Server is running"
echo

# Run smoke tests
echo "🚀 Running smoke tests..."
echo

uv run python scripts/smoke_test.py

echo
echo "🎉 Smoke tests complete!"
