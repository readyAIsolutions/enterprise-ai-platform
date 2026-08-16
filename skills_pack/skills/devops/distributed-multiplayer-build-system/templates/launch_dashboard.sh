#!/bin/bash
# launch_dashboard.sh — Start web dashboard

set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR/creed_dashboard"

echo "📊 DEMIURGE CREED — DASHBOARD"
echo "============================="

# Check if already running
if curl -sf http://localhost:8766/ >/dev/null 2>&1; then
    echo "  ✓ Dashboard already running on :8766"
    echo "  Open: http://localhost:8766"
    exit 0
fi

# Install deps if needed
if ! python3 -c "import aiohttp" 2>/dev/null; then
    echo "  Installing dashboard dependencies..."
    pip install aiohttp aiohttp-cors -q
fi

# Start dashboard
echo "  Starting dashboard on :8766..."
python3 server.py &
DASH_PID=$!

sleep 2
if curl -sf http://localhost:8766/ >/dev/null 2>&1; then
    echo "  ✓ Dashboard started (PID: $DASH_PID)"
    echo "  Open: http://localhost:8766"
else
    echo "  ⚠ Dashboard failed to start"
    kill $DASH_PID 2>/dev/null
    exit 1
fi