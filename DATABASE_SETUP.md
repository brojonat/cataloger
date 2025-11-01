# Database Setup & Container Access

## How DuckDB Files Work with Containers

### The Problem You Identified

You asked a great question: "How is our agent supposed to connect to this DB (in its python process/container) if the DB isn't listening on some port?"

**Answer**: We use **Docker volume mounting** to make local files accessible inside containers.

## How It Works

### 1. DuckDB is File-Based

Unlike Postgres/MySQL which are network services listening on ports, DuckDB is an **embedded database** that reads/writes to local files:

```python
# Network database (works across containers)
conn = ibis.connect("postgresql://host:5432/db")

# File database (needs file access)
conn = ibis.connect("duckdb:///path/to/file.duckdb")
```

### 2. Volume Mounting Makes Files Available

The container pool mounts the host's `data/` directory into the container:

**Code**: `src/cataloger/container/pool.py:49-68`

```python
def _create_container(self) -> Container:
    """Create a new container and start it."""
    # Mount data directory if it exists (for DuckDB files)
    volumes = {}
    data_dir = os.path.abspath("data")  # Host: /home/user/cataloger/data
    if os.path.exists(data_dir):
        volumes[data_dir] = {"bind": "/data", "mode": "ro"}  # Container: /data

    container = self.client.containers.run(
        self.image_name,
        volumes=volumes,  # ← Mount happens here
        ...
    )
```

### 3. Path Translation

```
HOST FILESYSTEM              CONTAINER FILESYSTEM
├── data/                    ├── /data/           ← MOUNTED
│   ├── sample_ecommerce.duckdb  →  sample_ecommerce.duckdb
│   └── sample_timeseries.duckdb →  sample_timeseries.duckdb
├── src/
└── scripts/
```

The agent inside the container uses the **container path**:

```python
# Inside container
conn = ibis.connect("duckdb:////data/sample_ecommerce.duckdb")
#                            ^^^^^ Container path, not host path
```

## Example Flow

### 1. Create DuckDB file on host

```bash
./scripts/bootstrap-db.sh
# Creates: data/sample_ecommerce.duckdb (on your machine)
```

### 2. Start server

```bash
./scripts/run-server.sh
```

Server creates container with volume mount:

```
docker run -v /home/user/cataloger/data:/data cataloger-agent:latest
```

### 3. Trigger catalog

```bash
./scripts/catalog-ecommerce.sh
```

This script uses the **container path**:

```bash
CONTAINER_DB_PATH="/data/sample_ecommerce.duckdb"  # Not host path!
uv run cataloger catalog --db-conn "duckdb:///${CONTAINER_DB_PATH}" ...
```

### 4. Agent connects to file

Inside the container, the agent runs:

```python
import ibis
import os

# Connection string passed via environment
conn_str = os.environ["DB_CONNECTION_STRING"]  # "duckdb:////data/sample_ecommerce.duckdb"
conn = ibis.connect(conn_str)

# This works because:
# - Container has /data directory (mounted)
# - /data/sample_ecommerce.duckdb exists (from host)
# - DuckDB opens the file for reading
```

## Network Databases (Alternative)

For production, you might use network databases instead:

### Option 1: Postgres in Docker

```bash
# Start Postgres
docker run -d -p 5432:5432 \
  -e POSTGRES_PASSWORD=secret \
  postgres:16

# Agent connects over network (no volume mount needed)
uv run cataloger catalog \
  --db-conn "postgresql://postgres:secret@host.docker.internal:5432/postgres" \
  --tables "users,orders"
```

The agent container can reach the Postgres container via Docker's network bridge.

### Option 2: Remote Database

```bash
# Agent connects to remote database
uv run cataloger catalog \
  --db-conn "postgresql://user:pass@prod-db.company.com:5432/app" \
  --tables "users,orders"
```

No volume mounting needed - pure network connection.

## Why Volume Mounting for Local Testing

**Advantages**:
- ✅ No database server to manage
- ✅ Fast setup (just files)
- ✅ Easy to version control (small SQLite-style files)
- ✅ Perfect for development/testing
- ✅ No port conflicts

**Disadvantages**:
- ❌ Container needs file access (volume mount)
- ❌ Not suitable for concurrent writes (DuckDB limitation)
- ❌ Doesn't test network database behavior

## Key Takeaways

1. **DuckDB = file**, not network service
2. **Volume mount** makes host files visible to container
3. **Container path** (`/data/...`) used in connection strings, not host path
4. **Read-only mount** ensures safety (agent can't modify local files)
5. **Network databases** (Postgres, MySQL) don't need volume mounts

## Troubleshooting

### Agent can't find database file

**Error**: `IO Error: Cannot open file "/data/sample_ecommerce.duckdb"`

**Fix**: Ensure you're using the container path, not host path:

```bash
# ❌ Wrong (host path)
--db-conn "duckdb:////home/user/cataloger/data/sample_ecommerce.duckdb"

# ✅ Correct (container path)
--db-conn "duckdb:////data/sample_ecommerce.duckdb"
```

### Volume not mounted

**Error**: `IO Error: Directory "/data" does not exist`

**Fix**: Ensure `data/` directory exists before starting server:

```bash
mkdir -p data
./scripts/bootstrap-db.sh
./scripts/run-server.sh
```

### Permission errors

**Error**: `Permission denied: /data/sample_ecommerce.duckdb`

**Current setup**: Mount is read-only (`"mode": "ro"`) which is good for safety.

If you need write access (e.g., for temporary tables), change to:
```python
volumes[data_dir] = {"bind": "/data", "mode": "rw"}
```

But for cataloging (readonly), `"ro"` is safer.

## Summary

The "trick" you asked about is **Docker volume mounting**:

1. Host has files: `data/*.duckdb`
2. Container mounts: `-v host/data:/data`
3. Agent accesses: `duckdb:////data/*.duckdb`
4. It just works! 🎉

No database server needed for local testing - just files + volume mounts.
