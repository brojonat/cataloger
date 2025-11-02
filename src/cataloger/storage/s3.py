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
        endpoint_url: str | None = None,
    ):
        """Initialize S3 storage.

        Args:
            bucket: S3 bucket name
            region: AWS region
            access_key_id: AWS access key (defaults to environment)
            secret_access_key: AWS secret key (defaults to environment)
            endpoint_url: Custom S3 endpoint (e.g., for MinIO: http://localhost:9000)
        """
        self.bucket = bucket
        self.region = region
        self.endpoint_url = endpoint_url

        # Store credentials (fallback to environment if not provided)
        self.access_key_id = access_key_id or os.getenv("AWS_ACCESS_KEY_ID")
        self.secret_access_key = secret_access_key or os.getenv("AWS_SECRET_ACCESS_KEY")

        # Initialize boto3 client
        session_kwargs: dict[str, Any] = {"region_name": region}
        if self.access_key_id and self.secret_access_key:
            session_kwargs.update(
                {
                    "aws_access_key_id": self.access_key_id,
                    "aws_secret_access_key": self.secret_access_key,
                }
            )

        # Add custom endpoint for S3-compatible services (MinIO, LocalStack, etc.)
        if endpoint_url:
            session_kwargs["endpoint_url"] = endpoint_url

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

    def list_prefixes(self, limit: int = 100) -> list[str]:
        """List all available catalog prefixes in the bucket.

        Returns:
            List of prefixes (e.g., ["customer-123/orders", "customer-456/users"])
        """
        # List top-level prefixes (assumes structure: prefix/timestamp/files)
        # We need to scan two levels deep to get customer-id/database-name format
        try:
            response = self.s3.list_objects_v2(
                Bucket=self.bucket, Prefix="", Delimiter="/"
            )
        except Exception as e:
            log.warning("storage.list_prefixes.error", error=str(e))
            return []

        prefixes = []
        # First level: customer IDs
        for item in response.get("CommonPrefixes", []):
            customer_prefix = item["Prefix"].rstrip("/")

            # Second level: database names under each customer
            try:
                sub_response = self.s3.list_objects_v2(
                    Bucket=self.bucket, Prefix=f"{customer_prefix}/", Delimiter="/"
                )
                for sub_item in sub_response.get("CommonPrefixes", []):
                    full_prefix = sub_item["Prefix"].rstrip("/")
                    prefixes.append(full_prefix)
            except Exception as e:
                log.warning("storage.list_prefixes.sub.error", error=str(e))
                continue

        log.info("storage.list_prefixes", count=len(prefixes))
        return prefixes[:limit]

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

    def list_all_files(
        self, prefix: str, timestamp: str
    ) -> dict[str, list[dict[str, str]]]:
        """List all files for a given timestamp, categorized by type.

        Args:
            prefix: S3 prefix
            timestamp: ISO timestamp

        Returns:
            Dict with categorized files: {
                "html": [...],
                "scripts": [...],
                "comments": [...],
                "other": [...]
            }
        """
        key_prefix = f"{prefix}/{timestamp}/"

        response = self.s3.list_objects_v2(Bucket=self.bucket, Prefix=key_prefix)

        files = {
            "html": [],
            "scripts": [],
            "comments": [],
            "other": []
        }

        for obj in response.get("Contents", []):
            key = obj["Key"]
            filename = key.split("/")[-1]

            # Skip the timestamp directory itself
            if key == key_prefix:
                continue

            file_info = {
                "filename": filename,
                "key": key,
                "size": obj.get("Size", 0),
            }

            # Categorize by type
            if "/comments/" in key:
                files["comments"].append(file_info)
            elif key.endswith(".html"):
                files["html"].append(file_info)
            elif key.endswith(".py"):
                files["scripts"].append(file_info)
            else:
                files["other"].append(file_info)

        log.info("storage.list_all_files", prefix=prefix, timestamp=timestamp,
                 html=len(files["html"]), scripts=len(files["scripts"]),
                 comments=len(files["comments"]))
        return files

    def write_comment(
        self, prefix: str, timestamp: str, user: str, comment: str
    ) -> str:
        """Write a user comment to S3.

        Args:
            prefix: S3 prefix (e.g., "customer-123/orders")
            timestamp: ISO timestamp of the catalog being commented on
            user: Username of commenter
            comment: Comment text

        Returns:
            S3 URI of written comment
        """
        comment_timestamp = generate_timestamp()
        filename = f"{user}-{comment_timestamp}.txt"
        key = f"{prefix}/{timestamp}/comments/{filename}"

        self.s3.put_object(
            Bucket=self.bucket,
            Key=key,
            Body=comment.encode("utf-8"),
            ContentType="text/plain",
        )

        uri = f"s3://{self.bucket}/{key}"
        log.info("storage.write_comment", uri=uri, user=user)
        return uri

    def list_comments(self, prefix: str, timestamp: str) -> list[dict[str, str]]:
        """List all comments for a given catalog timestamp.

        Args:
            prefix: S3 prefix
            timestamp: ISO timestamp

        Returns:
            List of dicts with "filename", "key", "user", "date" for each comment
        """
        key_prefix = f"{prefix}/{timestamp}/comments/"

        try:
            response = self.s3.list_objects_v2(Bucket=self.bucket, Prefix=key_prefix)
        except Exception as e:
            log.warning("storage.list_comments.error", error=str(e))
            return []

        comments = []
        for obj in response.get("Contents", []):
            key = obj["Key"]
            if key.endswith(".txt"):
                filename = key.split("/")[-1]
                # Parse filename: user-timestamp.txt
                parts = filename.rsplit("-", 1)
                if len(parts) == 2:
                    user = parts[0]
                    date = parts[1].replace(".txt", "")
                    comments.append({
                        "filename": filename,
                        "key": key,
                        "user": user,
                        "date": date,
                    })

        # Sort by date, newest first
        comments.sort(key=lambda x: x["date"], reverse=True)
        log.info("storage.list_comments", prefix=prefix, timestamp=timestamp, count=len(comments))
        return comments

    def read_comment(self, prefix: str, timestamp: str, filename: str) -> str | None:
        """Read a comment file from S3.

        Args:
            prefix: S3 prefix
            timestamp: ISO timestamp
            filename: Comment filename (e.g., "alice-2024-01-15T10:00:00Z.txt")

        Returns:
            Comment text, or None if not found
        """
        key = f"{prefix}/{timestamp}/comments/{filename}"

        try:
            response = self.s3.get_object(Bucket=self.bucket, Key=key)
            content = response["Body"].read().decode("utf-8")
            log.info("storage.read_comment", key=key)
            return content
        except self.s3.exceptions.NoSuchKey:
            log.info("storage.read_comment.not_found", key=key)
            return None

    def get_config(self) -> dict[str, Any]:
        """Return S3 config dict suitable for passing to containers."""
        config = {
            "bucket": self.bucket,
            "region": self.region,
            "aws_access_key_id": self.access_key_id or "",
            "aws_secret_access_key": self.secret_access_key or "",
        }
        # Include endpoint_url for MinIO/LocalStack
        if self.endpoint_url:
            config["endpoint_url"] = self.endpoint_url
        return config


def generate_timestamp() -> str:
    """Generate an ISO-formatted timestamp for use in S3 paths."""
    return datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
