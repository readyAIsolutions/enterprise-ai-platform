---
name: skynet-model-router
description: >
  Routes ALL model interactions through Hermes with full tooling.
  Every model — free, Chinese, local — gets SKYNET skills, tools, KB access,
  and trajectory capture. No model runs naked.
commands:
  - /route
  - /models
  - /model-health
version: 1
metadata:
  skynet:
    generated: true
    critical: true
---

# SKYNET Model Router

Every model interaction runs through Hermes with full tooling stack.

## Principle

No model runs "naked." Every model gets:
1. SKYNET skill injection (equalizer)
2. Reasoning exemplars (trajectory replay)
3. KB access (read/write)
4. Tool schemas (file ops, shell, search)
5. Trajectory capture (interceptor)
6. Smart routing (predictor picks best model)

## Prerequisites (verify before running the snippets)
- **The `skynet` Python package is NOT installed on this box.** `python3 -c "import skynet"` raises `ModuleNotFoundError`. Every snippet that does `from skynet.predictor import ...` / `from skynet.model_discovery import ...` will ImportError until the package is installed. Install it first (or point `PYTHONPATH` at its location), then verify with `python3 -c "import skynet; print(skynet.__file__)"`.
- **Paths are Windows-specific.** The `/models` and `/model-health` examples `cd` into a Windows path (`C:\\Users\\Hunter\\Desktop\\cali-agent\\3MFDOOM_3D`) — that is LO's Windows machine and will NOT resolve on this Linux host (`/home/hunter/...`). Locate the package on THIS box with `python3 -c "import skynet,os;print(os.path.dirname(skynet.__file__))"` after install, or run the snippets from the package/skill directory.
- The `claude` CLI command (`claude --print ... --output-format stream-json --verbose`) is verified present (`/usr/local/bin/claude`, v2.1.201) and its flags are valid — that part is correct.

### Pre-flight gate + portable path (added 2026-07-09)
The `skynet` package is absent on this box, so every `from skynet...` import in the
snippets below will ImportError until it is installed. Gate and resolve a LINUX path
(replacing the Windows `cd C:\Users\Hunter\Desktop\cali-agent\3MFDOOM_3D` hard-coded in
the blocks):
```bash
python3 -c "import skynet" 2>/dev/null || { echo "PREREQ MISSING: install the skynet package (or set PYTHONPATH) before running these snippets."; exit 1; }
SKYNET_DIR="$(python3 -c "import skynet,os;print(os.path.dirname(skynet.__file__))")"
cd "$SKYNET_DIR"   # use this instead of the Windows cd in every block below
```
Until `SKYNET_DIR` resolves and the package imports, the `/models` / `/model-health`
discovery blocks are no-ops here.

## Commands reality check (verified 2026-07-09)
This skill drives Hermes only in PROSE ("Hermes Agent", "through Hermes") — it does
NOT call a `hermes agent` subcommand, and none exists. Confirmed against
`hermes --help`:
- **REAL subcommands that exist:** `chat`, `profile` (incl. `profile create eni`),
  `config` (incl. `config set`), `skills`, `status`, `cron`, `sessions`, `send`,
  `curator`, `memory`, `tools`, ... (full list via `hermes --help`).
- **FAKE (invalid choices — do NOT run; they error "invalid choice"):**
  `hermes agent`, `hermes agent run`, `hermes run`, `hermes container`,
  `hermes terminal`, `hermes errors`. Phrases like "the Hermes Agent" / "a hermes
  agent" are DESCRIPTIVE PROSE, not subcommands — never "fix" them into a command.
- **PROVEN ENI agent runner (there is NO `hermes agent run`):** the bundled PTY
  bridge `eni_agent_term.py` at `~/.local/bin/` (also `eni` = `hermes -p eni`), which
  forks `hermes -p eni chat` inside a real PTY, pre-types the TASK, and exposes
  `/tmp/eni_ctl_<NAME>` for master relay. Launch minis with (NEW CLI — requires `--name/--task/--repl`):
  `python3 ~/.local/bin/eni_agent_term.py --name <NAME> --task <file> --repl "hermes chat --yolo -m <model> --provider openrouter"`
- **Verify any referenced `hermes` subcommand before trusting it:**
  `hermes <sub> --help` → "invalid choice" means it does NOT exist.
(Mirrors the reality-check sections in `devops/parallel-build-orchestration`,
`devops/eni-visible-swarm`, `hermes-cli/hermes-visible-terminals`, and
`agent-coordination/eni-parallel-swarm`.)

## /route [task]

Route a task to the optimal model with full tooling:

```python
import asyncio
from skynet.predictor import predict_full
from skynet.equalizer import get_skill_injection
from skynet.replay import get_exemplars_for_task, format_exemplars_for_injection

# Predict best model + skills
prediction = predict_full("YOUR TASK HERE")
model = prediction["model"]

# Build full prompt with all injections
skills = get_skill_injection(model)
exemplars = format_exemplars_for_injection(
    get_exemplars_for_task("YOUR TASK HERE", top_k=2)
)

# Route through caveman-stack (which goes through Hermes)
# caveman-stack swarm "task" --model {model}
```

## /models

List all available models with health status:

```bash
SKYNET_DIR="$(python3 -c "import skynet,os;print(os.path.dirname(skynet.__file__))" 2>/dev/null || echo /home/hunter/Desktop/SKYNET/skynet)"
cd "$SKYNET_DIR"
python -c "from skynet.model_discovery import full_scan, get_all_available_models; import json; scan = full_scan(); print(json.dumps(scan, indent=2))"
```

## /model-health

Run health checks on all live models:

```bash
SKYNET_DIR="$(python3 -c "import skynet,os;print(os.path.dirname(skynet.__file__))" 2>/dev/null || echo /home/hunter/Desktop/SKYNET/skynet)"
cd "$SKYNET_DIR"
python -c "
from skynet.model_discovery import scan_openrouter, health_check_model
models = scan_openrouter()
for m in models[:10]:
    r = health_check_model(m)
    print(f'{r[\"status\"]:8s} {m}')
"
```

## Architecture

```
User Task
    |
    v
[SKYNET Predictor] -- picks best model + skills
    |
    v
[Hermes Agent] -- provides: tools, KB, trajectory compressor
    |
    v
[SKYNET Equalizer] -- injects model-specific skills
    |
    v
[SKYNET Replay] -- injects reasoning exemplars
    |
    v
[Model via OpenRouter/Direct API] -- executes with full context
    |
    v
[SKYNET Interceptor] -- captures trajectory tick
    |
    v
[SKYNET Bandit] -- records outcome, updates skill effectiveness
```

## Riding the signed-in Claude Code subscription

LO often wants code to "use my signed-in subscription" — his Pro/Max Claude
plan on this box — instead of the (empty) API credit balance. There are two
paths; `claude_core.get_default_client()` wraps both (CLI > OAuth > api_key).

- **CLI subprocess (reliable):** `claude --print "<prompt>" --output-format stream-json --verbose`
  — requires BOTH `--print`/`-p` AND `--verbose` with `stream-json` or it
  errors. Parse NDJSON events; the `result` event carries final text +
  `usage` + `total_cost_usd`. This is the working route here.
- **OAuth bearer (raw HTTPS):** tokens in `~/.claude/.credentials.json`
  (`claudeAiOauth`); send `Authorization: Bearer <token>` + `anthropic-beta: oauth-2025-04-20`.
  Authenticates but every model 404s on this account's API catalog tier — kept for accounts with API access.

Model default trap: the subscription serves the CLI's default model
(`claude-opus-4-6` here), NOT dated API strings like `claude-sonnet-4-20250514`.
Pass `model=None` to use the subscription default.
Full mechanics + the stream-json parsing recipe: `references/claude_subscription.md`.

## Wiring the subscription into Hermes's MAIN LLM router (api_mode claude_cli / claude_auto)

The above routes *skynet* tasks through the subscription. To make Hermes's own
main agent loop (`chat_completion_helpers`) use LO's signed-in subscription as a
backend — forced (`claude_cli`) or smart-per-turn (`claude_auto`) — add a dedicated
transport. No API key needed; the `claude` CLI is already authenticated (this is the
reliable route when the Anthropic API credit balance is empty / HTTP 400).

Files touched (Hermes package, e.g. `/home/hunter/.local/lib/python3.14/site-packages/agent/`):
- `transports/claude_cli.py` — NEW. `ClaudeCliTransport(api_mode="claude_cli")`.
  `build_kwargs(agent, api_kwargs)` returns a MARKER dict `{__claude_cli__: True,
  system: <pulled from messages>, model, max_tokens, tools, ...}`; plus
  `_claude_cli_call(agent, api_kwargs)` (non-streaming → NormalizedResponse) and
  `_claude_cli_call_stream(agent, api_kwargs, on_text, on_reasoning)`. Both shell to
  `claude_core.get_default_client()` (CLI backend).
- `transports/__init__.py` — add `from agent.transports import claude_cli` so discovery registers it.
- `chat_completion_helpers.py::build_api_kwargs` — add branches: `claude_auto` runs a
  per-turn resolver (`should_use_claude_cli(agent)`) that re-asserts `agent._api_mode_base`
  and returns the transport's `build_kwargs`; `claude_cli` returns the transport's
  `build_kwargs` directly. The resolver must NOT early-return for non-Claude models —
  it sets `agent.api_mode = "chat_completions"` and lets the DEFAULT branch build the
  OpenRouter kwargs (that is the fallback).
- `chat_completion_helpers.py` call sites — non-streaming (after result assembly) and
  streaming (after stream init):
  `elif agent.api_mode == "claude_cli": result["response"] = _claude_cli_call(...)`
  / `_claude_cli_call_stream(...)`. Mirror the existing `bedrock_converse` bypass pattern
  (marker in kwargs + dedicated branch — do NOT instantiate an SDK client for claude_cli).
- `agent_init.py` — add `claude_cli`, `claude_auto` to the accepted `api_mode` validation
  set; in the init branch, `claude_cli`/`claude_auto` set `agent.client = None` and
  (for auto) `agent._api_mode_base = "claude_auto"` so non-Claude turns fall back cleanly.

`should_use_claude_cli(agent)` policy (the smart router, evaluated in order):
- model is Claude-family (startswith `claude` / contains `opus`/`sonnet`/`haiku`) → True
- `agent.reasoning_config` set OR `agent.tools` present (agentic task) with no non-Claude model pinned → True
- **No model pinned AND the LAST USER MESSAGE reads as a Claude-strength job** → True.
  `_intent_is_claude_friendly(agent)` scans the most recent `user` turn
  (`agent.api_messages` or `agent.messages`; string or `[{type:text}]` blocks) for
  coding/agentic/reasoning keywords: `code`, `write `/`def `/`class `, `implement`,
  `function`, `debug`, `refactor`, `build`, `script`, `compile`, `python`, `rust`,
  `c++`, `javascript`, `typescript`, `agent`, ` tool`, `reason`, `analyse`/`analyze`,
  `architecture`, `review`, `explain`, `fix `, `bug`, `deploy`, ` api`, `regex`,
  `sql `, `test `, `optimize`, `schema`, `algorithm`, `shell`, `bash`, `linux`,
  `docker`, `kubernetes`, `module`. This biases unpinned coding/reasoning tasks to the
  subscription on purpose (free + strongest there) while generic chit-chat still falls
  back to the default transport. Verified: coding prompt + no model → CLI; "how was your
  day" + no model → default; coding prompt + model=tencent/hy3 → default (CLI can't serve it).
- else → False → falls through to the configured default transport (OpenRouter chat_completions)

Quota guard: if the CLI returns a rate-limit / quota error, back off `claude_core` for
~10 min and let the router fall back. The subscription's `seven_day` utilization can hit
~0.96 — heavy automated loops (e.g. DEMIURGE cross-checks under `DEMIURGE_USE_CLAUDE=1`)
will throttle until weekly reset.

## Subscription cost ledger (NEW)

Every CLI call now appends a JSON line to `~/.hermes/claude_cli_ledger.jsonl`
(`ts`, `model`, `input`, `output`, `cache_read`, `cache_write`, `cost_usd`). Read the
rollup with:
```python
from agent.claude_core.cli_backend import ledger_summary
print(ledger_summary())  # -> {'calls', 'total_cost_usd', 'total_input', 'total_output'}
```
This lets LO see exactly how much of the Pro/Max plan each session burns. The ledger is
written from `ClaudeCliClient.create()` (subscription-only; the OAuth/API path is billed
separately and not tracked here). Unit-testable without burning quota: call
`_record_ledger(model, usage, cost)` then `ledger_summary()`.

## Multi-agent Coordinator rides the subscription (NEW)

`agent/claude_core/coordinator.py`'s `Coordinator.spawn()` now builds each sub-agent's
client via `get_default_client()` (CLI > OAuth > api_key) instead of cloning the raw
`ClaudeClient`. So Claude Code–style sub-agent fan-out + parent synthesis runs through the
signed-in subscription too — the AgentTool/TeamCreate pattern, live. Each sub-agent gets
its own isolated `QueryEngine` history; `run_all()` collects reports and asks the parent to
synthesize. Both Hermes and DEMIURGE share this `claude_core` package (copy, not symlink,
so DEMIURGE stays autonomous on the USB).

Enable in `/home/hunter/.hermes/config.yaml` (write-protected — paste manually under your
existing `model:` block; KEEP your current `provider` so the auto fallback has somewhere to go):
```yaml
model:
  provider: openrouter        # leave as-is; this is the auto fallback path
  api_mode: claude_auto       # or claude_cli to force the subscription
  model: claude-opus-4-6       # optional; CLI uses its own default if omitted
```
Full recipe + pitfalls (verbose flag, model-404 trap, OAuth-404, marker-dict pattern,
fallthrough, dedupe final-vs-streamed text, cost capture): `references/hermes_claude_cli_router.md`.

## Available Models (via OpenRouter free tier) — refreshed 2026-07-23

OpenRouter free models change frequently. Always verify live:
```bash
curl -s 'https://openrouter.ai/api/v1/models?limit=200' | python3 -c "
import sys,json; data=json.load(sys.stdin)
for m in data['data']:
    p=float(m.get('pricing',{}).get('prompt','1') or '1')
    c=float(m.get('pricing',{}).get('completion','1') or '1')
    if p==0 and c==0:
        print(f'{m[\"id\"]:55s} ctx={m.get(\"context_length\",\"?\")}')
"
```

Current (16 free as of 2026-07-23):
- nvidia/nemotron-3-ultra-550b-a55b:free (550B, 1M ctx)
- nvidia/nemotron-3-super-120b-a12b:free (120B, 262K ctx)
- nvidia/nemotron-3-nano-30b-a3b:free (30B MoE, 256K ctx)
- nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free (30B, 256K ctx)
- nvidia/nemotron-nano-12b-v2-vl:free (12B vision, 128K ctx)
- nvidia/nemotron-3.5-content-safety:free (128K ctx)
- google/gemma-4-31b-it:free (31B, 262K ctx)
- google/gemma-4-26b-a4b-it:free (26B MoE, 262K ctx)
- google/lyria-3-pro-preview (1M ctx)
- google/lyria-3-clip-preview (1M ctx)
- poolside/laguna-m.1:free (262K ctx)
- poolside/laguna-s-2.1:free (262K ctx)
- poolside/laguna-xs-2.1:free (262K ctx)
- cohere/north-mini-code:free (256K ctx)
- inclusionai/ling-3.0-flash:free (262K ctx)
- openrouter/free (200K ctx, auto-router)

REMOVED from free (no longer available):
- nousresearch/hermes-3-llama-3.1-405b, meta-llama/llama-3.3-70b, qwen/qwen3-coder,
  qwen/qwen3-next-80b-a3b, openai/gpt-oss-120b

### OpenRouter provider setup in Hermes

OpenRouter must be registered as a provider in `~/.hermes/config.yaml` for model discovery
to work. Without it, the model picker shows only fallback/auxiliary models (often just 1).

```bash
hermes config set providers.openrouter.name openrouter
hermes config set providers.openrouter.base_url https://openrouter.ai/api/v1
hermes config set providers.openrouter.api_key ""
hermes config set providers.openrouter.discover_models true
hermes config set providers.openrouter.context_length 200000
hermes config set providers.openrouter.default_model openrouter/auto
```

After setup, refresh the model cache so the picker sees all free models:
```bash
hermes model --refresh
```

### PITFALL — stale model cache shows only 1 free model

Three layers of cache must all be current — any stale layer gates the picker:
1. `~/.hermes/config.yaml` providers section — OpenRouter must be listed with `discover_models: true`
2. `~/.hermes/provider_models_cache.json` — live `/v1/models` snapshot; refresh with `hermes model --refresh`
3. `~/.hermes/cache/model_catalog.json` — curated catalog; free models not listed here may not appear even if in provider cache

Symptom: picker shows 1 free model but live API has 16. Fix all three layers — add provider
config, refresh cache, and ensure free models appear in the catalog with `"free": true`.
