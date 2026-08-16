#!/bin/bash
# launch_server.sh — Coordination Server
# Usage: ./launch_server.sh

set -e
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR/creed_server"

echo "⚡ CREED SERVER"
echo "=============="

# Check if already running
if curl -sf http://localhost:8765/health >/dev/null 2>&1; then
    echo "  ✓ Server already running on :8765"
    echo "  API: http://localhost:8765/api/"
    echo "  WS:  ws://localhost:8765/ws"
    exit 0
fi

# Install deps if needed
if ! python3 -c "import aiohttp" 2>/dev/null; then
    echo "  Installing server dependencies..."
    pip install -r requirements.txt -q
fi

# Start server
echo "  Starting server on :8765..."
python3 server.py &
SERVER_PID=$!

# Wait for health check
for i in {1..10}; do
    sleep 1
    if curl -sf http://localhost:8765/health >/dev/null 2>&1; then
        echo "  ✓ Server started (PID: $SERVER_PID)"
        echo "  API: http://localhost:8765/api/"
        echo "  WS:  ws://localhost:8765/ws"
        exit 0
    fi
done

echo "  ⚠ Server failed to start — check logs"
kill $SERVER_PID 2>/dev/null
exit 1