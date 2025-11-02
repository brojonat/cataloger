# Development Guide

## Project Structure

```
cataloger/
├── src/cataloger/           # Main package
│   ├── agent/              # Agent loop and tools
│   ├── container/          # Container runtime and pool
│   ├── storage/            # S3 storage client
│   ├── workflow/           # DBOS workflow orchestration
│   └── cli.py             # Command-line interface
├── server/                 # FastAPI server
│   └── main.py            # API endpoints
├── prompts/               # Agent prompts (YAML)
├── tests/                 # Test suite
├── scripts/               # Helper scripts
└── data/                  # Local data (gitignored)
```

## Setup

### Prerequisites

- Python 3.13+
- Docker (for container runtime)
- uv (Python package manager)
- AWS credentials (for S3)
- Anthropic API key

### Installation

1. Install dependencies:
```bash
uv pip install -e ".[dev]"
```

2. Build the agent container:
```bash
make build-container
```

3. Set up environment:
```bash
./scripts/setup-env.sh
```

4. Edit `.env.server` with your credentials:
   - `LLM_API_KEY`: Your Anthropic API key
   - `S3_BUCKET`: Your S3 bucket name
   - `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY`: AWS credentials
   - `AUTH_SECRET`: Strong secret for JWT signing

## Running

### Start the server

```bash
make run-server
```

The server will be available at `http://localhost:8000`.

### Generate a test token

```bash
uv run cataloger generate-token your-secret-key
```

### Trigger a catalog

Using the CLI:
```bash
export CATALOGER_API_URL=http://localhost:8000
export CATALOGER_AUTH_TOKEN=<your-token>

uv run cataloger catalog \
  --db-conn "postgresql://user:pass@host:5432/db" \
  --table users --table orders --table products \
  --s3-prefix "customer-123/prod"
```

Using curl:
```bash
curl -X POST http://localhost:8000/catalog \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "db_connection_string": "postgresql://user:pass@host:5432/db",
    "tables": ["users", "orders"],
    "s3_prefix": "customer-123/prod"
  }'
```

## Testing

Run the test suite:
```bash
make test
```

Note: Container tests require Docker and the agent image to be built.

## Code Quality

Format code:
```bash
make format
```

Lint code:
```bash
make lint
```

## Architecture

### Container Runtime

- `ContainerRuntime`: Executes Python code in a Docker container
- `ContainerPool`: Manages a pool of pre-warmed containers
- Each container runs Python 3.13 with ibis, boto3, pandas/polars

### Agent Loop

- `AgentLoop`: Manages conversation with Claude API
- Tools: `execute_python(code)` and `submit_html(content)`
- Token budget tracking and safety limits

### Workflow

- `CatalogWorkflow`: Orchestrates the full pipeline
- Uses DBOS for workflow management
- Steps:
  1. Acquire container
  2. Run cataloging agent → HTML
  3. Write to S3
  4. Run summary agent → HTML
  5. Write to S3
  6. Release container

### Storage

- `S3Storage`: Handles S3 reads/writes
- Path structure: `{prefix}/{timestamp}/{filename}.html`
- HTML files ARE the application state

## Prompt Engineering

Prompts are stored in `prompts/` as YAML files and loaded as base64-encoded environment variables.

To update a prompt:

1. Edit the YAML file in `prompts/`
2. Run `./scripts/setup-env.sh` to re-encode
3. Restart the server

## Debugging

Enable debug logging:
```bash
export LOG_LEVEL=DEBUG
make run-server
```

View container logs:
```bash
docker ps
docker logs <container-id>
```

## Common Issues

### Container image not found

Build the image:
```bash
make build-container
```

### Agent exceeds token budget

Adjust `max_tokens` in `AgentLoop` initialization (workflow/catalog.py)

### S3 connection errors

Verify AWS credentials:
```bash
aws s3 ls s3://your-bucket-name
```

## Deployment

For production deployment:

1. Use a secrets manager for credentials (AWS Secrets Manager, Vault)
2. Set up proper S3 bucket policies and IAM roles
3. Configure log aggregation (CloudWatch, Datadog)
4. Set up monitoring and alerting on `/metrics` endpoint
5. Use a process manager (systemd, supervisord) or container orchestrator (ECS, K8s)
6. Enable JSON logging: `export LOG_JSON=true`

## Extensions

To add a new agent:

1. Create a prompt YAML in `prompts/`
2. Add environment variable for the prompt
3. Update `CatalogWorkflow.run()` to call the new agent
4. Update the API schema if needed

## Contributing

1. Follow the style guidelines in `claude_guidelines/`
2. Write tests for new features
3. Run `make format lint test` before committing
4. Keep prompts under version control
