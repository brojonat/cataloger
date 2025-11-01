#!/usr/bin/env bash
# Build the agent container image

set -e

echo "Building cataloger-agent container..."
docker build -t cataloger-agent:latest -f Dockerfile.agent .

echo ""
echo "Container built successfully!"
echo "Image: cataloger-agent:latest"
