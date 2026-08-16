#!/bin/bash
# launch_all.sh — Full stack on single machine
# Usage: ./launch_all.sh

set -e
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

echo "⚡ CREED MULTIPLAYER — FULL STACK"
echo "================================="

# 1. Server
echo ""
echo "[1/3] Starting coordination server..."
bash "$DIR/launch_server.sh"

# 2. Dashboard
echo ""
echo "[2/3] Starting dashboard..."
bash "$DIR/launch_dashboard.sh"

# 3. Local client
echo ""
echo "[3/3] Starting local builder client..."
bash "$DIR/launch_client.sh"

echo ""
echo "================================="
echo "✅ FULL STACK RUNNING"
echo ""
echo "  Server API:   http://localhost:8765/api/"
echo "  Server WS:    ws://localhost:8765/ws"
echo "  Dashboard:    http://localhost:8766"
echo ""
echo "To submit a task:"
echo "  python3 -m creed_client.submit_task \\"
echo "    --name my-build \\"
echo "    --prompt \"Build a Python script that...\" \\"
echo "    --workdir ~/creed_work"