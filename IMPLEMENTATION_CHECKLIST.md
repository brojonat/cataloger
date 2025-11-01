# Implementation Checklist

## Phase 1: Core Agent Runtime

### Container Runtime
- [ ] Create Dockerfile with Python + ibis + database drivers (postgres, mysql, duckdb)
- [ ] Include boto3, pandas/polars for data processing
- [ ] Set up container execution interface (exec Python code, return output stream)
- [ ] Implement container pool (acquire, release, reset Python process)
- [ ] Add container timeout mechanism
- [ ] Test: Spin up container, execute code, get output, reset, reuse

### Agent Loop
- [ ] Define tool schemas for `execute_python(code)` and `submit_html(content)`
- [ ] Implement core agent loop (send prompt, handle tool calls, accumulate messages)
- [ ] Integrate with LLM API (Claude/Anthropic)
- [ ] Add token budget tracking
- [ ] Handle tool call routing (execute_python vs submit_html)
- [ ] Test: Run agent with mock container, verify it can iterate and terminate

### Integration Test
- [ ] End-to-end test: Agent queries mock database, generates HTML, calls submit_html
- [ ] Verify container state persists across execute_python calls within one agent
- [ ] Verify container resets between different agents

## Phase 2: Storage & Workflows

### S3/Object Storage
- [ ] Implement S3 client wrapper (list, read, write HTML)
- [ ] Define path schema: `{prefix}/{timestamp}/{agent_name}.html`
- [ ] Add timestamp generation (ISO format)
- [ ] Test: Write HTML, read back, list by prefix

### DBOS Workflow Orchestration
- [ ] Set up DBOS project structure
- [ ] Implement `catalog_workflow(db_conn_string, tables, s3_prefix)`
- [ ] Chain: cataloging agent → write HTML → summary agent → write HTML
- [ ] Pass container through workflow (acquire once, use for both agents, release)
- [ ] Add workflow error handling and cleanup
- [ ] Test: Run full workflow, verify both HTMLs written to S3

## Phase 3: Prompts & Configuration

### Prompt Management
- [ ] Create `prompts/` directory with YAML files
- [ ] Define cataloging agent prompt (instructions, table limits, HTML format)
- [ ] Define summary agent prompt (temporal analysis, good/bad criteria)
- [ ] Implement YAML → base64 encoding
- [ ] Load prompts from environment variables
- [ ] Test: Modify prompt, verify agent behavior changes

### Agent Context Injection
- [ ] Cataloging agent: inject `{"tables": [...]}` into initial message
- [ ] Summary agent: inject `{"s3_prefix": "...", "current_timestamp": "..."}`
- [ ] Document expected context structure for each agent

## Phase 4: API Service

### HTTP Endpoint
- [ ] Implement POST `/catalog` endpoint
- [ ] Request schema: `{db_conn_string, tables, s3_prefix}`
- [ ] Trigger DBOS workflow asynchronously
- [ ] Return workflow ID or status
- [ ] Add request validation
- [ ] Test: POST request → workflow executes → HTML appears in S3

### Error Handling
- [ ] Handle agent failures (timeout, token budget exceeded)
- [ ] Handle container failures (crash, network issues)
- [ ] Handle S3 write failures
- [ ] Return meaningful error responses

## Phase 5: Polish & Production

### Observability
- [ ] Add structured logging (workflow start/end, agent start/end, tool calls)
- [ ] Log token usage per agent
- [ ] Log S3 write operations
- [ ] Add metrics/tracing if needed

### Documentation
- [ ] Document environment variables (prompts, S3 config, LLM API keys)
- [ ] Document deployment (Docker, DBOS setup)
- [ ] Add example requests and expected outputs
- [ ] Document prompt engineering guidelines

### Testing
- [ ] Unit tests for container pool
- [ ] Unit tests for agent loop
- [ ] Integration tests for workflows
- [ ] End-to-end test with real database (postgres/duckdb)
- [ ] Load testing (concurrent catalog requests)

### Security & Hardening
- [ ] Validate readonly database connections (test with write attempt)
- [ ] Sanitize S3 paths (prevent path traversal)
- [ ] Review container sandboxing
- [ ] Add rate limiting to API endpoint
- [ ] Secrets management for DB connection strings

## Phase 6: Extensions (Future)

- [ ] Additional analysis agents (anomaly detection, schema drift, etc.)
- [ ] Agent dependencies (agent B only runs if agent A succeeded)
- [ ] Webhook notifications on catalog completion
- [ ] Web UI for browsing catalog history
- [ ] Scheduled catalogs (cron-like triggers)
- [ ] Multi-database support in single catalog run

---

## Implementation Notes

**Recommended Order**: Follow phases sequentially. Phase 1 & 2 are foundational.
Phase 3 can be done in parallel with Phase 4. Phase 5 is ongoing.

**Quick Start Path**: For MVP, implement just the cataloging agent (skip summary
agent initially). This proves the core concept with minimal scope.

**Testing Strategy**: Write integration tests early. The agent loop is the
highest-risk component (LLM unpredictability, container orchestration).

**Dependencies**:
- DBOS for workflow orchestration
- Anthropic SDK for Claude API
- Docker SDK for container management
- boto3 for S3
- ibis-framework for database queries
