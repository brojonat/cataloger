#!/bin/bash
#
# Start local development services (MinIO for S3-compatible storage)
#
# Usage:
#   ./scripts/start-dev-services.sh

set -e

cd "$(dirname "$0")/.."

echo "🚀 Starting local development services..."
echo

# Check if docker-compose is available
if ! command -v docker-compose &> /dev/null && ! docker compose version &> /dev/null 2>&1; then
    echo "❌ docker-compose not found. Please install Docker Compose."
    exit 1
fi

# Use 'docker compose' (v2) if available, otherwise 'docker-compose' (v1)
if docker compose version &> /dev/null 2>&1; then
    COMPOSE_CMD="docker compose"
else
    COMPOSE_CMD="docker-compose"
fi

# Start services
echo "📦 Starting MinIO (S3-compatible storage)..."
$COMPOSE_CMD -f docker-compose.dev.yaml up -d

echo
echo "⏳ Waiting for services to be ready..."
sleep 3

# Check health
if docker ps | grep -q cataloger-minio; then
    echo "✅ MinIO is running"
    echo
    echo "📊 MinIO Console: http://localhost:9001"
    echo "   Username: minioadmin"
    echo "   Password: minioadmin"
    echo
    echo "🪣 S3 API Endpoint: http://localhost:9000"
    echo "   Bucket: cataloger-dev"
    echo
    echo "💡 Configure your .env.server to use MinIO:"
    echo "   uv run cataloger admin setup-env"
    echo
    echo "   Then edit .env.server and set your LLM_API_KEY"
else
    echo "❌ Failed to start MinIO"
    exit 1
fi

echo "🎉 Development services ready!"
