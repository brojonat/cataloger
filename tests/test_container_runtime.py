"""Tests for container runtime."""

import pytest

from cataloger.container.runtime import ContainerRuntime, ExecutionError


def test_execute_simple_expression(container_runtime):
    """Test executing a simple Python expression."""
    output = container_runtime.execute("2 + 2")
    assert "4" in output


def test_execute_print_statement(container_runtime):
    """Test executing print statements."""
    output = container_runtime.execute("print('hello world')")
    assert "hello world" in output


def test_execute_with_error(container_runtime):
    """Test that execution errors are captured."""
    with pytest.raises(ExecutionError):
        container_runtime.execute("raise ValueError('test error')")


def test_execute_multiline(container_runtime):
    """Test executing multiline code."""
    code = """
x = 10
y = 20
print(f"Sum: {x + y}")
"""
    output = container_runtime.execute(code)
    assert "Sum: 30" in output


def test_state_persists(container_runtime):
    """Test that state persists across execute calls."""
    container_runtime.execute("x = 42")
    output = container_runtime.execute("print(x)")
    assert "42" in output


def test_get_session_script(container_runtime):
    """Test that session script includes both code and output."""
    # Execute some code
    container_runtime.execute("x = 10")
    container_runtime.execute("print(x * 2)")
    container_runtime.execute("y = 'hello'")

    # Get the session script
    script = container_runtime.get_session_script()

    # Verify script contains code blocks
    assert "# === Code Block 1 ===" in script
    assert "x = 10" in script
    assert "# === Code Block 2 ===" in script
    assert "print(x * 2)" in script
    assert "# === Code Block 3 ===" in script
    assert "y = 'hello'" in script

    # Verify ALL blocks have output sections (even if no output)
    assert "# --- Output 1 ---" in script
    assert "# (no output)" in script  # Block 1 has no output
    assert "# --- Output 2 ---" in script
    assert "# 20" in script  # Output of print(x * 2)
    assert "# --- Output 3 ---" in script
    # Block 3 also has no output, so another "# (no output)" will appear


def test_database_connection_switching(container_pool):
    """Test that database connection strings are properly switched when reusing containers."""
    # First runtime with DB_A
    runtime1 = container_pool.acquire(db_connection_string="duckdb:///data/db_a.duckdb")
    output1 = runtime1.execute('import os; print(os.environ.get("DB_CONNECTION_STRING"))')
    assert "db_a.duckdb" in output1
    container_pool.release(runtime1)

    # Second runtime with DB_B (should reuse the same container)
    runtime2 = container_pool.acquire(db_connection_string="duckdb:///data/db_b.duckdb")
    output2 = runtime2.execute('import os; print(os.environ.get("DB_CONNECTION_STRING"))')
    assert "db_b.duckdb" in output2
    assert "db_a.duckdb" not in output2  # Should NOT see the old connection
    container_pool.release(runtime2)


@pytest.fixture
def container_runtime(container_pool):
    """Fixture providing a container runtime."""
    runtime = container_pool.acquire()
    yield runtime
    container_pool.release(runtime)


@pytest.fixture(scope="module")
def container_pool():
    """Fixture providing a container pool."""
    import docker
    from cataloger.container.pool import ContainerPool

    # Check if Docker is available
    try:
        client = docker.from_env()
        client.ping()
    except Exception:
        pytest.skip("Docker not available")

    # Check if image exists
    try:
        pool = ContainerPool(pool_size=2)
    except RuntimeError:
        pytest.skip("Container image not built. Run: make build-container")

    yield pool
    pool.cleanup()
