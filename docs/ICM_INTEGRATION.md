# ICM — Interpretable Context Methodology Integration
## The prompt-engineering & skill-discipline layer for the Enterprise stack

**Source spec:** `ICM_Enterprise_Integration_Spec.docx`
**Status:** implemented v1 (2026-08-16), tests green
**Module:** `modules/icm/`

---

## 1. What ICM is (and is NOT)

ICM is an **internal discipline layer**. It governs *how an individual agent
task is structured* once the orchestration layer (Hermes routing / swarm / model
access) has decided *which* agent runs it.

- ICM is **not** a replacement for orchestration.
- ICM is **not** a substitute for swarm reasoning.
- ICM gives: auditability, predictable behavior, and **lower token overhead at
  the single-agent level**.

The core mechanic is deliberately simple: an agent's instructions live in
**numbered, self-contained stage folders** (markdown + scripts), not in inline
prompt strings.

---

## 2. The three integration points (from the spec) — and how it's done here

### 2.1 Prompt / Skill layer (primary) ✅ DONE
Every task is backed by folder markdown + a script, not a bare inline prompt.

Implementation:
- New `modules/icm/` platform module (auto-discovers into the kernel).
- `eni_cli icm scaffold <name>` creates the standard numbered-stage template plus
  two ready reference implementations.
- `ICMProject.route(task)` maps a task to the correct stage folder.
- `ICMProject.stage_context(stage)` returns ONLY that stage's markdown.

### 2.2 Context compression (progressive disclosure) ✅ DONE
Load only the markdown relevant to the current stage → lower tokens per call.

Implementation:
- `local_controller/planner.py::enrich_prompt` now consults `ICM_PROJECT`
  (an env var pointing at an ICM skill project). When set, it routes the goal to
  a stage and injects ONLY that stage's instructions into the enriched prompt.
- When `ICM_PROJECT` is unset, behaviour is identical to before (no-op) — so
  there is zero coupling unless you opt in.

### 2.3 Standardized skill format across projects ✅ DONE
One folder/markdown/script convention applies everywhere (Aurora, Marlin, ops),
so new agents are fast to build, audit, and port.

Implementation:
- A single canonical template: `00_master.md` + `01_intake … 05_output`, each
  with `instructions.md` + `scripts/`.
- Two shipped reference implementations prove the pattern:
  - `11_example_doc_compliance` (Aurora-style deterministic compliance checklist)
  - `12_example_ops_deploy` (Oracle-Cloud-style repeatable ops + health check)

### Division of labor: ICM vs Swarm ✅ DONE
Returns the rule so the router doesn't misuse one for the other:
- `icm.classify(task)` → `"sequential"` or `"swarm"`.
- `icm.should_use_swarm(task)` → bool.
- Judgment-heavy work (legal reasoning, classification, creative generation,
  cross-validation) routes to **swarm**; predictable deterministic work
  (compliance, verify, export, deploy, format) routes to **sequential ICM**.

---

## 3. The folder template

```
project/
├── 00_master.md            ← table of contents; maps a task to a stage folder
├── 01_intake/      instructions.md + scripts/
├── 02_research/
├── 03_drafting/
├── 04_verification/
├── 05_output/
├── 11_example_doc_compliance/   (reference impl)
└── 12_example_ops_deploy/       (reference impl)
```

`00_master.md` is the only file an orchestrator must read to know which folder
to activate — it holds the map (task → stage), not the details. Each stage is
self-contained: one `instructions.md` (role / inputs / definition of good
output) plus a `scripts/` dir for anything that doesn't need model reasoning.

---

## 4. Commands

```bash
# scaffold a new skill project
python3 scripts/eni_cli icm scaffold aurora_demo

# classify a task -> 'sequential' | 'swarm' (+ routed stage, if a project is found)
python3 scripts/eni_cli icm route "run the compliance checklist"
python3 scripts/eni_cli icm route "cross-validate the legal reasoning"

# print only the requested stage's markdown (progressive disclosure)
python3 scripts/eni_cli icm context icm_projects/aurora_demo 04_verification

# list projects
python3 scripts/eni_cli icm list
```

---

## 5. Using ICM from the one-prompt brains (compression)

```bash
# point the planner at an ICM project, then submit any goal
export ICM_PROJECT=/path/to/enterprise/icm_projects/aurora_demo
curl -X POST http://127.0.0.1:8913/enrich -H "Content-Type: application/json" \
     -d '{"prompt":"verify the citation","goal":"verify the citation"}'
```
The response will include an `## ICM STAGE` block with the routed stage's
instructions — meaning the model receives less irrelevant context (token savings)
and follows the project's discipline.

---

## 6. Files

| Path | Role |
|---|---|
| `modules/icm/__init__.py` | Kernel module registration + facade |
| `modules/icm/icm.py` | Data model, routing, progressive disclosure, classifier |
| `modules/icm/scaffold.py` | Standard template generator + 2 reference impls |
| `modules/icm/tests/test_icm.py` | 7 tests |
| `local_controller/tests/test_icm_integration.py` | 2 integration tests |
| `icm_projects/` | Scaffolded skill projects (runtime, gitignored-ish) |

## 7. Verified
- 9 ICM + integration tests pass.
- Live CLI: scaffold → route → context all work.
- `enrich_prompt` with `ICM_PROJECT` injects the stage (verified by test + script).
- Full platform suite remains green (see STATUS_UPGRADE_v3 §3).