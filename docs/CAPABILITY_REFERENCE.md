# ENI ENTERPRISE AI PLATFORM — Full Capability & Operation Reference
**Version:** v2.0.0 Golden Boot + v3 "CO-OP" (multi-player cooperative build)
**Repo:** `/home/hunter/Desktop/Enterprise Builder/enterprise`
**Branch:** `upgrade/demiurge-enterprise-boost` (3 feature commits local-only; not yet pushed)
**Last verified:** 2026-08-16 — **4,411 tests collected, 4,410 passed, 1 skipped**

---

## 1. What it is — one sentence
A self-validating, modular **AI build operating system** that turns one plain-
English goal into a tested program — and lets a whole team's machines (each with
their own GPUs + API keys) build the SAME codebase at the SAME time, coordinated
by one server with a live board.

## 2. The five layers

```
┌───────────────────────────────────────────────────────────────┐
│  LAYER 4  PORTABLE HERMES LAYER  — 963 files (skills/LSP/MCP/  │
│           plugins) mirror + one-command installer             │
├───────────────────────────────────────────────────────────────┤
│  LAYER 3  LOCAL BRAINS  :8913  — one-prompt → program         │
│           planner · redacting vault · build provider         │
├───────────────────────────────────────────────────────────────┤
│  LAYER 2  COOPERATIVE BUILD FLOOR  WS:8787/HTTP:8788         │
│           broker · conflict-safe merge · auth/TLS/tenancy    │
│           submit_plan fan-out a goal into N step-tasks       │
├───────────────────────────────────────────────────────────────┤
│  LAYER 1  PLATFORM KERNEL — lifecycle, EventBus, health,     │
│           metrics, auto-discovery of every module            │
├───────────────────────────────────────────────────────────────┤
│  LAYER 0  50 capability modules (self-validating, stdlib)    │
└───────────────────────────────────────────────────────────────┘
```

## 3. Layer 0 — the 50 capability modules (every one)
Each follows the strict `@module → initialize/health_check/shutdown` contract and
**auto-discovers with zero kernel edits**. Grouped by function (50 total):

### Agent & orchestration (14)
| Module | What it does |
|---|---|
| `agent_core` | Claude Code Core re-implementation — the agent kernel module |
| `agent_infra` | Claude Code Superior infrastructure module |
| `agent_tools` | Re-implements ALL Claude Code tools as platform module |
| `agent_os` | Pulls + scores trending news from free RSS feeds (no API key) |
| `agent_coordination` | Multi-agent orchestration: scheduling, shared knowledge, conflict resolution, verification, fault tolerance |
| `agent_graph` | langgraph-style stateful agent graph (stdlib-only) |
| `agent_catalog` | Unified **432-specialist** registry (Codex + Agency occupations) |
| `autonomous_agent_runtime` | Multi-provider LLM abstraction for the kernel |
| `a2a` | Agent-to-Agent protocol (Google A2A style), stdlib-only |
| `task_harness` | Maestro-style long-running tasks: SQLite cards, pause/resume, dependency order, priority |
| `skill_factory` | Meta-skill generator / registry / self-evolution |
| `gateway` | Multi-channel remote control + automations (Telegram/Discord/webhook, cron) |
| `swarm_network` | Connection multiplexer for maximum multi-agent throughput |
| `swarm_bridge` | ENI Swarm 50-builder on-demand coordination (v5.0) |

### Model, MLOps & verification (8)
| Module | What it does |
|---|---|
| `model_router` | LiteLLM-style retry/cooldown/fallback routing gateway |
| `model_miner` | Local model mining: scan/rip/download→serve→rip→delete, multi-drive, cloud-ripple |
| `model_security` | Model-agnostic infrastructure security guards |
| `mlops_lifecycle` | Complete agent experiment lifecycle management |
| `llmops_trace` | langfuse-style offline LLM tracing/observability |
| `eval_gate` | Automated LLM evaluation gates (local & offline) |
| `universal_score` | One industry-grounded build-quality score (ISO25010/Sonar/DORA/CMMI/Snyk); certifies builds; can exceed 100 |
| `enterprise_validation` | Validation & certification OS module |

### Safety, security & compliance (10)
| Module | What it does |
|---|---|
| `safety_governance` | AI safety/security/guardrails/evaluation/monitoring/incident response |
| `threat_model` | Offline MITRE ATLAS / STRIDE threat modeling for LLM systems |
| `ai_defense` | Defense vs AI-driven/automated attackers: anomaly detection, bot classification |
| `compliance` | Offline control mapping + audit evidence (OWASP LLM Top10, NIST, MITRE) |
| `privacy_data` | Privacy, data governance, security, compliance |
| `guardrails` | Programmable I/O validators (validate/fix/refix loop), stdlib |
| `prompt_guard` | Injection / jailbreak / policy guarding facade |
| `secret_broker` | Local-first secret handling — keeps secrets off remote LLM calls |
| `secret_rotation` | Credential hygiene: rotation policies, expiry, schedules |
| `vuln_scanner` | Offline LLM vulnerability scanning (garak-style), black-box |

### Knowledge, memory & retrieval (6)
| Module | What it does |
|---|---|
| `knowledge_graph` | Organizational knowledge graph: entities, relationships, provenance |
| `kb_bridge` | Wrapper around the Hermes KB core: CRUD, search, vector search, metrics, health |
| `memory` | mem0-style hybrid long-term memory (semantic/episodic/declarative/procedural) |
| `semantic_memory` | cognee-style graph/persistent memory + semantic retrieval |
| `rag` | Production RAG: chunking, retrieval, generation pipeline |
| `compression_bridge` | Enterprise compression bridge (PAQ8/Wenyan/PxPipe carriers, glyphs) |

### Governance, ops & lifecycle (8)
| Module | What it does |
|---|---|
| `release_change` | Release & change management: lifecycle, approvals |
| `disaster_recovery` | Backup/recovery/cyber-recovery, business continuity, crisis mgmt |
| `innovation_rd` | Research/experiment/capability pipeline management |
| `developer_experience` | Unified DX framework + tooling |
| `customer_experience` | Customer journey, support tickets, engagement |
| `look_and_feel` | Visual design registry |
| `response_hardening` | **(NEW)** audits/repairs Hermes output-length caps |
| `hermes_controller` | Autonomous controller facade for Hermes (prompt orchestration) |

### Developer, integration & infra tooling (4)
| Module | What it does |
|---|---|
| `mcp_tools` | FastMCP-style tool registry & MCP serving layer (stdlib) |
| `prompt_context` | Prompt & context lifecycle management |
| `research_verification` | Research tracking + verification |
| `triadforge` | White/Grey/Black box security testing (wraps the TRIAD hacker box) |

**Platform subsystems (layers 1–4)**
- `kernel/` — kernel.py, orchestrator.py, registry.py, audit.py, quality_gate.py
- `foundation/` — policy_engine.py, evaluation_engine.py, prompt_registry.py
- `orchestration/` — workflow_composer.py, plugin_framework.py, feature_flags.py
- `tenancy/` — tenant_manager.py (multi-tenant / per-customer sandbox)
- `integration/` — api_gateway.py, event_hub.py, service_mesh.py
- `monitoring/` — metrics_collector.py, health_dashboard.py, alert_manager.py, log_aggregator.py
- `dashboard/` — Starlette admin console (:8421), live kernel telemetry
- `docker/` — multi-stage Dockerfile, compose (prod + dev), monitoring

## 4. Layer 2 — Cooperative Multi-Player Build Floor (the selling feature)
- **Server** (`multiplayer/server/`) WS:8787 + HTTP:8788 — broker, capability-aware
  round-robin assignment, heartbeat-timeout requeue, retry-once, JSONL persistence.
- **Clients** (`multiplayer/client/`) — one per machine; bring own GPU/keys; the
  server never sees other machines' secrets. Workers: `shell`, `python`, `llm`.
  The `llm_worker` writes real code via the planner + an external LLM (`MP_LLM_URL`),
  with two-layer secret redaction.
- **`/api/submit_plan`** — one goal → N uniquely-named step-tasks → across the fleet
  → conflict-safe, test-hinted merge.
- **Hardening (all tested):** binds `0.0.0.0`, auth token (`MP_AUTH_TOKEN`),
  per-tenant isolated workspaces, TLS (`wss`), conflict detector that never clobbers.
- **Proven live:** `POST /api/submit_plan {"goal":"build a budget tracker","tenant":
  "acme"}` → 6 steps → llm builder on the LAN → real artifacts → merged into
  `wspace/acme/` (tenant-isolated), ledger `APPLIED ... conflicts=0`.

## 5. Layer 3 — Local Brains :8913 (one-prompt → program)
- `/plan` goal→step DAG · `/enrich` bigger-prompt · `/program` runs it to artifacts +
  manifest + self-test (retry ≤2) · `/health`.
- **vault** redacts real secrets (registered placeholders + inline `api_key=` scrub)
  so nothing sensitive ever leaves the machine.

## 6. Layer 4 — Portable Hermes layer & operators
- `skills_pack/` — **20 skill categories, 957 skill files, 1 LSP, 2 MCP, 3 plugins
  (963 files)**; `install_skillspack.sh` (idempotent, backup, strips pycache).
- `eni_cli` (canonical, one CLI): `status` `doctor` `install` `setup` `fleet`
  `local` `agent-os` `up`. 
- `hermes-local` (installed to `~/.local/bin`): side-by-side boot of ENI
  controller+multiplayer+**hermes dashboard**.
- `setup.sh` (root + `enterprise/scripts/`): one-command install (deps, pack,
  systemd services, verify, status). `boot_all.sh`/`boot_all.bat`: boot all servers.
- `systemd/*.service` units: `eni-controller.service` (:8913), `eni-multiplayer-server.service` (:8787).

## 7. Verification & quality bar
- **4,411 tests collected, 4,410 passed, 1 skipped** (full platform regression).
- Every module ships unit tests; new modules this session: multiplayer 22,
  local_controller 11, response_hardening 6 — all green.
- `universal_score` certifies builds to a sellable-enterprise bar (100 = sellable,
  can exceed 100).
- **No fake data** — every number above is a real measured count.

## 8. Security posture (by design)
- Clients send capability tags only; protocol anti-secret guard refuses
  `api_key/apikey/secret/authorization/bearer/password/token=` in payloads.
- Secret vault redacts before any outbound LLM call; placeholders only leave.
- Optional auth token + TLS; per-tenant workspace isolation.
- Response-hardening self-heals Hermes output-length caps after upgrades.

## 9. Monetization (docs/SELLING.md)
Anchor to labor solved: **$12k–25k/yr team license**, free up to 10 builders funnel,
$10/builder/mo hosted margin, 30–60% white-label. Demo = cooperative floor +
one-prompt→program on a 15-min call.

## 10. Quick start
```bash
cd /home/hunter/Desktop/Enterprise\ Builder/enterprise
python3 scripts/eni_cli status            # health
bash setup.sh --bare                      # one-command install (verify only)
python3 scripts/eni_cli local             # side-by-side ENI + hermes dashboard
python3 scripts/boot_all.sh --headless    # boot all servers
curl -X POST :8788/api/submit_plan -d '{"goal":"build a to-do app","tenant":"acme"}'
```