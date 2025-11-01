# Feedback Loop Implementation

## Overview

Cataloger implements a feedback loop where agents learn from previous successful runs. After each catalog generation, the Python code executed by the agent is extracted, stored in S3, and provided to future runs as context.

## How It Works

### 1. Script Extraction

When an agent runs, the `ContainerRuntime` tracks every `execute_python()` call:

```python
runtime.execute("import ibis")
runtime.execute("conn = ibis.connect(...)")
runtime.execute("table = conn.table('users')")

# Later, extract the session
script = runtime.get_session_script()
# Returns:
# """
# import ibis
#
# conn = ibis.connect(...)
#
# table = conn.table('users')
# """
```

### 2. Script Storage

The workflow saves scripts alongside HTML outputs:

```
s3://bucket/customer-123/orders/
  2024-01-15T10:00:00Z/
    catalog.html           # HTML report
    catalog_script.py      # Python code that generated it
    recent_summary.html
    summary_script.py
  2024-01-15T11:00:00Z/
    catalog.html           # Next run
    catalog_script.py      # Potentially improved version
    ...
```

### 3. Script Retrieval

Before running an agent, the workflow fetches the most recent script:

```python
previous_script = storage.get_latest_script(
    prefix="customer-123/orders",
    filename="catalog_script.py"
)
# Returns: ("2024-01-15T10:00:00Z", "<python code>")
```

### 4. Context Injection

The previous script is passed to the agent via context:

```json
{
  "tables": ["users", "orders"],
  "previous_script": {
    "timestamp": "2024-01-15T10:00:00Z",
    "code": "import ibis\n\nconn = ibis.connect(...)"
  }
}
```

### 5. Agent Adaptation

The agent's prompt instructs it to:
- Review the previous script
- Identify what worked well
- Improve efficiency or clarity
- Adapt the approach based on learning

## Example Evolution

### Run 1: Initial Exploration

```python
# Agent explores database from scratch
import ibis
import os

conn = ibis.connect(os.environ["DB_CONNECTION_STRING"])
users = conn.table("users")

# Naive query - fetches all data
df = users.to_pandas()
print(f"Total users: {len(df)}")
```

### Run 2: Learning from Previous

```python
# Agent sees previous script and improves it
import ibis
import os

conn = ibis.connect(os.environ["DB_CONNECTION_STRING"])
users = conn.table("users")

# Improved - uses count() instead of fetching all rows
count = users.count().execute()
print(f"Total users: {count}")

# Also adds schema inspection learned from previous run
schema = users.schema()
print(f"Columns: {list(schema.names)}")
```

### Run 3: Further Refinement

```python
# Agent refines approach further
import ibis
import os

conn = ibis.connect(os.environ["DB_CONNECTION_STRING"])
users = conn.table("users")

# Efficient aggregations
stats = {
    "count": users.count().execute(),
    "columns": list(users.schema().names),
    "null_rates": {
        col: users[col].isnull().sum().execute() / users.count().execute()
        for col in users.schema().names
    }
}

print(f"User table stats: {stats}")
```

## Benefits

### 1. Iterative Improvement

Each run builds on previous successes, converging on optimal patterns for a given database.

### 2. Script Reusability

Extracted scripts become standalone tools:

```bash
# Download script from S3
aws s3 cp s3://bucket/prefix/timestamp/catalog_script.py .

# Run it standalone
python catalog_script.py
```

### 3. Debugging & Audit Trail

Every catalog has an associated script showing exactly what was executed.

### 4. Reduced Token Usage

After a few runs, agents can execute efficient, battle-tested code instead of exploring from scratch each time.

## Persistent Python Sessions

Critically, the `ContainerRuntime` maintains a **persistent Python interpreter** across tool calls:

```python
# Call 1
runtime.execute("x = 42")

# Call 2 - x is still defined!
runtime.execute("print(x)")  # Works! Prints "42"
```

This matches Armin Ronacher's MCP pattern from [his blog post](https://lucumr.pocoo.org/2025/8/18/code-mcps/):

> Rather than building MCPs with 30+ specialized tools, a more effective approach is exposing a single "ubertool" that accepts programming code as input, maintaining state across invocations.

## Architecture Details

### ContainerRuntime Implementation

The runtime uses a file-based communication pattern:

1. Start persistent Python interpreter in container
2. For each `execute()` call:
   - Write code to `/tmp/code_input.py`
   - Wait for `/tmp/code_output.txt` to appear
   - Read and return output
3. Interpreter loop in container:
   - Watch for input file
   - Execute in persistent `_globals` namespace
   - Write output to output file

This enables true state persistence without complex subprocess management.

### S3 Storage Methods

```python
# Write script
storage.write_script(
    prefix="customer-123/orders",
    timestamp="2024-01-15T10:00:00Z",
    filename="catalog_script.py",
    content=script
)

# Read specific script
storage.read_script(prefix, timestamp, filename)

# Get most recent script (searches last 10 timestamps)
storage.get_latest_script(prefix, filename)
```

### Workflow Integration

```python
# Before agent runs
previous_script = self._get_previous_script(s3_prefix, "catalog_script.py")

# Run agent with context
html = self._run_cataloging_agent(
    runtime=runtime,
    prompt=prompt,
    tables=tables,
    previous_script=previous_script
)

# After agent runs
script = runtime.get_session_script()
storage.write_script(prefix, timestamp, "catalog_script.py", script)
```

## Testing the Feedback Loop

```python
def test_feedback_loop():
    """Verify scripts are extracted and reused."""

    # First run - no previous script
    workflow.run(db_conn, tables, "customer-123/orders")

    # Check script was saved
    result = storage.get_latest_script("customer-123/orders", "catalog_script.py")
    assert result is not None
    timestamp, script = result

    # Second run - should find previous script
    # (Agent would see it in context and can adapt)
    workflow.run(db_conn, tables, "customer-123/orders")
```

## Future Enhancements

### Multi-Database Learning

Track scripts per database type:
- `postgres_catalog_script.py`
- `mysql_catalog_script.py`
- `duckdb_catalog_script.py`

### A/B Testing

Compare approaches:
```python
if random.random() < 0.1:
    # 10% of runs: explore new approaches
    context["previous_script"] = None
else:
    # 90% of runs: use learned script
    context["previous_script"] = latest_script
```

### Script Ranking

Track metrics (execution time, HTML quality) and prefer best-performing scripts:

```python
storage.write_script_with_metrics(
    prefix, timestamp, filename, script,
    metrics={"execution_time": 12.3, "html_size": 45000}
)
```

### Cross-Table Learning

Apply patterns learned from one table to others:
```python
# If we learned good patterns for "users" table,
# suggest them when cataloging "customers" table
```

## Summary

The feedback loop transforms Cataloger from a stateless tool into a **learning system** that improves over time. Each run contributes to a growing library of effective data analysis patterns, specific to your databases.
