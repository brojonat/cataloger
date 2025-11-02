#!/usr/bin/env bash
# Build the agent container image

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${REPO_ROOT}"

if command -v pigz >/dev/null 2>&1; then
	if ! pigz --version >/dev/null 2>&1; then
		PIGZ_OUTPUT="$(pigz --version 2>&1 || true)"
		if grep -q "zlib version less than 1.2.3" <<<"${PIGZ_OUTPUT}"; then
			echo "Detected pigz linked against zlib < 1.2.3:"
			echo "    ${PIGZ_OUTPUT}"
			echo ""
			echo "Docker relies on pigz/unpigz to unpack image layers, and this outdated build"
			echo "causes the cataloger-agent image build to fail (\"unpigz: abort: zlib version less than 1.2.3\")."
			echo ""
			echo "Fix the local environment before retrying by either:"
			echo "  • Upgrading pigz (requires zlib ≥ 1.2.3)"
			echo "  • Removing pigz so Docker falls back to gzip"
			echo "  • Upgrading Docker/host packages that provide pigz"
			exit 1
		fi
	fi
fi

echo "Building cataloger-agent container..."
docker build -t cataloger-agent:latest -f Dockerfile.agent .

echo ""
echo "Container built successfully!"
echo "Image: cataloger-agent:latest"
