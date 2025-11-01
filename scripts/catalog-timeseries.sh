#!/usr/bin/env bash
# Generate catalog for time-series database

set -e

DB_PATH="data/sample_timeseries.duckdb"

if [ ! -f "$DB_PATH" ]; then
    echo "Error: Database not found at $DB_PATH"
    echo "Run: ./scripts/bootstrap-db.sh"
    exit 1
fi

echo "Generating catalog for time-series database..."
echo ""

# Get absolute path
DB_ABS_PATH=$(cd "$(dirname "$DB_PATH")" && pwd)/$(basename "$DB_PATH")

uv run cataloger catalog \
  --db-conn "duckdb:///${DB_ABS_PATH}" \
  --tables "daily_metrics,system_events" \
  --s3-prefix "test/timeseries"

echo ""
echo "Catalog generated!"
echo "View at: http://localhost:8000/database/current?prefix=test/timeseries"
