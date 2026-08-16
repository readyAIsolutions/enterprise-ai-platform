# Hermes ↔ Local Server Routing Troubleshooting

When Hermes reports "Model returned no content" or "Empty response from model" despite the server being healthy on `curl`, the issue is routing. Here's the systematic debug flow.

## Quick check: is Hermes even connecting?

```bash
ss -tp | grep 8913
```

- **ESTABLISHED/CLOSE-WAIT connections from `hermes` pid** → Hermes IS connecting. The issue is server-side (wrong model name, malformed response).
- **No connections** → Hermes is NOT routing to this port. Check provider config: `hermes config show | grep -A10 airllm`

## The model alias trap (most common failure)

Hermes sends the **alias name** (e.g. `"airllm"`) as the `model` field in API requests, NOT the resolved HF model ID. Your server must accept this.

**How to test**: From your terminal, send a request with the exact alias name Hermes would use:
```bash
curl -s http://127.0.0.1:8913/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"model":"airllm","messages":[{"role":"user","content":"hi"}],"max_tokens":10}'
```

If this returns `"Model load failed"` but the full HF name works, you hit the alias trap. Add `"airllm"` to the server's MODEL_ALIASES dict.

## The model catalog hijack

When `model_catalog.enabled: true`, Hermes may match a local model to an external catalog entry with wrong context length. Symptoms:
- TUI shows 256K context for a model configured at 8K
- `ss -tp` shows CLOSE-WAIT to 8913 (Hermes connected to YOUR server but someone else handled the response)
- `curl` to your server works fine

Fix: `hermes config set model_catalog.enabled false`, delete `~/.hermes/cache/model_catalog.json`, then **fully exit and restart Hermes** (`/new` won't reload config).

## Debug middleware for request capture

When you need to see exactly what Hermes sends, add this middleware to the FastAPI server:

```python
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

class DebugMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        body = b""
        async for chunk in request.stream():
            body += chunk
        print(f"[DEBUG] {request.method} {request.url.path} body={body.decode()[:500]}", flush=True)
        request._body = body  # reconstruct
        response = await call_next(request)
        resp_body = b""
        async for chunk in response.body_iterator:
            resp_body += chunk
        print(f"[DEBUG] RESP {response.status_code}: {resp_body.decode()[:500]}", flush=True)
        from starlette.responses import Response
        return Response(content=resp_body, status_code=response.status_code,
                       headers=dict(response.headers), media_type=response.media_type)

app.add_middleware(DebugMiddleware)
```

This logs every request body and response body to stdout, letting you see exactly what model name Hermes sends.

## Config change ≠ `/new`

After `hermes config set`:
- `/new` → new chat session, does NOT reload providers/auxiliary config
- Full exit + restart → reloads everything

If the TUI still shows wrong context after `/new`, you need a full restart.

## The three-model-name test

The definitive verification that your server handles all possible Hermes requests:

```bash
# Full HF path (server's internal name)
curl ... -d '{"model":"mistralai/Mistral-7B-Instruct-v0.2",...}'

# Short display name (what Hermes may show in TUI)  
curl ... -d '{"model":"Mistral-7B-Instruct-v0.2",...}'

# Alias name (what Hermes sends as model field)
curl ... -d '{"model":"airllm",...}'
```

All three must return 200 with valid content. If any fails, your MODEL_ALIASES is incomplete.