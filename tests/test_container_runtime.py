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
