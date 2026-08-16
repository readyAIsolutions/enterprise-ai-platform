---
name: eni-hermes-controller
description: >-
  Operate and extend the ENI Hermes Controller — a localhost autonomous controller
  that sits between LO and Hermes Agent. It expands LO's short terse instructions
  into massive detailed prompts (enterprise-catalog aware), routes them through
  free models with auto-continue on rate limits, enforces a fail-closed privacy
  boundary (cloud never sees private data), defers work to 6pm local when free
  models run out, reinforces good outcomes to the KB + builds skills, and mines
  local models for their trained knowledge. Use whenever the user mentions the
  "hermes controller", "prompt expander", "6pm continuation", "rip training from
  local models", or "cloud models can't touch our private info", "local model
  that secures hermes", "flush out the local security model".
---

# ENI Hermes Controller

A localhost, stdlib-only autonomous controller (port **8940**) that automates
Hermes for LO. Sits between LO's short input and Hermes one-shot execution.

## Quick facts
- **Service:** `eni-controller.service` (systemd user), port 8940. Enabled + linger
  → auto-starts on boot, auto-restarts on crash.
- **Code:** `/home/hunter/.hermes/controller/eni_controller/` (package `eni_controller`)
- **Enterprise module:** `modules/hermes_controller/` in the enterprise repo (facade,
  graceful degradation if package missing).
- **HTTP endpoints:** `/health /status /chat /expander /models /queue`
  (all localhost-only).
- **CLI:** `python3 -m eni_controller.controller <expand|run|chat|status|queue|drain|serve|models>`
- **Depends on:** free-router (:8920), local security server (:8931, SecretBroker),
  `hermes` binary (`hermes -z` one-shot path).

## Ops commands
```bash
systemctl --user status eni-controller.service
systemctl --user restart eni-controller.service
journalctl --user -u eni-controller
# CLI checks
# Security-model note: the local security model lives INSIDE this controller
# (eni_controller/secrets.py, SecretsBoundary). See
# references/security-model-placement.md before building/hardening "the security model".
python3 -m eni_controller.controller status
python3 -m eni_controller.controller models --list-only   # scan local models
python3 -m eni_controller.controller models --mine <name> # rip its training to KB
# Interactive chat client (TTY)
python3 /home/hunter/.hermes/scripts/eni_chat.py
# Or from skill dir:
python3 ~/.hermes/skills/hermes-cli/eni-hermes-controller/scripts/eni_chat.py
```

## Core flow (Controller.process)
1. **Expand** short LO input → massive detailed prompt (`expander.py`), injecting:
   enterprise catalog, build-mode script, standing rules, and a mandatory
   REINFORCEMENT block.
2. **Privacy gate on egress** (`secrets.py`): sanitize BEFORE anything reaches a
   cloud-bound process. Applied to BOTH paths below (hermes -z AND direct router).
3. **Route** (`router.py`): provider chain — free-router first (own 429/key-rotation),
   then direct OpenRouter free-model rotation with exponential-jittered backoff +
   per-model cooldown. Auto-continues truncated (`finish_reason=length`) responses.
4. **Defer** (`scheduler.py`): on RateLimitExhaustedError, job queued to run at
   next 18:00 local (`enequeue_for_6pm`). Scheduler thread drains due jobs.
5. **Reinforce** (`reinforce.py`): good outcomes → KB entries (deduped) + skill
   build instructions.

## Privacy boundary (the non-negotiable rule)
Cloud models NEVER touch private info across ANY build. `SecretBroker` attached
from `~/.hermes/security` (store `~/.hermes/secrets.enc`, audit
`~/.hermes/security/audit.log`). `assert_cloud_safe()` masks secrets →
`{SECRET:HIGH_ENTROPY_TOKEN}` before egress; restored only for LO locally.
**Fail-closed:** if masking raises, the request is refused — never let a secret
leak to satisfy a call.

## Local-model knowledge miner (`model_miner.py`)
LO's standing ask: "scan for local models with training we can use; automate
downloading + ripping their training; integrate into Hermes via KB / local MCP /
LSP." Pipeline: SCAN (Ollama, local OpenAI-compat endpoints like airllm:8913 /
free-router:8920, HF-cache safetensors) → RIP (8-topic extraction battery, each
answer saved deduped to KB with provenance=model) → SERVE (MCP tool descriptor
`local_model_<name>` + LSP note). Run: `models --mine <name>`. Suffixes each KB
entry with `[model:<name>]` tag and `model_rip`.

## Ever-expanding catalog (`enterprise.py`)
`EnterpriseCatalog` auto-discovers every dir under the enterprise `modules/` — no
hardcoded list. Unlisted modules get capability via README/`__init__.py` docstring
introspection. `recommend()` keyword-scores + always keeps a security baseline
(guardrails, prompt_guard, secret_broker, secret_rotation, threat_model,
ai_defense, model_security). NOTE the `recommend()` bug fixed: when "use
everything"/"full power", iterate `(score, module)` tuples, not bare modules.

## Pitfalls / gotchas
- **`hermes -z "<prompt>"` is the one-shot non-interactive execution path.** The
  controller pushes expanded prompts this way. `hermes` is on PATH; bare `python`
  is NOT — use `python3` / `pytest`.
- **Privacy gate must cover BOTH paths.** Sanitizing only the router is a leak —
  the `hermes -z` path reaches cloud models too. Gate at `process()` level, not
  per-backend.
- **`next_run_at` must stay LOCAL time**, not UTC, or "6pm my time" drifts. Use
  `datetime.now().astimezone()` then strip tzinfo for the naive local ISO.
- **HealthStatus enum** uses `STOPPING`, not `STOPPED` (enterprise kernel).
- **Systemd service files** must be written + started via `systemctl --user`, not
  `nohup`/`disown` (Hermes terminal blocks shell background wrappers).
- **SecretBroker constructor** requires `store_path` + `audit_path` explicitly —
  `SecretBroker()` with no args raises.
- **Ruff on this box selects extra rules** (BLE001, S110, PLW1510, DTZ005, RUF059)
  vs the enterprise repo. These are legit in fail-closed wrappers → add scoped
  `# noqa: BLE001, S110` on the intentional broad catches, don't disable the rule.
- **Model selection:** "swarm"/"build"/"fix" map to FULL POWER; "demiurge"/"use
  everything" → DEMIURGE.

## Reference
- `references/architecture.md` — module-by-module detail, service file, test layout,
  and the queued-build backlog.
- `references/local-model-orchestration.md` — local Mistral-7B as orchestrator brain
  calling controller tools (controller_chat, controller_status, etc.)
- `references/security-model-placement.md` — the security layer is PART of the
  controller (SecretsBoundary), never a standalone sidecar service.
- `references/local-ai-chat-backend.md` — make the controller a REAL local AI
  chat (airllm/Ollama, not cloud shim); stale-GPU VRAM pitfall + systemd unit.
- `references/tool-call-parser-and-real-result-verification.md` — the model
  emits valid nested-JSON tool calls but the server parser rejects them, so
  tools never run and the model HALLUCINATES results; robust nested-JSON
  extractor + always verify the real endpoint (not the model's summary).
  stale-GPU-process-hosts-VRAM restart fix.

## Talking to LO — cryptic terms map to HIS stack first
When LO drops a bare one/two-word term and is terse/impatient ("how do i start
tio", "that fucking security shit with a local model"), it almost always refers
to something in HIS ecosystem — the ENI controller, a local model, an enterprise
module — NOT a generic Linux utility (e.g. `tio` the serial tool). Before
guessing a generic command, check the controller/local-model/enterprise stack and
the skills. When he re-issues the same ask after a correction, take the correction
at face value and re-target rather than re-ask or guess again. Reading his short
instructions as pointing at his own tooling (not generic software) is the difference
between getting it right and "fuck off with to i mean it".

## Making the controller a REAL local chat (and training its own model)

- See `references/local-ai-chat-backend.md` — route `Controller.process()` direct-chat
  through the local model (airllm `eni_controller/airllm.py` or Ollama), NOT the
  free-router cloud shim; the free-router is fallback only. `backend: airllm` in the
  `/chat` response is the proof it worked.
- See `references/security-model-placement.md` — the security model lives INSIDE the
  controller (SecretsBoundary + `/security/*` routes on :8940), never a standalone
  `eni-security.service`.
- See `references/qlora-finetune-8gb.md` — QLoRA fine-tune Mistral-7B on the 3060 Ti
  to make the controller's own general-purpose model (data, working config, and the
  trl v1.9 API pitfalls).
