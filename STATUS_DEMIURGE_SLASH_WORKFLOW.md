# STATUS — DEMIURGE: `slash_workflow` module

**Transcript source:** ColeMedin — "The True Power of AI Coding - Build Your OWN Workflows"
(https://www.youtube.com/watch?v=mHBk8Z7Exag) · duration 1563s
**Channel:** ColeMedin · **Video id:** mHBk8Z7Exag
**Repo:** `/home/hunter/Desktop/Enterprise Builder/enterprise`
**Branch:** upgrade/demiurge-enterprise-boost
**Date:** 2026-08-17

## Technique understood from the transcript
ColeMedin builds a reusable AI-coding **system** (not just prompts) around a
three-phase mental model — **Plan -> Implement -> Validate** — implemented as:

1. **Planning (most important, context curation):**
   - *Vibe planning*: free-form exploration of the idea before any structure.
   - Write an *initial requirements markdown* (feature, endpoints, examples).
   - Run a **`primer` slash command** at the start of every fresh conversation to
     quickly catch the assistant up on the codebase by reading key files.
   - A **`create_plan` slash command** turns requirements into a full planning
     document, using a **codebase-analyst sub-agent** (own context window) plus
     RAG/research so the primary context window stays concise.
2. **Plan document schema:** goals, granular step-by-step tasks, files-to-modify,
   files-to-create, existing patterns to follow, and **success criteria**.
3. **Implementation:** a **`execute_plan` slash command** reads the plan, sets up
   the project/tasks, analyzes code, then drives a **task cycle**
   (`to-do -> doing -> review -> next`) one granular task at a time until done.
   **Critical rule: NO sub-agents during implementation** — separate context
   windows cannot share memory, causing conflicting/overlapping changes. Everything
   must stay in the primary context window.
4. **Validation:** a **`validate` slash command** / **validator sub-agent** runs in
   its own context window to write/run tests and report back; the human then does a
   **code review + manual tests** (never vibe-code).
5. **Global rules (`CLAUDE.md`):** golden instructions that cascade into every phase
   no matter the task, and the whole slash-command + sub-agent + task-cycle system is
   reusable across any project.

## Module layout
- `modules/slash_workflow/__init__.py` — platform kernel module (`SlashWorkflowModule`).
- `modules/slash_workflow/slash_workflow.py` — pure-logic core (stdlib only, no network).
- `modules/slash_workflow/tests/test_slash_workflow.py` — pytest suite (real assertions).

## Verification board
| Check | Result |
|-------|--------|
| `python3 -m pytest modules/slash_workflow/tests -q` | **PASS** |
| Tests run | **34** |
| Tests passed | **34** |
| Tests failed | 0 |
| Import `enterprise.modules.slash_workflow` (no error) | PASS |
| Registration `'slash_workflow' in _MODULE_REGISTRY` | **True** |
| Module name / version | `slash_workflow` / `1.0.0` |
| Health status after `initialize()` | HEALTHY |

## Public API
- `SlashCommand`, `SlashCommandRegistry`, `default_slash_commands()`
  (`primer`, `create_plan`, `execute_plan`, `validate`).
- `TaskStatus` (todo/doing/review/done/blocked), `TaskItem` (guarded
  `advance()` transitions), `TaskManager` (deterministic cycle).
- `PlanDocument`, `build_plan()` — the planning-document schema.
- `SubAgent` (isolated context), `GlobalRules`/`default_global_rules()` (CLAUDE.md cascade).
- `Phase`, `PhaseReport`, `WorkflowValidator` (plan/cycle + sub-agent policy),
  `WorkflowEngine` (run Plan->Implement->Validate).
- `SlashWorkflowModule`, `create_slash_workflow_module()`, `create_slash_workflow()`.

## Commit
- Files committed: `modules/slash_workflow/` + `STATUS_DEMIURGE_SLASH_WORKFLOW.md`.
- config.yaml, platform_kernel.py, other modules, and the ledger were **NOT** touched.

## UNVALIDATED / notes
- No live AI assistant / LLM was invoked; sub-agents are modelled as isolated
  context workers returning concise summaries (no real LLM calls).
- Deterministic task-cycle semantics are unit-tested; end-to-end behaviour with a
  real codebase / real MCP servers (as shown in the talk with Archon/Code Rabbit)
  is not exercised in this environment.
- Success-criteria satisfaction in `validate_phase` is reported optimistically when
  the plan is sound; real test execution is the user's manual-review step.
- `REVIEW -> BLOCKED` transition was added to the core to model rework-budget
  exhaustion (a task whose review keeps failing).
