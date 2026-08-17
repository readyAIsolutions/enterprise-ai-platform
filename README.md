# enterprise-ai-platform

Enterprise AI operating system — a modular, self-validating platform powered by an
agentic kernel, swarm orchestration, free-model routing, and independent OS modules.
Built to run autonomously, validate itself, and cross domains (3D printing, trading,
KB, compression, research).

## Architecture

- **Platform Kernel** (`platform_kernel.py`) — singleton `PlatformOS` orchestrator:
  `ModuleRegistry` auto-discovery, `EventBus` pub/sub, `HealthChecker`, lifecycle
  management, metrics collection, logging bridge.
- **Modules** (`modules/<name>/`) — independent capability modules, each a
  `@module(...)`-decorated `Module` subclass with `initialize` / `health_check` /
  `shutdown` lifecycle, discovered automatically by scanning `modules/*/__init__.py`.
- **Tooling** (`foundation`, `orchestration`, `tenancy`, `integration`) — prompt
  registry, policy/evaluation engines, workflow composer, plugin framework, feature
  flags, tenant manager, API gateway + event hub + service mesh.
- **Dashboard** (`dashboard/`) — Starlette admin console on `:8421`.
- **Infra** — Docker + multi-stage Dockerfile, CI/CD, Makefile, scripts.

## Modules

### Complete module reference (all modules)

Every platform module (auto-discovered by the Platform Kernel):
one page per module in [`docs/modules/`](docs/modules/) and the full grouped index in [`docs/MODULES_REFERENCE.md`](docs/MODULES_REFERENCE.md).

#### Knowledge Intake
| Module | Purpose |
|--------|---------|
| `ai_memory_hierarchy` | Layered memory model for agents (working/short/long) from AI-memory transcripts. |
| `ai_systems_thinking` | Feedback loops, coupling and systems lens for AI feature design. |
| `paper_feeds` | Daily research feeds (arXiv/HF/PwC/AlphaXiv), dedup, tagging, JSON/CSV export. |
| `second_brain` | Knowledge capture/resurfacing engine: nodes+links, spaced repetition, concept query, compounding. |

#### Agent Workflow
| Module | Purpose |
|--------|---------|
| `agentic_rag` | Agent-driven retrieval-augmented generation workflow. |
| `ai_coding_harness` | Harness for coding-agent output: run, verify, audit. |
| `context_routing` | Task -> {read/skip/skills} routing table with token-budget guard. |
| `group_chat_orchestration` | Multi-participant AI+human group chat: round-robin, moderator focus, escalation, handoffs. |
| `human_in_the_loop` | Human review/approval gates inside agent runs. |
| `shared_workspace` | Live multi-editor workspace: lock, merge-safe write, history, redact-before-share. |

#### Build Quality
| Module | Purpose |
|--------|---------|
| `automation_triage` | What-to-automate ladder, wrong-layer detection, one-client scoping guard. |
| `codegen_audit` | Audit generated code for correctness, security and quality signals. |
| `engineering_tradeoff` | Structured tradeoff scoring for engineering decisions. |
| `production_agent_hardening` | Demo->production hardening linter across 8 scored dimensions + systems loops. |
| `production_hardening` | Operational hardening checks for shipping an agent into production. |

#### Domain
| Module | Purpose |
|--------|---------|
| `ai_education_guardrails` | Guardrails for using AI in education (anti-cheating, learning-first). |
| `model_psychometrics` | Probe/evaluate model reasoning attributes (psychometric-style evals). |
| `procurement_bid_automation` | Automate procurement/RFP bid intake, scoring and responses. |
| `video_as_code` | Represent/edit long-form video (animations) as code/scripts. |

#### Legacy Core
| Module | Purpose |
|--------|---------|
| `a2a` | ENI A2A Module -- Agent-to-Agent protocol (Google A2A style). |
| `agent_catalog` | ENI Agent Catalog Module -- unified specialist-agent registry. |
| `agent_coordination` | Agent Communication & Coordination OS — Multi-agent orchestration, task scheduling, |
| `agent_core` | Claude Code Core — Enterprise Platform Kernel Module v2.0.0 |
| `agent_graph` | ENI Agent Graph Module — langgraph-style stateful agent graph orchestration. |
| `agent_infra` | Claude Code Superior — Infrastructure Module v1.0.0 |
| `agent_os` | Enterprise Agent OS Module — a unified AI agent operating system. |
| `agent_tools` | ENI Enterprise — Claude Code Tools Module v2.0.0 |
| `ai_defense` | ENI Enterprise AI Defense OS Module. |
| `artifact_pipeline` | Artifact Pipeline — navigate & organize all creative works (no LLM). |
| `autonomous_agent_runtime` | ENI Autonomous Agent Runtime Module -- Multi-provider LLM abstraction. |
| `compliance` | ENI Enterprise Compliance OS Module. |
| `compression_bridge` | Enterprise Platform — Compression Bridge Module v3.0.0 |
| `cost_meter` | Cost Meter — per-tenant cost metering + fractional-reasoning policy (B3 + C4). |
| `customer_experience` | Customer Experience OS Module. |
| `developer_experience` | Developer Experience OS Module |
| `disaster_recovery` | Disaster Recovery OS Module |
| `enterprise_validation` | Enterprise Validation & Certification OS — Module Entry Point |
| `error_correction` | error_correction — Hamming error-correcting code as an enterprise module. |
| `eval_gate` | ENI Eval Gate OS Module — automated LLM evaluation gates (local & offline). |
| `gateway` | ENI Multi-Gateway Remote Control & Automations Module |
| `guardrails` | ENI Guardrails OS Module. |
| `hermes_controller` | Enterprise Hermes Controller OS Module — autonomous controller for Hermes Agent. |
| `icm` | ICM (Interpretable Context Methodology) — skill/prompt-engineering layer. |
| `innovation_rd` | Innovation R&D OS Module |
| `kb_bridge` | ENI Knowledge Base OS Module |
| `knowledge_graph` | Knowledge Graph OS Module |
| `llmops_trace` | ENI LLMOps Trace OS Module — local, offline LLM tracing & observability. |
| `look_and_feel` | Enterprise Platform — Look & Feel Registry Module v1.0.0 |
| `mcp_tools` | ENI MCP Tools Module — FastMCP-style tool registry & MCP serving layer. |
| `memory` | ENI Agent Memory OS Module. |
| `mlops_lifecycle` | ENI Enterprise MLOps/LLMOps Lifecycle Module — Complete Agent Experiment Lifecycle Management |
| `model_miner` | Enterprise Model Miner OS Module — scan/rip local model training into the KB. |
| `model_router` | ENI Model Router OS Module — enterprise model-routing / fallback gateway. |
| `model_security` | ENI Model Security OS Module. |
| `observability` | Observability — real, consolidated fleet health + Prometheus export. |
| `privacy_data` | Privacy & Data Governance OS Module |
| `prompt_context` | Prompt & Context Management OS Module |
| `prompt_guard` | Enterprise Prompt Guard OS Module — injection / jailbreak / policy guarding. |
| `rag` | Production RAG System — Enterprise-grade Retrieval-Augmented Generation. |
| `release_change` | Release & Change Management OS Module |
| `research_verification` | Research & Verification OS — Enterprise Platform Kernel Module v1.0.0 |
| `response_hardening` | ENI Response Hardening module. |
| `response_ops` | ENI Response Ops Module — self-healing fleet supervisor + ICM routing hook. |
| `safety_governance` | ENI Enterprise — Safety & Governance OS v1.0.0 |
| `secret_broker` | Enterprise Secret Broker OS Module — local-first secret handling. |
| `secret_rotation` | ENI Enterprise Secret Rotation OS Module. |
| `semantic_memory` | ENI Semantic Memory OS Module. |
| `skill_factory` | ENI Skill Factory Module — Meta-Skill Generator / Registry / Self-Evolution. |
| `swarm_bridge` | ENI Swarm Enterprise Module v5.0.0 |
| `swarm_network` | Swarm Network Optimization OS — Enterprise Module |
| `task_harness` | ENI Task Harness OS Module |
| `threat_model` | ENI Threat Model OS Module. |
| `triadforge` | ENI TRIAD FORGE Module — White/Grey/Black Box security testing, as a kernel module. |
| `unified_inbox` | Enterprise Platform Unified Inbox module package. |
| `unified_work_system` | ENI Unified Work System Module |
| `universal_score` | ENI Universal Build Score module. |
| `vuln_scanner` | ENI Vuln Scanner OS Module — offline LLM vulnerability scanning (garak-style). |
| `youtube_transcripts` | YouTube transcript puller with PIA VPN IP rotation. |


Core OS modules: `safety_governance`, `agent_coordination`, `privacy_data`,
`knowledge_graph`, `prompt_context`, `developer_experience`, `customer_experience`,
`release_change`, `innovation_rd`, `disaster_recovery`, plus agent stack
(`agent_core`, `agent_infra`, `agent_tools`), swarm stack (`swarm_network`,
`swarm_bridge`, `kb_bridge`), validation (`enterprise_validation`,
`research_verification`, `compression_bridge`).

### Upgrade: Autonomy & Tooling layer (2026-08-02)

Four new modules added to extend autonomous operation:

| Module | Capability | What it does |
|--------|-----------|--------------|
| `skill_factory` | Meta-skill generator | Auto-compiles command/terminal patterns into versioned markdown skill recipes; registry + self-evolution loop (score/refine). |
| `task_harness` | Long-running task cards | Maestro-style SQLite task cards with status transitions, dependency gating, pause/resume, next-runnable scheduling for background builds. |
| `gateway` | Multi-channel automation | stdlib-only Telegram / Discord / webhook connectors (injectable for tests) + 5-field cron + interval scheduler for pushing events and scheduled runs. |
| `semantic_memory` | Semantic/vector memory | Dependency-free embedding (feature-hash) + cosine retrieval + metadata filtering + knowledge-graph ingestion adapter (cognee-style). |

### Upgrade: Demiurge Enterprise Boost (2026-08-04)

| Module | Capability | What it does |
|--------|-----------|--------------|
| `model_router` | Model routing / fallback gateway | LiteLLM-style retry/cooldown state machine — per-deployment cooldown, per-exception retry policy, weighted dispatch, cross-model failover with `max_fallbacks`. Offline EchoAdapter for deterministic tests + urllib HTTPAdapter for real providers. |
| `universal_score` | One universal build-quality number | Industry-grounded (ISO 25010 + Sonar + DORA + CMMI + Snyk) build scorer that runs REAL code-inspection probes across 6 weighted dimensions + hard gates + excellence bonus. 100 = sellable enterprise; a genuine build can exceed 100. Forces any Hermes build to a sellable-enterprise bar. |

**Kernel fixes in this wave:** `ModuleRegistry.discover()` now actually imports module
packages so every `@module` class binds (all 38 modules boot HEALTHY — previously it
silently initialized nothing); kernel `MetricsCollector` is now fed at startup; the
defined-but-dead `PAUSE`/`RECOVERING` lifecycle paths are implemented via
`PlatformOS.pause()/resume()` (resume re-inits failed modules); per-module startup
timeouts are honored. The 10 unregistered OS modules are now kernel-registered with
health probes.

### Release v2.0.0 — Golden Boot (2026-08-11)

All previously-scaffolded-but-non-booting modules are now complete, first-class,
Kernel-registered modules. Platform gold-boots on **49 modules**.

| Module | Capability | What it does |
|--------|-----------|--------------|
| `agent_catalog` | Unified specialist-agent registry | Fuses 172 Codex subagents + 263 Agency agents into 432 deduplicated specialists; SQLite faceted search, A2A AgentCard registration, offline canonical JSON + refresh ingest. Hermes skill: `agent-catalog`. |
| `mlops_lifecycle` | Experiment / LLMOps lifecycle | Feature+label store (SQLite), experiment tracking, canary rollout state machine, eval gates, OpenTelemetry-style observability, statistical drift (KS + PSI), rollback controller, pipeline orchestrator — all `@module`-registered. |
| `rag` | Production RAG pipeline | Chunking, embeddings, retrieval, reranking, context assembly, citation formatting, composable RAGPipeline (offline via deterministic HashEmbedder). |
| `autonomous_agent_runtime` | Multi-provider LLM abstraction | Provider registry, cost tracking, fallback/circuit-breaker, streaming SSE normalization — now a bootable facade module. |
| `agent_os` | Agent OS control surface | Dashboard (`:8421`) + `eni_cli.py` control Hermes/Oracle/Paperclip/Jarvis; browser-submittable commands. |

**Hygiene:** removed root/child `conftest.py` namespace-package shims that were
pre-registering `rag`/`mlops_lifecycle` to dodge missing-submodule imports — they
now import cleanly and self-register. Replaced nondeterministic `hash()` in the RAG
`HashEmbedder` with stable `hashlib`-derived hashing (killed a latent CI flake).

## Quick start

```bash
python3 -m pytest -q -p no:cacheprovider          # full test suite
python3 dashboard/server.py                        # admin dashboard :8421
```

## Configuration

All modules are configured in `config.yaml` under `modules.<name>` (enabled,
priority, required, timeouts, `config`). New upgrade modules are wired there and
auto-discovered by the registry.
