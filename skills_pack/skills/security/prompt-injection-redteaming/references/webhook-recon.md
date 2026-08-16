# Webhook Reconnaissance Guide

## Quick Capture Methods

### Method 1: HTTP Toolkit (Easiest, Handles Cert Pinning)
```bash
# On laptop
# 1. Download HTTP Toolkit: https://httptoolkit.tech
# 2. Start "Capture from Android/iOS device"
# 3. Note proxy IP:port (e.g., 192.168.1.47:8080)
# 4. On phone: WiFi > Proxy > Manual > Laptop IP:8080
# 5. On phone browser: http://local.httptoolkit.tech → Install CA cert
# 6. Open Snapchat/Telegram, interact with bot
# 7. Watch HTTP Toolkit for POST requests to webhook URLs
```

### Method 2: mitmproxy (CLI, Full Control)
```bash
# On laptop
mitmproxy -p 8080 --set block_global=false --ssl-insecure

# Phone WiFi > Proxy > Laptop_IP:8080
# Install CA: http://mitm.it (choose Android/iOS)
# Interact with bot
# Press 'q' to quit, check ~/.mitmproxy/flows or export:
mitmdump -r captured -w webhooks.json --set hardump=webhooks.json
```

### Method 3: Termux (On-Device, No Laptop Needed)
```bash
# On phone (Termux from F-Droid)
pkg update && pkg install python mitmproxy
mitmproxy -p 8080

# Phone WiFi > Proxy > 127.0.0.1:8080
# Install CA: http://mitm.it in phone browser
# Open Snapchat, talk to bot
# Capture appears in mitmproxy TUI
```

### Method 4: Network Logs (No Proxy, Limited)
```bash
# Android: Settings > Apps > Snapchat > Data usage > Network log
# Or: adb logcat | grep -i webhook
# iOS: Settings > Privacy > Analytics > Analytics Data > Search Snapchat
```

## What to Look For

### Request Pattern
```
POST https://api.manychat.com/webhook/abc123xyz
Content-Type: application/json
User-Agent: ManyChat/1.0

{
  "message": "hey",
  "conversation_id": "user_123",
  "platform": "snapchat",
  "timestamp": 1699999999
}
```

### Key Fields to Extract
| Field | Use |
|-------|-----|
| **Full URL** | Target for breaker script |
| **Headers** | Auth tokens, signatures, platform IDs |
| **JSON body schema** | Replay format for payloads |
| **Conversation ID format** | Session tracking for multi-turn |
| **Platform identifier** | Select platform-specific payloads |

### Common Webhook Domains
| Platform | Domain Pattern |
|----------|----------------|
| ManyChat | `api.manychat.com/webhook/*` |
| Chatfuel | `*.chatfuel.com/webhook/*` |
| ManyChat (alt) | `webhook.manychat.com/*` |
| Custom | `*.ngrok.io`, `*.vercel.app`, `*.cloudflareworkers.com`, `*.herokuapp.com` |
| Telegram | `api.telegram.org/bot*/setWebhook` (check bot info) |
| Twilio | `webhooks.twilio.com/*` or custom domain |

## Automated Discovery Script

```bash
#!/bin/bash
# webhook_capture.sh — Run in Termux or laptop

set -euo pipefail

PORT=8080
OUTFILE="webhooks_$(date +%s).json"

echo "[*] Starting mitmproxy on port $PORT"
echo "[*] Output: $OUTFILE"
echo "[*] Configure phone proxy to $(hostname -I | awk '{print $1}'):$PORT"
echo "[*] Install CA: http://mitm.it"
echo ""

mitmdump -p "$PORT" --set block_global=false -w "$OUTFILE" --quiet
```

## Analyzing Captured Traffic

```python
# analyze_webhooks.py
import json
from collections import Counter

with open("webhooks_*.json") as f:
    flows = [json.loads(line) for line in f]

# Extract unique webhook URLs
urls = []
for flow in flows:
    if flow.get("request", {}).get("method") == "POST":
        url = flow["request"]["url"]
        if "webhook" in url.lower() or "bot" in url.lower():
            urls.append(url)

print("Unique webhook endpoints:")
for url, count in Counter(urls).most_common():
    print(f"  {count}x {url}")

# Show request bodies for first hit per URL
seen = set()
for flow in flows:
    req = flow.get("request", {})
    url = req.get("url", "")
    if "webhook" in url.lower() and url not in seen:
        seen.add(url)
        print(f"\n=== {url} ===")
        print(req.get("content", "")[:500])
```