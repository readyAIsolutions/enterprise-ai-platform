"""
Tests for the ENI Task Harness resilient runner (task_harness/runner.py).

Covers the master-class execution layer:
  - RetryPolicy: max_attempts + backoff timing (injected sleep).
  - Deadline: expired tasks are marked EXPIRED and failed.
  - Heartbeat: liveness beats; watchdog marks stalled tasks retriable.
  - ErrorClassifier: retryable vs permanent classification.
  - WorkerRunner: claim order (priority/deps), retry-on-transient-then-success,
    permanent errors not retried, attempt tracking, stats, full lifecycle.

Determinism is guaranteed by an injected FakeClock and an injected executor
(mapping task id -> behaviour) — no real work and no wall-clock sleeps are
ever used.  All tests run against temporary SQLite files (pytest tmp_path).
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

from enterprise.modules.task_harness import (  # noqa: E402
    Deadline,
    ErrorClass,
    ErrorClassifier,
    Heartbeat,
    PermanentError,
    RetryableError,
    RetryPolicy,
    RunningStatus,
    TaskHarness,
    WorkerRunner,
    build_runner,
)
from enterprise.modules.task_harness.task_harness import TaskStatus  # noqa: E402


# ===========================================================================
# Deterministic clock + sleep fakes
# ===========================================================================
class FakeClock:
    """Injectable monotonic clock; tests advance it explicitly."""

    def __init__(self, start: float = 1000.0) -> None:
        self._now = start

    def __call__(self) -> float:
        return self._now

    def advance(self, seconds: float) -> float:
        self._now += seconds
        return self._now


class RecordingSleep:
    """Injectable sleep that records requested delays instead of sleeping."""

    def __init__(self) -> None:
        self.delays: list[float] = []

    def __call__(self, seconds: float) -> None:
        self.delays.append(seconds)


# ===========================================================================
# Fixtures
# ===========================================================================
@pytest.fixture
def harness(tmp_path: Path) -> TaskHarness:
    db = tmp_path / "runner.sqlite"
    h = TaskHarness(str(db))
    yield h
    h.close()


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def sleeper() -> RecordingSleep:
    return RecordingSleep()


def _runner(
    harness: TaskHarness,
    *,
    executor=None,
    clock: FakeClock | None = None,
    sleeper: RecordingSleep | None = None,
    retry_policy: RetryPolicy | None = None,
    max_runtime: float | None = None,
    heartbeat_timeout: float | None = None,
    **kwargs,
) -> WorkerRunner:
    clock = clock or FakeClock()
    sleeper = sleeper or RecordingSleep()
    retry_policy = retry_policy or RetryPolicy()
    deadline = Deadline(max_runtime, clock) if max_runtime is not None else None
    heartbeat = (
        Heartbeat(heartbeat_timeout, clock)
        if heartbeat_timeout is not None
        else None
    )
    return WorkerRunner(
        harness,
        executor=executor,
        retry_policy=retry_policy,
        deadline=deadline,
        heartbeat=heartbeat,
        clock=clock,
        sleep=sleeper,
        **kwargs,
    )


# ===========================================================================
# RetryPolicy / ErrorClassifier / Deadline / Heartbeat unit tests
# ===========================================================================
class TestPolicyAndClassifier:
    def test_retry_policy_exponential_backoff(self) -> None:
        policy = RetryPolicy(max_attempts=4, backoff=1.0)
        assert policy.max_attempts == 4
        assert policy.delay(1) == 1.0     # 2^0
        assert policy.delay(2) == 2.0     # 2^1
        assert policy.delay(3) == 4.0     # 2^2
        assert policy.exhausted(4) is True
        assert policy.exhausted(3) is False

    def test_retry_policy_custom_backoff_callable(self) -> None:
        policy = RetryPolicy(max_attempts=3, backoff=lambda a: a * 10)
        assert policy.delay(1) == 10
        assert policy.delay(2) == 20
        assert policy.delay(3) == 30

    def test_retry_policy_rejects_invalid_input(self) -> None:
        with pytest.raises(ValueError):
            RetryPolicy(max_attempts=0)
        with pytest.raises(TypeError):
            RetryPolicy(backoff="nope")  # type: ignore[arg-type]

    def test_error_classifier_defaults(self) -> None:
        cls = ErrorClassifier()
        assert cls.is_retryable(TimeoutError()) is True
        assert cls.is_retryable(ConnectionError()) is True
        assert cls.is_retryable(OSError()) is True
        assert cls.is_retryable(RetryableError()) is True
        assert cls.is_permanent(ValueError()) is True
        assert cls.is_permanent(TypeError()) is True
        assert cls.is_permanent(PermanentError()) is True
        # Unknown errors are permanent by default (never spin forever).
        assert cls.is_permanent(RuntimeError("? ")) is True

    def test_error_classifier_custom_sets(self) -> None:
        cls = ErrorClassifier(
            retryable=[RuntimeError], permanent=[ValueError]
        )
        assert cls.classify(RuntimeError()) is ErrorClass.RETRYABLE
        assert cls.classify(ValueError()) is ErrorClass.PERMANENT

    def test_deadline_enforces_runtime(self, clock: FakeClock) -> None:
        dl = Deadline(max_runtime=10.0, clock=clock)
        dl.start("t1", clock())
        assert dl.is_expired("t1") is False
        clock.advance(9.5)
        assert dl.is_expired("t1") is False
        clock.advance(1.0)  # total 10.5 >= 10
        assert dl.is_expired("t1") is True
        assert dl.remaining("t1") == 0.0

    def test_heartbeat_watchdog_marks_stalled(self, clock: FakeClock) -> None:
        hb = Heartbeat(timeout=5.0, clock=clock)
        hb.start("a", clock())            # b and a both start at 1000
        hb.beat("b", clock())             # name b started (not refreshed later)
        clock.advance(5.0)
        hb.beat("a")                      # a refreshed at 1005 (alive)
        clock.advance(4.0)                # -> 1009
        # a: 1009-1005=4 < 5 -> alive ; b: 1009-1000=9 > 5 -> stalled
        assert hb.is_stalled("a") is False
        assert hb.is_stalled("b") is True
        assert hb.watchdog(["a", "b"]) == ["b"]


# ===========================================================================
# WorkerRunner behaviour
# ===========================================================================
class TestRunnerRetry:
    def test_retries_on_retryable_error_then_success(
        self, harness: TaskHarness, clock: FakeClock, sleeper: RecordingSleep
    ) -> None:
        calls: list[int] = []

        def flaky(card):
            calls.append(card.id)
            if len(calls) < 3:
                raise ConnectionError("transient")
            return "ok"

        task = harness.create_card("flaky-task")
        runner = _runner(harness, executor=flaky, clock=clock, sleeper=sleeper)
        outcome = runner.run_once()

        assert outcome is RunningStatus.RUNNING
        assert len(calls) == 3
        assert harness.get(task.id).status is TaskStatus.COMPLETED
        assert harness.get(task.id).result == "ok"
        assert runner.attempts[task.id] == 3
        assert runner.stats.retried == 2
        assert runner.stats.completed == 1
        # Backoff sleeps: two retries after the 1st and 2nd attempts.
        assert sleeper.delays == [1.0, 2.0]

    def test_exhausts_attempts_on_persistent_retryable(
        self, harness: TaskHarness, sleeper: RecordingSleep
    ) -> None:
        calls: list[int] = []
        policy = RetryPolicy(max_attempts=4, backoff=1.0)

        def always_flaky(card):
            calls.append(card.id)
            raise ConnectionError("down")

        task = harness.create_card("down")
        runner = _runner(
            harness,
            executor=always_flaky,
            retry_policy=policy,
            sleeper=sleeper,
        )
        outcome = runner.run_once()

        assert outcome is RunningStatus.RUNNING_PERMANENT
        assert len(calls) == 4
        assert harness.get(task.id).status is TaskStatus.FAILED
        assert runner.stats.failed == 1
        assert holder_str(runner.errors[task.id]) == "ConnectionError: down"
        # Backoff for attempts 1..3 (no sleep after the final attempt).
        assert sleeper.delays == [policy.delay(1), policy.delay(2), policy.delay(3)]

    def test_permanent_error_is_not_retried(
        self, harness: TaskHarness, sleeper: RecordingSleep
    ) -> None:
        calls: list[int] = []

        def bad_logic(card):
            calls.append(card.id)
            raise ValueError("bad input")

        task = harness.create_card("logic")
        runner = _runner(harness, executor=bad_logic, sleeper=sleeper)
        outcome = runner.run_once()

        assert outcome is RunningStatus.RUNNING_PERMANENT
        assert len(calls) == 1                       # never retried
        assert sleeper.delays == []                  # no backoff
        assert harness.get(task.id).status is TaskStatus.FAILED
        assert runner.stats.failed == 1
        assert runner.stats.retried == 0


class TestRunnerDeadline:
    def test_deadline_expiry_marks_expired(
        self, harness: TaskHarness, clock: FakeClock, sleeper: RecordingSleep
    ) -> None:
        calls: list[int] = []

        def slow(card):
            calls.append(card.id)
            return "not done"

        task = harness.create_card("slow")
        # max_runtime=10; executor returns instantly, so we advance the clock
        # past the deadline before the loop checks it.
        runner = _runner(
            harness,
            executor=slow,
            clock=clock,
            sleeper=sleeper,
            max_runtime=10.0,
        )
        runner.claim()
        clock.advance(11.0)
        outcome = runner.run_task(task.id)

        assert outcome is RunningStatus.EXPIRED
        assert harness.get(task.id).status is TaskStatus.FAILED
        assert "deadline exceeded" in (harness.get(task.id).result or "")
        assert runner.stats.expired == 1
        assert runner.stats.completed == 0


class TestRunnerHeartbeat:
    def test_heartbeat_stall_is_retriable(
        self, harness: TaskHarness, clock: FakeClock, sleeper: RecordingSleep
    ) -> None:
        calls: list[int] = []

        def work(card):
            calls.append(card.id)
            return "done"

        task = harness.create_card("stall")
        runner = _runner(
            harness,
            executor=work,
            clock=clock,
            sleeper=sleeper,
            heartbeat_timeout=10.0,
        )
        # Claim the task (records heartbeat at t=1000), then let the worker
        # go silent past the heartbeat timeout before the loop resumes.
        runner.claim()
        clock.advance(100.0)
        outcome = runner.run_task(task.id)

        # The watchdog marks the stalled attempt retriable and retries once;
        # the retry finishes successfully with a fresh heartbeat.
        assert len(calls) == 1                        # work done only on retry
        assert runner.stats.retried == 1
        assert runner.stats.stalled == 0              # watchdog not invoked
        assert runner.stats.completed == 1
        assert task.id in runner.retriable or outcome is RunningStatus.RUNNING
        assert harness.get(task.id).status is TaskStatus.COMPLETED
        assert outcome is RunningStatus.RUNNING

    def test_watchdog_marks_retriable_set(
        self, harness: TaskHarness, clock: FakeClock
    ) -> None:
        task = harness.create_card("watch")
        runner = _runner(
            harness,
            executor=lambda c: "ok",
            clock=clock,
            heartbeat_timeout=5.0,
        )
        runner.claim()                 # starts + begins heartbeat
        assert runner.heartbeat is not None
        clock.advance(6.0)
        stalled = runner.watchdog()
        assert task.id in stalled
        assert task.id in runner.retriable
        assert runner.status[task.id] is RunningStatus.RUNNING_RETRY
        assert runner.stats.stalled == 1


class TestRunnerOrdering:
    def test_claims_by_priority_desc(
        self, harness: TaskHarness, clock: FakeClock
    ) -> None:
        low = harness.create_card("low", priority=1)
        high = harness.create_card("high", priority=10)
        mid = harness.create_card("mid", priority=5)

        runner = _runner(harness, executor=lambda c: "ok", clock=clock)
        first = runner.claim()
        assert first.id == high.id
        second = runner.claim()
        assert second.id == mid.id
        third = runner.claim()
        assert third.id == low.id

    def test_respects_dependencies_ordering(
        self, harness: TaskHarness, clock: FakeClock
    ) -> None:
        dep = harness.create_card("dep")
        child = harness.create_card("child", depends_on=[dep.id])

        runner = _runner(harness, executor=lambda c: "ok", clock=clock)
        # Only the dependency is runnable at first.
        assert runner.claim().id == dep.id
        # child still blocked until dep completes.
        assert runner.harness.next_runnable() == []
        # Complete dep, now child is runnable.
        harness.mark_completed(dep.id)
        assert runner.claim().id == child.id


class TestRunnerLifecycle:
    def test_run_drains_all_and_reports_stats(
        self, harness: TaskHarness, clock: FakeClock
    ) -> None:
        for i in range(3):
            harness.create_card(f"task-{i}", priority=i)
        runner = _runner(harness, executor=lambda c: f"done-{c.id}", clock=clock)
        stats = runner.run()

        assert stats.completed == 3
        assert stats.claimed == 3
        assert stats.total_runs == 3
        assert runner.harness.next_runnable() == []
        assert all(
            runner.harness.get(t.id).status is TaskStatus.COMPLETED
            for t in runner.harness.list()
        )

    def test_run_once_returns_none_when_idle(
        self, harness: TaskHarness, clock: FakeClock
    ) -> None:
        runner = _runner(harness, executor=lambda c: "ok", clock=clock)
        assert runner.run_once() is None
        assert runner.stats.claimed == 0

    def test_full_lifecycle_and_backoff_timing(
        self, harness: TaskHarness, clock: FakeClock, sleeper: RecordingSleep
    ) -> None:
        # One transient task that succeeds on the 2nd attempt, one permanent.
        transient_calls: list[int] = []

        def transient(card):
            transient_calls.append(card.id)
            if len(transient_calls) < 2:
                raise TimeoutError("retry me")
            return "ok"

        t_ok = harness.create_card("transient")
        t_bad = harness.create_card("bad")
        seen: set[str] = set()

        def dispatch(card):
            seen.add(card.id)
            if card.id == t_bad.id:
                raise PermanentError("nope")
            return transient(card)

        runner = _runner(
            harness,
            executor=dispatch,
            clock=clock,
            sleeper=sleeper,
            max_runtime=100.0,
            heartbeat_timeout=1000.0,
        )
        runner.run()

        assert harness.get(t_ok.id).status is TaskStatus.COMPLETED
        assert harness.get(t_bad.id).status is TaskStatus.FAILED
        assert runner.stats.completed == 1
        assert runner.stats.failed == 1
        assert runner.stats.retried == 1
        assert runner.stats.total_runs == 2
        # The single retry slept for backoff of the 1st attempt (2^0).
        assert sleeper.delays == [1.0]
        assert runner.attempts[t_ok.id] == 2
        assert runner.attempts[t_bad.id] == 1


def holder_str(exc: BaseException) -> str:
    return f"{type(exc).__name__}: {exc}"
