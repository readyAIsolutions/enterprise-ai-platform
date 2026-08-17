"""Custom agent workflows — build your OWN AI coding workflows.

Pure-stdlib, network-free capability grounded in the Cole Medin transcript
*"The True Power of AI Coding — Build Your OWN Workflows (Full Guide)"*
(https://www.youtube.com/watch?v=mHBk8Z7Exag, transcript
``data/transcripts/ColeMedin/mHBk8Z7Exag.md``).

The guide's central thesis: working with AI coding assistants is a lot more
than just prompts — it's about building *systems* and reusable workflows that
can evolve to fit your needs. The workflow is a three-phase loop:

  1. PLANNING  — "the most important phase by far": if you are not curating
     context correctly for the coding assistant, it will fall on its face. It
     starts with *vibe planning* (unstructured exploration where the assistant
     is a research companion) and produces an *initial MD* — a PRD / detailed
     feature request. That PRD is then turned into a *full plan* with all the
     context engineering: goals, tasks, resources, a granular task list,
     desired codebase structure, success criteria, and documentation
     references (exactly what the PRP framework accomplishes).
  2. IMPLEMENTATION — a predefined workflow (slash command) guides the
     assistant to knock out granular tasks one by one. Task management is
     paramount: "if the coding assistant tries to do too much at once, that's
     when you have a lot of hallucinations." Everything must stay in the
     primary context window, so subagents are deliberately NOT used here —
     they do not share memory and produce conflicting / overlapping changes.
  3. VALIDATION — the plan tells the assistant how to validate its own work; a
     *validator* subagent runs tests inside its own isolated context window
     and reports back; then the human acts as project manager and performs a
     code review + manual tests (we don't want to vibe code).

Supporting mechanisms from the guide:

  - Slash commands — prompts turned into reusable markdown workflows
    (``primer``, ``create_plan``, ``execute_plan``).
  - Subagents — their own context window; used for research upfront and for
    validation, never for implementation (``codebase_analyst``, ``validator``).
  - Global rules — the golden instructions (``.claude.md`` / ``.cursorrules``)
    the assistant follows no matter what the task.
  - Context engineering pillars — RAG (external docs), memory (conversation
    history), task management, and prompt engineering.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional

# ---------------------------------------------------------------------------
# Phases (the plan -> implement -> validate mental model)
# ---------------------------------------------------------------------------
PHASE_PLANNING = "planning"
PHASE_IMPLEMENTATION = "implementation"
PHASE_VALIDATION = "validation"

# ---------------------------------------------------------------------------
# Task states (the to-do -> doing -> review -> done cycle from execute_plan)
# ---------------------------------------------------------------------------
TASK_TODO = "todo"
TASK_DOING = "doing"
TASK_REVIEW = "review"
TASK_DONE = "done"

_TASK_TRANSITIONS: Dict[str, set] = {
    TASK_TODO: {TASK_DOING},
    TASK_DOING: {TASK_REVIEW},
    TASK_REVIEW: {TASK_DONE},
    TASK_DONE: set(),
}

# ---------------------------------------------------------------------------
# Slash command names (reusable prompt-workflows from the guide)
# ---------------------------------------------------------------------------
SLASH_PRIMER = "primer"
SLASH_CREATE_PLAN = "create_plan"
SLASH_EXECUTE_PLAN = "execute_plan"

# Subagent roles
AGENT_CODEBASE_ANALYST = "codebase_analyst"
AGENT_VALIDATOR = "validator"


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------
@dataclass
class Task:
    """A single granular unit of implementation work."""

    id: str
    description: str
    files: List[str] = field(default_factory=list)
    status: str = TASK_TODO


@dataclass
class WorkflowPlan:
    """The full implementation prompt: task list + structure + criteria."""

    title: str
    summary: str
    tasks: List[Task]
    success_criteria: List[str] = field(default_factory=list)
    desired_structure: List[str] = field(default_factory=list)
    references: List[str] = field(default_factory=list)


@dataclass
class SubAgent:
    """A specialist that runs inside its own isolated context window."""

    name: str
    role: str
    system_prompt: str


@dataclass
class SlashCommand:
    """A prompt turned into a reusable workflow."""

    name: str
    description: str
    prompt_template: str


CODEBASE_ANALYST = SubAgent(
    name=AGENT_CODEBASE_ANALYST,
    role="Research",
    system_prompt=(
        "You research the existing codebase in your own context window and "
        "return only a concise summary of where the new feature integrates."
    ),
)

VALIDATOR = SubAgent(
    name=AGENT_VALIDATOR,
    role="Validation",
    system_prompt=(
        "You validate the produced code inside your own context window by "
        "running tests, then report back what needs fixing."
    ),
)


# Default granular implementation tasks grounded in the guide's execute_plan loop.
_DEFAULT_TASKS: List[str] = [
    "Analyze the codebase to locate integration points and existing patterns",
    "Scaffold the new feature module following existing codebase patterns",
    "Implement the core logic behind the feature",
    "Wire the feature into the identified integration points",
    "Write unit tests that validate the feature end to end",
    "Update supporting documentation and references",
]


# ---------------------------------------------------------------------------
# Planning phase helpers
# ---------------------------------------------------------------------------
def build_initial_md(
    feature: str,
    references: Optional[List[str]] = None,
    integration_points: Optional[List[str]] = None,
    is_new_project: bool = True,
) -> str:
    """Produce the *initial MD* — a PRD / detailed feature request.

    For a new project the guide keeps it high level: "a simple MVP for the
    application you want to build, including a lot of references to the
    supporting documentation and examples." For an existing project it is much
    more focused and names the integration points (files to edit / reference
    for architecture).
    """
    refs = references or []
    ips = integration_points or []

    md: List[str] = [f"# {feature}", ""]
    md.append("> PRD — detailed feature request (initial MD).")
    md.append("")
    if is_new_project:
        md.append(
            "- Scope: simple MVP for the application, including references to the "
            "supporting documentation and examples gathered during vibe planning."
        )
    else:
        md.append("- Scope: focused and detailed feature added to the existing codebase.")
        if ips:
            md.append("")
            md.append("## Integration Points")
            for ip in ips:
                md.append(f"- `{ip}`")
    if refs:
        md.append("")
        md.append("## References")
        for r in refs:
            md.append(f"- {r}")
    md.append("")
    md.append("## Success Criteria")
    md.append("- The feature works end to end and is validated by tests.")
    md.append("")
    return "\n".join(md)


def _extract_title(md_text: str) -> str:
    for line in md_text.splitlines():
        stripped = line.strip()
        if stripped.startswith("# "):
            return stripped[2:].strip()
    return ""


def _extract_references(md_text: str) -> List[str]:
    refs: List[str] = []
    in_refs = False
    for line in md_text.splitlines():
        stripped = line.strip()
        if stripped.startswith("## References"):
            in_refs = True
            continue
        if in_refs:
            if stripped.startswith("## "):
                break
            if stripped.startswith("- "):
                refs.append(stripped[2:].strip())
    return refs


def build_plan(
    initial_md: str,
    codebase_summary: str = "",
    default_tasks: Optional[List[str]] = None,
) -> WorkflowPlan:
    """Turn the initial MD (PRD) into a full implementation plan.

    Mirrors the guide's *create_plan* slash command: take the requirements
    document and produce a step-by-step plan with granular tasks, the desired
    codebase structure, success criteria, and documentation references.
    """
    tasks = list(default_tasks if default_tasks is not None else _DEFAULT_TASKS)
    plan_tasks = [Task(id=f"task-{i}", description=desc) for i, desc in enumerate(tasks, 1)]
    title = _extract_title(initial_md) or "Untitled feature"
    return WorkflowPlan(
        title=title,
        summary=codebase_summary or (
            "Implementation plan with granular task list, desired codebase "
            "structure, success criteria, and documentation references."
        ),
        tasks=plan_tasks,
        success_criteria=["The feature works end to end and is validated by tests"],
        desired_structure=["modules/<feature>/", "modules/<feature>/tests/"],
        references=_extract_references(initial_md),
    )


# ---------------------------------------------------------------------------
# Task management (implementation phase)
# ---------------------------------------------------------------------------
class TaskManager:
    """Task state machine: to-do -> doing -> review -> done, one at a time."""

    def __init__(self, tasks: List[Task]) -> None:
        self._tasks: Dict[str, Task] = {t.id: t for t in tasks}

    @property
    def tasks(self) -> List[Task]:
        return list(self._tasks.values())

    def next(self) -> Optional[Task]:
        """Return the next task still in ``todo`` (None when all are queued)."""
        for task in self._tasks.values():
            if task.status == TASK_TODO:
                return task
        return None

    def mark(self, task_id: str, new_status: str) -> Task:
        """Advance a task to a valid next state; raises on invalid transitions."""
        if task_id not in self._tasks:
            raise KeyError(task_id)
        task = self._tasks[task_id]
        allowed = _TASK_TRANSITIONS.get(task.status, set())
        if new_status not in allowed:
            raise ValueError(f"invalid transition {task.status} -> {new_status}")
        task.status = new_status
        return task

    def remaining(self) -> int:
        return sum(1 for t in self._tasks.values() if t.status != TASK_DONE)

    @property
    def completed(self) -> bool:
        return all(t.status == TASK_DONE for t in self._tasks.values())


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------
def validate_plan(plan: WorkflowPlan) -> Dict[str, object]:
    """Check a plan is usable: titled, granular tasks, success criteria."""
    issues: List[str] = []
    if not plan.title:
        issues.append("plan has no title")
    if not plan.tasks:
        issues.append("plan has no granular tasks")
    else:
        for task in plan.tasks:
            if not task.description:
                issues.append(f"{task.id}: missing description")
    if not plan.success_criteria:
        issues.append("plan has no success criteria")
    return {"valid": not issues, "issues": issues}


def validate_code(code_path: str, agent: SubAgent = VALIDATOR) -> Dict[str, object]:
    """Validator subagent: verify files exist and are non-empty."""
    if not os.path.isdir(code_path):
        raise ValueError(f"code path not found: {code_path}")
    files: List[str] = []
    for root, _dirs, names in os.walk(code_path):
        for name in names:
            full = os.path.join(root, name)
            if os.path.isfile(full):
                files.append(os.path.relpath(full, code_path))
    files.sort()
    issues = [f"{f}: empty file" for f in files if os.path.getsize(os.path.join(code_path, f)) == 0]
    passed = bool(files) and not issues
    return {
        "agent": agent.name,
        "context": "isolated",
        "passed": passed,
        "checked": len(files),
        "issues": issues,
        "summary": f"Validator subagent verified {len(files)} files in its own context window.",
    }


# ---------------------------------------------------------------------------
# Subagent runner (research / validation use isolated context windows)
# ---------------------------------------------------------------------------
def research_codebase(codebase_path: str, agent: SubAgent = CODEBASE_ANALYST) -> Dict[str, object]:
    """Codebase-analyst subagent: scan the existing codebase for integration points.

    Runs in its own isolated context window so the heavy research does not
    pollute the primary conversation (the guide: subagents "can do a ton of
    research and then output a summary ... without polluting our primary
    conversation").
    """
    if not os.path.isdir(codebase_path):
        raise ValueError(f"codebase not found: {codebase_path}")
    files: List[str] = []
    for root, _dirs, names in os.walk(codebase_path):
        for name in names:
            full = os.path.join(root, name)
            if os.path.isfile(full):
                files.append(os.path.relpath(full, codebase_path))
    files.sort()
    return {
        "agent": agent.name,
        "context": "isolated",
        "file_count": len(files),
        "files": files,
        "summary": f"Codebase analyst examined {len(files)} files across the repository.",
    }


# ---------------------------------------------------------------------------
# Slash commands (reusable prompt-workflows)
# ---------------------------------------------------------------------------
_PRIMER_TARGETS = {"readme.md", "claude.md", ".cursorrules", ".clinerules"}


def primer_slash_command(
    project_root: Optional[str] = None, key_files: Optional[List[str]] = None
) -> Dict[str, object]:
    """The ``primer`` command: list the files to read to catch the assistant up.

    When starting a new conversation in an existing codebase, the primer "lists
    out instructions for files to read to quickly catch the AI coding assistant
    up to speed on our project."
    """
    files_to_read: List[str] = list(key_files or [])
    if project_root and os.path.isdir(project_root):
        for base in sorted(os.listdir(project_root)):
            if base.lower() in _PRIMER_TARGETS and os.path.isfile(os.path.join(project_root, base)):
                files_to_read.append(base)
    return {
        "command": SLASH_PRIMER,
        "instruction": (
            "Read these files to quickly catch the AI coding assistant up to "
            "speed on the project:"
        ),
        "files_to_read": sorted(set(files_to_read)),
    }


def create_plan_slash_command(requirements_doc: str) -> Dict[str, object]:
    """The ``create_plan`` command: requirements -> full implementation plan."""
    return {
        "command": SLASH_CREATE_PLAN,
        "instruction": "Take the requirements document and produce a full implementation plan.",
        "requirements_doc": requirements_doc,
        "phases": [
            "read and understand the requirements",
            "research (web search for RAG / archon if available)",
            "codebase analysis subagent research",
            "produce the implementation plan task by task",
        ],
    }


def execute_plan_slash_command(plan: WorkflowPlan) -> Dict[str, object]:
    """The ``execute_plan`` command: knock out tasks one by one + validate."""
    return {
        "command": SLASH_EXECUTE_PLAN,
        "instruction": (
            "Execute the predefined workflow, knocking out tasks one by one "
            "(to-do -> doing -> review -> done), then validate the result."
        ),
        "task_count": len(plan.tasks),
        "phases": ["read plan", "analyze the code", "task loop", "validation"],
    }


# ---------------------------------------------------------------------------
# Orchestrator: plan -> implement -> validate
# ---------------------------------------------------------------------------
class CodingWorkflow:
    """End-to-end custom AI coding workflow (plan -> implement -> validate)."""

    def __init__(self, name: str = "default") -> None:
        self.name = name
        self._task_manager: Optional[TaskManager] = None
        self._event_log: List[str] = []

    def plan(
        self,
        feature: str,
        references: Optional[List[str]] = None,
        integration_points: Optional[List[str]] = None,
        is_new_project: bool = True,
    ) -> WorkflowPlan:
        """Planning phase: initial MD -> full plan -> fresh TaskManager."""
        initial_md = build_initial_md(feature, references, integration_points, is_new_project)
        plan = build_plan(initial_md)
        self._task_manager = TaskManager(plan.tasks)
        return plan

    def execute(self) -> bool:
        """Implementation phase: advance each task through the review loop."""
        if self._task_manager is None:
            raise RuntimeError("workflow has not been planned yet")
        while True:
            task = self._task_manager.next()
            if task is None:
                break
            self._task_manager.mark(task.id, TASK_DOING)
            self._task_manager.mark(task.id, TASK_REVIEW)
            self._task_manager.mark(task.id, TASK_DONE)
            self._event_log.append(task.id)
        return self._task_manager.completed

    def run(
        self,
        feature: str,
        references: Optional[List[str]] = None,
        integration_points: Optional[List[str]] = None,
        is_new_project: bool = True,
    ) -> Dict[str, object]:
        """Run the full plan -> implement -> validate pipeline."""
        plan = self.plan(feature, references, integration_points, is_new_project)
        done = self.execute()
        plan_valid = validate_plan(plan)
        return {
            "phases": [PHASE_PLANNING, PHASE_IMPLEMENTATION, PHASE_VALIDATION],
            "plan": plan,
            "tasks_completed": done,
            "plan_valid": plan_valid["valid"],
            "plan_issues": plan_valid["issues"],
        }
