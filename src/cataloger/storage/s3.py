"""S3 client wrapper for HTML storage."""

import os
from datetime import datetime
from typing import Any

import boto3
import structlog

log = structlog.get_logger()


class S3Storage:
    """Handles reading and writing HTML catalogs to S3.

    Path structure: s3://{bucket}/{prefix}/{timestamp}/{filename}.html
    """

    def __init__(
        self,
        bucket: str,
        region: str = "us-east-1",
        access_key_id: str | None = None,
        secret_access_key: str | None = None,
    ):
        """Initialize S3 storage.

        Args:
            bucket: S3 bucket name
            region: AWS region
            access_key_id: AWS access key (defaults to environment)
            secret_access_key: AWS secret key (defaults to environment)
        """
        self.bucket = bucket
        self.region = region

        # Initialize boto3 client
        session_kwargs: dict[str, Any] = {"region_name": region}
        if access_key_id and secret_access_key:
            session_kwargs.update(
                {
                    "aws_access_key_id": access_key_id,
                    "aws_secret_access_key": secret_access_key,
                }
            )

        self.s3 = boto3.client("s3", **session_kwargs)

    def write_html(
        self, prefix: str, timestamp: str, filename: str, content: str
    ) -> str:
        """Write HTML content to S3.

        Args:
            prefix: S3 prefix (e.g., "customer-123/orders")
            timestamp: ISO timestamp (e.g., "2024-01-15T10:00:00Z")
            filename: HTML filename (e.g., "catalog.html")
            content: HTML content

        Returns:
            S3 URI of written object
        """
        key = f"{prefix}/{timestamp}/{filename}"

        self.s3.put_object(
            Bucket=self.bucket,
            Key=key,
            Body=content.encode("utf-8"),
            ContentType="text/html",
        )

        uri = f"s3://{self.bucket}/{key}"
        log.info("storage.write", uri=uri, size=len(content))
        return uri

    def read_html(self, prefix: str, timestamp: str, filename: str) -> str:
        """Read HTML content from S3.

        Args:
            prefix: S3 prefix
            timestamp: ISO timestamp
            filename: HTML filename

        Returns:
            HTML content as string
        """
        key = f"{prefix}/{timestamp}/{filename}"

        response = self.s3.get_object(Bucket=self.bucket, Key=key)
        content = response["Body"].read().decode("utf-8")

        log.info("storage.read", key=key, size=len(content))
        return content

    def write_script(
        self, prefix: str, timestamp: str, filename: str, content: str
    ) -> str:
        """Write Python script to S3.

        Args:
            prefix: S3 prefix (e.g., "customer-123/orders")
            timestamp: ISO timestamp (e.g., "2024-01-15T10:00:00Z")
            filename: Script filename (e.g., "catalog_script.py")
            content: Python code

        Returns:
            S3 URI of written object
        """
        key = f"{prefix}/{timestamp}/{filename}"

        self.s3.put_object(
            Bucket=self.bucket,
            Key=key,
            Body=content.encode("utf-8"),
            ContentType="text/x-python",
        )

        uri = f"s3://{self.bucket}/{key}"
        log.info("storage.write_script", uri=uri, size=len(content))
        return uri

    def read_script(self, prefix: str, timestamp: str, filename: str) -> str | None:
        """Read Python script from S3.

        Args:
            prefix: S3 prefix
            timestamp: ISO timestamp
            filename: Script filename

        Returns:
            Python code as string, or None if not found
        """
        key = f"{prefix}/{timestamp}/{filename}"

        try:
            response = self.s3.get_object(Bucket=self.bucket, Key=key)
            content = response["Body"].read().decode("utf-8")
            log.info("storage.read_script", key=key, size=len(content))
            return content
        except self.s3.exceptions.NoSuchKey:
            log.info("storage.read_script.not_found", key=key)
            return None

    def get_latest_script(self, prefix: str, filename: str) -> tuple[str, str] | None:
        """Get the most recent script for a given prefix.

        Args:
            prefix: S3 prefix
            filename: Script filename (e.g., "catalog_script.py")

        Returns:
            Tuple of (timestamp, script_content) or None if not found
        """
        timestamps = self.list_timestamps(prefix, limit=10)

        for timestamp in timestamps:
            script = self.read_script(prefix, timestamp, filename)
            if script:
                log.info(
                    "storage.get_latest_script",
                    prefix=prefix,
                    filename=filename,
                    timestamp=timestamp,
                )
                return (timestamp, script)

        log.info("storage.get_latest_script.not_found", prefix=prefix, filename=filename)
        return None

    def list_timestamps(self, prefix: str, limit: int = 100) -> list[str]:
        """List timestamps for a given prefix, most recent first.

        Args:
            prefix: S3 prefix
            limit: Maximum number of timestamps to return

        Returns:
            List of ISO timestamps, sorted newest to oldest
        """
        # List objects under prefix
        response = self.s3.list_objects_v2(
            Bucket=self.bucket, Prefix=f"{prefix}/", Delimiter="/"
        )

        # Extract timestamps from CommonPrefixes
        timestamps = []
        for item in response.get("CommonPrefixes", []):
            # item["Prefix"] looks like "prefix/2024-01-15T10:00:00Z/"
            parts = item["Prefix"].rstrip("/").split("/")
            if len(parts) >= 2:
                timestamp = parts[-1]
                timestamps.append(timestamp)

        # Sort newest first
        timestamps.sort(reverse=True)
        return timestamps[:limit]

    def list_catalogs(
        self, prefix: str, timestamp: str
    ) -> list[dict[str, str]]:
        """List all HTML catalogs for a given timestamp.

        Args:
            prefix: S3 prefix
            timestamp: ISO timestamp

        Returns:
            List of dicts with "filename" and "key" for each HTML file
        """
        key_prefix = f"{prefix}/{timestamp}/"

        response = self.s3.list_objects_v2(Bucket=self.bucket, Prefix=key_prefix)

        catalogs = []
        for obj in response.get("Contents", []):
            key = obj["Key"]
            if key.endswith(".html"):
                filename = key.split("/")[-1]
                catalogs.append({"filename": filename, "key": key})

        log.info("storage.list_catalogs", prefix=prefix, timestamp=timestamp, count=len(catalogs))
        return catalogs

    def get_config(self) -> dict[str, Any]:
        """Return S3 config dict suitable for passing to containers."""
        return {
            "bucket": self.bucket,
            "region": self.region,
            "aws_access_key_id": os.getenv("AWS_ACCESS_KEY_ID", ""),
            "aws_secret_access_key": os.getenv("AWS_SECRET_ACCESS_KEY", ""),
        }


def generate_timestamp() -> str:
    """Generate an ISO-formatted timestamp for use in S3 paths."""
    return datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
