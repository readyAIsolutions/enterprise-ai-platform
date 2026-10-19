"""Tests for the ai_coding_workflow module. Stdlib + pytest only, no network."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Ensure the repo parent (containing the ``enterprise`` package) is importable
# without hardcoding any absolute path.
_REPO_PARENT = Path(__file__).resolve().parents[4]
if str(_REPO_PARENT) not in sys.path:
    sys.path.insert(0, str(_REPO_PARENT))

from enterprise.modules.ai_coding_workflow import (  # noqa: E402
    AICodingWorkflowModule,
    TaskState,
    WorkflowEngine,
    WorkflowError,
    WorkflowPhase,
    create_ai_coding_workflow_module,
)


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------

def _plan_tasks():
    return [
        {"id": "t1", "description": "scaffold", "files_to_create": ["a.py"]},
        {"id": "t2", "description": "wire", "files_to_modify": ["b.py"],
         "patterns": ["facade"]},
    ]


def _primed_engine(framework="plain"):
    eng = WorkflowEngine("demo", framework=framework)
    eng.set_requirements("Build the thing")
    eng.create_plan(_plan_tasks(), success_criteria=["tests pass"])
    return eng


# --------------------------------------------------------------------------
# phase ordering
# --------------------------------------------------------------------------

def test_phase_ordering():
    eng = WorkflowEngine("demo")
    assert eng.phase is WorkflowPhase.REQUIREMENTS
    eng.set_requirements("reqs")
    assert eng.phase is WorkflowPhase.PLAN
    eng.create_plan(_plan_tasks(), success_criteria=["ok"])
    assert eng.phase is WorkflowPhase.EXECUTE


def test_cannot_plan_before_requirements():
    eng = WorkflowEngine("demo")
    with pytest.raises(WorkflowError):
        eng.create_plan(_plan_tasks(), success_criteria=["ok"])


def test_empty_requirements_rejected():
    eng = WorkflowEngine("demo")
    with pytest.raises(WorkflowError):
        eng.set_requirements("   ")


def test_plan_needs_tasks_and_criteria():
    eng = WorkflowEngine("demo")
    eng.set_requirements("r")
    with pytest.raises(WorkflowError):
        eng.create_plan([], success_criteria=["ok"])
    with pytest.raises(WorkflowError):
        eng.create_plan(_plan_tasks(), success_criteria=[])


def test_unknown_framework_rejected():
    with pytest.raises(WorkflowError):
        WorkflowEngine("demo", framework="nope")


def test_duplicate_task_id_rejected():
    eng = WorkflowEngine("demo")
    eng.set_requirements("r")
    dupes = [
        {"id": "x", "description": "a"},
        {"id": "x", "description": "b"},
    ]
    with pytest.raises(WorkflowError):
        eng.create_plan(dupes, success_criteria=["ok"])


# --------------------------------------------------------------------------
# task transitions
# --------------------------------------------------------------------------

def test_legal_task_transitions():
    eng = _primed_engine()
    t = eng.start_task("t1")
    assert t.state is TaskState.DOING
    eng.advance_task("t1")
    assert eng.plan.task_by_id("t1").state is TaskState.REVIEW
    eng.advance_task("t1")
    assert eng.plan.task_by_id("t1").state is TaskState.DONE


def test_illegal_transition_rejected():
    eng = _primed_engine()
    # TODO cannot jump straight to DONE
    with pytest.raises(WorkflowError):
        eng.set_task_state("t1", TaskState.DONE)
    # DONE task cannot advance further
    eng.start_task("t1")
    eng.advance_task("t1")
    eng.advance_task("t1")
    with pytest.raises(WorkflowError):
        eng.advance_task("t1")


def test_only_one_task_in_progress():
    eng = _primed_engine()
    eng.start_task("t1")
    with pytest.raises(WorkflowError):
        eng.start_task("t2")


def test_next_task():
    eng = _primed_engine()
    assert eng.next_task().id == "t1"
    eng.start_task("t1")
    eng.advance_task("t1")
    eng.advance_task("t1")  # t1 DONE
    assert eng.next_task().id == "t2"
    eng.start_task("t2")
    eng.advance_task("t2")
    eng.advance_task("t2")
    assert eng.next_task() is None


def test_block_and_recover():
    eng = _primed_engine()
    eng.start_task("t1")
    eng.block_task("t1", "missing dep")
    assert eng.plan.task_by_id("t1").state is TaskState.BLOCKED
    eng.set_task_state("t1", TaskState.DOING)
    assert eng.plan.task_by_id("t1").state is TaskState.DOING


# --------------------------------------------------------------------------
# validation gate
# --------------------------------------------------------------------------

def test_validation_fails_when_incomplete():
    eng = _primed_engine()
    eng.start_task("t1")
    result = eng.validate()
    assert result.passed is False
    assert eng.phase is WorkflowPhase.VALIDATE


def _complete_all(eng):
    for tid in ("t1", "t2"):
        eng.start_task(tid)
        eng.advance_task(tid)
        eng.advance_task(tid)


def test_validation_passes_when_all_done():
    eng = _primed_engine()
    _complete_all(eng)
    assert eng.all_tasks_done()
    result = eng.validate(generated_tests=["test_a"])
    assert result.passed is True
    assert eng.phase is WorkflowPhase.COMPLETE


def test_validation_reopens_on_review_findings():
    eng = _primed_engine()
    _complete_all(eng)
    result = eng.validate(review_findings=["bad error handling"])
    assert result.passed is False
    assert set(result.reopened_tasks) == {"t1", "t2"}
    assert eng.phase is WorkflowPhase.EXECUTE
    assert eng.plan.task_by_id("t1").state is TaskState.TODO


# --------------------------------------------------------------------------
# progress counts
# --------------------------------------------------------------------------

def test_progress_counts():
    eng = _primed_engine()
    p = eng.progress()
    assert p["todo"] == 2
    eng.start_task("t1")
    p = eng.progress()
    assert p["doing"] == 1 and p["todo"] == 1
    eng.advance_task("t1")
    eng.advance_task("t1")
    assert eng.progress()["done"] == 1


def test_summary_and_render():
    eng = _primed_engine()
    s = eng.summary()
    assert s["task_count"] == 2
    assert s["framework"] == "plain"
    assert "Workflow: demo" in eng.render()


# --------------------------------------------------------------------------
# module lifecycle + event emission
# --------------------------------------------------------------------------

async def test_module_lifecycle():
    mod = create_ai_coding_workflow_module()
    assert isinstance(mod, AICodingWorkflowModule)
    await mod.initialize()
    from enterprise.platform_kernel import HealthStatus
    assert await mod.health_check() is HealthStatus.HEALTHY
    await mod.shutdown()
    assert await mod.health_check() is HealthStatus.STOPPING


async def test_event_emission_with_bus():
    class FakeBus:
        def __init__(self):
            self.events = []

        def publish(self, event):
            self.events.append(event)

    bus = FakeBus()
    mod = create_ai_coding_workflow_module()
    await mod.initialize()
    mod.set_event_bus(bus)
    mod.create_workflow("wf", framework="prp")
    mod.set_requirements("wf", "build it")
    mod.create_plan("wf", _plan_tasks(), success_criteria=["ok"])
    mod.start_task("wf", "t1")
    mod.advance_task("wf", "t1")
    topics = [e.topic for e in bus.events]
    assert "ai_coding_workflow.workflow_created" in topics
    assert "ai_coding_workflow.requirements_set" in topics
    assert "ai_coding_workflow.plan_created" in topics
    assert "ai_coding_workflow.task_started" in topics
    assert all(e.source == "ai_coding_workflow" for e in bus.events)


async def test_no_events_without_bus():
    mod = create_ai_coding_workflow_module()
    await mod.initialize()
    # no bus attached -> _publish is a no-op, should not raise
    mod.create_workflow("wf")
    mod.set_requirements("wf", "build it")
    assert mod.get_workflow("wf") is not None
