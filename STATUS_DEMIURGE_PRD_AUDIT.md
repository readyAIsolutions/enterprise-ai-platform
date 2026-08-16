# STATUS — DEMIURGE `prd_audit` Module

**Module:** `modules/prd_audit`
**Grounded in:** JEVanClief, "I'm Building a Custom Front End for Claude Code" (J2GLzkaUrBc)
**Branch:** upgrade/demiurge-enterprise-boost
**Date:** 2026-08-17

## Technique understood from the transcript

The transcript demonstrates a **PRD-gated build workflow** for Claude Code:

1. **Generate the PRD first.** Before building anything, have Claude produce a
   PRD (product requirements document) markdown for the *whole task*: "I'm
   actually going to have it make a PRD document... a PRD markdown of this for
   Claude code... that describes what we are trying to do and breaks down
   steps and structure for early phase to late phase." The intent is to "break
   it into steps rather than build the whole thing at once."
2. **Audit with a second instance.** "You can actually feed this into another
   version of Claude and have it act as that auditor and it can kind of redo
   it there" — a fresh pass re-reviews the PRD before any build starts.
3. **Drop into workspace and execute.** "When this is done, I can download it,
   drop it into my workspace, and actually have it build the front end inside
   of this workspace... 'Hey, read the PRD for the front end.'"

`prd_audit` encodes that gate in deterministic, stdlib-only logic: parse the
PRD, run the second-instance auditor over it, and block execution until the
audit clears a threshold.

## Module API (public surface)

Core (`modules/prd_audit/prd_audit.py`):
- `PrdDocument` — structured PRD with canonical sections `goals`, `scope`,
  `acceptance-criteria`, `risks`, `tasks`. `from_markdown()` /
  `to_markdown()` round-trip; `missing_sections` / `is_complete`.
- `Task` — planned step with `acceptance_test` and `done` checkbox.
- `PrdValidator` (alias `Auditor`) — the second-instance reviewer. Deterministic
  rules: `MISSING_SECTION`, `VAGUE_GOAL`, `GOAL_PROLIFERATION`,
  `VAGUE_ACCEPTANCE_CRITERION`, `NO_ACCEPTANCE_TESTS`, `SCOPE_CREEP`,
  `SCOPE_CREEP_TASK_EXPLOSION`, `NO_RISKS`. Returns `AuditReport` with
  severity-typed `AuditFinding`s.
- `AuditReport` — `errors`/`warnings`/`info`, `score()`, `passes()`, `to_dict()`.
- `AuditSeverity` — `INFO < WARNING < ERROR` with numeric `weight`.
- `PrdGate` — blocks execution until audit passes (`max_errors`, `max_warnings`,
  `min_score`); `enforce*` raise `PrdGateBlocked`; `evaluate*` return
  `GateDecision`.
- `audit_prd(markdown, validator=None)` — parse + audit convenience.

Facade (`modules/prd_audit/__init__.py`):
- `PrdAuditModule` — `@module(name="prd_audit")`, lifecycle
  `initialize`/`health_check`/`shutdown`, `set_event_bus` (defensive event
  publishing), facade methods `parse_prd`, `audit`, `audit_markdown`, `gate`,
  `gate_document`, `gate_markdown`.
- `create_prd_audit_module(config=None)`.

## Verification

| Check | Result |
|---|---|
| `python3 -m pytest modules/prd_audit/tests -q` | **PASS** |
| Test count | **20 passed** (0 failed, 0.04s) |
| Registration (`'prd_audit' in _MODULE_REGISTRY`) | **True** |
| Facade smoke test (initialize → HEALTHY, gate/audit) | **True** |

## UNVALIDATED / OUT OF SCOPE (not touched)

- `config.yaml`, `platform_kernel.py`, other modules, and the ledger
  `data/build/manifest.json` were **not** modified (ledger updated centrally).
- No network, no numpy/pandas/requests — pure stdlib (`re`, `dataclasses`,
  `enum`).
- Event bus publishing is defensive; no live bus integration test was run.
- `scope_creep_terms` / vagueness lexicons are heuristic; coverage is unit
  tested against the real GOOD/BAD PRD samples in `tests/`.
