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

## Quick start

```bash
python3 -m pytest -q -p no:cacheprovider          # full test suite
python3 dashboard/server.py                        # admin dashboard :8421
```

## Configuration

All modules are configured in `config.yaml` under `modules.<name>` (enabled,
priority, required, timeouts, `config`). New upgrade modules are wired there and
auto-discovered by the registry.
