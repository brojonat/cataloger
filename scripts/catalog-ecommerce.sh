#!/usr/bin/env bash
# Generate catalog for e-commerce database

set -e

DB_PATH="data/sample_ecommerce.duckdb"

if [ ! -f "$DB_PATH" ]; then
    echo "Error: Database not found at $DB_PATH"
    echo "Run: ./scripts/bootstrap-db.sh"
    exit 1
fi

echo "Generating catalog for e-commerce database..."
echo ""

# Container path (data/ is mounted to /data in container)
CONTAINER_DB_PATH="/data/sample_ecommerce.duckdb"

uv run cataloger catalog \
  --db-conn "duckdb:///${CONTAINER_DB_PATH}" \
  --tables "users,products,orders,order_items" \
  --s3-prefix "test/ecommerce"

echo ""
echo "Catalog generated!"
echo "View at: http://localhost:8000/database/current?prefix=test/ecommerce"
