# Smoke Test Guide

Comprehensive smoke tests to verify all Cataloger endpoints return valid HTML and work correctly.

## Quick Start

```bash
# 1. Start the server (in one terminal)
./scripts/run-server.sh

# 2. Run smoke tests (in another terminal)
./scripts/run-smoke-test.sh
```

## What Gets Tested

The smoke test validates all major functionality:

### Core Endpoints
- ✅ `GET /healthz` - Health check
- ✅ `GET /metrics` - Prometheus metrics
- ✅ `GET /whoami` - Authentication validation

### UI Endpoints
- ✅ `GET /` - Home page HTML
- ✅ `GET /database/current` - Latest catalog view
- ✅ `GET /database/timelapse` - Historical catalog view

### API Endpoints
- ✅ `GET /api/catalog/content` - Fetch catalog content
- ✅ `GET /api/catalog/list` - List catalog files
- ✅ `GET /catalog/context` - Context summary (HTML)
- ✅ `GET /catalog/context?strip_tags=true` - Context summary (plain text)

### Catalog Operations
- ✅ `POST /catalog` - Generate new catalog (creates real catalog with agent)
- ✅ `POST /catalog/comment` - Add user comment

### Validation
- ✅ HTML structure validation (well-formed tags)
- ✅ Response code validation
- ✅ Content validation (expected text present)
- ✅ Comment integration (verifies comments appear in context)

## Prerequisites

### 1. Sample Database

The smoke test uses `data/sample_ecommerce.duckdb` by default.

If it doesn't exist, the script will create it automatically, or run:

```bash
./scripts/bootstrap-db.sh
```

### 2. Environment Configuration

Create `.env.server` with required settings:

```bash
./scripts/setup-env.sh
```

Edit `.env.server` to set:
```bash
export LLM_API_KEY=sk-ant-your-key-here
export S3_BUCKET=your-test-bucket
export AWS_ACCESS_KEY_ID=your-access-key
export AWS_SECRET_ACCESS_KEY=your-secret-key
export AUTH_SECRET=your-random-secret-for-jwt
```

### 3. Running Server

Start the server before running tests:

```bash
./scripts/run-server.sh
```

Wait until you see:
```
INFO:     Application startup complete.
```

## Running Tests

### Basic Usage

```bash
./scripts/run-smoke-test.sh
```

### Custom Configuration

```bash
# Test against different server
CATALOGER_API_URL=http://staging.example.com:8000 ./scripts/run-smoke-test.sh

# Use different database
DB_PATH=data/sample_timeseries.duckdb ./scripts/run-smoke-test.sh

# Custom auth secret
AUTH_SECRET=my-secret ./scripts/run-smoke-test.sh
```

### Direct Python Invocation

```bash
uv run python scripts/smoke_test.py
```

## Expected Output

Successful run:

```
🧪 Cataloger Smoke Test
=======================

🔍 Checking if server is running at http://localhost:8000...
✅ Server is running

🚀 Running smoke tests...

🧪 Running smoke tests against http://localhost:8000
📊 Test database: data/sample_ecommerce.duckdb
🔑 Auth token: eyJhbGciOiJIUzI1NiIs...

Testing: Health Check... ✅
Testing: Metrics Endpoint... ✅
Testing: Auth Check... ✅
Testing: Home Page... ✅
Testing: Generate Catalog...
    (This may take 30-60 seconds)...
    Catalog timestamp: 2024-01-15T10:00:00Z ✅
Testing: Current View... ✅
Testing: Timelapse View... ✅
Testing: Catalog Content API... ✅
Testing: Catalog List API... ✅
Testing: Context Summary (HTML)... ✅
Testing: Context Summary (Plain Text)... ✅
Testing: Add Comment... ✅
Testing: Context Summary After Comment... ✅

============================================================
✅ Passed: 13
❌ Failed: 0
============================================================

🎉 Smoke tests complete!
```

## Test Details

### 1. Health & Metrics

Basic connectivity and observability checks:
- Service responds to health checks
- Prometheus metrics exposed
- Authentication working

### 2. UI Pages

Validates HTML rendering:
- Well-formed HTML structure
- Required content present
- Proper content-type headers

### 3. Catalog Generation

**Most important test** - creates a real catalog:
- Connects to test database
- Runs cataloging agent (calls Anthropic API)
- Generates HTML reports
- Stores in S3
- **Takes 30-60 seconds** depending on agent performance

### 4. Context System

Tests the new context summary feature:
- Generates context HTML from previous catalog
- Strips HTML tags for plain text version
- Adds user comment
- Verifies comment appears in next context

## Troubleshooting

### Server not responding

```
❌ Server not responding at http://localhost:8000
```

**Fix**: Start the server:
```bash
./scripts/run-server.sh
```

### Database not found

```
❌ Database not found: data/sample_ecommerce.duckdb
```

**Fix**: Create sample database:
```bash
./scripts/bootstrap-db.sh
```

### Missing AUTH_SECRET

```
❌ AUTH_SECRET not found. Set environment variable or create .env.server
```

**Fix**: Create environment file:
```bash
./scripts/setup-env.sh
# Then edit .env.server with your AUTH_SECRET
```

### S3 errors during catalog generation

```
❌ Failed to write to S3
```

**Fix**: Check S3 configuration in `.env.server`:
```bash
export S3_BUCKET=your-bucket-name
export AWS_ACCESS_KEY_ID=...
export AWS_SECRET_ACCESS_KEY=...
```

Test S3 access:
```bash
aws s3 ls s3://your-bucket-name/
```

### Agent timeout

```
❌ Status 500: Catalog generation failed: Agent exceeded token budget
```

**Possible causes**:
- Anthropic API key invalid
- Network issues
- Database too large

**Fix**: Check logs:
```bash
# Server logs will show agent execution details
```

### HTML validation failures

```
❌ Invalid HTML: ['Missing <html> tag']
```

**Indicates**: Server returned error page or malformed HTML

**Fix**: Check server logs for errors

## CI/CD Integration

### GitHub Actions

```yaml
name: Smoke Tests

on: [push, pull_request]

jobs:
  smoke-test:
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v3

      - name: Setup Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.13'

      - name: Install uv
        run: curl -LsSf https://astral.sh/uv/install.sh | sh

      - name: Install dependencies
        run: uv pip install -e ".[dev]"

      - name: Create sample database
        run: ./scripts/bootstrap-db.sh

      - name: Build container
        run: ./scripts/build-container.sh

      - name: Start server
        run: |
          ./scripts/run-server.sh &
          sleep 10

      - name: Run smoke tests
        env:
          LLM_API_KEY: ${{ secrets.LLM_API_KEY }}
          S3_BUCKET: ${{ secrets.S3_BUCKET }}
          AWS_ACCESS_KEY_ID: ${{ secrets.AWS_ACCESS_KEY_ID }}
          AWS_SECRET_ACCESS_KEY: ${{ secrets.AWS_SECRET_ACCESS_KEY }}
          AUTH_SECRET: ${{ secrets.AUTH_SECRET }}
        run: ./scripts/run-smoke-test.sh
```

## Development Workflow

### After Code Changes

```bash
# Terminal 1: Restart server
# Ctrl+C to stop, then:
./scripts/run-server.sh

# Terminal 2: Run smoke tests
./scripts/run-smoke-test.sh
```

### Testing Specific Endpoints

Edit `scripts/smoke_test.py` and comment out tests you don't need:

```python
tests = [
    ("Health Check", self.test_healthz),
    # ("Generate Catalog", self.test_create_catalog),  # Skip slow test
    ("Current View", self.test_current_view),
]
```

### Adding New Tests

Add a new method to the `SmokeTest` class:

```python
def test_my_new_endpoint(self):
    """Test my new endpoint."""
    resp = requests.get(f"{self.base_url}/my-endpoint", timeout=5)
    assert resp.status_code == 200, f"Status {resp.status_code}"

    is_valid, errors = validate_html(resp.text)
    assert is_valid, f"Invalid HTML: {errors}"

    assert "expected content" in resp.text, "Missing expected content"
```

Then add it to the test list in `run()`:

```python
tests = [
    # ... existing tests ...
    ("My New Endpoint", self.test_my_new_endpoint),
]
```

## Test Data Cleanup

Smoke tests create temporary data in S3:

```
s3://bucket/smoke-test/{timestamp}/
  catalog.html
  catalog_script.py
  recent_summary.html
  summary_script.py
  comments/
    smoke-test-user-{timestamp}.txt
```

### Manual Cleanup

```bash
# List smoke test prefixes
aws s3 ls s3://your-bucket/smoke-test/

# Delete old smoke test data
aws s3 rm s3://your-bucket/smoke-test/ --recursive
```

### Automated Cleanup

Add to your CI/CD:

```bash
# After tests pass
aws s3 rm s3://$S3_BUCKET/smoke-test/ --recursive || true
```

## Performance Benchmarks

Expected timings:

- Health/metrics checks: < 1 second
- UI page loads: < 2 seconds
- Catalog generation: 30-60 seconds (agent execution)
- Comment operations: < 2 seconds
- Context generation: < 5 seconds

If tests take significantly longer, investigate:
- Network latency to Anthropic API
- S3 latency
- Database query performance
- Container startup time

## Summary

The smoke test provides confidence that:
- ✅ All endpoints work correctly
- ✅ HTML is well-formed
- ✅ Authentication functions
- ✅ Agents can generate catalogs
- ✅ Context system works end-to-end
- ✅ Comments integrate properly

Run it frequently during development and in CI/CD!
