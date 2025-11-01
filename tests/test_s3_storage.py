"""Tests for S3 storage."""

import pytest

from cataloger.storage.s3 import S3Storage, generate_timestamp


def test_generate_timestamp():
    """Test timestamp generation."""
    ts = generate_timestamp()
    assert "T" in ts
    assert "Z" in ts
    assert len(ts) == 20  # YYYY-MM-DDTHH:MM:SSZ


def test_s3_storage_initialization():
    """Test S3Storage initialization."""
    storage = S3Storage(bucket="test-bucket", region="us-west-2")
    assert storage.bucket == "test-bucket"
    assert storage.region == "us-west-2"


def test_s3_config():
    """Test S3 config generation."""
    storage = S3Storage(bucket="test-bucket")
    config = storage.get_config()
    assert config["bucket"] == "test-bucket"
    assert "region" in config
