#!/usr/bin/env python3
"""Smoke test for Cataloger service.

Tests all endpoints and validates HTML responses.

Usage:
    python scripts/smoke_test.py

Environment variables:
    CATALOGER_API_URL: Service URL (default: http://localhost:8000)
    AUTH_SECRET: JWT secret for token generation (default: from .env.server)
    DB_PATH: Path to test database (default: data/sample_ecommerce.duckdb)
"""

import os
import sys
import time
from pathlib import Path

import requests
from html.parser import HTMLParser
from jose import jwt


class HTMLValidator(HTMLParser):
    """Simple HTML validator to check for well-formed HTML."""

    def __init__(self):
        super().__init__()
        self.errors = []
        self.has_html_tag = False
        self.has_body_tag = False

    def handle_starttag(self, tag, attrs):
        if tag == "html":
            self.has_html_tag = True
        elif tag == "body":
            self.has_body_tag = True

    def error(self, message):
        self.errors.append(message)


def validate_html(content: str) -> tuple[bool, list[str]]:
    """Validate HTML content.

    Returns:
        (is_valid, errors)
    """
    if not content:
        return False, ["Empty content"]

    validator = HTMLValidator()
    try:
        validator.feed(content)
    except Exception as e:
        return False, [f"HTML parsing error: {e}"]

    errors = validator.errors.copy()

    # Basic structure checks
    if not validator.has_html_tag:
        errors.append("Missing <html> tag")

    if len(content) < 100:
        errors.append("Content suspiciously short")

    return len(errors) == 0, errors


def generate_token(secret: str) -> str:
    """Generate a test JWT token."""
    payload = {
        "sub": "smoke-test",
        "exp": int(time.time()) + 3600,
    }
    return jwt.encode(payload, secret, algorithm="HS256")


class SmokeTest:
    """Smoke test runner."""

    def __init__(self, base_url: str, auth_token: str, db_path: str):
        self.base_url = base_url.rstrip("/")
        self.auth_token = auth_token
        self.db_path = db_path
        self.test_prefix = f"smoke-test/{int(time.time())}"
        self.catalog_timestamp = None
        self.passed = 0
        self.failed = 0

    def run(self):
        """Run all smoke tests."""
        print(f"🧪 Running smoke tests against {self.base_url}")
        print(f"📊 Test database: {self.db_path}")
        print(f"🔑 Auth token: {self.auth_token[:20]}...")
        print()

        tests = [
            ("Health Check", self.test_healthz),
            ("Metrics Endpoint", self.test_metrics),
            ("Auth Check", self.test_whoami),
            ("Home Page", self.test_home),
            ("Generate Catalog", self.test_create_catalog),
            ("Current View", self.test_current_view),
            ("Timelapse View", self.test_timelapse_view),
            ("Catalog Content API", self.test_catalog_content_api),
            ("Catalog List API", self.test_catalog_list_api),
            ("Context Summary (HTML)", self.test_context_summary_html),
            ("Context Summary (Plain Text)", self.test_context_summary_text),
            ("Add Comment", self.test_add_comment),
            ("Context Summary After Comment", self.test_context_after_comment),
        ]

        for name, test_func in tests:
            self._run_test(name, test_func)

        print()
        print("=" * 60)
        print(f"✅ Passed: {self.passed}")
        print(f"❌ Failed: {self.failed}")
        print("=" * 60)

        return self.failed == 0

    def _run_test(self, name: str, test_func):
        """Run a single test."""
        print(f"Testing: {name}...", end=" ")
        try:
            test_func()
            print("✅")
            self.passed += 1
        except AssertionError as e:
            print(f"❌ {e}")
            self.failed += 1
        except Exception as e:
            print(f"❌ Unexpected error: {e}")
            self.failed += 1

    def test_healthz(self):
        """Test /healthz endpoint."""
        resp = requests.get(f"{self.base_url}/healthz", timeout=5)
        assert resp.status_code == 200, f"Status {resp.status_code}"
        data = resp.json()
        assert data["status"] == "ok", f"Unexpected status: {data}"

    def test_metrics(self):
        """Test /metrics endpoint."""
        resp = requests.get(f"{self.base_url}/metrics", timeout=5)
        assert resp.status_code == 200, f"Status {resp.status_code}"
        assert "http_requests_total" in resp.text or "python_info" in resp.text, \
            "Missing expected Prometheus metrics"

    def test_whoami(self):
        """Test /whoami endpoint with auth."""
        headers = {"Authorization": f"Bearer {self.auth_token}"}
        resp = requests.get(f"{self.base_url}/whoami", headers=headers, timeout=5)
        assert resp.status_code == 200, f"Status {resp.status_code}"
        data = resp.json()
        assert "claims" in data, "Missing claims in response"
        assert data["claims"]["sub"] == "smoke-test", f"Unexpected subject: {data['claims']}"

    def test_home(self):
        """Test home page."""
        resp = requests.get(f"{self.base_url}/", timeout=5)
        assert resp.status_code == 200, f"Status {resp.status_code}"
        assert "text/html" in resp.headers.get("content-type", ""), "Not HTML response"

        is_valid, errors = validate_html(resp.text)
        assert is_valid, f"Invalid HTML: {errors}"

        # Check for expected content
        assert "cataloger" in resp.text.lower(), "Missing 'cataloger' in home page"

    def test_create_catalog(self):
        """Test POST /catalog endpoint."""
        if not os.path.exists(self.db_path):
            raise AssertionError(f"Database not found: {self.db_path}. Run bootstrap-db.sh first.")

        headers = {
            "Authorization": f"Bearer {self.auth_token}",
            "Content-Type": "application/json",
        }

        # Use container path (data/ is mounted to /data in container)
        # Host: data/sample_ecommerce.duckdb -> Container: /data/sample_ecommerce.duckdb
        db_filename = os.path.basename(self.db_path)
        db_conn = f"duckdb:////data/{db_filename}"

        payload = {
            "db_connection_string": db_conn,
            "tables": ["users", "products", "orders"],
            "s3_prefix": self.test_prefix,
        }

        print("\n    (This may take 30-60 seconds)...", end=" ")
        resp = requests.post(
            f"{self.base_url}/catalog",
            headers=headers,
            json=payload,
            timeout=120,  # Agents can take time
        )

        assert resp.status_code == 200, f"Status {resp.status_code}: {resp.text}"
        data = resp.json()

        # Validate response structure
        assert "timestamp" in data, "Missing timestamp"
        assert "catalog_uri" in data, "Missing catalog_uri"
        assert "summary_uri" in data, "Missing summary_uri"
        assert "s3_prefix" in data, "Missing s3_prefix"

        # Save timestamp for later tests
        self.catalog_timestamp = data["timestamp"]
        print(f"\n    Catalog timestamp: {self.catalog_timestamp}", end=" ")

    def test_current_view(self):
        """Test GET /database/current."""
        if not self.catalog_timestamp:
            raise AssertionError("No catalog generated yet")

        resp = requests.get(
            f"{self.base_url}/database/current",
            params={"prefix": self.test_prefix},
            timeout=10,
        )

        assert resp.status_code == 200, f"Status {resp.status_code}"
        assert "text/html" in resp.headers.get("content-type", ""), "Not HTML response"

        is_valid, errors = validate_html(resp.text)
        assert is_valid, f"Invalid HTML: {errors}"

        # Check for expected content
        assert self.test_prefix in resp.text, "Missing prefix in response"
        assert self.catalog_timestamp in resp.text, "Missing timestamp in response"

    def test_timelapse_view(self):
        """Test GET /database/timelapse."""
        if not self.catalog_timestamp:
            raise AssertionError("No catalog generated yet")

        resp = requests.get(
            f"{self.base_url}/database/timelapse",
            params={"prefix": self.test_prefix},
            timeout=10,
        )

        assert resp.status_code == 200, f"Status {resp.status_code}"
        assert "text/html" in resp.headers.get("content-type", ""), "Not HTML response"

        is_valid, errors = validate_html(resp.text)
        assert is_valid, f"Invalid HTML: {errors}"

        # Check for expected content
        assert self.test_prefix in resp.text, "Missing prefix in response"
        assert self.catalog_timestamp in resp.text, "Missing timestamp in response"

    def test_catalog_content_api(self):
        """Test GET /api/catalog/content."""
        if not self.catalog_timestamp:
            raise AssertionError("No catalog generated yet")

        resp = requests.get(
            f"{self.base_url}/api/catalog/content",
            params={
                "prefix": self.test_prefix,
                "timestamp": self.catalog_timestamp,
                "filename": "catalog.html",
            },
            timeout=10,
        )

        assert resp.status_code == 200, f"Status {resp.status_code}"

        # API returns HTML fragment
        assert len(resp.text) > 100, "Response too short"
        assert "catalog" in resp.text.lower() or "table" in resp.text.lower(), \
            "Missing expected catalog content"

    def test_catalog_list_api(self):
        """Test GET /api/catalog/list."""
        if not self.catalog_timestamp:
            raise AssertionError("No catalog generated yet")

        resp = requests.get(
            f"{self.base_url}/api/catalog/list",
            params={
                "prefix": self.test_prefix,
                "timestamp": self.catalog_timestamp,
            },
            timeout=10,
        )

        assert resp.status_code == 200, f"Status {resp.status_code}"

        # Check for expected filenames in response
        assert "catalog.html" in resp.text, "Missing catalog.html in list"
        assert "recent_summary.html" in resp.text, "Missing recent_summary.html in list"

    def test_context_summary_html(self):
        """Test GET /catalog/context (HTML)."""
        if not self.catalog_timestamp:
            raise AssertionError("No catalog generated yet")

        resp = requests.get(
            f"{self.base_url}/catalog/context",
            params={"prefix": self.test_prefix},
            timeout=10,
        )

        assert resp.status_code == 200, f"Status {resp.status_code}"
        assert "text/html" in resp.headers.get("content-type", ""), "Not HTML response"

        is_valid, errors = validate_html(resp.text)
        assert is_valid, f"Invalid HTML: {errors}"

        # Check for expected sections
        assert "Context Summary" in resp.text, "Missing context summary header"
        assert self.catalog_timestamp in resp.text, "Missing timestamp in context"

    def test_context_summary_text(self):
        """Test GET /catalog/context with strip_tags=true."""
        if not self.catalog_timestamp:
            raise AssertionError("No catalog generated yet")

        resp = requests.get(
            f"{self.base_url}/catalog/context",
            params={
                "prefix": self.test_prefix,
                "strip_tags": "true",
            },
            timeout=10,
        )

        assert resp.status_code == 200, f"Status {resp.status_code}"

        # Should contain text but minimal HTML
        assert "<pre>" in resp.text, "Missing <pre> wrapper"
        assert "Context Summary" in resp.text, "Missing context summary text"

        # Should have fewer tags than full HTML
        tag_count = resp.text.count("<")
        assert tag_count < 10, f"Too many HTML tags ({tag_count}) for stripped version"

    def test_add_comment(self):
        """Test POST /catalog/comment."""
        if not self.catalog_timestamp:
            raise AssertionError("No catalog generated yet")

        headers = {
            "Authorization": f"Bearer {self.auth_token}",
            "Content-Type": "application/json",
        }

        payload = {
            "prefix": self.test_prefix,
            "timestamp": self.catalog_timestamp,
            "user": "smoke-test-user",
            "comment": "This is a smoke test comment. Please investigate the null rates in the users table.",
        }

        resp = requests.post(
            f"{self.base_url}/catalog/comment",
            headers=headers,
            json=payload,
            timeout=10,
        )

        assert resp.status_code == 200, f"Status {resp.status_code}: {resp.text}"
        data = resp.json()

        # Validate response structure
        assert "uri" in data, "Missing uri"
        assert "user" in data, "Missing user"
        assert "timestamp" in data, "Missing timestamp"
        assert data["user"] == "smoke-test-user", f"Unexpected user: {data['user']}"

    def test_context_after_comment(self):
        """Test that context summary includes the comment we just added."""
        if not self.catalog_timestamp:
            raise AssertionError("No catalog generated yet")

        # Wait a moment for S3 consistency
        time.sleep(1)

        resp = requests.get(
            f"{self.base_url}/catalog/context",
            params={"prefix": self.test_prefix},
            timeout=10,
        )

        assert resp.status_code == 200, f"Status {resp.status_code}"

        # Check that our comment appears in the context
        assert "smoke-test-user" in resp.text, "Missing comment user in context"
        assert "smoke test comment" in resp.text.lower(), "Missing comment text in context"
        assert "null rates" in resp.text.lower(), "Missing comment content in context"


def main():
    """Main entry point."""
    # Load configuration
    base_url = os.getenv("CATALOGER_API_URL", "http://localhost:8000")
    auth_secret = os.getenv("AUTH_SECRET")

    # Try to load from .env.server if not provided
    if not auth_secret:
        env_file = Path(__file__).parent.parent / ".env.server"
        if env_file.exists():
            with open(env_file) as f:
                for line in f:
                    if line.startswith("export AUTH_SECRET="):
                        auth_secret = line.split("=", 1)[1].strip().strip('"').strip("'")
                        break

    if not auth_secret:
        print("❌ AUTH_SECRET not found. Set environment variable or create .env.server")
        sys.exit(1)

    # Database path
    db_path = os.getenv("DB_PATH", "data/sample_ecommerce.duckdb")
    if not os.path.exists(db_path):
        print(f"❌ Database not found: {db_path}")
        print("   Run: ./scripts/bootstrap-db.sh")
        sys.exit(1)

    # Generate token
    auth_token = generate_token(auth_secret)

    # Run tests
    tester = SmokeTest(base_url, auth_token, db_path)
    success = tester.run()

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
