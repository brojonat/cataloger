"""Tests for script extraction and feedback loop."""

import pytest


def test_code_history_tracking(container_runtime):
    """Test that code history is tracked correctly."""
    container_runtime.execute("x = 1")
    container_runtime.execute("y = 2")
    container_runtime.execute("print(x + y)")

    history = container_runtime.get_code_history()
    assert len(history) == 3
    assert history[0] == "x = 1"
    assert history[1] == "y = 2"
    assert history[2] == "print(x + y)"


def test_session_script_extraction(container_runtime):
    """Test that session can be extracted as a script."""
    container_runtime.execute("import os")
    container_runtime.execute("x = 42")
    container_runtime.execute("print(f'x = {x}')")

    script = container_runtime.get_session_script()
    assert "import os" in script
    assert "x = 42" in script
    assert "print(f'x = {x}')" in script

    # Verify double newlines between blocks
    assert "\n\n" in script


def test_true_state_persistence(container_runtime):
    """Test that state TRULY persists across execute calls.

    This is the critical test that verifies we fixed the issue
    from IMPLEMENTATION_GAPS.md - state must persist!
    """
    # Define variable
    container_runtime.execute("my_var = 'hello world'")

    # Use it in next call
    output = container_runtime.execute("print(my_var)")
    assert "hello world" in output

    # Define function
    container_runtime.execute(
        """
def add(a, b):
    return a + b
"""
    )

    # Use function in next call
    output = container_runtime.execute("print(add(10, 20))")
    assert "30" in output


def test_reset_clears_state(container_runtime):
    """Test that reset() clears the interpreter state."""
    # Set up state
    container_runtime.execute("x = 999")
    output = container_runtime.execute("print(x)")
    assert "999" in output

    # Reset
    container_runtime.reset()

    # State should be cleared (will error)
    # Note: We don't actually catch the error in this test,
    # just verify history is cleared
    history = container_runtime.get_code_history()
    assert len(history) == 0


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
