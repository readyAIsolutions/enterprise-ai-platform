# STATUS: ENI AGENT CATALOG — Unified Specialist-Agent Registry

Date: 2026-08-11
Module: `enterprise/modules/agent_catalog/`
Skill: `~/.hermes/skills/agent-catalog/`
Sources: `~/Desktop/awesome-codex-subagents-main` (Codex) + `~/Desktop/agency-agents-main` (Agency)

## What was built

"Rebuilt better": the two complementary specialist-agent catalogs were FUSED into
one normalized, deduplicated, searchable enterprise module + Hermes skill instead
of being dumped in raw.

| Source | Format | Raw count |
|--------|--------|-----------|
| Codex  | `.toml` subagents | 172 |
| Agency | `.md` division agents | 263 |
| **Unique after dedup** | | **432** |

Cross-source shared roles collapsed into a single record with unioned
categories + sources (3 shared slugs: customer-success-manager, product-manager,
sales-engineer).

## Files

Enterprise module:
- `modules/agent_catalog/__init__.py` — @module-decorated AgentCatalogModule + AgentCatalogFacade (search/get/overview/register_all_in_a2a). Boots healthy, A2A-registers all 432 specialists as AgentCards.
- `modules/agent_catalog/store.py` — SQLite registry with faceted search (query/source/category), JSON read-only fallback.
- `modules/agent_catalog/ingest.py` — deterministic re-ingest from both live source repos.
- `modules/agent_catalog/data/agent_catalog.json` — committed canonical (432 agents, works offline).
- `modules/agent_catalog/data/agents/<slug>.json` — per-agent detail.
- `modules/agent_catalog/tests/test_agent_catalog.py` — 15 tests.
- `config.yaml` — `agent_catalog` module entry (enabled, priority 11, db path).

Hermes skill `~/.hermes/skills/agent-catalog/`:
- `SKILL.md` — trigger conditions + how to locate/invoke a specialist.
- `references/master-index.md` — full 432-agent index by category.
- `scripts/fetch_agent.py` — CLI: overview / list / search / fetch-full-instructions.

## Test results — PASS

| Check | Result |
|-------|--------|
| `pytest modules/agent_catalog/` | **15 passed** |
| `pytest tests/` (full platform suite) | **205 passed** (no regressions) |
| Gold boot (`verify_gold_boot.py`) | **PASS** — 48 modules, agent_catalog booted + healthy |
| Facade smoke: 432 total, search("architect", source=codex) works | PASS |
| A2A registration: 432 AgentCards registered | PASS |
| Fetch CLI: overview/search/fetch for codex + agency agents | PASS |

## What adds R / what to drop

ADDS:
- 432 named specialists immediately queryable/invokable from Hermes + platform.
- Unified schema bridges two divergent tooling families (Codex + agency-persona).
- A2A cards let specialists participate in swarm/task orchestration.
- Offline canonical JSON + refresh CLI decouple runtime from source repos.

DROP / low-value:
- Per-agent `<slug>.json` files (432 small files) are redundant with the one
  canonical JSON — keep only if external tooling wants separate files. (Kept for
  now; harmless.)

## UNVALIDATED

- Not yet exercised as *live* A2A task participants end-to-end (only card
  registration verified). Real handoff/orchestration needs a swarm run.
- Agent *quality* not benchmarked — catalog stores instructions; no eval of how
  well each persona performs vs a baseline. A representative-sample A/B (e.g. 10
  agents vs no-specialist on matching tasks) is the honest validation.
- model hints (codex) are advisory; no router integration yet (free-router /
  model_router could prioritize a codex agent's preferred model).
