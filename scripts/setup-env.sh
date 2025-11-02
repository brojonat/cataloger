#!/usr/bin/env bash
# Setup environment for Cataloger development
#
# Usage:
#   ./scripts/setup-env.sh

set -e

USE_MINIO=false
if [ "$1" = "--minio" ]; then
    USE_MINIO=true
fi

echo "Setting up environment for Cataloger..."

# Check if prompts exist
if [ ! -f "prompts/cataloging_agent.yaml" ]; then
    echo "Error: prompts/cataloging_agent.yaml not found"
    exit 1
fi

if [ ! -f "prompts/summary_agent.yaml" ]; then
    echo "Error: prompts/summary_agent.yaml not found"
    exit 1
fi

# Create .env.server from template if it doesn't exist
if [ ! -f ".env.server" ]; then
    if [ "$USE_MINIO" = true ]; then
        cp .env.server.minio .env.server
        echo "✓ Created .env.server from MinIO template"
        echo "  MinIO will provide local S3-compatible storage"
        echo "  Start MinIO: ./scripts/start-dev-services.sh"
    else
        cp .env.server.example .env.server
        echo "✓ Created .env.server from example"
        echo "  You'll need to configure AWS S3 credentials"
    fi
else
    echo "ℹ️  .env.server already exists, skipping creation"
    echo "  To update S3 configuration, edit .env.server directly"
fi

# Encode prompts
echo "Encoding prompts..."
CATALOGING_PROMPT=$(base64 -i prompts/cataloging_agent.yaml)
SUMMARY_PROMPT=$(base64 -i prompts/summary_agent.yaml)

# Update .env.server with encoded prompts
if grep -q "^CATALOGING_AGENT_PROMPT=" .env.server; then
    # Update existing
    sed -i.bak "s|^CATALOGING_AGENT_PROMPT=.*|CATALOGING_AGENT_PROMPT=\"${CATALOGING_PROMPT}\"|" .env.server
    sed -i.bak "s|^SUMMARY_AGENT_PROMPT=.*|SUMMARY_AGENT_PROMPT=\"${SUMMARY_PROMPT}\"|" .env.server
    rm .env.server.bak
else
    # Append new
    echo "CATALOGING_AGENT_PROMPT=\"${CATALOGING_PROMPT}\"" >> .env.server
    echo "SUMMARY_AGENT_PROMPT=\"${SUMMARY_PROMPT}\"" >> .env.server
fi

echo "✓ Encoded prompts and updated .env.server"
echo ""
echo "Next steps:"
echo "  1. Edit .env.server and set your API keys and S3 configuration"
echo "  2. Build the container: make build-container"
echo "  3. Start the server: make run-server"
