---
name: free-model-router
description: Set up, operate, and debug the Free Model Router — a local OpenAI-compatible proxy that smart-routes to the best free LLM across all configured providers. Use when the user mentions the free model router, free-router provider, or wants to change how Hermes selects free models.
---

# Free Model Router

A local proxy server (localhost:8920) that acts as a single Hermes provider,
aggregating all free-tier LLMs and auto-routing each request to the best one.

> **Consumed by:** the ENI Hermes Controller (eni-controller.service :8940) uses
> free-router as its primary routing tier. If free-router is down, the controller
> falls back to direct OpenRouter free-model rotation. See skill `eni-hermes-controller`.

## Architecture

```
Hermes → free-router(localhost:8920) → nvidia/nemotron-nano  (fast, simple)
                                     → sambanova/DeepSeek   (code, reasoning)
                                     → upstage/solar-pro     (writing, creative)
                                     → zhipu/glm-5.2        (1M context)
                                     → OpenRouter :free pool (fallback)
```

The router classifies every prompt by task type (code, debugging, writing, qa, etc.)
and routes to the optimal provider. If the primary fails (rate limit, auth, timeout),
it falls through the chain automatically.

## Key Files

- `/home/hunter/.hermes/scripts/free_router.py` — the proxy server (600+ lines)
- `/home/hunter/.config/systemd/user/free-router.service` — auto-boot service
- Provider config in `~/.hermes/config.yaml` under `providers.free-router`

## Operations

### Check health
```
curl -s http://127.0.0.1:8920/health
curl -s http://127.0.0.1:8920/status   # full provider status
```

### List available models
```
curl -s http://127.0.0.1:8920/v1/models | python3 -m json.tool
```

### Test a chat completion
```
curl -s http://127.0.0.1:8920/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"free-router","messages":[{"role":"user","content":"say hi"}],"max_tokens":50}'
```

### Restart the service
```
systemctl --user restart free-router.service
```

### View logs
```
journalctl --user -u free-router.service -f     # follow
journalctl --user -u free-router.service -n 20  # last 20
```

### Test via Hermes CLI
```
hermes chat -q "write a hello world in python" --yolo --provider free-router -m free-router
```

## Troubleshooting

### Hermes says "Empty response from model"
This means the router isn't returning SSE streaming data. Check:
1. Is the service running? `systemctl --user status free-router`
2. Port free? `ss -tlnp | grep 8920`
3. Can curl get a response? `curl -s http://127.0.0.1:8920/v1/chat/completions ...`
4. Restart the service: `systemctl --user restart free-router`

### Hermes crashes with "list index out of range"
This is a Hermes v0.15.2 bug when the model list doesn't include the requested model name.
Ensure the router has a model with id "free-router" in its /v1/models response.
Restart the router service after any code changes.

### Provider unhealthy / rate limited
Check `/status` endpoint. Unhealthy providers get a cooldown (60-3600s).
After the cooldown expires, they're retried automatically.
POST to `/reset` to clear all state immediately.

### OpenRouter key not found
The router reads OPENROUTER_API_KEY from `~/.hermes/.env`.
Verify: `grep OPENROUTER_API_KEY ~/.hermes/.env`

### Hermes streams but router doesn't (CRITICAL - Verified 2026-07-31)
**Symptom**: Hermes expects SSE streaming, router returns single JSON response.
**Root Cause**: Hermes streams by default; upstream providers (NVIDIA, SambaNova, Upstage, Zhipu) return non-streaming responses; router fakes SSE by buffering full response then chunking.
**Config Fix**: In `~/.hermes/config.yaml`, ensure:
```yaml
providers:
  free-router:
    stream: false  # Router fakes SSE from non-streaming upstream
```
**Test**: `curl -X POST http://127.0.0.1:8920/v1/chat/completions -d '{"model":"free-router","messages":[{"role":"user","content":"test"}],"stream":false}'` — should return complete response, not stream.

### Rate limit 429 on all :free models (OpenRouter daily cap)
**Symptom**: All OpenRouter :free models return 429 simultaneously.
**Root Cause**: OpenRouter enforces `free-models-per-day-high-balance` cap.
**Fix**: 
1. Rotate OpenRouter keys: `export OPENROUTER_API_KEY=$OPENROUTER_API_KEY_2 && systemctl --user restart free-router`
2. Ensure direct providers (NVIDIA, SambaNova, Upstage, Zhipu) are healthy — they have no daily cap
3. Free Router routes to direct providers first; OpenRouter only as last resort

## Configuration

### Adding a new free provider
Edit `PROVIDERS` dict in free_router.py.
Required fields: name, base_url, api_key, default_model, context, speed, best_for.
Then update TASK_ROUTING to include the new provider in appropriate chains.
Restart service after changes.

### Changing routing priorities
Edit `TASK_ROUTING` dict — ordered list per task type, first = primary.
Also edit `FALLBACK_CHAIN` for the universal fallback order.

### Provider API key rotation
Edit the api_key field in PROVIDERS dict, restart service.