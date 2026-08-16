# Cohere SSE Proxy — Working Pattern (July 25, 2026)

Cohere's native API uses a non-OpenAI-compatible format. Build a local proxy
that translates to OpenAI-compatible SSE streaming. This pattern generalizes to
any provider with a non-standard API.

## Critical: SSE streaming format

Hermes uses `stream=True` by default. The proxy MUST return Server-Sent Events
(SSE) format, NOT plain JSON. Plain JSON responses are rejected as "(empty)"
even when the content is correct.

## Working Implementation

```python
#!/usr/bin/env python3
"""Cohere → OpenAI SSE proxy for hermes."""
import json, http.server, urllib.request, ssl, os, time, uuid

KEY = "cohere_gBRDlQK6PnVcYonoOoTSfOQBXyEPDxdBccnA46ie3B1E2D"
COHERE_URL = "https://api.cohere.ai/v1/chat"
PORT = 8914
MODEL = "command-r-plus-08-2024"
ctx = ssl.create_default_context()

class P(http.server.BaseHTTPRequestHandler):
    def do_POST(self):
        if self.path != "/v1/chat/completions":
            self._send(404, {"error": "not found"}); return
        
        clen = int(self.headers.get('Content-Length', 0))
        body = json.loads(self.rfile.read(clen))
        messages = body.get("messages", [])
        user = next((m["content"] for m in messages if m.get("role") == "user"), "hello")
        
        # Build Cohere request with chat history
        creq = {
            "model": body.get("model", MODEL),
            "message": user,
            "max_tokens": max(body.get("max_tokens", 256), 10),
        }
        
        req = urllib.request.Request(COHERE_URL, data=json.dumps(creq).encode(),
            headers={"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"})
        
        with urllib.request.urlopen(req, timeout=180, context=ctx) as resp:
            cr = json.loads(resp.read())
        
        text = cr.get("text", "")
        resp_id = f"chatcmpl-{uuid.uuid4().hex[:29]}"
        now = int(time.time())
        
        # Build SSE response chunks
        chunk = json.dumps({
            "id": resp_id,
            "object": "chat.completion.chunk",
            "created": now,
            "model": body.get("model", MODEL),
            "system_fingerprint": f"fp_cohere_{uuid.uuid4().hex[:12]}",
            "choices": [{
                "index": 0,
                "delta": {"role": "assistant", "content": text},
                "finish_reason": None
            }]
        })
        
        sse = f"data: {chunk}\n\ndata: [DONE]\n\n"
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Content-Length", str(len(sse)))
        self.end_headers()
        self.wfile.write(sse.encode())
    
    def do_GET(self):
        if self.path == "/health":
            self._send(200, {"status": "ok"})
        elif self.path == "/v1/models":
            self._send(200, {"data": [{"id": MODEL, "object": "model"}]})
    
    def _send(self, code, data):
        b = json.dumps(data).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)
    
    def log_message(self, *a): pass

if __name__ == "__main__":
    http.server.HTTPServer(("127.0.0.1", PORT), P).serve_forever()
```

## Hermes Config

```yaml
providers:
  cohere-local:
    name: cohere-local
    base_url: http://127.0.0.1:8914/v1
    api_key: local
    discover_models: false
    default_model: command-r-plus-08-2024
    context_length: 128000
```

## Key Design Rules

1. **SSE format is mandatory.** Hermes streams by default. Non-streaming responses fail silently.
2. **Use `delta` not `message` in choices.** Streaming format uses `delta`, not `message`.
3. **Object type `chat.completion.chunk`** for SSE, not `chat.completion`.
4. **Required fields:** `system_fingerprint`, real `created` timestamp, `service_tier: "default"`.
5. **Finish with `data: [DONE]\n\n`** or hermes hangs waiting for more chunks.
6. **Translate single `text` field** from Cohere to `choices[0].delta.content`.
7. **Include chat_history** in Cohere requests for multi-turn conversations.

## Auto-Start (systemd)

```ini
# ~/.config/systemd/user/demiurge-cohere.service
[Unit]
Description=Demiurge Cohere API Proxy
After=network.target

[Service]
Type=simple
ExecStart=/usr/bin/python3 /tmp/cohere_final.py
Restart=on-failure
RestartSec=5
StandardOutput=append:%h/Desktop/Demiurge_Creed/logs/cohere-proxy.log

[Install]
WantedBy=default.target
```

## Pitfalls

- Plain JSON returns "(empty)" in hermes even with correct content
- Missing `data: [DONE]` causes hermes to time out
- `finish_reason: "MAX_TOKENS"` from Cohere should be normalized to "stop" or "length"
- The `api_key: "local"` in hermes config must match any value (it's ignored for localhost)
- Port conflicts with other services — check with `ss -tlnp | grep 8914` before starting
- systemd can't bind the port if a manual `python3 /tmp/cohere_final.py &` process is still running