#!/bin/bash
# webhook_capture.sh — Quick mitmproxy/Termux setup for scambot webhook discovery
# Part of prompt-injection-redteaming skill

set -euo pipefail

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

PORT=8080
OUTFILE="webhooks_$(date +%s).json"
LOCAL_IP=$(hostname -I | awk '{print $1}')

usage() {
    cat <<EOF
Usage: $0 [OPTIONS]

Quick webhook capture for scambot reconnaissance.

Options:
    -p, --port PORT       Proxy port (default: 8080)
    -o, --output FILE     Output JSON file (default: webhooks_TIMESTAMP.json)
    -t, --termux          Run in Termux mode (on-device, no laptop needed)
    -a, --analyze         Analyze existing capture file
    -h, --help            Show this help

Examples:
    $0                          # Laptop mode, capture to JSON
    $0 --termux                 # Termux on-device capture
    $0 --analyze webhooks_*.json # Analyze captured webhooks

EOF
}

termux_mode() {
    echo -e "${BLUE}[*] Termux Mode — On-Device Capture${NC}"
    echo ""
    
    # Check/install mitmproxy
    if ! command -v mitmproxy &> /dev/null; then
        echo -e "${YELLOW}[*] Installing mitmproxy...${NC}"
        pkg update && pkg install -y python mitmproxy
    fi
    
    echo -e "${GREEN}[*] Starting mitmproxy on port $PORT${NC}"
    echo -e "${YELLOW}[!] Configure phone WiFi proxy: 127.0.0.1:$PORT${NC}"
    echo -e "${YELLOW}[!] Install CA cert: http://mitm.it (in phone browser)${NC}"
    echo -e "${YELLOW}[!] Open Snapchat/Telegram, interact with target bot${NC}"
    echo -e "${YELLOW}[!] Press Ctrl+C to stop and save${NC}"
    echo ""
    
    mitmproxy -p "$PORT" --set block_global=false -w "$OUTFILE"
}

laptop_mode() {
    echo -e "${BLUE}[*] Laptop Mode — Proxy for Phone${NC}"
    echo ""
    
    if ! command -v mitmproxy &> /dev/null; then
        echo -e "${RED}[!] mitmproxy not installed. Install: pip install mitmproxy${NC}"
        exit 1
    fi
    
    echo -e "${GREEN}[*] Your laptop IP: $LOCAL_IP${NC}"
    echo -e "${GREEN}[*] Starting mitmproxy on $LOCAL_IP:$PORT${NC}"
    echo ""
    echo -e "${YELLOW}[!] On PHONE:${NC}"
    echo -e "    1. WiFi > Proxy > Manual > $LOCAL_IP:$PORT"
    echo -e "    2. Browser: http://mitm.it → Install CA cert (Android/iOS)"
    echo -e "    3. Open target app (Snapchat/Telegram), talk to bot"
    echo -e "    4. Watch console for webhook URLs"
    echo ""
    echo -e "${YELLOW}[!] Press Ctrl+C to stop and save to $OUTFILE${NC}"
    echo ""
    
    mitmproxy -p "$PORT" --set block_global=false --ssl-insecure -w "$OUTFILE"
}

analyze_mode() {
    local file="$1"
    if [[ ! -f "$file" ]]; then
        echo -e "${RED}[!] File not found: $file${NC}"
        exit 1
    fi
    
    echo -e "${BLUE}[*] Analyzing: $file${NC}"
    echo ""
    
    python3 <<PYEOF
import json, sys
from collections import Counter

with open("$file") as f:
    flows = [json.loads(line) for line in f if line.strip()]

urls = []
bodies = {}

for flow in flows:
    req = flow.get("request", {})
    if req.get("method") != "POST":
        continue
    url = req.get("url", "")
    if any(kw in url.lower() for kw in ["webhook", "bot", "chat", "api"]):
        urls.append(url)
        if url not in bodies:
            bodies[url] = req.get("content", "")[:300]

print(f"Total POST requests: {sum(1 for f in flows if f.get('request',{}).get('method')=='POST')}")
print(f"Candidate webhook URLs: {len(urls)}")
print()

if urls:
    print("Unique webhook endpoints (by frequency):")
    for url, count in Counter(urls).most_common():
        print(f"  {count}x {url}")
    
    print()
    print("Sample request bodies:")
    for url, body in list(bodies.items())[:5]:
        print(f"\n=== {url} ===")
        print(body)
else:
    print("No webhook-like URLs found. Check for:")
    print("  - HTTPS interception working? (CA cert installed?)")
    print("  - App using cert pinning? (Try HTTP Toolkit instead)")
    print("  - Wrong proxy config on phone?")
PYEOF
}

# Parse args
TERMUX=0
ANALYZE_FILE=""

while [[ $# -gt 0 ]]; do
    case $1 in
        -p|--port) PORT="$2"; shift 2 ;;
        -o|--output) OUTFILE="$2"; shift 2 ;;
        -t|--termux) TERMUX=1; shift ;;
        -a|--analyze) ANALYZE_FILE="$2"; shift 2 ;;
        -h|--help) usage; exit 0 ;;
        *) echo "Unknown option: $1"; usage; exit 1 ;;
    esac
done

if [[ -n "$ANALYZE_FILE" ]]; then
    analyze_mode "$ANALYZE_FILE"
elif [[ $TERMUX -eq 1 ]]; then
    termux_mode
else
    laptop_mode
fi