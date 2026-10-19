# STATUS — context_workflow_framework

**Module:** `context_workflow_framework` (v1.0.0)
**Transcript:** ColeMedin — "The True Power of AI Coding - Build Your OWN
Workflows" (https://www.youtube.com/watch?v=mHBk8Z7Exag, id mHBk8Z7Exag)

## What it is
AI coding is about building REUSABLE WORKFLOWS/SYSTEMS, not one-off prompts.
Existing frameworks (PRP = Product Requirement Prompt, BMAD, GitHub spec-kit)
share the same philosophy — scope the task, gather and assemble context
(docs/examples/rules), plan, implement, validate. This module lets you
understand that shared structure and COMPOSE YOUR OWN workflow.

## API
- `WorkflowPhase(name, purpose, instructions, required_context)` with
  `missing_context()` / `render()`.
- `WorkflowFramework` — ordered, composable phases (default:
  scope -> gather_context -> plan -> implement -> validate). Methods:
  `add_phase`, `remove_phase`, `reorder`, `render`, `validate_context`,
  `next_phase`, `phase_names`, `get_phase`, classmethod `load_template`,
  staticmethod `available_templates`. Built-in templates: prp / bmad /
  spec_kit.
- `ContextAssembler` — gather docs/examples/rules into one ordered,
  headered context block (`add`, `add_docs`, `add_examples`, `add_rules`,
  `sections`, `assemble`).
- `ContextWorkflowFrameworkModule(Module)` lifecycle
  (initialize/health_check/shutdown), `set_event_bus`, event-guarded
  publish, facade methods, plus factory
  `create_context_workflow_framework_module`.

## Verification
- pytest: `8 passed` (modules/context_workflow_framework/tests).
- Kernel registration: `True`.

Network-free, pure stdlib. Registered via `@module`.
