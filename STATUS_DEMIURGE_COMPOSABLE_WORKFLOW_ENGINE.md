# STATUS — composable_workflow_engine (DEMIURGE)

Module: `modules/composable_workflow_engine/`
Source: ColeMedin — "The True Power of AI Coding - Build Your OWN Workflows (Full Guide)"
(https://www.youtube.com/watch?v=mHBk8Z7Exag)

## PASS/FAIL BOARD
| Check | Result |
|-------|--------|
| pytest (modules/composable_workflow_engine/tests) | PASS — 56 passed in 0.15s |
| Module registration in `_MODULE_REGISTRY` | PASS — prints `True` |
| core.py line count (<= ~700) | PASS — ~560 lines |
| stdlib-only, network-free | PASS |

## WHAT WAS UNDERSTOOD FROM THE TRANSCRIPT
- AI coding is about building SYSTEMS / WORKFLOWS, not one-off prompts.
- Rather than adopt an existing framework wholesale (PRP = Product Requirement
  Prompt, BMAD, GitHub spec-kit), understand the PHILOSOPHY and fundamental
  PHASES behind them so you can COMPOSE YOUR OWN.
- Primary mental model: PLANNING -> IMPLEMENTATION -> VALIDATION.
  - Planning = vibe planning (free-form exploration) -> initial requirements
    ("initial MD" / PRD) -> create plan (research via RAG + web + codebase
    analyst sub-agent; produce granular tasks, desired codebase structure,
    doc/example references, success criteria — exactly what a PRP produces).
  - Implementation = execute plan task-by-task (TODO->DOING->REVIEW->DONE),
    one at a time to avoid hallucination; NO sub-agents (shared primary
    context).
  - Validation = validator sub-agent generates/runs tests in isolated context
    + human code review; can reopen tasks.
- Context-engineering components (diagram): RAG, memory, task management,
  prompt engineering. Reusable blocks: slash commands, sub-agents, global rules.

## PUBLIC API
- Class `ComposableWorkflowEngineModule(Module)` + factory
  `create_composable_workflow_engine_module(config=None)`.
- Facade methods: `all_templates`, `get_template`, `register_template`,
  `compose`, `validate_template`, `run`, `describe`, `set_event_bus`.
- Core: `WorkflowPhase`, `WorkflowTemplate`, `WorkflowEngine`,
  `ValidationResult`, `WorkflowError`; built-in templates `prp`, `spec-kit`,
  `three-step`; constants `KNOWN_FRAMEWORKS`, `CONTEXT_COMPONENTS`,
  `BUILDING_BLOCKS`.

## UNVALIDATED / LIMITATIONS
- Phase execution is a pure deterministic simulation (structured artifact
  records with provenance) — there are NO real LLM calls, no real tests run,
  no real codebase analysis. Artifacts are placeholders, not generated code.
- Built-in template contents reflect the author's described phases but are an
  interpretation; the transcript does not give a formal phase schema.
- No integration test against the full PlatformOS lifecycle beyond registration.
