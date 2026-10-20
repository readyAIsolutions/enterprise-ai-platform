"""Tests for Workflow Forge module.

Tests cover:
- Building workflows from presets
- Generating plans from feature requests
- Task breakdown and management
- Validation gates
- Async module lifecycle (initialize -> health_check -> shutdown)
"""

import asyncio
import json
import tempfile
from pathlib import Path

import pytest

from enterprise.modules.workflow_forge import (
    PhaseKind,
    TaskStatus,
    ValidationResult,
    WorkflowPhase,
    WorkflowTask,
    ValidationGate,
    ValidationReport,
    WorkflowPlan,
    Workflow,
    WorkflowForge,
    WorkflowForgeModule,
    run_workflow_async,
    create_workflow_forge_module,
)
from enterprise.platform_kernel import HealthStatus


# ── Fixtures ───────────────────────────────────────────────────────────────

@pytest.fixture
def forge() -> WorkflowForge:
    return WorkflowForge()


@pytest.fixture
def standard_workflow() -> Workflow:
    return WorkflowForge.standard_ai_coding_workflow()


@pytest.fixture
def minimal_workflow() -> Workflow:
    return WorkflowForge.minimal_workflow()


@pytest.fixture
async def module_instance() -> WorkflowForgeModule:
    """Create and initialize a module instance."""
    module = create_workflow_forge_module()
    await module.initialize()
    yield module
    await module.shutdown()


# ── Workflow Construction Tests ────────────────────────────────────────────

def test_standard_workflow_has_five_phases(standard_workflow: Workflow) -> None:
    """Standard workflow should have exactly 5 phases in correct order."""
    assert len(standard_workflow) == 5

    phase_kinds = [p.kind for p in standard_workflow.phases]
    expected = [
        PhaseKind.RULES,
        PhaseKind.PLAN,
        PhaseKind.TASKS,
        PhaseKind.IMPLEMENT,
        PhaseKind.VALIDATE,
    ]
    assert phase_kinds == expected


def test_standard_workflow_phase_names(standard_workflow: Workflow) -> None:
    """Standard workflow phases should have expected names."""
    names = [p.name for p in standard_workflow.phases]
    assert names == [
        "global_rules",
        "planning",
        "task_breakdown",
        "implementation",
        "validation",
    ]


def test_minimal_workflow_has_three_phases(minimal_workflow: Workflow) -> None:
    """Minimal workflow should have exactly 3 phases."""
    assert len(minimal_workflow) == 3
    phase_kinds = [p.kind for p in minimal_workflow.phases]
    assert phase_kinds == [PhaseKind.PLAN, PhaseKind.TASKS, PhaseKind.IMPLEMENT]


def test_planning_only_workflow() -> None:
    """Planning-only workflow should have rules, plan, tasks phases."""
    wf = WorkflowForge.planning_only_workflow()
    assert len(wf) == 3
    phase_kinds = [p.kind for p in wf.phases]
    assert phase_kinds == [PhaseKind.RULES, PhaseKind.PLAN, PhaseKind.TASKS]


def test_workflow_add_remove_phase() -> None:
    """Should be able to add and remove phases dynamically."""
    wf = Workflow("test")
    assert len(wf) == 0

    phase = WorkflowPhase(name="custom", kind=PhaseKind.PLAN, description="Custom phase")
    wf.add_phase(phase)
    assert len(wf) == 1
    assert wf.get_phase("custom") is not None

    removed = wf.remove_phase("custom")
    assert removed is True
    assert len(wf) == 0
    assert wf.get_phase("custom") is None

    # Removing non-existent returns False
    assert wf.remove_phase("nonexistent") is False


def test_workflow_get_phases_by_kind() -> None:
    """Should filter phases by kind."""
    wf = WorkflowForge.standard_ai_coding_workflow()
    plan_phases = wf.get_phases_by_kind(PhaseKind.PLAN)
    assert len(plan_phases) == 1
    assert plan_phases[0].name == "planning"


# ── Plan Generation Tests ──────────────────────────────────────────────────

def test_generate_plan_basic(forge: WorkflowForge) -> None:
    """Should generate a plan from a feature request."""
    plan = forge.generate_plan("Add user authentication")

    assert isinstance(plan, WorkflowPlan)
    assert plan.feature_request == "Add user authentication"
    assert plan.overview
    assert len(plan.goals) > 0
    assert len(plan.success_criteria) > 0
    assert len(plan.tasks) > 0
    assert len(plan.validation_gates) >= 3  # syntax, tests, criteria


def test_generate_plan_with_context(forge: WorkflowForge) -> None:
    """Should incorporate context into generated plan."""
    context = {
        "goals": ["Custom goal 1", "Custom goal 2"],
        "success_criteria": ["Custom criterion"],
        "integration_points": ["auth_service", "user_db"],
        "documentation_refs": ["API.md", "ARCHITECTURE.md"],
    }
    plan = forge.generate_plan("Add user authentication", context=context)

    assert plan.goals == ["Custom goal 1", "Custom goal 2"]
    assert plan.success_criteria == ["Custom criterion"]
    assert plan.integration_points == ["auth_service", "user_db"]
    assert plan.documentation_refs == ["API.md", "ARCHITECTURE.md"]


def test_plan_to_markdown(forge: WorkflowForge) -> None:
    """Plan should render to PRP-style markdown."""
    plan = forge.generate_plan("Test feature")
    md = plan.to_markdown()

    assert "# PRP: Test feature" in md
    assert "## Overview" in md
    assert "## Goals" in md
    assert "## Success Criteria" in md
    assert "## Tasks" in md


def test_plan_to_json(forge: WorkflowForge) -> None:
    """Plan should serialize to valid JSON."""
    plan = forge.generate_plan("Test feature")
    json_str = plan.to_json()
    data = json.loads(json_str)

    assert data["feature_request"] == "Test feature"
    assert "goals" in data
    assert "tasks" in data
    assert isinstance(data["tasks"], list)


def test_plan_tasks_have_unique_ids(forge: WorkflowForge) -> None:
    """Generated tasks should have unique IDs."""
    plan = forge.generate_plan("Feature with many goals", context={
        "goals": [f"Goal {i}" for i in range(10)]
    })
    task_ids = [t.id for t in plan.tasks]
    assert len(task_ids) == len(set(task_ids))


# ── Task Management Tests ──────────────────────────────────────────────────

def test_task_lifecycle() -> None:
    """Task should transition through statuses correctly."""
    task = WorkflowTask(
        id="task-001",
        title="Test task",
        description="A test task",
    )

    assert task.status == TaskStatus.PENDING
    assert task.started_at is None
    assert task.completed_at is None

    task.mark_in_progress()
    assert task.status == TaskStatus.IN_PROGRESS
    assert task.started_at is not None

    task.mark_completed()
    assert task.status == TaskStatus.COMPLETED
    assert task.completed_at is not None


def test_task_mark_failed() -> None:
    """Failed task should have completed_at set."""
    task = WorkflowTask(id="task-001", title="Test")
    task.mark_failed()
    assert task.status == TaskStatus.FAILED
    assert task.completed_at is not None


def test_task_to_dict() -> None:
    """Task should serialize to dictionary."""
    task = WorkflowTask(
        id="task-001",
        title="Test",
        description="Desc",
        acceptance_criteria=["AC1", "AC2"],
    )
    d = task.to_dict()

    assert d["id"] == "task-001"
    assert d["title"] == "Test"
    assert d["status"] == "pending"
    assert d["acceptance_criteria"] == ["AC1", "AC2"]


def test_get_next_task_no_dependencies(forge: WorkflowForge) -> None:
    """Should get first pending task when no dependencies."""
    tasks = [
        WorkflowTask(id="task-001", title="First"),
        WorkflowTask(id="task-002", title="Second"),
    ]
    next_task = forge.get_next_task(tasks)
    assert next_task.id == "task-001"


def test_get_next_task_with_dependencies(forge: WorkflowForge) -> None:
    """Should respect task dependencies."""
    tasks = [
        WorkflowTask(id="task-001", title="First"),
        WorkflowTask(id="task-002", title="Second", dependencies=["task-001"]),
        WorkflowTask(id="task-003", title="Third", dependencies=["task-002"]),
    ]

    # First task should be available
    next_task = forge.get_next_task(tasks)
    assert next_task.id == "task-001"

    # Complete first, second should be available
    tasks[0].mark_completed()
    next_task = forge.get_next_task(tasks)
    assert next_task.id == "task-002"

    # Complete second, third should be available
    tasks[1].mark_completed()
    next_task = forge.get_next_task(tasks)
    assert next_task.id == "task-003"


def test_get_next_task_returns_none_when_all_done(forge: WorkflowForge) -> None:
    """Should return None when all tasks completed."""
    tasks = [
        WorkflowTask(id="task-001", title="First"),
    ]
    tasks[0].mark_completed()
    assert forge.get_next_task(tasks) is None


def test_execute_task_success(forge: WorkflowForge) -> None:
    """Executor returning True should mark task completed."""
    task = WorkflowTask(id="task-001", title="Test")
    success = forge.execute_task(task, lambda t: True)
    assert success is True
    assert task.status == TaskStatus.COMPLETED


def test_execute_task_failure(forge: WorkflowForge) -> None:
    """Executor returning False should mark task failed."""
    task = WorkflowTask(id="task-001", title="Test")
    success = forge.execute_task(task, lambda t: False)
    assert success is False
    assert task.status == TaskStatus.FAILED


def test_execute_task_exception(forge: WorkflowForge) -> None:
    """Executor raising exception should mark task failed."""
    task = WorkflowTask(id="task-001", title="Test")
    success = forge.execute_task(task, lambda t: (_ for _ in ()).throw(ValueError("boom")))
    assert success is False
    assert task.status == TaskStatus.FAILED


# ── Validation Gates Tests ─────────────────────────────────────────────────

def test_validation_gate_creation() -> None:
    """Should create validation gates."""
    gate = ValidationGate(
        name="test_gate",
        description="A test gate",
        check_fn="validate_something",
        severity="error",
    )
    assert gate.name == "test_gate"
    assert gate.severity == "error"


def test_validation_report_creation() -> None:
    """Should create validation reports."""
    report = ValidationReport(
        gate_name="test_gate",
        result=ValidationResult.PASS,
        message="All good",
        details={"key": "value"},
    )
    assert report.result == ValidationResult.PASS
    assert report.gate_name == "test_gate"


def test_run_validation_gates_syntax(forge: WorkflowForge) -> None:
    """Should run syntax validation gate."""
    plan = forge.generate_plan("Test", context={"code": "print('hello')"})
    reports = forge.run_validation_gates(plan, artifacts={"code": "print('hello')"})

    syntax_reports = [r for r in reports if r.gate_name == "syntax_check"]
    assert len(syntax_reports) == 1
    assert syntax_reports[0].result == ValidationResult.PASS


def test_run_validation_gates_syntax_failure(forge: WorkflowForge) -> None:
    """Should fail syntax validation on invalid code."""
    plan = forge.generate_plan("Test")
    reports = forge.run_validation_gates(plan, artifacts={"code": "print('hello'"})  # Missing paren

    syntax_reports = [r for r in reports if r.gate_name == "syntax_check"]
    assert len(syntax_reports) == 1
    assert syntax_reports[0].result == ValidationResult.FAIL


def test_run_validation_gates_tests(forge: WorkflowForge) -> None:
    """Should run test validation gate."""
    plan = forge.generate_plan("Test")
    reports = forge.run_validation_gates(
        plan,
        artifacts={"test_results": {"passed": 5, "failed": 0}},
    )

    test_reports = [r for r in reports if r.gate_name == "test_execution"]
    assert len(test_reports) == 1
    assert test_reports[0].result == ValidationResult.PASS


def test_run_validation_gates_tests_failure(forge: WorkflowForge) -> None:
    """Should fail test validation when tests fail."""
    plan = forge.generate_plan("Test")
    reports = forge.run_validation_gates(
        plan,
        artifacts={"test_results": {"passed": 3, "failed": 2}},
    )

    test_reports = [r for r in reports if r.gate_name == "test_execution"]
    assert len(test_reports) == 1
    assert test_reports[0].result == ValidationResult.FAIL


def test_run_validation_gates_criteria(forge: WorkflowForge) -> None:
    """Should run criteria validation gate."""
    plan = forge.generate_plan("Test")
    reports = forge.run_validation_gates(
        plan,
        artifacts={"criteria_met": ["c1", "c2"], "criteria_total": 2},
    )

    criteria_reports = [r for r in reports if r.gate_name == "criteria_match"]
    assert len(criteria_reports) == 1
    assert criteria_reports[0].result == ValidationResult.PASS


def test_run_validation_gates_missing_validator(forge: WorkflowForge) -> None:
    """Should warn when validator not registered."""
    plan = forge.generate_plan("Test")
    # Add a gate with unknown validator
    plan.validation_gates.append(
        ValidationGate(
            name="unknown_gate",
            description="Unknown",
            check_fn="validate_nonexistent",
        )
    )
    reports = forge.run_validation_gates(plan, artifacts={})

    unknown_reports = [r for r in reports if r.gate_name == "unknown_gate"]
    assert len(unknown_reports) == 1
    assert unknown_reports[0].result == ValidationResult.WARNING
    assert "missing_validator" in unknown_reports[0].details


def test_all_gates_passed(forge: WorkflowForge) -> None:
    """Should correctly identify all gates passed."""
    reports = [
        ValidationReport(gate_name="a", result=ValidationResult.PASS, message=""),
        ValidationReport(gate_name="b", result=ValidationResult.PASS, message=""),
    ]
    assert forge.all_gates_passed(reports) is True


def test_all_gates_passed_with_failure(forge: WorkflowForge) -> None:
    """Should return False when any gate fails."""
    reports = [
        ValidationReport(gate_name="a", result=ValidationResult.PASS, message=""),
        ValidationReport(gate_name="b", result=ValidationResult.FAIL, message=""),
    ]
    assert forge.all_gates_passed(reports) is False


def test_all_gates_passed_warning_ok(forge: WorkflowForge) -> None:
    """Warnings should not cause all_gates_passed to return False."""
    reports = [
        ValidationReport(gate_name="a", result=ValidationResult.PASS, message=""),
        ValidationReport(gate_name="b", result=ValidationResult.WARNING, message=""),
    ]
    assert forge.all_gates_passed(reports) is True


# ── Serialization Tests ────────────────────────────────────────────────────

def test_workflow_serialization(forge: WorkflowForge) -> None:
    """Should serialize and deserialize workflow."""
    wf = WorkflowForge.standard_ai_coding_workflow("test_serialization")
    data = forge.workflow_to_dict(wf)

    assert data["name"] == "test_serialization"
    assert len(data["phases"]) == 5


def test_workflow_save_load_roundtrip(forge: WorkflowForge, tmp_path: Path) -> None:
    """Should save and load workflow from file."""
    wf = WorkflowForge.standard_ai_coding_workflow("persist_test")
    file_path = tmp_path / "workflow.json"

    forge.save_workflow(wf, str(file_path))
    loaded = forge.load_workflow(str(file_path))

    assert loaded.name == "persist_test"
    assert len(loaded) == 5
    phase_names = [p.name for p in loaded.phases]
    assert phase_names == ["global_rules", "planning", "task_breakdown", "implementation", "validation"]


def test_plan_save_load_roundtrip(forge: WorkflowForge, tmp_path: Path) -> None:
    """Should save and load plan from file."""
    plan = forge.generate_plan("Persist test feature")
    file_path = tmp_path / "plan.json"

    forge.save_plan(plan, str(file_path))

    # Verify file exists and is valid JSON
    with open(file_path) as f:
        data = json.load(f)

    assert data["feature_request"] == "Persist test feature"
    assert "tasks" in data


# ── Custom Validator Registration Tests ────────────────────────────────────

def test_register_custom_validator_class_level() -> None:
    """Should register validator at class level."""

    def custom_validator(artifacts, metadata):
        return True, "Custom passed", {}

    WorkflowForge.register_validator("custom_test", custom_validator)
    forge = WorkflowForge()
    validator = forge._get_validator("custom_test")
    assert validator is not None
    assert validator == custom_validator

    # Cleanup
    del WorkflowForge._VALIDATORS["custom_test"]


def test_register_custom_validator_instance_level(forge: WorkflowForge) -> None:
    """Should register validator at instance level."""

    def custom_validator(artifacts, metadata):
        return True, "Custom passed", {}

    forge.register_instance_validator("instance_custom", custom_validator)
    validator = forge._get_validator("instance_custom")
    assert validator is not None
    assert validator == custom_validator

    # Should not affect other instances
    other_forge = WorkflowForge()
    assert other_forge._get_validator("instance_custom") is None


# ── Module Lifecycle Tests ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_module_initialize(module_instance: WorkflowForgeModule) -> None:
    """Module should initialize to HEALTHY."""
    assert module_instance.status == HealthStatus.HEALTHY
    assert module_instance.forge is not None


@pytest.mark.asyncio
async def test_module_health_check_healthy(module_instance: WorkflowForgeModule) -> None:
    """Health check should return HEALTHY for initialized module."""
    status = await module_instance.health_check()
    assert status == HealthStatus.HEALTHY


@pytest.mark.asyncio
async def test_module_shutdown(module_instance: WorkflowForgeModule) -> None:
    """Module should shut down gracefully."""
    await module_instance.shutdown()
    # After shutdown, status returns to HEALTHY (per kernel contract)
    assert module_instance.status == HealthStatus.HEALTHY
    assert module_instance.forge is None


@pytest.mark.asyncio
async def test_module_lifecycle_full(module_instance: WorkflowForgeModule) -> None:
    """Full lifecycle: initialize -> health_check -> shutdown."""
    # Already initialized by fixture
    assert module_instance.status == HealthStatus.HEALTHY

    # Health check
    status = await module_instance.health_check()
    assert status == HealthStatus.HEALTHY

    # Shutdown
    await module_instance.shutdown()
    assert module_instance.status == HealthStatus.HEALTHY
    assert module_instance.forge is None


@pytest.mark.asyncio
async def test_module_set_event_bus(module_instance: WorkflowForgeModule) -> None:
    """Should accept event bus."""
    from enterprise.platform_kernel import EventBus
    bus = EventBus()
    module_instance.set_event_bus(bus)
    # No exception = success


# ── Integration / End-to-End Tests ────────────────────────────────────────

@pytest.mark.asyncio
async def test_run_workflow_async_basic() -> None:
    """Should run complete workflow asynchronously."""
    forge = WorkflowForge()
    workflow = WorkflowForge.standard_ai_coding_workflow()

    plan, tasks, reports = await run_workflow_async(
        forge=forge,
        workflow=workflow,
        feature_request="Build a simple API",
        context={"goals": ["Create API endpoints", "Add authentication"]},
    )

    assert isinstance(plan, WorkflowPlan)
    assert len(tasks) > 0
    assert len(reports) >= 3  # At least syntax, tests, criteria


@pytest.mark.asyncio
async def test_run_workflow_async_with_executor() -> None:
    """Should execute tasks when executor provided."""
    forge = WorkflowForge()
    workflow = WorkflowForge.standard_ai_coding_workflow()

    executed_tasks = []

    def tracking_executor(task: WorkflowTask) -> bool:
        executed_tasks.append(task.id)
        return True

    plan, tasks, reports = await run_workflow_async(
        forge=forge,
        workflow=workflow,
        feature_request="Test feature",
        executor=tracking_executor,
    )

    # All tasks should have been executed
    assert len(executed_tasks) == len(plan.tasks)


# ── Enum Tests ─────────────────────────────────────────────────────────────

def test_phase_kind_values() -> None:
    """PhaseKind should have expected values."""
    assert PhaseKind.RULES.value == "rules"
    assert PhaseKind.PLAN.value == "plan"
    assert PhaseKind.TASKS.value == "tasks"
    assert PhaseKind.IMPLEMENT.value == "implement"
    assert PhaseKind.VALIDATE.value == "validate"


def test_task_status_values() -> None:
    """TaskStatus should have expected values."""
    assert TaskStatus.PENDING.value == "pending"
    assert TaskStatus.IN_PROGRESS.value == "in_progress"
    assert TaskStatus.COMPLETED.value == "completed"
    assert TaskStatus.FAILED.value == "failed"
    assert TaskStatus.SKIPPED.value == "skipped"


def test_validation_result_values() -> None:
    """ValidationResult should have expected values."""
    assert ValidationResult.PASS.value == "pass"
    assert ValidationResult.FAIL.value == "fail"
    assert ValidationResult.WARNING.value == "warning"


# ── Edge Cases ─────────────────────────────────────────────────────────────

def test_plan_with_empty_context(forge: WorkflowForge) -> None:
    """Should handle empty context gracefully."""
    plan = forge.generate_plan("Test", context={})
    assert len(plan.tasks) > 0
    assert len(plan.goals) > 0


def test_plan_with_none_context(forge: WorkflowForge) -> None:
    """Should handle None context gracefully."""
    plan = forge.generate_plan("Test", context=None)
    assert len(plan.tasks) > 0


def test_workflow_iteration() -> None:
    """Workflow should be iterable."""
    wf = WorkflowForge.standard_ai_coding_workflow()
    phases = list(wf)
    assert len(phases) == 5


def test_validation_report_to_dict() -> None:
    """ValidationReport should serialize to dict."""
    report = ValidationReport(
        gate_name="test",
        result=ValidationResult.PASS,
        message="OK",
        details={"foo": "bar"},
    )
    d = report.to_dict()
    assert d["gate_name"] == "test"
    assert d["result"] == "pass"
    assert d["details"]["foo"] == "bar"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])