# STATUS_UPGRADE_RUNS — Post-Merge Hardening Wave

Updated: 2026-08-03 (after PR merge prep)

## PASS/FAIL BOARD (real numbers)

| Check | Result | Evidence |
|-------|--------|----------|
| a2a module tests | PASS | 59/59 passed |
| eval_gate module tests | PASS | 58/58 passed |
| agent_graph module tests | PASS | 48/48 passed |
| skill_factory (markdown-skills import) | PASS | 28 new + 44 existing = 72/72 |
| **Full platform suite** | **PASS** | **2405 passed** (was 2212 → +193) |
| config.yaml registration | PASS | 20 modules registered |
| Kernel boot (new modules) | PASS | a2a/eval_gate/agent_graph → HEALTHY |
| Module import smoke | PASS | All facades import cleanly (OK) |

## What was ADDED this wave (4 items — all stdlib-only, zero new deps)

1. **`a2a` module** — Google A2A (Agent-to-Agent) protocol, stdlib-only:
   AgentCard/AgentKey, Task with validated lifecycle transitions, Message/MessagePart,
   TaskManager (idempotency keys, retries), handoff with parent-link + context inheritance,
   negotiation (`A2AExchange`). `A2AFacade` (register_agent_card, list_agents, create_task,
   get_task, send_message, handoff). 59 tests.

2. **`eval_gate` module** — deepeval-style automated eval gates, computed LOCALLY (offline,
   no LLM calls): AnswerRelevancy, Faithfulness, ToxicityDetector, HallucinationProxy,
   RefusalDetector, JailbreakGuard — each a metric class returning MetricResult (score/passed).
   `EvalGate` enforces thresholds + policy; `EvalRunner` runs suites → report. `EvalGateFacade`.
   58 tests.

3. **`agent_graph` module** — langgraph-style stateful agent graph engine, stdlib-only:
   GraphNode/GraphEdge/AgentGraph (add_node/add_edge validation, topo execution honoring
   conditional edges, cycle protection), StateCheckpointStore (state persisted per run_id),
   SupervisorGraph (coordinator → worker routing), GraphRun result. `AgentGraphFacade`. 48 tests.

4. **`skill_factory` enhancement** — markdown-SKILLS-standard import (superpowers / anthropics
   format): `skills_import.py` parses YAML frontmatter (hand-rolled, no yaml dep),
   `--TRIGGERS--` blocks, stores real SkillRecords via the existing registry; `SkillsImportFacade`
   (parse_file / import_file / import_dir / list_all). 28 new tests, existing 44 preserved.

## What this ADDS to the platform (R calculus)
- **Agent interop**: A2A = agents can discover each other (AgentCard), exchange tasks,
  and hand off cross-domain — a genuinely missing capability for multi-agent fleets.
- **Quality gates**: eval_gate gives the platform automated offline eval to gate model output
  (complements model_security's *safety* guards with *quality* evals).
- **Orchestration**: agent_graph lets enterprise flows be modeled as checkpointable,
  resumable state graphs with a supervisor — moves beyond the linear task harness.
- **Skills standard**: skill_factory now ingests the open markdown-skills ecosystem, so
  external recipes import cleanly.

## What to DROP / consider
- None of the 4 need dropping. If line-count is a concern, a2a.py (714) and eval_gate.py (699)
  run near the ~700 guideline — acceptable; functional, no duplication.

## UNVALIDATED
- No real LLM eval run was executed (eval_gate metrics are offline heuristics only — a real
  LLM-backed eval harness would need a model call path, which this wave deliberately left
  local/offline to stay dependency-free). Validating metric sensitivity against real LLM
  outputs requires the live model layer.
- A2A wire-level interop against an external A2A server was not tested (no external peer) —
  only internal protocol semantics. In-memory, deterministic by design.

## Git
- Branch: upgrade/gold-picks
- New commit: "UPGRADE WAVE 2: a2a + eval_gate + agent_graph modules + skill_factory markdown-skills import (2405 tests, +193)"
