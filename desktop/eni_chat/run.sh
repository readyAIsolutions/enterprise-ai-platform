#!/usr/bin/env bash
# ENI Desktop — Hermes + Local side-by-side native chat.
# Starts the local bridge (if needed) and opens the GTK two-pane app.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"
export PYTHONPATH="$PWD/../..:$PWD"   # repo root so enterprise.* imports resolve
exec python3 app.py "$@"
