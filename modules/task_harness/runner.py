"""
task_harness.runner — resilient worker runner for the ENI Task Harness.

Extends the SQLite-backed :class:`TaskHarness` store (a Maestro-style task
card harness) with a master-class execution layer:

  RetryPolicy     — bounded attempts + exponential backoff (injectable).
  Deadline        — enforce a maximum wall-clock runtime per task.
  Heartbeat       — per-task liveness; a watchdog marks stalled tasks
                    (no heartbeat past ``timeout``) as retriable.
  ErrorClassifier — classify retryable (network/timeout) vs permanent
                    (logic/bad-input) errors; unknown errors are permanent.
  RunningStatus   — per-run outcome enum: running / running_retry /
                    running_permanent / expired.
  WorkerRunner    — a loop that claims the next runnable task (honouring
                    dependency ordering & priority via the store's
                    ``next_runnable``), runs it through an *injectable*
                    executor, tracks attempts, retries per policy with
                    backoff, marks success / failure / expiry, and emits
                    heartbeats so a watchdog can reap stalled runs.

Determinism: every timed primitive (clock, sleep) is injectable, and the
task function is injected via ``executor``.  Tests therefore never run real
work and never depend on ``time``.

Design notes:
  - Pure-stdlib (no external deps).
  - The runner is *tolerant* of whatever executor you hand it; a default
    executor raises :class:`PermanentError` so a misconfigured runner fails
    fast instead of silently no-oping.
  - Stall detection is a first-class retryable condition: a task that stops
    heartbeating past ``Heartbeat.timeout`` is treated like a retryable
    error and retried (up to ``RetryPolicy.max_attempts``).

Python: 3.10+
"""

from __future__ import annotations

import time as _time
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Any

from .task_harness import TaskCard, TaskHarness, TaskStatus

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence


# ===========================================================================
# Outcome enum
# ===========================================================================
class RunningStatus(Enum):
    """Outcome classification for a single task run."""

    RUNNING = "running"  # success (completed) or healthy
    RUNNING_RETRY = "running_retry"  # transient/stall -> will retry
    RUNNING_PERMANENT = "running_permanent"  # permanent failure, no retry
    EXPIRED = "expired"  # exceeded the deadline

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.value


# ===========================================================================
# Error classification
# ===========================================================================
class ErrorClass(Enum):
    """Broad error classes used by the retry machinery."""

    RETRYABLE = "retryable"
    PERMANENT = "permanent"

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.value


class RetryableError(Exception):
    """Marker: an error that may succeed if retried (network/timeout/etc.)."""


class PermanentError(Exception):
    """Marker: an error that will not succeed on retry (logic/bad input)."""


# Exceptions that are, by default, safe to retry (network / transient I/O).
_DEFAULT_RETRYABLE: tuple[type[BaseException], ...] = (
    RetryableError,
    ConnectionError,
    TimeoutError,
    OSError,  # includes ConnectionError; network + filesystem flakes
)

# Exceptions that are, by default, permanent (logic / bad input / misuse).
_DEFAULT_PERMANENT: tuple[type[BaseException], ...] = (
    PermanentError,
    ValueError,  # bad input
    TypeError,  # wrong types -> bug
    KeyError,  # bad key -> logic
    AttributeError,
    IndexError,
    ZeroDivisionError,
)


class ErrorClassifier:
    """Classify exceptions as retryable or permanent.

    ``classify`` checks the permanent set first (a ValueError raised while
    retrying is still permanent), then the retryable set.  Anything unknown
    is treated as permanent so the runner never spins forever on an
    unexpected failure.
    """

    def __init__(
        self,
        retryable: Sequence[type[BaseException]] | None = None,
        permanent: Sequence[type[BaseException]] | None = None,
    ) -> None:
        self._retryable: tuple[type[BaseException], ...] = tuple(
            retryable if retryable is not None else _DEFAULT_RETRYABLE
        )
        self._permanent: tuple[type[BaseException], ...] = tuple(
            permanent if permanent is not None else _DEFAULT_PERMANENT
        )

    def classify(self, exc: BaseException) -> ErrorClass:
        if isinstance(exc, self._permanent):
            return ErrorClass.PERMANENT
        if isinstance(exc, self._retryable):
            return ErrorClass.RETRYABLE
        return ErrorClass.PERMANENT

    def is_retryable(self, exc: BaseException) -> bool:
        return self.classify(exc) is ErrorClass.RETRYABLE

    def is_permanent(self, exc: BaseException) -> bool:
        return self.classify(exc) is ErrorClass.PERMANENT


# ===========================================================================
# Retry policy
# ===========================================================================
def _DEFAULT_BACKOFF(attempt: int) -> float:
    return 2.0 ** (attempt - 1)


@dataclass
class RetryPolicy:
    """How many attempts and how long to wait between them.

    ``backoff`` may be a float (constant delay) or a callable taking the
    attempt number (1-based) and returning the delay in seconds.  A small
    ``jitter`` (0..1 fraction) is optionally added for spreading retries.
    """

    max_attempts: int = 3
    backoff: float | Callable[[int], float] = 1.0
    jitter: float = 0.0

    def __post_init__(self) -> None:
        if self.max_attempts < 1:
            msg = "max_attempts must be >= 1"
            raise ValueError(msg)
        if isinstance(self.backoff, (int, float)):
            if self.backoff < 0:
                msg = "backoff must be >= 0"
                raise ValueError(msg)
            self._base: float = float(self.backoff)
            self._fn: Callable[[int], float] | None = None
        elif callable(self.backoff):
            self._base = 0.0
            self._fn = self.backoff
        else:
            msg = "backoff must be a float or a callable"
            raise TypeError(msg)
        if not (0.0 <= self.jitter < 1.0):
            msg = "jitter must be in [0, 1)"
            raise ValueError(msg)

    def delay(self, attempt: int) -> float:
        """Return the sleep delay (seconds) before the given retry attempt."""
        if self._fn is not None:
            raw = float(self._fn(attempt))
        else:
            raw = self._base * _DEFAULT_BACKOFF(attempt)
        if self.jitter:
            import random

            raw += random.uniform(0.0, raw * self.jitter)
        return max(0.0, raw)

    def exhausted(self, attempt: int) -> bool:
        """True if ``attempt`` was the final allowed attempt."""
        return attempt >= self.max_attempts


# ===========================================================================
# Deadline
# ===========================================================================
class Deadline:
    """Enforce a maximum wall-clock runtime per task.

    The runner records ``start`` when a task is claimed; a task is expired
    once ``now - start >= max_runtime``.  Fully clock-driven so it is
    deterministic under an injected clock.
    """

    def __init__(self, max_runtime: float, clock: Callable[[], float]) -> None:
        if max_runtime <= 0:
            msg = "max_runtime must be > 0"
            raise ValueError(msg)
        self.max_runtime: float = max_runtime
        self.clock: Callable[[], float] = clock
        self._start: dict[str, float] = {}

    def start(self, task_id: str, now: float | None = None) -> float:
        now = self.clock() if now is None else now
        self._start[task_id] = now
        return now

    def is_expired(self, task_id: str, now: float | None = None) -> bool:
        start = self._start.get(task_id)
        if start is None:
            return False
        now = self.clock() if now is None else now
        return now - start >= self.max_runtime

    def remaining(self, task_id: str, now: float | None = None) -> float:
        start = self._start.get(task_id)
        if start is None:
            return self.max_runtime
        now = self.clock() if now is None else now
        return max(0.0, start + self.max_runtime - now)

    def clear(self, task_id: str) -> None:
        self._start.pop(task_id, None)


# ===========================================================================
# Heartbeat
# ===========================================================================
class Heartbeat:
    """Per-task liveness tracking.

    A task/worker periodically calls :meth:`beat`; if no beat is recorded
    within ``timeout`` seconds, the task is *stalled*.  A task that has never
    beaten is also considered stalled (conservative).  ``watchdog`` maps a
    collection of task ids to the subset that are stalled so a runner can
    mark them retriable.
    """

    def __init__(self, timeout: float, clock: Callable[[], float]) -> None:
        if timeout <= 0:
            msg = "timeout must be > 0"
            raise ValueError(msg)
        self.timeout: float = timeout
        self.clock: Callable[[], float] = clock
        self._beat: dict[str, float] = {}

    def start(self, task_id: str, now: float | None = None) -> float:
        now = self.clock() if now is None else now
        self._beat[task_id] = now
        return now

    def beat(self, task_id: str, now: float | None = None) -> float:
        now = self.clock() if now is None else now
        self._beat[task_id] = now
        return now

    def last_beat(self, task_id: str) -> float | None:
        return self._beat.get(task_id)

    def is_stalled(self, task_id: str, now: float | None = None) -> bool:
        last = self._beat.get(task_id)
        if last is None:
            return True
        now = self.clock() if now is None else now
        return now - last > self.timeout

    def watchdog(self, task_ids: Sequence[str], now: float | None = None) -> list[str]:
        """Return the subset of ``task_ids`` that have stalled."""
        now = self.clock() if now is None else now
        return [t for t in task_ids if self.is_stalled(t, now)]

    def clear(self, task_id: str) -> None:
        self._beat.pop(task_id, None)


# ===========================================================================
# Execution stats
# ===========================================================================
@dataclass
class RunnerStats:
    """Aggregate counters exposed by a :class:`WorkerRunner`."""

    claimed: int = 0
    completed: int = 0
    failed: int = 0
    expired: int = 0
    retried: int = 0  # attempts triggered by retryable error
    stalled: int = 0  # tasks reaped by heartbeat watchdog
    stalled_failed: int = 0  # stalled tasks that exhausted attempts
    attempts: int = 0  # total executor invocations

    @property
    def total_runs(self) -> int:
        return self.completed + self.failed + self.expired + self.stalled_failed

    def snapshot(self) -> dict[str, int]:
        return {
            "claimed": self.claimed,
            "completed": self.completed,
            "failed": self.failed,
            "expired": self.expired,
            "retried": self.retried,
            "stalled": self.stalled,
            "stalled_failed": self.stalled_failed,
            "attempts": self.attempts,
            "total_runs": self.total_runs,
        }


# ===========================================================================
# Worker runner
# ===========================================================================
class WorkerRunner:
    """Resilient worker that claims and executes tasks from a TaskHarness.

    The runner loops over the store's ``next_runnable()`` (which already
    honours dependency ordering and priority), then drives each claimed task
    through a retry-aware execution loop:

      1. claim -> ``harness.start`` (state machine guarded).
      2. record deadline start + heartbeat start.
      3. for each attempt (up to ``retry_policy.max_attempts``):
           - if the deadline is expired -> mark EXPIRED, mark_failed.
           - beat the heartbeat (liveness).
           - if the heartbeat watchdog reports the task stalled -> treat as
             a retryable condition (retry if attempts remain, else fail).
           - run ``executor(card)``; on success mark_completed; on a
             retryable error sleep ``retry_policy.delay(attempt)`` and retry;
             on a permanent error (or exhausted attempts) mark_failed.

    Everything timed is injectable (``clock`` / ``sleep``) and the task
    function itself is injected (``executor``), so tests are fully
    deterministic and never execute real work.
    """

    def __init__(
        self,
        harness: TaskHarness,
        *,
        executor: Callable[[TaskCard], Any] | None = None,
        retry_policy: RetryPolicy | None = None,
        error_classifier: ErrorClassifier | None = None,
        deadline: Deadline | None = None,
        heartbeat: Heartbeat | None = None,
        clock: Callable[[], float] | None = None,
        sleep: Callable[[float], None] | None = None,
        on_heartbeat: Callable[[str], None] | None = None,
    ) -> None:
        self.harness: TaskHarness = harness
        self.executor: Callable[[TaskCard], Any] = executor or self._default_executor
        self.retry_policy = retry_policy or RetryPolicy()
        self.error_classifier = error_classifier or ErrorClassifier()
        self.clock: Callable[[], float] = clock or _time.monotonic
        self.sleep: Callable[[float], None] = sleep or _time.sleep
        self.deadline = deadline
        self.heartbeat = heartbeat
        # Optional hook invoked every time the worker emits a heartbeat for a
        # task id (lets a caller persist liveness or stream progress).
        self.on_heartbeat: Callable[[str], None] | None = on_heartbeat

        self.attempts: dict[str, int] = {}
        self.status: dict[str, RunningStatus] = {}
        self.results: dict[str, Any] = {}
        self.errors: dict[str, BaseException] = {}
        self.retriable: set[str] = set()
        self._running: set[str] = set()
        self.stats = RunnerStats()

    @staticmethod
    def _default_executor(card: TaskCard) -> Any:  # pragma: no cover - default
        msg = f"no executor configured for task {card.id!r}; inject one"
        raise PermanentError(msg)

    # ------------------------------------------------------------------
    # Claiming
    # ------------------------------------------------------------------
    def claim(self, now: float | None = None) -> TaskCard | None:
        """Claim the highest-priority runnable task, or None if none ready.

        Uses the store's ``next_runnable()`` (respects deps + priority),
        starts the claimed card, and sets up deadline/heartbeat tracking.
        """
        runnable = self.harness.next_runnable()
        if not runnable:
            return None
        card = runnable[0]
        self.harness.start(card.id)
        self.stats.claimed += 1
        self._running.add(card.id)
        now = self.clock() if now is None else now
        if self.deadline is not None:
            self.deadline.start(card.id, now)
        if self.heartbeat is not None:
            self.heartbeat.start(card.id, now)
        return card

    # ------------------------------------------------------------------
    # Watchdog
    # ------------------------------------------------------------------
    def watchdog(self, now: float | None = None) -> list[str]:
        """Mark any heartbeat-stalled running task as retriable.

        Returns the list of stalled task ids and bumps ``stats.stalled``.
        A stalled task is a first-class retryable condition: the execution
        loop below will retry it (up to ``max_attempts``).
        """
        if self.heartbeat is None:
            return []
        stalled = self.heartbeat.watchdog(sorted(self._running), now)
        for task_id in stalled:
            self.retriable.add(task_id)
            self.status[task_id] = RunningStatus.RUNNING_RETRY
            self.stats.stalled += 1
        return stalled

    # ------------------------------------------------------------------
    # Execution loop
    # ------------------------------------------------------------------
    def run_task(self, task_id: str) -> RunningStatus:
        """Drive one task through the full retry-aware execution loop."""
        card = self.harness.get(task_id)
        if card.status is not TaskStatus.RUNNING:
            self.harness.start(task_id)  # may raise if transition illegal

        max_attempts = self.retry_policy.max_attempts
        for attempt in range(1, max_attempts + 1):
            self.attempts[task_id] = attempt
            self.stats.attempts += 1

            # 1) Deadline enforcement
            if self.deadline is not None and self.deadline.is_expired(task_id):
                self.harness.mark_failed(task_id, result="deadline exceeded")
                self.status[task_id] = RunningStatus.EXPIRED
                self.results[task_id] = "deadline exceeded"
                self.stats.expired += 1
                self.retriable.discard(task_id)
                self._running.discard(task_id)
                return RunningStatus.EXPIRED

            # 2) Stall watchdog: if the *previous* cycle left this task silent
            #    past the heartbeat timeout, treat it as a retryable condition.
            if self.heartbeat is not None and self.heartbeat.is_stalled(task_id):
                if attempt < max_attempts:
                    self.status[task_id] = RunningStatus.RUNNING_RETRY
                    self.retriable.add(task_id)
                    self.stats.retried += 1
                    self.sleep(self.retry_policy.delay(attempt))
                    # Restore liveness before doing the next unit of work.
                    self._emit_heartbeat(task_id)
                    continue
                self.harness.mark_failed(task_id, result="stalled (no heartbeat)")
                self.status[task_id] = RunningStatus.RUNNING_PERMANENT
                self.errors[task_id] = TimeoutError("stalled: no heartbeat")
                self.stats.stalled_failed += 1
                self.retriable.discard(task_id)
                self._running.discard(task_id)
                return RunningStatus.RUNNING_PERMANENT

            # 3) Heartbeat (liveness) — emit before doing work.
            self._emit_heartbeat(task_id)

            # 4) Execute the injected task function.
            try:
                result = self.executor(card)
            except Exception as exc:  # noqa: BLE001 - capture ALL failures
                self.errors[task_id] = exc
                cls = self.error_classifier.classify(exc)
                if cls is ErrorClass.PERMANENT or attempt >= max_attempts:
                    self.harness.mark_failed(
                        task_id,
                        result=f"{type(exc).__name__}: {exc}",
                    )
                    self.status[task_id] = RunningStatus.RUNNING_PERMANENT
                    self.stats.failed += 1
                    self.retriable.discard(task_id)
                    self._running.discard(task_id)
                    return RunningStatus.RUNNING_PERMANENT

                # Retryable error -> backoff and retry.
                self.status[task_id] = RunningStatus.RUNNING_RETRY
                self.stats.retried += 1
                delay = self.retry_policy.delay(attempt)
                self.sleep(delay)
                continue
            else:
                self.harness.mark_completed(
                    task_id,
                    result=str(result) if result is not None else None,
                )
                self.status[task_id] = RunningStatus.RUNNING
                self.results[task_id] = result
                self.stats.completed += 1
                self.retriable.discard(task_id)
                self._running.discard(task_id)
                return RunningStatus.RUNNING

        # Defensive: all attempts consumed and loop fell through.
        self.harness.mark_failed(task_id, result="attempts exhausted")
        self.status[task_id] = RunningStatus.RUNNING_PERMANENT
        self.stats.failed += 1
        self.retriable.discard(task_id)
        self._running.discard(task_id)
        return RunningStatus.RUNNING_PERMANENT

    def _emit_heartbeat(self, task_id: str) -> None:
        if self.heartbeat is not None:
            self.heartbeat.beat(task_id)
        if self.on_heartbeat is not None:
            self.on_heartbeat(task_id)

    # ------------------------------------------------------------------
    # Loop drivers
    # ------------------------------------------------------------------
    def run_once(self) -> RunningStatus | None:
        """Claim one runnable task and run it to completion.

        Returns the :class:`RunningStatus` outcome, or ``None`` if there is
        nothing runnable (all work drained or blocked on dependencies).
        """
        card = self.claim()
        if card is None:
            return None
        return self.run_task(card.id)

    def run(self, max_iterations: int | None = None) -> RunnerStats:
        """Run the claim->execute loop until no runnable tasks remain.

        ``max_iterations`` caps the number of tasks processed (useful for
        bounded draining and tests).  Returns the aggregate stats.
        """
        iterations = 0
        while max_iterations is None or iterations < max_iterations:
            outcome = self.run_once()
            if outcome is None:
                break
            iterations += 1
        return self.stats


# ===========================================================================
# Convenience builder
# ===========================================================================
def build_runner(
    harness: TaskHarness,
    *,
    executor: Callable[[TaskCard], Any] | None = None,
    max_attempts: int = 3,
    backoff: float | Callable[[int], float] = 1.0,
    max_runtime: float | None = None,
    heartbeat_timeout: float | None = None,
    clock: Callable[[], float] | None = None,
    sleep: Callable[[float], None] | None = None,
    **kwargs: Any,
) -> WorkerRunner:
    """Convenience factory wiring retry/deadline/heartbeat from simple args."""
    clock = clock or _time.monotonic
    sleep = sleep or _time.sleep
    retry_policy = RetryPolicy(max_attempts=max_attempts, backoff=backoff)
    deadline = Deadline(max_runtime, clock) if max_runtime is not None else None
    heartbeat = Heartbeat(heartbeat_timeout, clock) if heartbeat_timeout is not None else None
    return WorkerRunner(
        harness,
        executor=executor,
        retry_policy=retry_policy,
        deadline=deadline,
        heartbeat=heartbeat,
        clock=clock,
        sleep=sleep,
        **kwargs,
    )
