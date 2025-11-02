# CLI Reference

Complete reference for the `cataloger` command-line interface.

## Installation

```bash
uv pip install -e ".[dev]"
```

## Quick Start Commands

```bash
# 1. Setup environment (idempotent - safe to run multiple times)
uv run cataloger admin setup-env
# Edit .env.server to set LLM_API_KEY and S3 credentials

# 2. Generate a test token
uv run cataloger generate-token your-secret

# 3. Trigger catalog generation
uv run cataloger catalog \
  --db-conn "duckdb:////data/sample_ecommerce.duckdb" \
  --table users --table products --table orders \
  --s3-prefix "test/ecommerce"
```

**Note**: After editing prompts, just run `setup-env` again to re-encode them!

## Command Reference

### Main Commands

#### `cataloger catalog`

Trigger a catalog generation by calling the API server.

```bash
cataloger catalog \
  --db-conn <connection-string> \
  --table <table-name> [--table <table-name> ...] \
  --s3-prefix <prefix> \
  [--api-url <url>] \
  [--token <jwt-token>]
```

**Options:**

- `--db-conn` (required): Database connection string
  - Examples:
    - `postgresql://user:pass@host:5432/db`
    - `duckdb:////data/mydb.duckdb`
    - `mysql://user:pass@host:3306/db`
- `--table`, `-t` (required, multiple): Table name to catalog (repeat for multiple tables)
  - Example: `--table users --table orders --table products`
- `--s3-prefix` (required): S3 prefix for output
  - Example: `customer-123/prod`
- `--api-url` (optional): API server URL
  - Default: `$CATALOGER_API_URL`
  - Example: `http://localhost:8000`
- `--token` (optional): JWT authentication token
  - Default: `$CATALOGER_AUTH_TOKEN`
  - Generate with: `cataloger generate-token`

**Example:**

```bash
export CATALOGER_API_URL=http://localhost:8000
export CATALOGER_AUTH_TOKEN=$(cataloger generate-token your-secret)

cataloger catalog \
  --db-conn "duckdb:////data/sample_ecommerce.duckdb" \
  --table users --table products --table orders \
  --s3-prefix "test/ecommerce"
```

**Output:**

```
✓ Catalog generated successfully
  Timestamp: 2024-01-15T10:00:00Z
  Catalog:   s3://bucket/test/ecommerce/2024-01-15T10:00:00Z/catalog.html
  Summary:   s3://bucket/test/ecommerce/2024-01-15T10:00:00Z/recent_summary.html
```

#### `cataloger generate-token`

Generate a JWT token for API authentication (development/testing only).

```bash
cataloger generate-token [secret]
```

**Arguments:**

- `secret` (optional): JWT secret key
  - Default: `$AUTH_SECRET` or `change-me`

**Example:**

```bash
# Generate token
TOKEN=$(cataloger generate-token my-secret)

# Use token
export CATALOGER_AUTH_TOKEN=$TOKEN
cataloger catalog --db-conn ... --table TABLE1 --table TABLE2 --s3-prefix ...
```

**Security Note:** This is for development only. In production, use proper identity providers.

### Admin Commands

Administrative and setup commands under the `admin` subcommand group.

#### `cataloger admin setup-env`

Setup environment configuration for Cataloger. Creates/updates `.env.server` file with encoded prompts.

**Idempotent**: Safe to run multiple times. Always updates prompts to latest version.

```bash
cataloger admin setup-env
```

**Examples:**

```bash
# Setup environment
cataloger admin setup-env

# Re-run after editing prompts (automatically updates them)
vim prompts/cataloging_agent.yaml
cataloger admin setup-env
```

**What it does:**

1. Checks that prompt files exist in `prompts/`
2. **If .env.server doesn't exist**: Copies template and encodes prompts
3. **If .env.server exists**: Updates prompt lines, preserves everything else
4. Shows next steps

**This is your one-stop setup command!**

**Output:**

```
✓ Created .env.server from .env.server.minio
✓ Encoding prompts...
✓ Encoded prompts and updated .env.server

Storage configured for: MinIO (local S3)

Next steps:
  1. Edit .env.server and set:
     - LLM_API_KEY (your LLM provider API key)
     - Start MinIO: ./scripts/start-dev-services.sh
  2. Build container: ./scripts/build-container.sh
  3. Create databases: ./scripts/bootstrap-db.sh
  4. Start server: ./scripts/run-server.sh
```

Update encoded prompts in existing `.env.server` file. Use this after editing prompt YAML files.

```bash

```

**Example:**

```bash
# Edit prompts
vim prompts/cataloging_agent.yaml

# Re-encode and update

# Restart server to use new prompts
./scripts/run-server.sh
```

**What it does:**

1. Checks that `.env.server` exists
2. Reads prompt YAML files
3. Encodes to base64
4. Updates `CATALOGING_AGENT_PROMPT` and `SUMMARY_AGENT_PROMPT` lines
5. Preserves all other configuration

#### `cataloger admin encode-prompt`

Encode a single prompt YAML file to base64 (for manual use).

```bash
cataloger admin encode-prompt <prompt-file>
```

**Arguments:**

- `prompt-file`: Path to YAML prompt file

**Example:**

```bash
cataloger admin encode-prompt prompts/cataloging_agent.yaml
```

**Output:**

```
cHJvbXB0OiB8CiAgWW91IGFyZSBhIGRhdGFiYXNlIGNhdGFsb2dpbmcgYWdlbnQuLi4=
```

**Use case:** Manual debugging or custom prompt testing.

## Environment Variables

### Required

- `LLM_API_KEY`: LLM provider API key (Anthropic Claude, OpenAI, etc.)
- `S3_BUCKET`: S3 bucket name for catalog storage
- `AUTH_SECRET`: Secret for JWT signing

### Optional

**S3 Configuration:**

- `S3_REGION`: AWS region (default: `us-east-1`)
- `S3_ENDPOINT_URL`: Custom endpoint for MinIO/LocalStack
- `AWS_ACCESS_KEY_ID`: AWS access key
- `AWS_SECRET_ACCESS_KEY`: AWS secret key

**Container Configuration:**

- `CONTAINER_IMAGE`: Docker image name (default: `cataloger-agent:latest`)
- `CONTAINER_POOL_SIZE`: Number of containers in pool (default: `5`)

**Server Configuration:**

- `SERVICE_NAME`: Service name for logging (default: `cataloger`)
- `HOST`: Server host (default: `0.0.0.0`)
- `PORT`: Server port (default: `8000`)
- `LOG_LEVEL`: Logging level (default: `INFO`)
- `LOG_JSON`: JSON logging (default: `false`)

**API Client Configuration:**

- `CATALOGER_API_URL`: API server URL (for `catalog` command)
- `CATALOGER_AUTH_TOKEN`: JWT token (for `catalog` command)

## Workflow Examples

### Initial Setup

```bash
# 1. Install
uv pip install -e ".[dev]"

# 2. Configure environment
uv run cataloger admin setup-env

# 3. Edit config
vim .env.server
# Set LLM_API_KEY=sk-ant-...

# 4. Start MinIO
./scripts/start-dev-services.sh

# 5. Build and bootstrap
./scripts/build-container.sh
./scripts/bootstrap-db.sh

# 6. Start server
./scripts/run-server.sh
```

### Daily Development

```bash
# Generate token
export CATALOGER_AUTH_TOKEN=$(cataloger generate-token your-secret)
export CATALOGER_API_URL=http://localhost:8000

# Run catalog
cataloger catalog \
  --db-conn "duckdb:////data/sample_ecommerce.duckdb" \
  --table users --table orders \
  --s3-prefix "test/ecommerce"

# View results
open http://localhost:8000/database/current?prefix=test/ecommerce
```

### Updating Prompts

```bash
# Edit prompt
vim prompts/cataloging_agent.yaml

# Update .env.server

# Restart server (Ctrl+C, then:)
./scripts/run-server.sh
```

### Switching Storage

```bash
# Recreate .env.server with fresh template
cataloger admin setup-env --force
# Edit .env.server - set your credentials and endpoints
```

## Troubleshooting

### Command not found

```bash
# Ensure installed
uv pip install -e ".[dev]"

# Check installation
which cataloger
cataloger --help
```

### Missing .env.server

```bash
cataloger admin setup-env
```

### Outdated prompts

```bash
cataloger admin setup-env
```

### Connection refused

```bash
# Check server is running
curl http://localhost:8000/healthz

# Start server if needed
./scripts/run-server.sh
```

### Authentication failed

```bash
# Generate new token
export CATALOGER_AUTH_TOKEN=$(cataloger generate-token your-secret)

# Use same secret as AUTH_SECRET in .env.server
```

## Help

```bash
# Main help
cataloger --help

# Command help
cataloger catalog --help
cataloger generate-token --help

# Admin commands help
cataloger admin --help
cataloger admin setup-env --help
cataloger admin encode-prompt --help
```

## Summary

**Main commands:**

- `cataloger catalog` - Generate database catalog
- `cataloger generate-token` - Create JWT token

**Admin commands:**

- `cataloger admin setup-env` - Setup/update environment (idempotent!)
- `cataloger admin encode-prompt` - Encode single prompt file (debug)

**Workflow:**

1. `admin setup-env` - Setup environment
2. Edit `.env.server` - Add LLM_API_KEY
3. `generate-token` - Get auth token
4. `catalog` - Generate catalogs
5. `admin setup-env` - Re-run anytime to update prompts!
