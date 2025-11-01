# Bootstrap & Testing Guide

Complete guide to setting up Cataloger with sample databases for testing.

## Directory Structure

```
cataloger/
├── python_bootstrap_scripts/    # Python scripts to create sample databases
│   ├── create_sample_db.py      # E-commerce database
│   ├── create_timeseries_db.py  # Time-series metrics
│   └── README.md
├── scripts/                      # Bash scripts for development workflows
│   ├── setup-env.sh             # Environment setup
│   ├── bootstrap-db.sh          # Create databases
│   ├── build-container.sh       # Build Docker image
│   ├── run-server.sh            # Start server
│   ├── catalog-ecommerce.sh     # Catalog e-commerce DB
│   ├── catalog-timeseries.sh    # Catalog time-series DB
│   └── README.md
└── data/                         # Generated databases (gitignored)
    ├── sample_ecommerce.duckdb
    └── sample_timeseries.duckdb
```

## Complete Workflow

### 1. Initial Setup

```bash
# Install dependencies
uv pip install -e ".[dev]"

# Set up environment
./scripts/setup-env.sh

# Edit .env.server with your API keys
vim .env.server
```

Required configuration:
- `LLM_API_KEY` - Your Anthropic API key
- `S3_BUCKET` - Your S3 bucket name
- `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` - AWS credentials
- `AUTH_SECRET` - Random secret for JWT signing

### 2. Build Container

```bash
./scripts/build-container.sh
```

Creates `cataloger-agent:latest` with Python, ibis, and database drivers.

### 3. Create Sample Databases

```bash
./scripts/bootstrap-db.sh
```

Creates two sample databases:

**E-commerce (`data/sample_ecommerce.duckdb`):**
- 1,000 users
- 200 products
- 3,000 orders
- 10,000+ order items

**Time-series (`data/sample_timeseries.duckdb`):**
- 90 days of metrics
- Growth trends
- Weekly seasonality
- Anomalies (error spikes, latency issues)

### 4. Start Server

In one terminal:

```bash
./scripts/run-server.sh
```

Server available at:
- UI: http://localhost:8000
- API: http://localhost:8000/docs
- Health: http://localhost:8000/healthz

### 5. Generate Catalogs

In another terminal:

```bash
# E-commerce database
./scripts/catalog-ecommerce.sh

# Time-series database
./scripts/catalog-timeseries.sh
```

Both scripts:
- Generate catalogs using the agent
- Save to S3 under `test/` prefix
- Print viewing URL

### 6. View Catalogs

Open browser:

**E-commerce:**
- Latest: http://localhost:8000/database/current?prefix=test/ecommerce
- History: http://localhost:8000/database/timelapse?prefix=test/ecommerce

**Time-series:**
- Latest: http://localhost:8000/database/current?prefix=test/timeseries
- History: http://localhost:8000/database/timelapse?prefix=test/timeseries

## Sample Databases

### E-commerce Database

**Schema:**
```sql
users (
    user_id, email, first_name, last_name, phone,
    country, state, city, signup_date, is_active,
    total_orders, total_spent
)

products (
    product_id, name, category, subcategory,
    price, cost, stock_quantity, supplier, created_at
)

orders (
    order_id, user_id, order_date, status, total_amount,
    shipping_address, payment_method, discount_code,
    shipped_date, delivered_date
)

order_items (
    order_item_id, order_id, product_id,
    quantity, unit_price, discount
)
```

**What agents discover:**
- User growth over time
- Active/inactive user patterns (85% active)
- Product distribution across categories
- Order status breakdown (60% delivered, 10% cancelled)
- Null data patterns (~5% missing emails, ~10% missing phones)
- Revenue by category
- Top products
- Seasonal ordering patterns

### Time-series Database

**Schema:**
```sql
daily_metrics (
    metric_date, active_users, new_signups, page_views,
    revenue, avg_session_duration, error_rate, api_latency_ms
)

system_events (
    event_id, event_timestamp, event_type, severity,
    source, message, user_id
)
```

**What agents discover:**
- 20% growth trend over 90 days
- Weekly seasonality (weekends lower)
- **Anomaly 1 (day 60):** Error rate spike 0.001 → 0.20 (20x)
- **Anomaly 2 (day 30):** API latency spike 100ms → 400ms (4x)
- Event patterns by type and severity
- System health over time

## Development Workflow

### Daily Development

```bash
# Terminal 1: Server
./scripts/run-server.sh

# Terminal 2: Generate catalogs
./scripts/catalog-ecommerce.sh
./scripts/catalog-timeseries.sh

# View in browser
open http://localhost:8000
```

### After Prompt Changes

```bash
# Re-encode prompts
./scripts/setup-env.sh

# Restart server (Ctrl+C, then)
./scripts/run-server.sh
```

### Testing Feedback Loop

Generate multiple catalogs to see script evolution:

```bash
# Run 1
./scripts/catalog-ecommerce.sh

# Run 2 - agent sees previous script
./scripts/catalog-ecommerce.sh

# Run 3 - agent refines further
./scripts/catalog-ecommerce.sh

# Compare scripts in S3
aws s3 ls s3://your-bucket/test/ecommerce/
```

### Recreate Databases

To regenerate with fresh data:

```bash
# Delete old databases
rm data/*.duckdb

# Recreate
./scripts/bootstrap-db.sh
```

## Script Reference

### Python Bootstrap Scripts

```bash
# Create e-commerce database
uv run python python_bootstrap_scripts/create_sample_db.py

# Create time-series database
uv run python python_bootstrap_scripts/create_timeseries_db.py
```

### Bash Development Scripts

```bash
./scripts/setup-env.sh          # Setup environment
./scripts/bootstrap-db.sh        # Create databases
./scripts/build-container.sh     # Build Docker image
./scripts/run-server.sh          # Start server
./scripts/catalog-ecommerce.sh   # Catalog e-commerce
./scripts/catalog-timeseries.sh  # Catalog time-series
```

## Customizing Sample Data

Edit Python scripts to change:

**Number of records:**
```python
# In create_sample_db.py
populate_users(conn, num_users=10000)  # Default: 1000
populate_orders(conn, num_orders=50000)  # Default: 3000
```

**Date ranges:**
```python
# In create_timeseries_db.py
populate_metrics(conn, days=180)  # Default: 90
```

**Data quality issues:**
```python
# In create_sample_db.py
# Adjust null rate
email = ... if random.random() > 0.1 else None  # 10% null
```

**Anomalies:**
```python
# In create_timeseries_db.py
# Change anomaly periods
if 40 <= day <= 45:  # Different period
    error_rate = round(random.uniform(0.20, 0.30), 4)  # Higher spike
```

## Testing Specific Scenarios

### Test Schema Evolution

```bash
# Generate catalog
./scripts/catalog-ecommerce.sh

# Modify database (add column)
echo "ALTER TABLE users ADD COLUMN loyalty_points INTEGER" | \
  duckdb data/sample_ecommerce.duckdb

# Generate another catalog
./scripts/catalog-ecommerce.sh

# View timelapse to see schema change
open http://localhost:8000/database/timelapse?prefix=test/ecommerce
```

### Test Data Quality Changes

```bash
# Generate catalog
./scripts/catalog-ecommerce.sh

# Update data (introduce nulls)
echo "UPDATE users SET email = NULL WHERE user_id % 5 = 0" | \
  duckdb data/sample_ecommerce.duckdb

# Generate another catalog
./scripts/catalog-ecommerce.sh

# Summary agent should detect increased null rate
```

### Test Volume Changes

```bash
# Generate catalog
./scripts/catalog-ecommerce.sh

# Add more data
uv run python -c "
import duckdb
conn = duckdb.connect('data/sample_ecommerce.duckdb')
# Add 500 more orders
conn.execute('INSERT INTO orders SELECT ...')
conn.close()
"

# Generate another catalog
./scripts/catalog-ecommerce.sh
```

## CI/CD Testing

Use sample databases in CI:

```yaml
# .github/workflows/test.yml
- name: Setup databases
  run: ./scripts/bootstrap-db.sh

- name: Run tests
  run: make test

- name: Test catalog generation
  run: |
    ./scripts/catalog-ecommerce.sh
    ./scripts/catalog-timeseries.sh
```

## Troubleshooting

### Database already exists

```bash
rm data/*.duckdb
./scripts/bootstrap-db.sh
```

### Container not built

```bash
./scripts/build-container.sh
```

### S3 connection issues

Check `.env.server`:
```bash
cat .env.server | grep S3
cat .env.server | grep AWS
```

Test S3 access:
```bash
aws s3 ls s3://your-bucket/
```

### Agent token expired

Generate new token:
```bash
uv run cataloger generate-token your-secret
```

## Summary

Bootstrap scripts provide:
- ✅ Realistic sample databases for testing
- ✅ Complete development workflow
- ✅ Reproducible test environments
- ✅ Examples of data patterns agents should discover
- ✅ Scenarios for feedback loop testing

All scripts are in `scripts/` (bash) and `python_bootstrap_scripts/` (Python).

See individual READMEs for detailed documentation.
