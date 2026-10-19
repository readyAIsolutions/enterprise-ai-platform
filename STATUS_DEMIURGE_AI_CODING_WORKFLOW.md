# STATUS — ai_coding_workflow (Demiurge Enterprise Boost)

**Module:** `ai_coding_workflow`  **Version:** 1.0.0
**Branch:** `upgrade/demiurge-enterprise-boost`
**Source transcript:** ColeMedin — *The True Power of AI Coding - Build Your OWN Workflows*
(https://www.youtube.com/watch?v=mHBk8Z7Exag)

## What was understood from the transcript
The talk teaches a **framework-agnostic 3-phase AI-coding workflow** (plan →
implement → validate) that works regardless of the chosen context-engineering
framework (PRP, BMAD, GitHub spec-kit, or plain markdown):

1. **REQUIREMENTS** — vibe-plan freely, then distill into a requirements doc.
2. **PLAN** — a codebase-analyst research step produces a *granular* ordered
   implementation plan: tasks, files to modify/create, patterns to follow,
   and success criteria.
3. **EXECUTE** — a task state machine cycles each task **one at a time**
   through TODO → DOING → REVIEW → DONE (granularity prevents the model from
   hallucinating by doing too much at once).
4. **VALIDATE** — after all tasks DONE, a validation sub-step generates tests
   and runs a human/AI code-review gate that can reopen tasks for fixes
   ("don't vibe-code"). Research/validation use isolated context.
5. **COMPLETE** — validation passed.

## Module API
- **core.py** (pure stdlib, no network):
  - `TaskState` (TODO/DOING/REVIEW/DONE/BLOCKED), `WorkflowPhase`
    (REQUIREMENTS/PLAN/EXECUTE/VALIDATE/COMPLETE)
  - `Task`, `Plan`, `ValidationResult` dataclasses
  - `WorkflowEngine(name, framework)`: `set_requirements`, `create_plan`,
    `next_task`, `start_task`, `advance_task`, `set_task_state`, `block_task`,
    `all_tasks_done`, `validate`, `progress`, `summary`, `render`.
    Enforces phase ordering and legal per-task transitions (rejects illegal
    ones, allows only one active task, reopens tasks on failed review).
  - `SUPPORTED_FRAMEWORKS = ('prp','bmad','spec_kit','plain')` (metadata only)
- **__init__.py**: `@module(name="ai_coding_workflow", version="1.0.0",
  config_defaults={"default_framework":"plain"})` on `AICodingWorkflowModule`
  (extends `Module`) with async `initialize`/`health_check`/`shutdown`,
  `set_event_bus`/`_publish` (events only when a bus is attached), multi-
  workflow facade methods, `create_ai_coding_workflow_module()` factory,
  `create_workflow_engine()` facade, and full `__all__`.

## Verification (real output)
- **pytest:** `19 passed in 0.05s` — **PASS** (0 failed).
  Note: the active hermes venv lacks pytest; ran with `/usr/bin/python3 -m
  pytest` (pytest 9.1.1). Covers phase ordering, legal + illegal transitions,
  one-task-at-a-time, next_task, validation gate (fails incomplete / passes
  when all DONE / reopens on review findings), progress counts, module
  lifecycle, and event emission with/without a bus.
- **Registration:** prints `True` — **REGISTERED**.

## Files created
- `modules/ai_coding_workflow/__init__.py`
- `modules/ai_coding_workflow/core.py`
- `modules/ai_coding_workflow/tests/__init__.py`
- `modules/ai_coding_workflow/tests/test_ai_coding_workflow.py`
- `STATUS_DEMIURGE_AI_CODING_WORKFLOW.md`

## Issues
- The active virtualenv (`~/.venvs/hermes`) has no `pytest`; the system
  interpreter `/usr/bin/python3` does. Tests were run with it successfully.
  No code issues; no network; config.yaml / platform_kernel.py untouched.
