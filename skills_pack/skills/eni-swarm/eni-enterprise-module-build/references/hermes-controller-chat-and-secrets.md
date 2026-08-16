# ENI Hermes Controller — chat + secret-vault contract (local model brain)

Source of truth for building a chat terminal / secret-capture UI on top of the
local controller. Verified 2026-08 against `eni-controller.service` (:8940).

## Backends / model stack
- Controller: `systemctl --user status eni-controller.service` — HTTP on
  `127.0.0.1:8940` (Python `http.server`-based handler, NOT Starlette).
- Local brain: `airllm.service` on `127.0.0.1:8913` — serves the trained
  QLoRA merged model at `/home/hunter/.hermes/controller/models/eni-controller/merged`.
  Check: `curl http://127.0.0.1:8913/v1/models` -> the `id` is the merged path.
- `free-router.service` (:8920) is the cloud fallback; `backend` field in the
  chat result tells you which one served the reply (`airllm` = local).

## POST /chat (the human-readable chat endpoint)
```
POST http://127.0.0.1:8940/chat    {"message":"...", "use_hermes":false}
```
- `use_hermes:false` -> routes to the local model, returns the reply directly.
- **Response keys:** `ok`, `backend` ("airllm"|"router"), `reply`, plus
  `expanded`/`catalog_block`/`recommended_modules` from the expander.
- **PITFALL:** the reply field is `result["reply"]`, NOT `result["response"]`.
  A naive client reading `["response"]` (as the old `eni_chat.py` did) gets
  empty output.
- **PITFALL:** the model's `reply` is a JSON tool-call string, e.g.
  `{"thought": "...", "tool": "respond", "arguments": {"message": "..."}}`.
  Unwrap `arguments.message` for the readable text; fall back to raw reply.
- Timeout: allow up to ~60–120s (local 7B brain on 3060 Ti can be slow).
- `/v1/chat/completions` also exists (OpenAI-compatible) and returns
  `choices[0].message.content` = `result["reply"]`.

## Secret vault (local-first, fail-closed)
Endpoints on the controller (all localhost-only):
- `POST /security/env/set`   `{"key":"NAME","value":"..."}` -> store.
- `POST /security/env/get`   `{"key":"NAME"}` -> `{"ok":bool,"value":...}`.
- `POST /security/env/list`  -> `{"keys":[...]}`  (names only — values never).
- `POST /security/env/remove` `{"key":"NAME"}`.
- `POST /security/sanitize` `{"text":...}` -> `{"sanitized":..., "masked":bool}`
  (scrubs secrets on egress — the HARD GATE before anything goes to cloud).
- `GET /security` -> `{"broker_attached":bool,"vault_entries":int,...}`.
  `broker_attached:false` means SecretBroker wasn't importable and it fell
  back to a plain `controller_vault.json` (0600). Both satisfy the flow; the
  broker is preferred.

### The "paste a secret, Hermes never sees it" pattern
1. User pastes a secret in the chat terminal.
2. Client intercepts BEFORE sending to the model: `POST /security/env/set`
   with the key name + value.
3. Model sees only the NAME (e.g. `{SECRET:OPENROUTER_API_KEY}`); the value
   never reaches the model or any cloud path.
4. `GET /security/env/get` returns the value only to the local terminal/Hermes
   runner — never echoed into prompts/logs headed to cloud (rely on
   `/security/sanitize` as the egress gate).

## Autoserve watchdog
`~/.hermes/controller/training/auto_serve_model.sh` (systemd
`eni-autoserve.service`) re-points airllm at the freshly merged model after
training and restarts. It uses `set -euo pipefail` and exits 0 early when
`merged/model.safetensors` is absent. If it keeps failing with exit 1 right
after computing `START_MARK`, the culprit is usually a `head` on a missing
`/tmp/eni_train3.log` under `set -u` — the merged model may already be served
fine regardless (check `curl :8913/health` for `"status":"ok"`).

## Model chat reply unwrap (copy-paste)
```python
import json, urllib.request

def chat(message, url="http://127.0.0.1:8940/chat", use_hermes=False):
    body = json.dumps({"message": message, "use_hermes": use_hermes}).encode()
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        d = json.loads(r.read().decode())
    reply = d.get("reply", "")
    try:  # unwrap tool-call JSON
        obj = json.loads(reply)
        return obj.get("arguments", {}).get("message", reply)
    except Exception:
        return reply
```
