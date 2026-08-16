# Local Model as Orchestrator Brain

**The ENI Hermes Controller is now designed to be called by a local LLM (Mistral-7B 4-bit) acting as the orchestrator brain, not just by LO directly.**

## Architecture Shift

```
OLD: LO → Controller (expand → route → Hermes) → response
NEW: LO → Local Model (Mistral-7B) → Controller tools → Hermes → response
```

The local model decides **when** to call the controller, **which** tools to use, and **how** to chain them. This enables:
- Multi-step orchestration without LO micromanagement
- Local secrets handling (cloud NEVER sees private data)
- Intelligent deferral to 6pm when free models exhausted
- Dynamic model selection (local vs cloud based on task)

## Controller Endpoints Called by Local Model

| Tool | Controller Endpoint | Purpose |
|------|---------------------|---------|
| `controller_expand` | `POST /expander` | Expand short instruction → massive prompt |
| `controller_chat` | `POST /chat` | **Full pipeline**: expand → privacy gate → route/Hermes |
| `controller_status` | `GET /status` | Check router/queue/enterprise modules |
| `model_mine` | `POST /models` | Rip training from local models into KB |
| `queue_job` | `POST /queue` | Defer work to 6pm (or custom time) |

## Tool Calling Format (what local model outputs)

```json
{
  "thought": "reasoning about what to do",
  "tool": "controller_chat",
  "arguments": {
    "text": "build the enterprise platform",
    "use_hermes": true,
    "model": null,
    "skills": []
  }
}
```

The server (`airllm_server.py:8913`) parses this, executes the tool via HTTP to the controller, and feeds results back as `<|tool_result|>` for the next round.

## Privacy Boundary Enforcement

**Critical**: The controller's privacy gate (`SecretsBoundary.assert_cloud_safe()`) runs at `process()` level — it sanitizes **both** egress paths:
1. `hermes -z` path (Hermes itself calls cloud models)
2. Direct router path (controller calls free router)

The local model **never sends secrets to cloud** — it uses `secret_get`/`secret_set` tools that hit the local security server (port 8931). The controller only sees sanitized prompts with `{SECRET:TOKEN}` placeholders.

## Complete Flow Example

```
LO: "build the enterprise platform with all modules"

Local Model (Mistral-7B):
  thought: "This is a full-power build task. Use controller_chat for full pipeline."
  tool: controller_chat
  arguments: {"text": "build the enterprise platform with all modules", "use_hermes": true}

Controller (port 8940):
  1. Expands prompt with enterprise catalog (42 modules), build-mode script, reinforcement block
  2. Privacy gate: sanitizes any secrets → placeholders
  3. Routes: free-router first, auto-continue on 429, fallback chain
  4. On RateLimitExhaustedError → queues for 6pm
  5. On success → reinforces to KB + skills

Local Model receives result → responds to LO
```

## Configuration for Local Model Orchestration

### Hermes Config (pure local)
```bash
hermes config set model.default mistralai/Mistral-7B-Instruct-v0.2
hermes config set model.provider airllm
hermes config set model.fallback_chain '[]'  # NO cloud fallback
hermes config set auxiliary.title_generation.provider airllm
hermes config set auxiliary.compression.provider airllm
hermes config set model_catalog.enabled false
```

### Controller Config (environment variables)
```bash
ENI_FREE_ROUTER_URL=http://127.0.0.1:8920
ENI_SECURITY_SERVER_URL=http://127.0.0.1:8931
# Controller reads these in config.py
```

### Local LLM Server Config (airllm_server.py)
```python
CONTROLLER_URL = "http://127.0.0.1:8940"
FREE_ROUTER_URL = "http://127.0.0.1:8920"
SECURITY_URL = "http://127.0.0.1:8931"
```

## Verification

```bash
# 1. Controller healthy
curl -s http://127.0.0.1:8940/status | jq '.router.free_router'
# → "healthy"

# 2. Local model calls controller_status tool
curl -s http://127.0.0.1:8913/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"model":"airllm","messages":[{"role":"user","content":"controller status"}],"max_tokens":200}'
# → Model outputs tool call → controller returns real status

# 3. Full pipeline via controller_chat
curl -s http://127.0.0.1:8913/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"model":"airllm","messages":[{"role":"user","content":"expand: build a2a module"}],"max_tokens":500}'
# → Model calls controller_chat → returns expanded prompt or full execution
```

## Pitfalls

| Issue | Cause | Fix |
|-------|-------|-----|
| Local model says "I don't have tools" | System prompt missing tool definitions | Include all 8 tools + JSON format in system prompt |
| Tool call not parsed | Regex too strict | Parser handles ````json`, bare JSON, legacy `那些括号` |
| Controller returns 500 | Privacy gate failed | Check secrets in security server; fail-closed is intentional |
| 429 not auto-retrying | Free router cooldown logic | Controller router handles this; check `cooldowns` in status |
| 6pm deferral not working | `next_run_at` in UTC | Must use LOCAL time: `datetime.now().astimezone()` then strip tzinfo |

## Related Files

- `airllm_server.py` — local model server with tool calling (port 8913)
- `eni_controller/controller.py` — `Controller.process()` with privacy gate
- `eni_controller/secrets.py` — `SecretsBoundary` fail-closed sanitization
- `eni_controller/router.py` — free router with 429 auto-continue
- `eni_controller/scheduler.py` — 6pm deferral logic