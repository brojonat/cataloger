# Quick Start Guide

Get Cataloger running locally in 5 minutes with sample data.

## Prerequisites

- Docker installed and running
- Python 3.13+ with uv
- Anthropic API key
- S3 bucket (or use LocalStack for local testing)

## Quick Setup

### 1. Install dependencies

```bash
uv pip install -e ".[dev]"
```

### 2. Set up environment

```bash
./scripts/setup-env.sh
```

Edit `.env.server` and set:

```bash
export ANTHROPIC_API_KEY=sk-ant-your-key-here
export S3_BUCKET=your-test-bucket
export AWS_ACCESS_KEY_ID=your-access-key
export AWS_SECRET_ACCESS_KEY=your-secret-key
export AUTH_SECRET=your-random-secret-for-jwt
```

### 3. Build the container

```bash
./scripts/build-container.sh
```

### 4. Create sample databases

```bash
./scripts/bootstrap-db.sh
```

This creates:
- `data/sample_ecommerce.duckdb` - E-commerce database
- `data/sample_timeseries.duckdb` - Time-series metrics

### 5. Start the server

In one terminal:

```bash
./scripts/run-server.sh
```

Server runs on `http://localhost:8000`.

Visit the UI: `http://localhost:8000`

### 6. Generate catalogs

In another terminal:

```bash
# E-commerce database
./scripts/catalog-ecommerce.sh

# Time-series database
./scripts/catalog-timeseries.sh
```

### 7. View catalogs

Open browser to:
- Latest: `http://localhost:8000/database/current?prefix=test/ecommerce`
- Timelapse: `http://localhost:8000/database/timelapse?prefix=test/ecommerce`

Or use the home page to navigate.

## Manual Catalog Generation

Generate a test token:

```bash
uv run cataloger generate-token your-random-secret-for-jwt
```

Set environment:

```bash
export CATALOGER_API_URL=http://localhost:8000
export CATALOGER_AUTH_TOKEN=<your-token>
```

Generate catalog:

```bash
uv run cataloger catalog \
  --db-conn "duckdb:///data/sample_ecommerce.duckdb" \
  --tables "users,products,orders" \
  --s3-prefix "test/ecommerce"
```

## Testing Without S3

For local development without S3, you can:

1. Use LocalStack:
```bash
docker run -d -p 4566:4566 localstack/localstack
```

2. Use MinIO (S3-compatible):
```bash
docker run -d -p 9000:9000 -p 9001:9001 \
  -e "MINIO_ROOT_USER=minioadmin" \
  -e "MINIO_ROOT_PASSWORD=minioadmin" \
  quay.io/minio/minio server /data --console-address ":9001"
```

Then configure boto3 to point to localhost (requires code changes).

## Verify It's Working

1. Check health endpoint:
```bash
curl http://localhost:8000/healthz
```

2. Check metrics:
```bash
curl http://localhost:8000/metrics
```

3. Test authentication:
```bash
curl -H "Authorization: Bearer <your-token>" \
  http://localhost:8000/whoami
```

## Example Database Setup

For quick testing, create a sample Postgres database:

```bash
docker run -d \
  -e POSTGRES_PASSWORD=postgres \
  -p 5432:5432 \
  postgres:16
```

Then:

```bash
# Create sample table
docker exec -it <container-id> psql -U postgres -c "
  CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100),
    email VARCHAR(100),
    created_at TIMESTAMP DEFAULT NOW()
  );
  INSERT INTO users (name, email) VALUES
    ('Alice', 'alice@example.com'),
    ('Bob', 'bob@example.com'),
    ('Charlie', 'charlie@example.com');
"

# Catalog it
uv run cataloger catalog \
  --db-conn "postgresql://postgres:postgres@localhost:5432/postgres" \
  --tables "users" \
  --s3-prefix "demo/users"
```

## Troubleshooting

**Container image not found:**
```bash
make build-container
```

**Docker daemon not running:**
```bash
# macOS
open -a Docker

# Linux
sudo systemctl start docker
```

**Port 8000 already in use:**
```bash
export PORT=8080
make run-server
```

**Agent timeout:**
- Check Docker container logs: `docker ps` then `docker logs <id>`
- Verify Anthropic API key is valid
- Check network connectivity

## Next Steps

- Read [DEVELOPMENT.md](./DEVELOPMENT.md) for architecture details
- Check [IMPLEMENTATION_CHECKLIST.md](./IMPLEMENTATION_CHECKLIST.md) for roadmap
- Customize agent prompts in `prompts/`
