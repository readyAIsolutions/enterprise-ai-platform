"""Pure-stdlib core logic for the ai_coding_workflow enterprise module.

Grounded in ColeMedin's "The True Power of AI Coding - Build Your OWN
Workflows" (https://www.youtube.com/watch?v=mHBk8Z7Exag).

The transcript describes a framework-agnostic, 3-phase AI-coding workflow:

  1. REQUIREMENTS  — capture a free-form requirements document (the "vibe
     planning" step distilled into initial requirements).
  2. PLAN         — a "codebase analyst" research step produces a granular
     implementation plan: an ordered list of tasks, each listing files to
     modify / create, patterns to follow, plus overall success criteria.
  3. EXECUTE      — a task state machine cycles each task, ONE AT A TIME,
     through TODO -> DOING -> REVIEW -> DONE (granular tasks prevent the
     model from hallucinating by doing too much at once).
  4. VALIDATE     — after every task is DONE, a validation step (a sub-agent
     generating tests + a human/AI code-review gate) runs and may send a
     task back to TODO for fixes.
  5. COMPLETE     — validation passed; the workflow is finished.

The engine is deliberately framework-agnostic: it works equally with PRP,
BMAD, the GitHub spec-kit, or plain markdown. The ``framework`` label is
carried purely as metadata and does not change the logic.

No network, no third-party deps — standard library only.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# Supported framework labels (metadata only)
# ---------------------------------------------------------------------------

SUPPORTED_FRAMEWORKS = ("prp", "bmad", "spec_kit", "plain")


class WorkflowError(Exception):
    """Raised on illegal workflow / task operations."""


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class TaskState(Enum):
    """Lifecycle state of a single implementation task."""

    TODO = "todo"
    DOING = "doing"
    REVIEW = "review"
    DONE = "done"
    BLOCKED = "blocked"


class WorkflowPhase(Enum):
    """High-level phase of the overall workflow."""

    REQUIREMENTS = "requirements"
    PLAN = "plan"
    EXECUTE = "execute"
    VALIDATE = "validate"
    COMPLETE = "complete"


# Legal forward transitions for the per-task state machine. Tasks move one
# step at a time; BLOCKED can be reached from active states and recovered.
_LEGAL_TASK_TRANSITIONS: Dict[TaskState, set] = {
    TaskState.TODO: {TaskState.DOING, TaskState.BLOCKED},
    TaskState.DOING: {TaskState.REVIEW, TaskState.BLOCKED},
    TaskState.REVIEW: {TaskState.DONE, TaskState.DOING, TaskState.BLOCKED},
    TaskState.DONE: {TaskState.TODO},  # validation may reopen a task
    TaskState.BLOCKED: {TaskState.TODO, TaskState.DOING},
}

# Natural forward progression used by ``advance_task``.
_ADVANCE_NEXT: Dict[TaskState, TaskState] = {
    TaskState.TODO: TaskState.DOING,
    TaskState.DOING: TaskState.REVIEW,
    TaskState.REVIEW: TaskState.DONE,
}


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass
class Task:
    """A single granular implementation task within a plan."""

    id: str
    description: str
    files_to_modify: List[str] = field(default_factory=list)
    files_to_create: List[str] = field(default_factory=list)
    patterns: List[str] = field(default_factory=list)
    state: TaskState = TaskState.TODO
    notes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "description": self.description,
            "files_to_modify": list(self.files_to_modify),
            "files_to_create": list(self.files_to_create),
            "patterns": list(self.patterns),
            "state": self.state.value,
            "notes": list(self.notes),
        }


@dataclass
class Plan:
    """An ordered implementation plan produced by the PLAN phase."""

    tasks: List[Task] = field(default_factory=list)
    success_criteria: List[str] = field(default_factory=list)
    research_notes: List[str] = field(default_factory=list)

    def task_by_id(self, task_id: str) -> Task:
        for task in self.tasks:
            if task.id == task_id:
                return task
        raise WorkflowError(f"No task with id {task_id!r}")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tasks": [t.to_dict() for t in self.tasks],
            "success_criteria": list(self.success_criteria),
            "research_notes": list(self.research_notes),
        }


@dataclass
class ValidationResult:
    """Outcome of the VALIDATE phase."""

    passed: bool
    generated_tests: List[str] = field(default_factory=list)
    review_findings: List[str] = field(default_factory=list)
    reopened_tasks: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "passed": self.passed,
            "generated_tests": list(self.generated_tests),
            "review_findings": list(self.review_findings),
            "reopened_tasks": list(self.reopened_tasks),
        }


# ---------------------------------------------------------------------------
# Workflow engine
# ---------------------------------------------------------------------------


class WorkflowEngine:
    """Framework-agnostic 3-phase AI-coding workflow engine.

    Enforces phase ordering (REQUIREMENTS -> PLAN -> EXECUTE -> VALIDATE ->
    COMPLETE) and a per-task state machine during EXECUTE.
    """

    def __init__(self, name: str = "workflow", framework: str = "plain") -> None:
        if framework not in SUPPORTED_FRAMEWORKS:
            raise WorkflowError(
                f"Unknown framework {framework!r}; "
                f"expected one of {SUPPORTED_FRAMEWORKS}"
            )
        self.name = name
        self.framework = framework
        self.phase: WorkflowPhase = WorkflowPhase.REQUIREMENTS
        self.requirements: str = ""
        self.plan: Optional[Plan] = None
        self.validation: Optional[ValidationResult] = None

    # -- phase 1: REQUIREMENTS ------------------------------------------------
    def set_requirements(self, text: str) -> None:
        """Capture the requirements document (REQUIREMENTS phase)."""
        if self.phase != WorkflowPhase.REQUIREMENTS:
            raise WorkflowError(
                f"Cannot set requirements in phase {self.phase.value}"
            )
        if not text or not text.strip():
            raise WorkflowError("Requirements text must be non-empty")
        self.requirements = text.strip()
        self.phase = WorkflowPhase.PLAN

    # -- phase 2: PLAN --------------------------------------------------------
    def create_plan(
        self,
        tasks: List[Dict[str, Any]],
        success_criteria: List[str],
        research_notes: Optional[List[str]] = None,
    ) -> Plan:
        """Build the granular implementation plan (PLAN phase).

        ``tasks`` is an ordered list of dicts; each must carry at least an
        ``id`` and ``description``. ``success_criteria`` must be non-empty.
        """
        if self.phase != WorkflowPhase.PLAN:
            raise WorkflowError(
                f"Cannot create plan in phase {self.phase.value}; "
                "set requirements first"
            )
        if not tasks:
            raise WorkflowError("A plan needs at least one task")
        if not success_criteria:
            raise WorkflowError("A plan needs at least one success criterion")

        built: List[Task] = []
        seen: set = set()
        for spec in tasks:
            tid = str(spec.get("id") or "").strip()
            desc = str(spec.get("description") or "").strip()
            if not tid:
                raise WorkflowError("Every task needs an id")
            if not desc:
                raise WorkflowError(f"Task {tid!r} needs a description")
            if tid in seen:
                raise WorkflowError(f"Duplicate task id {tid!r}")
            seen.add(tid)
            built.append(
                Task(
                    id=tid,
                    description=desc,
                    files_to_modify=list(spec.get("files_to_modify", [])),
                    files_to_create=list(spec.get("files_to_create", [])),
                    patterns=list(spec.get("patterns", [])),
                )
            )

        self.plan = Plan(
            tasks=built,
            success_criteria=list(success_criteria),
            research_notes=list(research_notes or []),
        )
        self.phase = WorkflowPhase.EXECUTE
        return self.plan

    # -- phase 3: EXECUTE -----------------------------------------------------
    def _require_execute(self) -> Plan:
        if self.phase != WorkflowPhase.EXECUTE:
            raise WorkflowError(
                f"Task operations require EXECUTE phase, not {self.phase.value}"
            )
        assert self.plan is not None  # guaranteed by phase invariant
        return self.plan

    def next_task(self) -> Optional[Task]:
        """Return the next TODO task (ordered), or None if none remain."""
        if self.plan is None:
            return None
        for task in self.plan.tasks:
            if task.state == TaskState.TODO:
                return task
        return None

    def start_task(self, task_id: Optional[str] = None) -> Task:
        """Move a task from TODO to DOING. Only one task at a time.

        If ``task_id`` is omitted, the next TODO task is started. Refuses to
        start a task while another is already DOING or REVIEW.
        """
        plan = self._require_execute()
        active = [
            t for t in plan.tasks if t.state in (TaskState.DOING, TaskState.REVIEW)
        ]
        if active:
            raise WorkflowError(
                f"Task {active[0].id!r} is already in progress; "
                "finish it before starting another"
            )
        task = plan.task_by_id(task_id) if task_id else self.next_task()
        if task is None:
            raise WorkflowError("No TODO task available to start")
        self._transition(task, TaskState.DOING)
        return task

    def advance_task(self, task_id: str) -> Task:
        """Advance a task one legal step along TODO->DOING->REVIEW->DONE."""
        plan = self._require_execute()
        task = plan.task_by_id(task_id)
        nxt = _ADVANCE_NEXT.get(task.state)
        if nxt is None:
            raise WorkflowError(
                f"Task {task_id!r} in state {task.state.value} cannot advance"
            )
        self._transition(task, nxt)
        return task

    def set_task_state(self, task_id: str, new_state: TaskState) -> Task:
        """Explicitly transition a task, enforcing legal transitions."""
        plan = self._require_execute()
        task = plan.task_by_id(task_id)
        self._transition(task, new_state)
        return task

    def block_task(self, task_id: str, reason: str = "") -> Task:
        """Mark a task BLOCKED, recording an optional reason."""
        plan = self._require_execute()
        task = plan.task_by_id(task_id)
        self._transition(task, TaskState.BLOCKED)
        if reason:
            task.notes.append(f"blocked: {reason}")
        return task

    def _transition(self, task: Task, new_state: TaskState) -> None:
        if new_state == task.state:
            raise WorkflowError(
                f"Task {task.id!r} is already in state {new_state.value}"
            )
        legal = _LEGAL_TASK_TRANSITIONS.get(task.state, set())
        if new_state not in legal:
            raise WorkflowError(
                f"Illegal transition {task.state.value} -> {new_state.value} "
                f"for task {task.id!r}"
            )
        task.state = new_state

    def all_tasks_done(self) -> bool:
        if self.plan is None or not self.plan.tasks:
            return False
        return all(t.state == TaskState.DONE for t in self.plan.tasks)

    # -- phase 4: VALIDATE ----------------------------------------------------
    def validate(
        self,
        generated_tests: Optional[List[str]] = None,
        review_findings: Optional[List[str]] = None,
    ) -> ValidationResult:
        """Run the validation gate.

        Only passes when every task is DONE and success criteria are
        recorded. Any ``review_findings`` constitute a failing code review
        that reopens all DONE tasks back to TODO for fixes (the human
        "don't vibe-code" gate).
        """
        if self.phase not in (WorkflowPhase.EXECUTE, WorkflowPhase.VALIDATE):
            raise WorkflowError(
                f"Cannot validate in phase {self.phase.value}"
            )
        if self.plan is None:
            raise WorkflowError("No plan to validate")

        self.phase = WorkflowPhase.VALIDATE
        findings = list(review_findings or [])

        if not self.all_tasks_done():
            result = ValidationResult(
                passed=False,
                generated_tests=list(generated_tests or []),
                review_findings=findings
                or ["validation blocked: not all tasks are DONE"],
            )
            self.validation = result
            return result

        if not self.plan.success_criteria:
            result = ValidationResult(
                passed=False,
                generated_tests=list(generated_tests or []),
                review_findings=findings or ["no success criteria recorded"],
            )
            self.validation = result
            return result

        if findings:
            # Code review failed: send every task back to TODO for fixes.
            reopened: List[str] = []
            for task in self.plan.tasks:
                if task.state == TaskState.DONE:
                    task.state = TaskState.TODO
                    task.notes.append("reopened by validation")
                    reopened.append(task.id)
            self.phase = WorkflowPhase.EXECUTE
            result = ValidationResult(
                passed=False,
                generated_tests=list(generated_tests or []),
                review_findings=findings,
                reopened_tasks=reopened,
            )
            self.validation = result
            return result

        # Everything passed.
        result = ValidationResult(
            passed=True,
            generated_tests=list(generated_tests or []),
            review_findings=[],
        )
        self.validation = result
        self.phase = WorkflowPhase.COMPLETE
        return result

    # -- reporting ------------------------------------------------------------
    def progress(self) -> Dict[str, int]:
        """Return task counts per state."""
        counts = {state.value: 0 for state in TaskState}
        if self.plan is not None:
            for task in self.plan.tasks:
                counts[task.state.value] += 1
        return counts

    def summary(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "framework": self.framework,
            "phase": self.phase.value,
            "has_requirements": bool(self.requirements),
            "task_count": len(self.plan.tasks) if self.plan else 0,
            "progress": self.progress(),
            "validated": bool(self.validation and self.validation.passed),
        }

    def render(self) -> str:
        """Human-readable multi-line rendering of the workflow."""
        lines = [
            f"Workflow: {self.name} [{self.framework}]",
            f"Phase: {self.phase.value}",
        ]
        if self.requirements:
            first = self.requirements.splitlines()[0]
            lines.append(f"Requirements: {first}")
        if self.plan is not None:
            lines.append("Tasks:")
            for i, task in enumerate(self.plan.tasks, 1):
                lines.append(f"  {i}. [{task.state.value}] {task.id}: {task.description}")
            lines.append("Success criteria:")
            for crit in self.plan.success_criteria:
                lines.append(f"  - {crit}")
        if self.validation is not None:
            status = "PASSED" if self.validation.passed else "FAILED"
            lines.append(f"Validation: {status}")
        return "\n".join(lines)


__all__ = [
    "SUPPORTED_FRAMEWORKS",
    "WorkflowError",
    "TaskState",
    "WorkflowPhase",
    "Task",
    "Plan",
    "ValidationResult",
    "WorkflowEngine",
]
