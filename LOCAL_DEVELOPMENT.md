# Local Development with MinIO

Complete guide for running Cataloger locally without AWS credentials using MinIO for S3-compatible storage.

## Why MinIO?

**MinIO** is an S3-compatible object storage service that runs locally:

✅ **No AWS account needed** - No signup, no costs
✅ **Fast development** - Run everything on localhost
✅ **Full S3 API compatibility** - Same boto3 code works
✅ **Easy to reset** - Delete volumes to start fresh
✅ **Web UI** - Browse buckets and objects visually

## Quick Start

### 1. Setup Environment for MinIO

```bash
./scripts/setup-env.sh
```

This creates `.env.server` with MinIO configuration:
```bash
export S3_BUCKET=cataloger-dev
export S3_ENDPOINT_URL=http://localhost:9000
export AWS_ACCESS_KEY_ID=minioadmin
export AWS_SECRET_ACCESS_KEY=minioadmin
```

Edit `.env.server` and add your Anthropic API key:
```bash
export LLM_API_KEY=sk-ant-your-key-here
```

### 2. Start MinIO

```bash
./scripts/start-dev-services.sh
```

This starts MinIO in Docker and creates the `cataloger-dev` bucket.

**MinIO Console**: http://localhost:9001
- Username: `minioadmin`
- Password: `minioadmin`

**S3 API Endpoint**: http://localhost:9000

### 3. Build Container & Create Databases

```bash
./scripts/build-container.sh
./scripts/bootstrap-db.sh
```

### 4. Start Cataloger Server

```bash
./scripts/run-server.sh
```

Server runs at: http://localhost:8000

### 5. Generate a Catalog

In another terminal:

```bash
./scripts/catalog-ecommerce.sh
```

### 6. View Results

- **Web UI**: http://localhost:8000
- **MinIO Console**: http://localhost:9001 (browse the `cataloger-dev` bucket)

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│ Your Machine                                                │
│                                                             │
│  ┌─────────────────┐         ┌──────────────────┐         │
│  │ Cataloger       │ HTTP    │ MinIO            │         │
│  │ Server          ├────────►│ (Port 9000/9001) │         │
│  │ (Port 8000)     │  boto3  │                  │         │
│  │                 │         │  📦 Buckets:     │         │
│  │ FastAPI         │         │   cataloger-dev/ │         │
│  │ + Agent Loop    │         │     └─ catalogs  │         │
│  └────────┬────────┘         └──────────────────┘         │
│           │                                                 │
│           │ Docker exec                                     │
│           ▼                                                 │
│  ┌─────────────────┐                                       │
│  │ Agent Container │                                       │
│  │ (Python + ibis) │                                       │
│  │                 │                                       │
│  │ Volume mount:   │                                       │
│  │ data/ → /data   │                                       │
│  └─────────────────┘                                       │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

## Full Workflow

### Terminal 1: Start Services

```bash
# Start MinIO
./scripts/start-dev-services.sh

# Start Cataloger (after MinIO is ready)
./scripts/run-server.sh
```

### Terminal 2: Run Catalogs

```bash
# Generate catalog
./scripts/catalog-ecommerce.sh

# View in browser
open http://localhost:8000/database/current?prefix=test/ecommerce
```

### Terminal 3 (Optional): Smoke Tests

```bash
./scripts/run-smoke-test.sh
```

## Managing Services

### Start Development Services

```bash
./scripts/start-dev-services.sh
```

Starts:
- MinIO (S3-compatible storage)
- Auto-creates `cataloger-dev` bucket

### Stop Development Services

```bash
# Stop but keep data
./scripts/stop-dev-services.sh

# Stop and delete all data
./scripts/stop-dev-services.sh --clean
```

### Check Status

```bash
# Check if services are running
docker ps | grep cataloger

# View logs
docker logs cataloger-minio
```

## MinIO Web Console

Access at: **http://localhost:9001**

**Login**:
- Username: `minioadmin`
- Password: `minioadmin`

**Features**:
- Browse buckets and objects
- View catalog HTML files
- Download scripts
- See object metadata
- Manage permissions

## Accessing Stored Catalogs

### Via MinIO Console

1. Open http://localhost:9001
2. Login with `minioadmin` / `minioadmin`
3. Navigate to `cataloger-dev` bucket
4. Browse by prefix: `test/ecommerce/2024-01-15T10:00:00Z/`
5. View/download files

### Via AWS CLI

```bash
# Configure AWS CLI for MinIO
aws configure --profile minio
# AWS Access Key ID: minioadmin
# AWS Secret Access Key: minioadmin
# Default region: us-east-1
# Output format: json

# List buckets
aws --profile minio --endpoint-url http://localhost:9000 s3 ls

# List catalogs
aws --profile minio --endpoint-url http://localhost:9000 \
  s3 ls s3://cataloger-dev/test/ecommerce/

# Download a catalog
aws --profile minio --endpoint-url http://localhost:9000 \
  s3 cp s3://cataloger-dev/test/ecommerce/2024-01-15T10:00:00Z/catalog.html .
```

### Via Python (boto3)

```python
import boto3

s3 = boto3.client(
    's3',
    endpoint_url='http://localhost:9000',
    aws_access_key_id='minioadmin',
    aws_secret_access_key='minioadmin',
    region_name='us-east-1'
)

# List objects
response = s3.list_objects_v2(
    Bucket='cataloger-dev',
    Prefix='test/ecommerce/'
)

for obj in response['Contents']:
    print(obj['Key'])
```

### Setting up the envs

```bash
# Setup
./scripts/setup-env.sh

# Edit .env.server - remove or comment out:
# export S3_ENDPOINT_URL=http://localhost:9000

# Set real AWS credentials:
# export S3_BUCKET=my-production-bucket
# export AWS_ACCESS_KEY_ID=AKIA...
# export AWS_SECRET_ACCESS_KEY=...
```

The code automatically detects whether to use MinIO or AWS based on `S3_ENDPOINT_URL`.

## Troubleshooting

### MinIO won't start

```bash
# Check if port is already in use
lsof -i :9000
lsof -i :9001

# Stop and restart
./scripts/stop-dev-services.sh
./scripts/start-dev-services.sh
```

### Bucket not found

```bash
# Recreate bucket manually
docker exec cataloger-minio \
  mc mb /data/cataloger-dev
```

### Permission errors

MinIO runs with default permissions. If you see access denied:

```bash
# Make bucket public for downloads
docker exec cataloger-minio \
  mc anonymous set download /data/cataloger-dev
```

### Reset everything

```bash
# Stop and delete all data
./scripts/stop-dev-services.sh --clean

# Restart fresh
./scripts/start-dev-services.sh
```

### Connection refused

If Cataloger can't connect to MinIO:

1. **Check MinIO is running**:
   ```bash
   docker ps | grep minio
   ```

2. **Check endpoint in .env.server**:
   ```bash
   grep S3_ENDPOINT_URL .env.server
   # Should be: export S3_ENDPOINT_URL=http://localhost:9000
   ```

3. **Test connection manually**:
   ```bash
   curl http://localhost:9000/minio/health/live
   # Should return: 200 OK
   ```

### Container network issues

If the agent container can't reach MinIO:

MinIO must be accessible from Docker containers. The container uses `host.docker.internal` or the Docker bridge network.

**Fix**: Update `.env.server` to use Docker's host gateway:
```bash
# For Linux
export S3_ENDPOINT_URL=http://172.17.0.1:9000

# For Mac/Windows
export S3_ENDPOINT_URL=http://host.docker.internal:9000
```

Or connect MinIO to same network:
```bash
# Edit docker-compose.dev.yaml to use network_mode: host
```

## Data Persistence

### Where is data stored?

MinIO data is stored in a Docker volume: `cataloger_minio-data`

```bash
# Inspect volume
docker volume inspect cataloger_minio-data

# Location (varies by OS):
# Linux: /var/lib/docker/volumes/cataloger_minio-data/_data
# Mac: ~/Library/Containers/com.docker.docker/Data/vms/0/
```

### Backup data

```bash
# Export all catalogs
docker run --rm \
  -v cataloger_minio-data:/data \
  -v $(pwd):/backup \
  alpine tar czf /backup/minio-backup.tar.gz /data
```

### Restore data

```bash
# Import backup
docker run --rm \
  -v cataloger_minio-data:/data \
  -v $(pwd):/backup \
  alpine tar xzf /backup/minio-backup.tar.gz -C /
```

## Production vs Development

| Feature | MinIO (Dev) | AWS S3 (Prod) |
|---------|-------------|---------------|
| Setup | `./scripts/start-dev-services.sh` | AWS Console |
| Cost | Free | Pay per GB/requests |
| Speed | Local (fast) | Network latency |
| Credentials | `minioadmin` | IAM roles |
| Endpoint | `http://localhost:9000` | `https://s3.amazonaws.com` |
| Bucket | `cataloger-dev` | Your bucket |
| Data persistence | Docker volume | S3 (durable) |

## CI/CD Integration

### GitHub Actions with MinIO

```yaml
name: Tests

on: [push]

jobs:
  test:
    runs-on: ubuntu-latest

    services:
      minio:
        image: minio/minio
        ports:
          - 9000:9000
        env:
          MINIO_ROOT_USER: minioadmin
          MINIO_ROOT_PASSWORD: minioadmin
        options: --health-cmd "curl -f http://localhost:9000/minio/health/live"

    steps:
      - uses: actions/checkout@v3

      - name: Setup environment
        run: ./scripts/setup-env.sh

      - name: Create bucket
        run: |
          docker run --rm --network host minio/mc \
            mc mb local/cataloger-dev

      - name: Run tests
        env:
          LLM_API_KEY: ${{ secrets.LLM_API_KEY }}
        run: ./scripts/run-smoke-test.sh
```

## Summary

MinIO provides a complete local S3 experience:

✅ **Fast setup**: One command to start
✅ **No costs**: Free local storage
✅ **Full compatibility**: Same code works in production
✅ **Easy testing**: Reset anytime
✅ **Visual interface**: Browse catalogs in web UI

**Quick Start**:
```bash
./scripts/setup-env.sh
./scripts/start-dev-services.sh
./scripts/run-server.sh
./scripts/catalog-ecommerce.sh
```

**View Results**: http://localhost:8000
**Browse Storage**: http://localhost:9001
