"""Workflow Forge — Composable AI-Coding Workflow System

A pure-stdlib, network-free implementation of the composable workflow philosophy
taught in Cole Medin's "The True Power of AI Coding - Build Your OWN Workflows"
(mHBk8Z7Exag).

Core primitives (from transcript):
  1. Global Rules/Context (claude.md-style) — persistent instructions
  2. Planning/Spec Creation (PRP = Product Requirements Prompt) — detailed plan from requirements
  3. Task Breakdown — granular, ordered tasks from the plan
  4. Implementation — guided execution, one task at a time
  5. Validation/Review Gates — verify output against success criteria

This module models these as composable phases that can be assembled into
reusable workflows, generating deterministic structured plans (PRP-style)
from feature requests without any LLM calls.
"""

from __future__ import annotations

import asyncio
import json
import textwrap
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any, Callable


class PhaseKind(Enum):
    """Fundamental workflow phase types derived from the transcript."""

    RULES = "rules"          # Global rules/context (claude.md)
    PLAN = "plan"            # Planning / spec creation (PRP)
    TASKS = "tasks"          # Task breakdown
    IMPLEMENT = "implement"  # Implementation
    VALIDATE = "validate"    # Validation / review gates


class TaskStatus(Enum):
    """Status of a discrete task within the workflow."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class ValidationResult(Enum):
    """Outcome of a validation gate."""

    PASS = "pass"
    FAIL = "fail"
    WARNING = "warning"


@dataclass(slots=True)
class WorkflowPhase:
    """A single phase in a composable workflow.

    Each phase has a kind (rules/plan/tasks/implement/validate), a name,
    optional description, and arbitrary configuration data.
    """

    name: str
    kind: PhaseKind
    description: str = ""
    config: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if isinstance(self.kind, str):
            self.kind = PhaseKind(self.kind)


@dataclass(slots=True)
class WorkflowTask:
    """A discrete, granular task derived from the plan phase.

    Tasks are the atomic units of work during implementation.
    """

    id: str
    title: str
    description: str = ""
    phase: str = "implement"
    status: TaskStatus = TaskStatus.PENDING
    dependencies: list[str] = field(default_factory=list)
    acceptance_criteria: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    started_at: datetime | None = None
    completed_at: datetime | None = None

    def mark_in_progress(self) -> None:
        self.status = TaskStatus.IN_PROGRESS
        self.started_at = datetime.now(UTC)

    def mark_completed(self) -> None:
        self.status = TaskStatus.COMPLETED
        self.completed_at = datetime.now(UTC)

    def mark_failed(self) -> None:
        self.status = TaskStatus.FAILED
        self.completed_at = datetime.now(UTC)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "phase": self.phase,
            "status": self.status.value,
            "dependencies": self.dependencies,
            "acceptance_criteria": self.acceptance_criteria,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }


@dataclass(slots=True)
class ValidationGate:
    """A validation check that runs against implementation output.

    Gates embody the "review" concept from the transcript — checking
    success criteria, code quality, test coverage, etc.
    """

    name: str
    description: str
    check_fn: str  # Name of the check function (for serialization)
    severity: str = "error"  # "error" | "warning"
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ValidationReport:
    """Result of running validation gates."""

    gate_name: str
    result: ValidationResult
    message: str
    details: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_dict(self) -> dict[str, Any]:
        return {
            "gate_name": self.gate_name,
            "result": self.result.value,
            "message": self.message,
            "details": self.details,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass(slots=True)
class WorkflowPlan:
    """A structured PRP-style plan generated from a feature request.

    This is the deterministic text template output — no LLM involved.
    Mirrors the PRP structure described in the transcript:
    - Feature overview
    - Goals & success criteria
    - Task breakdown
    - Codebase structure / integration points
    - Documentation references
    - Validation gates
    """

    feature_request: str
    overview: str
    goals: list[str]
    success_criteria: list[str]
    tasks: list[WorkflowTask]
    integration_points: list[str] = field(default_factory=list)
    documentation_refs: list[str] = field(default_factory=list)
    validation_gates: list[ValidationGate] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    generated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_markdown(self) -> str:
        """Render the plan as a PRP-style markdown document."""
        lines = [
            f"# PRP: {self.feature_request}",
            "",
            "## Overview",
            self.overview,
            "",
            "## Goals",
            *[f"- {g}" for g in self.goals],
            "",
            "## Success Criteria",
            *[f"- {c}" for c in self.success_criteria],
            "",
            "## Tasks",
        ]
        for i, task in enumerate(self.tasks, 1):
            lines.append(f"### Task {i}: {task.title}")
            if task.description:
                lines.append(f"{task.description}")
            if task.acceptance_criteria:
                lines.append("**Acceptance Criteria:**")
                for ac in task.acceptance_criteria:
                    lines.append(f"- {ac}")
            lines.append("")

        if self.integration_points:
            lines.append("## Integration Points")
            lines.extend(f"- {p}" for p in self.integration_points)
            lines.append("")

        if self.documentation_refs:
            lines.append("## Documentation References")
            lines.extend(f"- {r}" for r in self.documentation_refs)
            lines.append("")

        if self.validation_gates:
            lines.append("## Validation Gates")
            for gate in self.validation_gates:
                lines.append(f"- **{gate.name}** ({gate.severity}): {gate.description}")
            lines.append("")

        return "\n".join(lines)

    def to_json(self) -> str:
        return json.dumps(
            {
                "feature_request": self.feature_request,
                "overview": self.overview,
                "goals": self.goals,
                "success_criteria": self.success_criteria,
                "tasks": [t.to_dict() for t in self.tasks],
                "integration_points": self.integration_points,
                "documentation_refs": self.documentation_refs,
                "validation_gates": [
                    {
                        "name": g.name,
                        "description": g.description,
                        "check_fn": g.check_fn,
                        "severity": g.severity,
                        "metadata": g.metadata,
                    }
                    for g in self.validation_gates
                ],
                "metadata": self.metadata,
                "generated_at": self.generated_at.isoformat(),
            },
            indent=2,
        )


class Workflow:
    """An ordered sequence of WorkflowPhases representing a complete workflow."""

    def __init__(self, name: str, phases: list[WorkflowPhase] | None = None) -> None:
        self.name = name
        self._phases: list[WorkflowPhase] = phases or []
        self._lock = threading.RLock()
        self.created_at = datetime.now(UTC)
        self.id = str(uuid.uuid4())[:8]

    def add_phase(self, phase: WorkflowPhase) -> None:
        with self._lock:
            self._phases.append(phase)

    def remove_phase(self, name: str) -> bool:
        with self._lock:
            for i, p in enumerate(self._phases):
                if p.name == name:
                    self._phases.pop(i)
                    return True
            return False

    def get_phase(self, name: str) -> WorkflowPhase | None:
        with self._lock:
            for p in self._phases:
                if p.name == name:
                    return p
            return None

    def get_phases_by_kind(self, kind: PhaseKind) -> list[WorkflowPhase]:
        with self._lock:
            return [p for p in self._phases if p.kind == kind]

    @property
    def phases(self) -> list[WorkflowPhase]:
        with self._lock:
            return list(self._phases)

    def __len__(self) -> int:
        with self._lock:
            return len(self._phases)

    def __iter__(self):
        with self._lock:
            return iter(self._phases)

    def __repr__(self) -> str:
        phase_names = [f"{p.name}({p.kind.value})" for p in self._phases]
        return f"Workflow({self.name} [{', '.join(phase_names)}])"


class WorkflowForge:
    """Builder / factory for composing workflows and generating plans.

    This is the main entry point. It provides:
    - Preset workflow templates (standard 5-phase AI coding workflow)
    - Plan generation from feature requests (deterministic template)
    - Task breakdown from plans
    - Validation gate execution
    """

    # Built-in validation check functions (registered by name)
    _VALIDATORS: dict[str, Callable] = {}

    def __init__(self) -> None:
        self._custom_validators: dict[str, Callable] = {}

    @classmethod
    def register_validator(cls, name: str, fn: Callable) -> None:
        """Register a custom validation function by name."""
        cls._VALIDATORS[name] = fn

    def register_instance_validator(self, name: str, fn: Callable) -> None:
        """Register a validation function on this instance only."""
        self._custom_validators[name] = fn

    def _get_validator(self, name: str) -> Callable | None:
        return self._custom_validators.get(name) or self._VALIDATORS.get(name)

    # ── Preset Workflows ────────────────────────────────────────────────

    @classmethod
    def standard_ai_coding_workflow(cls, name: str = "standard_ai_coding") -> Workflow:
        """Create the standard 5-phase AI coding workflow from the transcript.

        Phases:
        1. rules      — Global rules/context (claude.md-style)
        2. plan       — Planning / spec creation (PRP)
        3. tasks      — Task breakdown
        4. implement  — Implementation
        5. validate   — Validation / review gates
        """
        return Workflow(
            name=name,
            phases=[
                WorkflowPhase(
                    name="global_rules",
                    kind=PhaseKind.RULES,
                    description="Persistent global rules and context (claude.md-style)",
                    config={"source": "claude.md", "auto_load": True},
                ),
                WorkflowPhase(
                    name="planning",
                    kind=PhaseKind.PLAN,
                    description="Create detailed PRP-style specification from requirements",
                    config={"template": "prp", "include_rag": True},
                ),
                WorkflowPhase(
                    name="task_breakdown",
                    kind=PhaseKind.TASKS,
                    description="Break the plan into discrete, ordered tasks",
                    config={"granularity": "fine", "include_acceptance": True},
                ),
                WorkflowPhase(
                    name="implementation",
                    kind=PhaseKind.IMPLEMENT,
                    description="Execute tasks one by one with guided workflow",
                    config={"mode": "sequential", "context_window_aware": True},
                ),
                WorkflowPhase(
                    name="validation",
                    kind=PhaseKind.VALIDATE,
                    description="Run validation gates and review against success criteria",
                    config={"gates": ["syntax", "tests", "criteria"], "fail_fast": False},
                ),
            ],
        )

    @classmethod
    def minimal_workflow(cls, name: str = "minimal") -> Workflow:
        """Create a minimal 3-phase workflow (plan → tasks → implement)."""
        return Workflow(
            name=name,
            phases=[
                WorkflowPhase(
                    name="planning",
                    kind=PhaseKind.PLAN,
                    description="Create specification from requirements",
                ),
                WorkflowPhase(
                    name="task_breakdown",
                    kind=PhaseKind.TASKS,
                    description="Break into discrete tasks",
                ),
                WorkflowPhase(
                    name="implementation",
                    kind=PhaseKind.IMPLEMENT,
                    description="Execute tasks",
                ),
            ],
        )

    @classmethod
    def planning_only_workflow(cls, name: str = "planning_only") -> Workflow:
        """Create a workflow focused only on planning and task breakdown."""
        return Workflow(
            name=name,
            phases=[
                WorkflowPhase(
                    name="global_rules",
                    kind=PhaseKind.RULES,
                    description="Load global context",
                ),
                WorkflowPhase(
                    name="planning",
                    kind=PhaseKind.PLAN,
                    description="Create detailed PRP",
                ),
                WorkflowPhase(
                    name="task_breakdown",
                    kind=PhaseKind.TASKS,
                    description="Generate task list",
                ),
            ],
        )

    # ── Plan Generation ────────────────────────────────────────────────

    def generate_plan(
        self,
        feature_request: str,
        context: dict[str, Any] | None = None,
        template: str = "prp",
    ) -> WorkflowPlan:
        """Generate a deterministic PRP-style plan from a feature request.

        No LLM calls — purely template-driven using the provided context.
        This mirrors the "initial MD → detailed PRP" process from the transcript.
        """
        ctx = context or {}

        # Extract or infer goals from the request
        goals = self._infer_goals(feature_request, ctx)
        success_criteria = self._infer_success_criteria(feature_request, ctx)
        integration_points = ctx.get("integration_points", [])
        documentation_refs = ctx.get("documentation_refs", [])

        # Generate tasks from the goals
        tasks = self._breakdown_into_tasks(goals, success_criteria, ctx)

        # Default validation gates
        validation_gates = [
            ValidationGate(
                name="syntax_check",
                description="Verify code syntax is valid",
                check_fn="validate_syntax",
                severity="error",
            ),
            ValidationGate(
                name="test_execution",
                description="Run project test suite",
                check_fn="validate_tests",
                severity="error",
            ),
            ValidationGate(
                name="criteria_match",
                description="Verify implementation meets success criteria",
                check_fn="validate_criteria",
                severity="error",
            ),
        ]

        # Add any custom gates from context
        for gate_cfg in ctx.get("validation_gates", []):
            validation_gates.append(
                ValidationGate(
                    name=gate_cfg.get("name", "custom"),
                    description=gate_cfg.get("description", ""),
                    check_fn=gate_cfg.get("check_fn", "validate_custom"),
                    severity=gate_cfg.get("severity", "warning"),
                    metadata=gate_cfg.get("metadata", {}),
                )
            )

        plan = WorkflowPlan(
            feature_request=feature_request,
            overview=self._generate_overview(feature_request, ctx),
            goals=goals,
            success_criteria=success_criteria,
            tasks=tasks,
            integration_points=integration_points,
            documentation_refs=documentation_refs,
            validation_gates=validation_gates,
            metadata={"template": template, "context_keys": list(ctx.keys())},
        )
        return plan

    def _infer_goals(self, request: str, ctx: dict[str, Any]) -> list[str]:
        """Infer high-level goals from the feature request."""
        goals = ctx.get("goals", [])
        if goals:
            return goals

        # Simple heuristic: split by common delimiters
        base_goals = [
            f"Implement core functionality for: {request[:80]}...",
            "Ensure code follows project conventions and patterns",
            "Write comprehensive tests",
            "Document the implementation",
        ]
        return base_goals

    def _infer_success_criteria(self, request: str, ctx: dict[str, Any]) -> list[str]:
        """Infer success criteria from the feature request."""
        criteria = ctx.get("success_criteria", [])
        if criteria:
            return criteria

        return [
            "All tests pass",
            "Code follows project style guide",
            "No regressions introduced",
            "Feature works as described in request",
            "Documentation updated",
        ]

    def _generate_overview(self, request: str, ctx: dict[str, Any]) -> str:
        """Generate a plan overview from the request and context."""
        overview = ctx.get("overview", "")
        if overview:
            return overview

        return textwrap.dedent(f"""
        This plan addresses the feature request: "{request}"

        The implementation follows the standard AI coding workflow:
        1. Establish global rules and context
        2. Create a detailed specification (PRP)
        3. Break down into granular tasks
        4. Implement tasks sequentially
        5. Validate against success criteria

        Context: {json.dumps(ctx, indent=2) if ctx else 'None provided'}
        """).strip()

    def _breakdown_into_tasks(
        self,
        goals: list[str],
        criteria: list[str],
        ctx: dict[str, Any],
    ) -> list[WorkflowTask]:
        """Break goals and criteria into discrete tasks."""
        tasks = []
        task_id = 0

        # Task for each goal
        for goal in goals:
            task_id += 1
            tasks.append(
                WorkflowTask(
                    id=f"task-{task_id:03d}",
                    title=goal[:80],
                    description=goal,
                    phase="implement",
                    acceptance_criteria=[c for c in criteria if any(w in c.lower() for w in goal.lower().split())][:2] or criteria[:2],
                )
            )

        # Add standard tasks if none from goals
        if not tasks:
            standard_tasks = [
                ("Setup & Configuration", "Configure project structure and dependencies"),
                ("Core Implementation", "Implement the main feature logic"),
                ("Testing", "Write and run tests"),
                ("Documentation", "Update documentation"),
                ("Review & Cleanup", "Code review and cleanup"),
            ]
            for title, desc in standard_tasks:
                task_id += 1
                tasks.append(
                    WorkflowTask(
                        id=f"task-{task_id:03d}",
                        title=title,
                        description=desc,
                        phase="implement",
                        acceptance_criteria=criteria[:2],
                    )
                )

        return tasks

    # ── Task Management ────────────────────────────────────────────────

    def get_next_task(self, tasks: list[WorkflowTask]) -> WorkflowTask | None:
        """Get the next pending task whose dependencies are satisfied."""
        for task in tasks:
            if task.status != TaskStatus.PENDING:
                continue
            deps_satisfied = all(
                any(t.id == dep and t.status == TaskStatus.COMPLETED for t in tasks)
                for dep in task.dependencies
            )
            if deps_satisfied:
                return task
        return None

    def execute_task(self, task: WorkflowTask, executor: Callable) -> bool:
        """Execute a single task with the provided executor function.

        Args:
            task: The task to execute
            executor: Callable(task) -> bool (True on success)

        Returns:
            True if task succeeded, False otherwise
        """
        task.mark_in_progress()
        try:
            success = executor(task)
            if success:
                task.mark_completed()
            else:
                task.mark_failed()
            return success
        except Exception:
            task.mark_failed()
            return False

    # ── Validation Gates ────────────────────────────────────────────────

    def run_validation_gates(
        self,
        plan: WorkflowPlan,
        artifacts: dict[str, Any] | None = None,
    ) -> list[ValidationReport]:
        """Run all validation gates defined in the plan against artifacts.

        Args:
            plan: The workflow plan containing validation gates
            artifacts: Implementation artifacts (files, test results, etc.)

        Returns:
            List of ValidationReport results
        """
        artifacts = artifacts or {}
        reports = []

        for gate in plan.validation_gates:
            validator = self._get_validator(gate.check_fn)
            if validator is None:
                reports.append(
                    ValidationReport(
                        gate_name=gate.name,
                        result=ValidationResult.WARNING,
                        message=f"No validator registered for '{gate.check_fn}'",
                        details={"gate": gate.name, "missing_validator": gate.check_fn},
                    )
                )
                continue

            try:
                result = validator(artifacts, gate.metadata)
                if isinstance(result, tuple):
                    passed, message, details = result
                else:
                    passed = bool(result)
                    message = "Validation passed" if passed else "Validation failed"
                    details = {}

                reports.append(
                    ValidationReport(
                        gate_name=gate.name,
                        result=ValidationResult.PASS if passed else ValidationResult.FAIL,
                        message=message,
                        details=details,
                    )
                )
            except Exception as e:
                reports.append(
                    ValidationReport(
                        gate_name=gate.name,
                        result=ValidationResult.FAIL,
                        message=f"Validator raised exception: {e}",
                        details={"exception": str(e)},
                    )
                )

        return reports

    def all_gates_passed(self, reports: list[ValidationReport]) -> bool:
        """Check if all error-severity gates passed."""
        return all(
            r.result != ValidationResult.FAIL
            for r in reports
        )

    # ── Serialization ────────────────────────────────────────────────

    def workflow_to_dict(self, workflow: Workflow) -> dict[str, Any]:
        """Serialize a workflow to a dictionary."""
        return {
            "id": workflow.id,
            "name": workflow.name,
            "created_at": workflow.created_at.isoformat(),
            "phases": [
                {
                    "name": p.name,
                    "kind": p.kind.value,
                    "description": p.description,
                    "config": p.config,
                }
                for p in workflow.phases
            ],
        }

    def plan_to_dict(self, plan: WorkflowPlan) -> dict[str, Any]:
        """Serialize a plan to a dictionary."""
        return json.loads(plan.to_json())

    def save_workflow(self, workflow: Workflow, path: str) -> None:
        """Save a workflow to a JSON file."""
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.workflow_to_dict(workflow), f, indent=2)

    def save_plan(self, plan: WorkflowPlan, path: str) -> None:
        """Save a plan to a JSON file."""
        with open(path, "w", encoding="utf-8") as f:
            f.write(plan.to_json())

    def load_workflow(self, path: str) -> Workflow:
        """Load a workflow from a JSON file."""
        with open(path, encoding="utf-8") as f:
            data = json.load(f)

        workflow = Workflow(name=data["name"])
        workflow.id = data.get("id", workflow.id)
        workflow.created_at = datetime.fromisoformat(data["created_at"])

        for phase_data in data["phases"]:
            workflow.add_phase(
                WorkflowPhase(
                    name=phase_data["name"],
                    kind=PhaseKind(phase_data["kind"]),
                    description=phase_data.get("description", ""),
                    config=phase_data.get("config", {}),
                )
            )
        return workflow


# ── Default Validators ────────────────────────────────────────────────

def validate_syntax(artifacts: dict[str, Any], metadata: dict[str, Any]) -> tuple[bool, str, dict[str, Any]]:
    """Validate Python syntax of code artifacts."""
    code = artifacts.get("code", "")
    if not code:
        return False, "No code artifact provided", {"has_code": False}

    try:
        compile(code, "<string>", "exec")
        return True, "Syntax valid", {"has_code": True}
    except SyntaxError as e:
        return False, f"Syntax error: {e.msg} at line {e.lineno}", {"error": str(e)}


def validate_tests(artifacts: dict[str, Any], metadata: dict[str, Any]) -> tuple[bool, str, dict[str, Any]]:
    """Validate that tests pass (placeholder - would run actual test suite)."""
    test_results = artifacts.get("test_results", {})
    passed = test_results.get("passed", 0)
    failed = test_results.get("failed", 0)
    total = passed + failed

    if total == 0:
        return False, "No tests executed", {"passed": 0, "failed": 0, "total": 0}

    success = failed == 0
    return success, f"Tests: {passed}/{total} passed", {"passed": passed, "failed": failed, "total": total}


def validate_criteria(artifacts: dict[str, Any], metadata: dict[str, Any]) -> tuple[bool, str, dict[str, Any]]:
    """Validate that success criteria are met (placeholder)."""
    criteria_met = artifacts.get("criteria_met", [])
    criteria_total = artifacts.get("criteria_total", len(criteria_met) + 1)

    if criteria_total == 0:
        return True, "No criteria defined", {"met": 0, "total": 0}

    success = len(criteria_met) == criteria_total
    return success, f"Criteria: {len(criteria_met)}/{criteria_total} met", {"met": len(criteria_met), "total": criteria_total}


# Register default validators
WorkflowForge.register_validator("validate_syntax", validate_syntax)
WorkflowForge.register_validator("validate_tests", validate_tests)
WorkflowForge.register_validator("validate_criteria", validate_criteria)


# ── Convenience Functions ────────────────────────────────────────────

async def run_workflow_async(
    forge: WorkflowForge,
    workflow: Workflow,
    feature_request: str,
    context: dict[str, Any] | None = None,
    executor: Callable | None = None,
) -> tuple[WorkflowPlan, list[WorkflowTask], list[ValidationReport]]:
    """Run a complete workflow asynchronously.

    Returns:
        Tuple of (plan, tasks, validation_reports)
    """
    # Generate plan
    plan = forge.generate_plan(feature_request, context)

    # Execute tasks if executor provided
    tasks = plan.tasks
    if executor:
        for task in tasks:
            next_task = forge.get_next_task(tasks)
            if next_task is None:
                break
            # Run in thread pool to avoid blocking
            await asyncio.to_thread(forge.execute_task, next_task, executor)

    # Run validation gates
    artifacts = {"code": context.get("code", "") if context else "", "test_results": context.get("test_results", {}) if context else {}}
    reports = forge.run_validation_gates(plan, artifacts)

    return plan, tasks, reports