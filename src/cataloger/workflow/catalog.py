"""DBOS workflow for catalog generation."""

import base64
import os
from typing import Any

import anthropic
import structlog
import yaml
from dbos import DBOS, SetWorkflowID, Workflow

from ..agent.loop import AgentLoop
from ..container.pool import ContainerPool
from ..storage.s3 import S3Storage, generate_timestamp

log = structlog.get_logger()


class CatalogWorkflow:
    """Orchestrates the catalog generation workflow.

    Workflow steps:
    1. Acquire container from pool
    2. Run cataloging agent → HTML
    3. Write catalog HTML to S3
    4. Run summary agent (using same container) → HTML
    5. Write summary HTML to S3
    6. Release container
    """

    def __init__(
        self,
        container_pool: ContainerPool,
        s3_storage: S3Storage,
        anthropic_client: anthropic.Anthropic,
    ):
        self.container_pool = container_pool
        self.s3_storage = s3_storage
        self.anthropic_client = anthropic_client

    @DBOS.workflow()
    def run(
        self,
        db_connection_string: str,
        tables: list[str],
        s3_prefix: str,
    ) -> dict[str, Any]:
        """Run the catalog workflow.

        Args:
            db_connection_string: Readonly database connection string
            tables: List of table names to catalog
            s3_prefix: S3 prefix for storing results (e.g., "customer-123/orders")

        Returns:
            Dict with:
                - timestamp: ISO timestamp
                - catalog_uri: S3 URI of catalog HTML
                - summary_uri: S3 URI of summary HTML
                - token_usage: Token usage stats
        """
        timestamp = generate_timestamp()

        log.info(
            "workflow.start",
            tables=tables,
            s3_prefix=s3_prefix,
            timestamp=timestamp,
        )

        # Load prompts from environment
        cataloging_prompt = self._load_prompt("CATALOGING_AGENT_PROMPT")
        summary_prompt = self._load_prompt("SUMMARY_AGENT_PROMPT")

        # Acquire container
        runtime = self.container_pool.acquire(
            db_connection_string=db_connection_string,
            s3_config=self.s3_storage.get_config(),
        )

        try:
            # Fetch previous scripts for feedback loop
            previous_catalog_script = self._get_previous_script(
                s3_prefix, "catalog_script.py"
            )
            previous_summary_script = self._get_previous_script(
                s3_prefix, "summary_script.py"
            )

            # Run cataloging agent
            catalog_html = self._run_cataloging_agent(
                runtime=runtime,
                prompt=cataloging_prompt,
                tables=tables,
                previous_script=previous_catalog_script,
            )

            # Extract and save cataloging script
            catalog_script = runtime.get_session_script()
            catalog_script_uri = self.s3_storage.write_script(
                prefix=s3_prefix,
                timestamp=timestamp,
                filename="catalog_script.py",
                content=catalog_script,
            )

            # Write catalog HTML to S3
            catalog_uri = self.s3_storage.write_html(
                prefix=s3_prefix,
                timestamp=timestamp,
                filename="catalog.html",
                content=catalog_html,
            )

            # Reset container for summary agent
            runtime.reset()

            # Run summary agent
            summary_html = self._run_summary_agent(
                runtime=runtime,
                prompt=summary_prompt,
                s3_prefix=s3_prefix,
                current_timestamp=timestamp,
                previous_script=previous_summary_script,
            )

            # Extract and save summary script
            summary_script = runtime.get_session_script()
            summary_script_uri = self.s3_storage.write_script(
                prefix=s3_prefix,
                timestamp=timestamp,
                filename="summary_script.py",
                content=summary_script,
            )

            # Write summary HTML to S3
            summary_uri = self.s3_storage.write_html(
                prefix=s3_prefix,
                timestamp=timestamp,
                filename="recent_summary.html",
                content=summary_html,
            )

            log.info(
                "workflow.complete",
                catalog_uri=catalog_uri,
                summary_uri=summary_uri,
            )

            return {
                "timestamp": timestamp,
                "catalog_uri": catalog_uri,
                "catalog_script_uri": catalog_script_uri,
                "summary_uri": summary_uri,
                "summary_script_uri": summary_script_uri,
                "s3_prefix": s3_prefix,
            }

        finally:
            # Always release container
            self.container_pool.release(runtime)

    def _run_cataloging_agent(
        self,
        runtime: Any,
        prompt: str,
        tables: list[str],
        previous_script: tuple[str, str] | None = None,
    ) -> str:
        """Run the cataloging agent."""
        agent = AgentLoop(
            client=self.anthropic_client,
            runtime=runtime,
        )

        context = {"tables": tables}

        # Add previous script to context if available
        if previous_script:
            prev_timestamp, prev_code = previous_script
            context["previous_script"] = {
                "timestamp": prev_timestamp,
                "code": prev_code,
            }

        return agent.run(system_prompt=prompt, context=context)

    def _run_summary_agent(
        self,
        runtime: Any,
        prompt: str,
        s3_prefix: str,
        current_timestamp: str,
        previous_script: tuple[str, str] | None = None,
    ) -> str:
        """Run the summary agent."""
        agent = AgentLoop(
            client=self.anthropic_client,
            runtime=runtime,
        )

        context = {
            "s3_prefix": s3_prefix,
            "current_timestamp": current_timestamp,
        }

        # Add previous script to context if available
        if previous_script:
            prev_timestamp, prev_code = previous_script
            context["previous_script"] = {
                "timestamp": prev_timestamp,
                "code": prev_code,
            }

        return agent.run(system_prompt=prompt, context=context)

    def _get_previous_script(
        self, s3_prefix: str, filename: str
    ) -> tuple[str, str] | None:
        """Get the most recent script for feedback loop.

        Args:
            s3_prefix: S3 prefix
            filename: Script filename (e.g., "catalog_script.py")

        Returns:
            Tuple of (timestamp, script_content) or None
        """
        result = self.s3_storage.get_latest_script(s3_prefix, filename)

        if result:
            log.info(
                "workflow.previous_script_found",
                s3_prefix=s3_prefix,
                filename=filename,
                timestamp=result[0],
            )
        else:
            log.info(
                "workflow.previous_script_not_found",
                s3_prefix=s3_prefix,
                filename=filename,
            )

        return result

    def _load_prompt(self, env_var: str) -> str:
        """Load a prompt from base64-encoded YAML in environment."""
        encoded = os.getenv(env_var)
        if not encoded:
            raise ValueError(f"Missing environment variable: {env_var}")

        # Decode base64
        decoded = base64.b64decode(encoded).decode("utf-8")

        # Parse YAML
        data = yaml.safe_load(decoded)

        # Return the prompt field
        return data.get("prompt", "")
