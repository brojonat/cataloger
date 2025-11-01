import os
from contextlib import contextmanager
from typing import Any, Iterator

import docker
from docker.models.containers import Container

from .runtime import ContainerRuntime


class ContainerPool:
    """Manages a pool of pre-warmed containers for agent execution.

    This provides acquire/release semantics for containers, with each
    container maintaining state across multiple agent runs until released.
    """

    def __init__(
        self,
        image_name: str = "cataloger-agent:latest",
        pool_size: int = 5,
        container_timeout: int = 300,
    ):
        """Initialize the container pool.

        Args:
            image_name: Docker image to use for containers
            pool_size: Maximum number of containers in the pool
            container_timeout: Maximum lifetime for a container in seconds
        """
        self.image_name = image_name
        self.pool_size = pool_size
        self.container_timeout = container_timeout
        self.client = docker.from_env()

        # Verify image exists
        try:
            self.client.images.get(image_name)
        except docker.errors.ImageNotFound:
            raise RuntimeError(
                f"Container image '{image_name}' not found. "
                f"Build it with: make build-container"
            )

        # Pool of available containers
        self._available: list[Container] = []
        self._in_use: set[str] = set()

    def _create_container(self) -> Container:
        """Create a new container and start it."""
        container = self.client.containers.run(
            self.image_name,
            detach=True,
            remove=False,  # We manage cleanup
            mem_limit="1g",
            cpu_quota=100000,  # 1 CPU
            network_mode="bridge",
        )
        return container

    def acquire(
        self,
        db_connection_string: str | None = None,
        s3_config: dict[str, Any] | None = None,
    ) -> ContainerRuntime:
        """Acquire a container from the pool.

        Args:
            db_connection_string: Optional database connection string
            s3_config: Optional S3 configuration dict

        Returns:
            ContainerRuntime instance ready for code execution
        """
        # Try to get an available container
        if self._available:
            container = self._available.pop()
        # Or create a new one if under pool size
        elif len(self._in_use) < self.pool_size:
            container = self._create_container()
        else:
            raise RuntimeError(f"Container pool exhausted (size={self.pool_size})")

        self._in_use.add(container.id)
        return ContainerRuntime(
            container=container,
            db_connection_string=db_connection_string,
            s3_config=s3_config,
        )

    def release(self, runtime: ContainerRuntime) -> None:
        """Release a container back to the pool.

        The container is reset and made available for reuse.
        """
        container_id = runtime.container.id
        if container_id not in self._in_use:
            raise ValueError(f"Container {container_id} not in use")

        self._in_use.remove(container_id)
        runtime.reset()
        self._available.append(runtime.container)

    def cleanup(self) -> None:
        """Stop and remove all containers in the pool."""
        # Clean up in-use containers
        for container_id in list(self._in_use):
            try:
                container = self.client.containers.get(container_id)
                container.stop(timeout=5)
                container.remove()
            except docker.errors.NotFound:
                pass
            self._in_use.discard(container_id)

        # Clean up available containers
        for container in self._available:
            try:
                container.stop(timeout=5)
                container.remove()
            except docker.errors.APIError:
                pass
        self._available.clear()

    @contextmanager
    def get_runtime(
        self,
        db_connection_string: str | None = None,
        s3_config: dict[str, Any] | None = None,
    ) -> Iterator[ContainerRuntime]:
        """Context manager for acquiring and releasing a container runtime.

        Example:
            with pool.get_runtime(db_conn) as runtime:
                output = runtime.execute("import ibis; print(ibis.__version__)")
        """
        runtime = self.acquire(
            db_connection_string=db_connection_string, s3_config=s3_config
        )
        try:
            yield runtime
        finally:
            self.release(runtime)
