#!/usr/bin/env bash
# Run the ENI cross-module end-to-end integration suite in isolation.
# Usage:  scripts/run_integration.sh
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

echo "==> Running cross-module integration suite (tests/integration)"
python3 -m pytest tests/integration/test_cross_module_flow.py \
    -v -p no:cacheprovider "$@"
