# Bootstrap Scripts

Python scripts to create sample databases for testing Cataloger.

## Scripts

### create_sample_db.py

Creates a realistic e-commerce database with:
- **users** table - 1,000 customers with contact info, signup dates, spending history
- **products** table - 200 products across 5 categories
- **orders** table - 3,000 orders with various statuses
- **order_items** table - Line items for each order

**Data Quality Features:**
- Some users missing email or phone (5-10% null rate)
- Some products out of stock
- Some orders missing shipping address
- Realistic temporal patterns (recent growth)
- Categorical distributions to analyze

**Usage:**
```bash
uv run python python_bootstrap_scripts/create_sample_db.py
```

**Output:**
- Database: `data/sample_ecommerce.duckdb`
- Connection: `duckdb:///data/sample_ecommerce.duckdb`

### create_timeseries_db.py

Creates a time-series database for testing temporal analysis:
- **daily_metrics** table - 90 days of application metrics
- **system_events** table - System events and logs

**Features:**
- Growth trend over 90 days (20% increase)
- Weekly seasonality (lower on weekends)
- **Anomalies for detection:**
  - Error rate spike around day 60 (0.15-0.25 vs normal 0.001-0.005)
  - API latency spike around day 30 (300-500ms vs normal 80-150ms)
- Multiple event types (logins, errors, deployments)

**Usage:**
```bash
uv run python python_bootstrap_scripts/create_timeseries_db.py
```

**Output:**
- Database: `data/sample_timeseries.duckdb`
- Connection: `duckdb:///data/sample_timeseries.duckdb`

## Quick Start

Create both databases:

```bash
# Create sample databases
uv run python python_bootstrap_scripts/create_sample_db.py
uv run python python_bootstrap_scripts/create_timeseries_db.py

# Verify they exist
ls -lh data/*.duckdb
```

## Testing with Cataloger

### E-commerce Database

```bash
# Generate catalog
uv run cataloger catalog \
  --db-conn "duckdb:///data/sample_ecommerce.duckdb" \
  --table users --table products --table orders --table order_items \
  --s3-prefix "test/ecommerce"

# View in browser
open http://localhost:8000/database/current?prefix=test/ecommerce
```

### Time-series Database

```bash
# Generate catalog
uv run cataloger catalog \
  --db-conn "duckdb:///data/sample_timeseries.duckdb" \
  --table daily_metrics --table system_events \
  --s3-prefix "test/timeseries"

# View in browser
open http://localhost:8000/database/current?prefix=test/timeseries
```

## What the Agent Should Discover

### E-commerce Database

**Schema Analysis:**
- 4 tables with foreign key relationships
- Mixed data types (integers, decimals, dates, timestamps, booleans)
- Nullable columns

**Data Patterns:**
- User growth over time (signup_date distribution)
- Active vs inactive users (85% active)
- Order status distribution (60% delivered, 10% cancelled)
- Product categories and pricing ranges
- Discount code usage patterns

**Data Quality Issues:**
- ~5% of users missing email
- ~10% of users missing phone
- ~2% of orders missing shipping address
- Some products with no supplier

### Time-series Database

**Temporal Trends:**
- 20% growth over 90 days
- Weekly seasonality (weekends lower)
- Revenue correlated with active users

**Anomalies:**
- **Day 60 incident:** Error rate spike from 0.001 to 0.20 (20x increase)
- **Day 30 incident:** API latency spike from 100ms to 400ms (4x increase)

**Event Patterns:**
- Error frequency by source
- Event severity distribution
- Deployment frequency

## Customizing

Edit the scripts to:
- Change number of rows (`num_users=1000`, `days=90`)
- Adjust data distributions
- Add new tables
- Introduce different anomalies
- Change data quality issues

Example:
```python
# Create larger database
populate_users(conn, num_users=10000)
populate_orders(conn, num_orders=50000)
```

## Dependencies

These scripts require:
- `duckdb` - Installed via project dependencies

Already included in `pyproject.toml`:
```toml
dependencies = [
    "ibis-framework[duckdb]>=9.5.0",
    ...
]
```

DuckDB is included as part of ibis extras.

## Output

Databases are created in `data/` directory (gitignored):
```
data/
├── sample_ecommerce.duckdb
└── sample_timeseries.duckdb
```

Each database includes:
- Schema (tables, columns, types)
- Sample data with realistic patterns
- Data quality issues for testing
- Temporal patterns for trend analysis
