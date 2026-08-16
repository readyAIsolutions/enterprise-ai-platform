# Hermes main-router wiring: subscription-backed `claude_cli` / `claude_auto`

Companion to `skynet-model-router` SKILL.md § "Wiring the subscription into Hermes's
MAIN LLM router". This is the re-implementation recipe + the pitfalls that bit us.

## Why this exists
Anthropic API credit balance was empty (every model → HTTP 400). LO's signed-in
Claude Code subscription (`claude` CLI) works fine and is free under Pro/Max. Goal:
make Hermes's *main* agent loop use it as a backend, forced or per-task smart-routed,
without touching the default OpenRouter path.

## Architecture (the 6 edits)

### 1. `agent/transports/claude_cli.py` (NEW)
```python
from agent.transports.base import Transport, FromConfig
from agent.claude_core import get_default_client

class ClaudeCliTransport(Transport):
    api_mode = "claude_cli"

    def build_kwargs(self, agent, api_kwargs):
        system = next((m["content"] for m in api_kwargs.get("messages", [])
                       if m.get("role") == "system"), None)
        return {
            "__claude_cli__": True,
            "model": api_kwargs.get("model"),
            "max_tokens": getattr(agent, "max_tokens", 2000),
            "system": system,
            "tools": api_kwargs.get("tools"),
            "messages": [m for m in api_kwargs.get("messages", [])
                         if m.get("role") != "system"],
        }

    def _call(self, agent, api_kwargs):  # non-streaming
        client = get_default_client()
        resp = client.generate(api_kwargs["messages"], model=api_kwargs.get("model"),
                               system=api_kwargs.get("system"),
                               max_tokens=api_kwargs["max_tokens"],
                               tools=api_kwargs.get("tools"))
        return NormalizedResponse(content=resp.text, finish_reason="stop",
                                  usage=resp.usage)

    def _call_stream(self, agent, api_kwargs, on_text, on_reasoning):
        client = get_default_client()
        client.generate_stream(api_kwargs["messages"], ...,
                               on_text=on_text, on_reasoning=on_reasoning)

def should_use_claude_cli(agent):
    m = (getattr(agent, "model", "") or "").lower()
    if m.startswith("claude") or any(k in m for k in ("opus", "sonnet", "haiku")):
        return True
    if getattr(agent, "reasoning_config", None) or getattr(agent, "tools", None):
        return True   # agentic task, no non-Claude model pinned
    return False
```
(`NormalizedResponse` / `Usage` come from `transports/types.py`.)

### 2. `agent/transports/__init__.py`
Append `from agent.transports import claude_cli` so `_discover_transports()` registers
it. Registration verified by `get_transport("claude_cli")` → not None.

### 3. `agent/chat_completion_helpers.py::build_api_kwargs`
Add near the top of the resolver:
```python
if agent.api_mode == "claude_cli":
    _ct = agent._get_transport()
    return _ct.build_kwargs(agent, api_kwargs)
if agent.api_mode == "claude_auto":
    agent._api_mode_base = "claude_auto"   # re-assert each turn
    if should_use_claude_cli(agent):
        return _ct.build_kwargs(agent, api_kwargs)
    # fallthrough: let the DEFAULT chat_completions branch build OpenRouter kwargs
    agent.api_mode = "chat_completions"
# ... existing default chain continues ...
```

### 4 & 5. Call sites in `chat_completion_helpers.py`
- Non-streaming (after the result is assembled / before return):
  `elif agent.api_mode == "claude_cli": result["response"] = _claude_cli_call(agent, api_kwargs)`
- Streaming (after stream init):
  `elif agent.api_mode == "claude_cli": _claude_cli_call_stream(agent, api_kwargs, _on_cli_text, _on_cli_reasoning)`
Mirror the existing `bedrock_converse` bypass: marker in kwargs + dedicated branch,
NO SDK client for claude_cli.

### 6. `agent/agent_init.py`
- Validation set: add `"claude_cli", "claude_auto"` alongside the other accepted `api_mode`s.
- Init branch: `elif agent.api_mode in ("claude_cli", "claude_auto"): agent.client = None; print("Claude Code subscription backend (no SDK client)")`
- For auto, also set `agent._api_mode_base = "claude_auto"` so non-Claude turns resolve to the default.

## Pitfalls (the ones that cost us turns)
- **`claude -p` requires `--verbose` with `--output-format stream-json`** or it errors:
  `Error: --verbose is required with --print and --output-format stream-json`.
  Correct invocation: `claude --print "<prompt>" --output-format stream-json --verbose`.
- **Model-404 trap**: the subscription serves the CLI's OWN default model
  (`claude-opus-4-6` on this box), NOT dated API strings like `claude-sonnet-4-20250514`
  (those 404). Pass `model=None` to `get_default_client()` so it uses the subscription default.
- **OAuth bearer 404s**: raw `Authorization: Bearer ` from
  `~/.claude/.credentials.json` authenticates (scope `user:inference` present) but EVERY
  model 404s on this account's API catalog tier. Keep it as a secondary path only; the CLI
  subprocess is the reliable primary. (See `references/claude_subscription.md`.)
- **Dedupe final vs streamed text**: the `result` event in stream-json repeats the full
  final text already emitted via `text`/`assistant` events. Track a `got_result` flag and
  do NOT append the result text again, or the answer doubles.
- **Capture real cost**: read `total_cost_usd` + the `usage` object (`input_tokens`,
  `output_tokens`, `cache_creation_input_tokens`, `cache_read_input_tokens`) from the
  `result` event into the `NormalizedResponse.usage` dict.
- **Keep `provider` as your existing default** (openrouter) in config.yaml when enabling
  `claude_auto` — the auto fallback builds chat_completions kwargs from `agent.provider`/
  `base_url`. If you set `provider: claude` with `api_mode: claude_auto`, the fallback would
  target a non-existent chat-completions endpoint.
- **`config.yaml` is write-protected** — you cannot patch it from the agent. Stage the
  snippet and have LO paste it manually (see SKILL.md).
- **Quota**: subscription `seven_day` utilization can reach ~0.96. Automated loops
  (DEMIURGE cross-checks under `DEMIURGE_USE_CLAUDE=1`) will rate-limit until weekly reset.
  Add a backoff: on CLI rate-limit, skip `claude_core` for ~10 min and fall back.

## Verify (without launching the live agent)
```bash
cd /home/hunter/.local/lib/python3.14/site-packages
python3 -m py_compile agent/transports/claude_cli.py agent/chat_completion_helpers.py agent/agent_init.py
python3 - <<'PY'
import agent.transports.claude_cli as m
from agent.transports import get_transport
print(type(get_transport("claude_cli")).__name__)   # ClaudeCliTransport
from agent.transports.claude_cli import should_use_claude_cli
class A: model=None; tools=None; reasoning_config=None
print(should_use_claude_cli(type('B',(),{'model':'claude-opus-4-6'})()))   # True
print(should_use_claude_cli(type('B',(),{'model':'tencent/hy3:free'})()))  # False
PY
```
Live handler check: `_claude_cli_call` over a fake agent returned a `NormalizedResponse`
with `finish_reason="stop"` and `usage.cached_tokens` populated — confirms the bypass path
through `chat_completion_helpers` works end-to-end (the actual `claude` CLI call is the only
live dependency, and it is already authenticated).
