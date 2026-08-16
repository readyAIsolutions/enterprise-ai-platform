# Provider Proxy Pattern — SSE Streaming

When a provider's native API is not OpenAI-compatible, build a local proxy that
translates the native format to OpenAI-compatible SSE (Server-Sent Events) format.

## Why SSE, not plain JSON

Hermes streams by default (`stream: true` in config). If the proxy returns plain
JSON instead of SSE-format events, hermes will show "(empty)" even though the
proxy returned valid content. The OpenAI SDK client requires SSE events for
streaming responses.

## Template (Python)

Apply this pattern for any non-OpenAI-compatible provider. Example: Cohere.

```python
#!/usr/bin/env python3
"""Provider → OpenAI-compatible SSE proxy."""
import json, http.server, urllib.request, ssl, time, uuid

KEY = "PROVIDER_API_KEY"
URL = "https://api.provider.com/v1/chat"       # Provider's native endpoint
PORT = 8914                                      # Unique port per provider
MODEL = "provider-model-name"

class P(http.server.BaseHTTPRequestHandler):
    def do_GET(s):
        if s.path == "/health":
            s._send(200, {"status":"ok"})
        elif s.path == "/v1/models":
            s._send(200, {"object":"list","data":[
                {"id":MODEL,"object":"model","created":int(time.time())}
            ]})

    def do_POST(s):
        body = json.loads(s.rfile.read(int(s.headers['Content-Length'])))
        msgs = body.get("messages",[])
        user = next((m["content"] for m in msgs if m.get("role")=="user"), "")

        # Translate to provider's native format
        native_req = {
            "model": body.get("model", MODEL),
            "message": user,                    # Provider-specific field
            "max_tokens": body.get("max_tokens", 1024),
        }

        # Call provider's native API
        req = urllib.request.Request(URL, data=json.dumps(native_req).encode(),
            headers={"Authorization":f"Bearer {KEY}","Content-Type":"application/json"})
        try:
            with urllib.request.urlopen(req, timeout=180, context=ssl.create_default_context()) as resp:
                native_resp = json.loads(resp.read())
            text = native_resp.get("text", "")   # Provider-specific field

            # CRITICAL: Return SSE streaming format
            now = int(time.time())
            cid = f"chatcmpl-{uuid.uuid4().hex[:29]}"
            sse_data = json.dumps({
                "id": cid,
                "object": "chat.completion.chunk",  # CHUNK, not completion
                "created": now,
                "model": MODEL,
                "system_fingerprint": f"fp_{uuid.uuid4().hex[:12]}",
                "choices": [{
                    "index": 0,
                    "delta": {"content": text},     # delta, not message
                    "finish_reason": None
                }]
            })
            # Send SSE events
            s.send_response(200)
            s.send_header("Content-Type", "text/event-stream")
            s.send_header("Cache-Control", "no-cache")
            s.end_headers()
            s.wfile.write(f"data: {sse_data}\n\n".encode())
            s.wfile.write(b"data: [DONE]\n\n")
        except Exception as e:
            s._send(500, {"error":{"message":str(e)}})

    def _send(s, code, data):
        b = json.dumps(data).encode()
        s.send_response(code); s.send_header("Content-Type","application/json")
        s.send_header("Content-Length",str(len(b))); s.end_headers()
        s.wfile.write(b)

    def log_message(s,*a): pass

http.server.HTTPServer(("127.0.0.1", PORT), P).serve_forever()
```

## Key Requirements

1. **SSE format mandatory.** Hermes streams by default. Return `text/event-stream`
   with `data: {...}\n\n` + `data: [DONE]\n\n`.

2. **Use `delta`, not `message`.** The choices array in streaming mode uses
   `delta: {"content": text}` not `message: {"content": text}`.

3. **Object type is `chat.completion.chunk`.** Not `chat.completion`.

4. **Include `system_fingerprint`.** The OpenAI SDK expects this field.

5. **Include `service_tier: "default"` and real timestamps in `created`.**

6. **Unique port per provider.** Cohere on 8914, HuggingFace on 8915, etc.

7. **Register as systemd user service** for auto-start on boot:
   `~/.config/systemd/user/demiurge-<provider>.service`

8. **Provider config in `~/.hermes/config.yaml`:**
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

## Providers Needing Proxies

| Provider | Native API | Proxy Port | Status |
|----------|-----------|-----------|--------|
| Cohere | `/v1/chat` (message field) | 8914 | WORKING |
| HuggingFace | `/models/...` (different format) | 8915 | DNS issues on LO's box |
| Cloudflare AI | Account-specific endpoint | 8916 | Auth format issues |
