"""
Tests for the ENI Task Harness enterprise module.

Covers:
  - TaskCard dataclass & TaskStatus enum
  - create + get round trip
  - list filtering by status
  - dependency gating via can_start
  - next_runnable ordering (priority then creation)
  - pause/resume transitions
  - illegal transition guard (e.g. completed -> running)
  - mark_completed with result
  - cancel
  - module registration via @module decorator
  - module lifecycle (initialize / health_check / shutdown) against tmp DB

All tests are real unit tests against temporary SQLite files (pytest
tmp_path); no production data is touched.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Ensure the project root is on sys.path for enterprise imports.
# ---------------------------------------------------------------------------
_PROJECT_ROOT: Path = Path(__file__).resolve().parents[4]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from enterprise.modules.task_harness import TaskHarness, TaskStatus  # noqa: E402
from enterprise.modules.task_harness.task_harness import (  # noqa: E402
    DependencyNotSatisfiedError,
    InvalidTransitionError,
    TaskNotFoundError,
)


@pytest.fixture
def harness(tmp_path: Path) -> TaskHarness:
    """A fresh TaskHarness backed by a temp SQLite file."""
    db = tmp_path / "tasks.sqlite"
    h = TaskHarness(str(db))
    yield h
    h.close()


# ===========================================================================
# Create + get round trip
# ===========================================================================
class TestCreateGet:
    def test_create_and_get_round_trip(self, harness: TaskHarness) -> None:
        card = harness.create_card(
            title="Refactor auth service",
            description="Split blob of auth logic into modules",
            priority=5,
            steps=["ast survey", "extract core", "wire DI"],
        )
        fetched = harness.get(card.id)
        assert fetched.id == card.id
        assert fetched.title == "Refactor auth service"
        assert fetched.description == "Split blob of auth logic into modules"
        assert fetched.priority == 5
        assert fetched.steps == ["ast survey", "extract core", "wire DI"]
        assert fetched.status == TaskStatus.PENDING
        assert fetched.depends_on == []
        assert fetched.created_at  # non-empty
        assert fetched.updated_at  # non-empty

    def test_get_missing_raises(self, harness: TaskHarness) -> None:
        with pytest.raises(TaskNotFoundError):
            harness.get("does-not-exist")

    def test_create_requires_title(self, harness: TaskHarness) -> None:
        from enterprise.modules.task_harness.task_harness import TaskHarnessError

        with pytest.raises(TaskHarnessError):
            harness.create_card(title="   ")

    def test_ids_are_unique(self, harness: TaskHarness) -> None:
        a = harness.create_card("first")
        b = harness.create_card("second")
        assert a.id != b.id


# ===========================================================================
# List filtering
# ===========================================================================
class TestList:
    def test_list_all(self, harness: TaskHarness) -> None:
        for i in range(3):
            harness.create_card(f"task-{i}")
        assert len(harness.list()) == 3

    def test_list_filters_by_status(self, harness: TaskHarness) -> None:
        pending_a = harness.create_card("pending-a")
        pending_b = harness.create_card("pending-b")
        running = harness.create_card("running")
        harness.start(running.id)
        assert all(c.id in (pending_a.id, pending_b.id) for c in harness.list(TaskStatus.PENDING))
        assert [c.id for c in harness.list(TaskStatus.RUNNING)] == [running.id]
        assert harness.list(TaskStatus.COMPLETED) == []


# ===========================================================================
# Dependency gating
# ===========================================================================
class TestDependencies:
    def test_no_deps_can_start(self, harness: TaskHarness) -> None:
        card = harness.create_card("independent")
        assert harness.can_start(card.id) is True

    def test_unsatisfied_dep_cannot_start(self, harness: TaskHarness) -> None:
        dep = harness.create_card("prereq")
        child = harness.create_card("depends", depends_on=[dep.id])
        # The dep is still pending -> child cannot start.
        assert harness.can_start(child.id) is False
        with pytest.raises(DependencyNotSatisfiedError):
            harness.start(child.id)

    def test_satisfied_dep_can_start(self, harness: TaskHarness) -> None:
        dep = harness.create_card("prereq")
        harness.start(dep.id)
        harness.mark_completed(dep.id, result="done")
        child = harness.create_card("depends", depends_on=[dep.id])
        assert harness.can_start(child.id) is True
        started = harness.start(child.id)
        assert started.status == TaskStatus.RUNNING

    def test_future_dependency_blocks(self, harness: TaskHarness) -> None:
        # Allowed at creation but blocks running until it exists & completes.
        child = harness.create_card("waits-on-future", depends_on=["not-created-yet"])
        assert harness.can_start(child.id) is False
        with pytest.raises(DependencyNotSatisfiedError):
            harness.start(child.id)


# ===========================================================================
# next_runnable ordering
# ===========================================================================
class TestNextRunnable:
    def test_runnable_excludes_blocked(self, harness: TaskHarness) -> None:
        dep = harness.create_card("prereq")
        blocked = harness.create_card("blocked", depends_on=[dep.id])
        nar = harness.create_card("no-dep")
        runnable_ids = [c.id for c in harness.next_runnable()]
        assert blocked.id not in runnable_ids
        assert nar.id in runnable_ids

    def test_orders_by_priority_desc(self, harness: TaskHarness) -> None:
        low = harness.create_card("low", priority=1)
        high = harness.create_card("high", priority=10)
        mid = harness.create_card("mid", priority=5)
        runnable = harness.next_runnable()
        assert [c.id for c in runnable] == [high.id, mid.id, low.id]

    def test_orders_by_creation_within_priority(self, harness: TaskHarness) -> None:
        first = harness.create_card("first", priority=5)
        second = harness.create_card("second", priority=5)
        third = harness.create_card("third", priority=5)
        runnable = harness.next_runnable()
        assert [c.id for c in runnable] == [first.id, second.id, third.id]

    def test_excludes_running_completed_paused(self, harness: TaskHarness) -> None:
        c1 = harness.create_card("c1")
        c2 = harness.create_card("c2")
        harness.start(c1.id)
        harness.mark_completed(c1.id)
        harness.start(c2.id)
        harness.pause(c2.id)
        assert harness.next_runnable() == []


# ===========================================================================
# Pause / resume / transitions
# ===========================================================================
class TestTransitions:
    def test_pause_resume(self, harness: TaskHarness) -> None:
        card = harness.create_card("long-running")
        harness.start(card.id)
        paused = harness.pause(card.id)
        assert paused.status == TaskStatus.PAUSED
        resumed = harness.resume(card.id)
        assert resumed.status == TaskStatus.RUNNING

    def test_pause_requires_running(self, harness: TaskHarness) -> None:
        card = harness.create_card("never-started")
        with pytest.raises(InvalidTransitionError):
            harness.pause(card.id)

    def test_resume_requires_paused(self, harness: TaskHarness) -> None:
        card = harness.create_card("running")
        harness.start(card.id)
        with pytest.raises(InvalidTransitionError):
            harness.resume(card.id)

    def test_completed_to_running_raises(self, harness: TaskHarness) -> None:
        card = harness.create_card("done")
        harness.start(card.id)
        harness.mark_completed(card.id)
        with pytest.raises(InvalidTransitionError):
            harness.start(card.id)

    def test_cancel_from_pending(self, harness: TaskHarness) -> None:
        card = harness.create_card("drop-me")
        cancelled = harness.cancel(card.id)
        assert cancelled.status == TaskStatus.CANCELLED
        # Terminal state: no further transitions allowed.
        with pytest.raises(InvalidTransitionError):
            harness.resume(card.id)

    def test_mark_completed_with_result(self, harness: TaskHarness) -> None:
        card = harness.create_card("build")
        harness.start(card.id)
        done = harness.mark_completed(card.id, result="build finished clean")
        assert done.status == TaskStatus.COMPLETED
        assert done.result == "build finished clean"

    def test_mark_failed(self, harness: TaskHarness) -> None:
        card = harness.create_card("flaky")
        harness.start(card.id)
        failed = harness.mark_failed(card.id, result="timeout")
        assert failed.status == TaskStatus.FAILED
        assert failed.result == "timeout"


# ===========================================================================
# Steps / notes / heartbeat
# ===========================================================================
class TestNotesStepsHeartbeat:
    def test_add_step_progress(self, harness: TaskHarness) -> None:
        card = harness.create_card("multi-step", steps=["a", "b"])
        updated = harness.add_step_progress(card.id, "c")
        assert updated.steps == ["a", "b", "c"]

    def test_set_note(self, harness: TaskHarness) -> None:
        card = harness.create_card("noted")
        updated = harness.set_note(card.id, "remember the constraints")
        assert updated.notes == "remember the constraints"

    def test_heartbeat_bumps_updated_at(self, harness: TaskHarness) -> None:
        card = harness.create_card("alive")
        before = card.updated_at
        # Force a tiny delay so timestamps differ.
        import time

        time.sleep(0.01)
        after = harness.heartbeat(card.id)
        assert after.updated_at >= before
        assert after.id == card.id


# ===========================================================================
# Module registration & lifecycle
# ===========================================================================
class TestModule:
    def test_module_registered(self) -> None:
        from enterprise.modules.task_harness import TaskHarnessModule
        from enterprise.platform_kernel import _MODULE_REGISTRY

        assert "task_harness" in _MODULE_REGISTRY
        assert _MODULE_REGISTRY["task_harness"] is TaskHarnessModule

    def test_module_metadata(self) -> None:
        from enterprise.modules.task_harness import TaskHarnessModule

        mod = TaskHarnessModule()
        assert mod.name == "task_harness"
        assert mod.version == "1.0.0"
        assert mod.module_id

    async def test_module_lifecycle_with_config_db(self, tmp_path: Path) -> None:
        from enterprise.modules.task_harness import TaskHarnessModule

        db_path = tmp_path / "nested" / "tasks.sqlite"
        mod = TaskHarnessModule({"db_path": str(db_path)})
        await mod.initialize()
        assert mod.harness is not None
        assert mod.status.value == "healthy"

        # Round-trip through the module-owned harness.
        card = mod.harness.create_card("module-task")
        assert mod.harness.get(card.id).id == card.id

        # Health check against the live store.
        from enterprise.platform_kernel import HealthStatus

        assert await mod.health_check() == HealthStatus.HEALTHY

        await mod.shutdown()
        assert mod.harness is None

    async def test_health_check_unknown_when_uninitialized(self) -> None:
        from enterprise.modules.task_harness import TaskHarnessModule
        from enterprise.platform_kernel import HealthStatus

        mod = TaskHarnessModule()
        assert await mod.health_check() == HealthStatus.UNKNOWN

    async def test_set_event_bus_and_publish(self, tmp_path: Path) -> None:
        from enterprise.modules.task_harness import TaskHarnessModule
        from enterprise.platform_kernel import EventBus

        events: list[str] = []
        bus = EventBus({"async_dispatch": False})
        bus.subscribe("task.created")(lambda e: events.append(e.topic))

        db_path = tmp_path / "tasks.sqlite"
        mod = TaskHarnessModule({"db_path": str(db_path)})
        mod.set_event_bus(bus)
        await mod.initialize()

        # Publish a synthetic event through the module's emitter.
        mod._publish("task.created", {"id": "abc"})
        assert events == ["task.created"]
        await mod.shutdown()
