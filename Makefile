#!/usr/bin/env bash

# Set the shell for make explicitly
SHELL := /bin/bash

define setup_env
	$(eval ENV_FILE := $(1))
	$(eval include $(1))
	$(eval export)
endef

.PHONY: help
help: ## List available make targets
	@awk 'BEGIN {FS = ":.*?## "}; /^[a-zA-Z0-9_-]+:.*?## / { printf "%-20s %s\n", $$1, $$2 }' $(MAKEFILE_LIST)

.PHONY: install
install: ## Install development dependencies
	uv pip install -e ".[dev]"

.PHONY: format
format: ## Format code with Ruff
	uv run ruff format src server tests
	uv run ruff check --fix src server tests

.PHONY: lint
lint: ## Lint code with Ruff
	uv run ruff check src server tests

.PHONY: test
test: ## Run pytest suite
	uv run pytest tests/ -v

.PHONY: start-dev-session
start-dev-session: ## Start all development services (server + minio) in Docker
	$(call setup_env, .env.server)
	docker compose -f docker-compose.dev.yaml up -d --build

.PHONY: stop-dev-session
stop-dev-session: ## Stop all development services
	docker compose -f docker-compose.dev.yaml down

.PHONY: dev-logs
dev-logs: ## View logs from development services
	docker compose -f docker-compose.dev.yaml logs -f

.PHONY: build-agent
build-agent: ## Build the agent Docker image
	./scripts/build-agent.sh

.PHONY: build-server
build-server: ## Build the agent Docker image
	./scripts/build-server.sh

.PHONY: clean
clean: ## Remove Python caches and build artifacts
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
