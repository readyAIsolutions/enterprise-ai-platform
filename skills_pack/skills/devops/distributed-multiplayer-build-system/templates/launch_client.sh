#!/bin/bash
# launch_client.sh — Start local builder client

set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR/creed_client"

echo "🤖 DEMIURGE CREED — CLIENT"
echo "=========================="

# Check if already running
if pgrep -f "creed_client/client.py" >/dev/null 2>&1; then
    echo "  ✓ Client already running"
    exit 0
fi

# Install deps if needed
if ! python3 -c "import aiohttp" 2>/dev/null; then
    echo "  Installing client dependencies..."
    pip install aiohttp aiofiles psutil -q
fi

# Check for API keys
KEYS_FOUND=0
for var in OPENROUTER_API_KEY ZHIPU_API_KEY SAMBANOVA_API_KEY CEREBRAS_API_KEY \
           NVIDIA_API_KEY UPSTAGE_API_KEY DEEPINFRA_API_KEY COHERE_API_KEY \
           OPENAI_API_KEY ANTHROPIC_API_KEY XAI_API_KEY MISTRAL_API_KEY \
           GROQ_API_KEY DEEPSEEK_API_KEY MOONSHOT_API_KEY; do
    if [ -n "${!var}" ]; then
        KEYS_FOUND=1
        break
    fi
done

if [ $KEYS_FOUND -eq 0 ]; then
    echo "  ⚠ No API keys found in environment"
    echo "  Set at least one: OPENROUTER_API_KEY, ZHIPU_API_KEY, etc."
    echo "  Or configure in ~/.hermes/config.yaml"
fi

# Start client
SERVER_URL="${CREED_SERVER_URL:-ws://localhost:8765/ws}"
echo "  Connecting to $SERVER_URL..."
CREED_SERVER_URL="$SERVER_URL" python3 client.py &
CLIENT_PID=$!

sleep 2
if kill -0 $CLIENT_PID 2>/dev/null; then
    echo "  ✓ Client started (PID: $CLIENT_PID)"
else
    echo "  ⚠ Client failed to start"
    exit 1
fi