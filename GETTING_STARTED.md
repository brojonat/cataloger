# Getting Started with Cataloger

Simple 5-minute setup to get Cataloger running locally with MinIO.

## Prerequisites

- Docker installed and running
- Python 3.13+ with uv
- LLM API key (Anthropic Claude, OpenAI, etc.)

## Setup

### 1. Install

```bash
uv pip install -e ".[dev]"
```

### 2. Setup Environment

```bash
uv run cataloger admin setup-env --minio
```

This:
- ✅ Creates `.env.server` with MinIO configuration
- ✅ Encodes agent prompts automatically
- ✅ Ready for deployment

### 3. Configure LLM API Key

Edit `.env.server` and add your API key:

```bash
vim .env.server
```

Change:
```bash
export LLM_API_KEY=sk-ant-your-key-here
```

To your actual key:
```bash
export LLM_API_KEY=sk-ant-api03-abc123...
```

Save and close.

### 4. Start Services

```bash
# Terminal 1: Start MinIO (local S3)
./scripts/start-dev-services.sh

# Terminal 2: Build container
./scripts/build-container.sh

# Create sample databases
./scripts/bootstrap-db.sh

# Start Cataloger server
./scripts/run-server.sh
```

### 5. Generate a Catalog

In Terminal 3:

```bash
# Set environment
export CATALOGER_API_URL=http://localhost:8000
export CATALOGER_AUTH_TOKEN=$(uv run cataloger generate-token change-me-to-a-random-secret)

# Generate catalog
uv run cataloger catalog \
  --db-conn "duckdb:////data/sample_ecommerce.duckdb" \
  --tables "users,products,orders" \
  --s3-prefix "test/ecommerce"
```

### 6. View Results

- **Web UI**: http://localhost:8000
- **MinIO Console**: http://localhost:9001 (minioadmin / minioadmin)

## That's It!

You now have:
- ✅ Cataloger running locally
- ✅ MinIO providing S3-compatible storage
- ✅ Sample databases to catalog
- ✅ Full web UI to view results

## Common Workflows

### Daily Development

```bash
# Terminal 1: Services running
# (MinIO and Cataloger server)

# Terminal 2: Generate catalogs
export CATALOGER_AUTH_TOKEN=$(uv run cataloger generate-token your-secret)

uv run cataloger catalog \
  --db-conn "duckdb:////data/sample_ecommerce.duckdb" \
  --tables "users,orders" \
  --s3-prefix "test/ecommerce"

# View at: http://localhost:8000/database/current?prefix=test/ecommerce
```

### After Editing Prompts

```bash
# 1. Edit prompt
vim prompts/cataloging_agent.yaml

# 2. Re-encode (idempotent!)
uv run cataloger admin setup-env --minio

# 3. Restart server
# Ctrl+C in Terminal 2, then:
./scripts/run-server.sh
```

### Clean Restart

```bash
# Stop everything
./scripts/stop-dev-services.sh --clean

# Start fresh
./scripts/start-dev-services.sh
./scripts/run-server.sh
```

## Next Steps

- Read [README.md](./README.md) for architecture overview
- See [CLI_REFERENCE.md](./CLI_REFERENCE.md) for all commands
- Check [LOCAL_DEVELOPMENT.md](./LOCAL_DEVELOPMENT.md) for MinIO details
- Run smoke tests: `./scripts/run-smoke-test.sh`

## Troubleshooting

### "Command not found: cataloger"

```bash
uv pip install -e ".[dev]"
```

### "Missing LLM_API_KEY"

Edit `.env.server` and set your API key.

### "S3 bucket not found"

Make sure MinIO is running:
```bash
./scripts/start-dev-services.sh
```

### "Container image not found"

Build the container:
```bash
./scripts/build-container.sh
```

### "Database not found"

Create sample databases:
```bash
./scripts/bootstrap-db.sh
```

## Quick Reference

```bash
# Setup (one time)
uv pip install -e ".[dev]"
uv run cataloger admin setup-env --minio
# Edit .env.server

# Start services
./scripts/start-dev-services.sh  # MinIO
./scripts/build-container.sh     # Agent container
./scripts/bootstrap-db.sh         # Sample databases
./scripts/run-server.sh          # Cataloger server

# Generate catalogs
export CATALOGER_AUTH_TOKEN=$(uv run cataloger generate-token secret)
uv run cataloger catalog --db-conn ... --tables ... --s3-prefix ...

# Update prompts (idempotent!)
uv run cataloger admin setup-env --minio
```

That's all you need to know to get started!
