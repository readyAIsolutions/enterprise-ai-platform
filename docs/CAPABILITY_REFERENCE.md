# ENI ENTERPRISE AI PLATFORM — Capability & Operation Reference
**Version:** v2.0.0 Golden Boot + v3 "CO-OP" (multi-player cooperative build)
**Repo:** `/home/hunter/Desktop/Enterprise Builder/enterprise`
**Branch:** `upgrade/demiurge-enterprise-boost` (work-in-progress; not yet pushed)
**Last verified:** 2026-08-16 — **4,411 tests collected, 4,410 passed**

---

## 1. What it is — one sentence
A self-validating, modular **AI build operating system** that lets a whole team's
machines (each with their own GPUs and API keys) work on the SAME codebase at the
SAME time, coordinated by one server — plus a local brains that turns one plain
English goal into an entire tested program.

## 2. The three layers

```
┌─────────────────────────────────────────────────────────────┐
│  LAYER 3  PORTABLE LAYER (skills/LSP/MCP/plugins) — 963 files │
│  one command mirrors your full Hermes agent stack so any    │
│  company can self-host a working agent layer                │
├─────────────────────────────────────────────────────────────┤
│  LAYER 2  LOCAL BRAINS (one-prompt -> program) :8913         │
│  planner (goal->task DAG) · redacting vault · build provider│
├─────────────────────────────────────────────────────────────┤
│  LAYER 1  COOPERATIVE BUILD FLOOR  WS :8787 / HTTP :8788    │
│  N builder clients (your PCs) · broker · conflict-safe merge│
│  auth/TLS/multi-tenancy · live board · submit_plan fan-out  │
├─────────────────────────────────────────────────────────────┤
│  LAYER 0  PLATFORM KERNEL + 51 modules (self-validating OS) │
└─────────────────────────────────────────────────────────────┘
```

## 3. Layer 0 — the Platform Kernel (51 modules)
A singleton `PlatformOS` orchestrator with `ModuleRegistry` auto-discovery
(scans `modules/*/__init__.py`), a pub/sub `EventBus`, `HealthChecker`, metrics
collector, unified logging bridge, and a lifecycle state machine
(initializing → discovering → configuring → starting → running). Every module
follows the strict `@module(...) → Module.initialize/health_check/shutdown`
contract, so a new capability **auto-discovers with zero kernel edits**.

The 51 modules group into these capability families:

**Core OS & governance**
a2a, compliance, safety_governance, privacy_data, prompt_guard, threat_model,
ai_defense, model_security, guardrails, disaster_recovery, release_change,
enterprise_validation, research_verification

**Agent stack**
agent_core, agent_infra, agent_tools, agent_os, agent_graph, agent_catalog
(432-specialist unified registry), autonomous_agent_runtime, agent_coordination

**Knowledge & memory**
knowledge_graph, rag, semantic_memory, memory, kb_bridge, model_miner

**Swarm & orchestration**
swarm_network, swarm_bridge, task_harness, gateway, skill_factory, model_router,
hermes_controller, orchestration (foundation), evaluation (eval_gate)

**Model lifecycle & MLOps**
mlops_lifecycle, model_router, llmops_trace, model_miner, universal_score,
response_hardening (NEW — audits/repairs Hermes output-length caps)

**Cloud/security ops**
secret_broker, secret_rotation, tenancy, mcp_tools, compression_bridge, eval_gate

**Experience & domain**
developer_experience, customer_experience, look_and_feel, innovation_rd,
triadforge, vuln_scanner

Every module carries its own unit tests; the full suite is **4,410 green**.

## 4. Layer 1 — Cooperative Multi-Player Build Floor (the selling feature)
This is what makes the platform a *cooperative* system rather than a single agent:
- **Coordination server** (`multiplayer/server/`, WS :8787 + HTTP :8788): brokers
  goals into atomic tasks, assigns each to the least-loaded *capable* client,
  merges results into a shared workspace, and exposes a live board + merge ledger.
- **Builder clients** (`multiplayer/client/`): one per machine, each contributing
  its own hardware and its own API keys — the server never sees other machines'
  secrets (clients send only capability tags). Pluggable workers: `shell`,
  `python`, and `llm`. The `llm_worker` generates real code via the planner's
  prompt-enrichment + an external LLM (env `MP_LLM_URL/KEY_ENV/MODEL`) with a
  two-layer secret redaction (never leaks credentials).
- **`/api/submit_plan`** — the killer demo: one natural-language goal → the local
  planner splits it into N uniquely-named step-tasks → dispatched across the fleet
  → results merged, test-hinted, conflict-safe.
- **Hardening** (all verified by tests): binds `0.0.0.0` (multi-machine LAN),
  optional auth token (`MP_AUTH_TOKEN`), **per-tenant isolated workspaces**
  (`tenants={acme:[client_ids]}`), optional **TLS** (`wss`), heartbeat-timeout
  requeue, retry-once policy, JSONL persistence (server restart resumes), and a
  whole-file conflict detector that never clobbers.

**Proven end-to-end (real run):** `POST /api/submit_plan {"goal":"build a budget
tracker","tenant":"acme"}` → 6 step-tasks → llm builder on the LAN executed them →
real, uniquely-named artifacts merged into `wspace/acme/` (tenant-isolated), ledger
recorded each `APPLIED ... conflicts=0`.

## 5. Layer 2 — Local Brains :8913 (one-prompt → program)
A stdlib HTTP server (`local_controller/`) Hermes can call directly:
- `POST /plan` — goal → 6-step dependency-ordered plan with test hints.
- `POST /enrich` — expands a terse prompt into a detailed, self-contained one.
- `POST /program` — runs the plan: writes each artifact + a manifest under
  `data/build_sessions/<id>/`, self-tests each step (retry ≤2 on failure).
- `GET /health`.
- **`vault`** — a local secret store whose `redact()` strips real values leaving
  placeholder names so nothing sensitive EVER leaves the machine. Belt-and-
  suspenders regex scrub catches inline `api_key=...`/`token: ...` values too.

## 6. Layer 3 — Portable setup (one machine → whole team)
- `skills_pack/` mirrors the full Hermes agent layer: **20 skill categories, 957
  skill files, 1 LSP server, 2 MCP servers, 3 plugin files (963 total)**.
- `scripts/install_skillspack.sh` — idempotent, backs up your destination, strips
  `__pycache__`; `--dry-run / --force / --target=`. Re-runs are safe.
- `scripts/eni_cli` — the operator CLI:
  - `eni status` — 51 modules present/healthy, 147 test files, pack present.
  - `eni doctor` — deep platform/kernel/pack checks.
  - `eni setup` — one-command install: deploys skillspack AND installs/enables
    systemd user services for the controller (:8913) + multiplayer server (:8787).
  - `eni fleet [host]` — start a builder client (llm worker) on the server.
  - `eni up` — docker compose bring-up.
- `systemd/*.service` unit files for the controller + multiplayer server.
- Docker multi-stage `Dockerfile` + `docker-compose.yml`.

## 7. Verification & quality bar
- **4,411 tests collected, 4,410 passed, 1 skipped** (full platform regression).
- New-module coverage this session: multiplayer 22, local_controller 11,
  response_hardening 6 — **all green**.
- Universal Build Score (`universal_score`) certifies any real build to a
  sellable-enterprise bar (100 = sellable; can exceed 100 = singularity band).
- **No fake data** — every number above is a real measured count.

## 8. Security posture (by design)
- Clients transmit capability tags only; the protocol has an anti-secret guard that
  refuses `api_key/apikey/secret/authorization/bearer/password/token=` in payloads.
- Secret vault redacts before any outbound LLM call; placeholders (`{KEY:name}`)
  are the only thing that leaves.
- Optional auth token + TLS for the coordination server.
- Per-tenant workspaces isolate customer projects (acme ≠ globex).
- Response-hardening module self-heals Hermes' output-length caps after upgrades.

## 9. How it makes money (see docs/SELLING.md)
- Anchor to the labor problem solved, not "AI tool" pricing: **$12k–25k/yr team
  license**, free up to 10 builders as a funnel, $10/builder/mo hosted margin,
  30–60% white-label split. The cooperative floor + one-prompt→program is the
  demo that closes deals.

---

## Quick start
```bash
cd /home/hunter/Desktop/Enterprise\ Builder/enterprise
python3 scripts/eni_cli status          # confirm health
python3 scripts/eni_cli setup           # one-command install (pack + services)
python3 -m enterprise.multiplayer.server.server 8787   # coordination server
python3 -m enterprise.multiplayer.client.client --worker llm  # a builder
curl -X POST :8788/api/submit_plan -d '{"goal":"build a to-do app","tenant":"acme"}'
```