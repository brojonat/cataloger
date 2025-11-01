#!/usr/bin/env bash

# Set the shell for make explicitly
SHELL := /bin/bash

define setup_env
	$(eval ENV_FILE := $(1))
	$(eval include $(1))
	$(eval export)
endef

.PHONY: install
install:
	uv pip install -e ".[dev]"

.PHONY: format
format:
	uv run ruff format src server tests
	uv run ruff check --fix src server tests

.PHONY: lint
lint:
	uv run ruff check src server tests

.PHONY: test
test:
	uv run pytest tests/ -v

.PHONY: run-server
run-server:
	$(call setup_env, .env.server)
	uv run uvicorn server.main:app --host 0.0.0.0 --port 8000 --reload

.PHONY: build-container
build-container:
	docker build -t cataloger-agent:latest -f Dockerfile.agent .

.PHONY: clean
clean:
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
