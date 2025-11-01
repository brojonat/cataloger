#!/usr/bin/env bash
# Bootstrap sample databases for testing

set -e

echo "Creating sample databases..."
echo ""

# Create e-commerce database
echo "1. Creating e-commerce database..."
uv run python python_bootstrap_scripts/create_sample_db.py

echo ""

# Create time-series database
echo "2. Creating time-series database..."
uv run python python_bootstrap_scripts/create_timeseries_db.py

echo ""
echo "="*60
echo "Sample databases created successfully!"
echo "="*60
echo ""
echo "Databases created:"
echo "  - data/sample_ecommerce.duckdb"
echo "  - data/sample_timeseries.duckdb"
echo ""
echo "Test with:"
echo "  ./scripts/catalog-ecommerce.sh"
echo "  ./scripts/catalog-timeseries.sh"
