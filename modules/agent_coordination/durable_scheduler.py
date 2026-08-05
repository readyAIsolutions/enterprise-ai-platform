"""
Durable Task Scheduler + Message Bus for Agent Coordination (MASTER CLASS).

A Temporal-style durable execution layer built on the stdlib (sqlite3 + time).
Provides three cooperating components:

    DurableScheduler
        SQLite-backed scheduler. Tasks are scheduled with an ETA, priority,
        max-retries and an optional dedupe key. Workers ``claim_next`` with a
        *lease* (exclusive ownership for ``lease_seconds``) and must keep the
        lease alive with ``heartbeat``; expired leases are reclaimed so a
        crashed worker's work is retried by someone else. Tasks move through
        the lifecycle: pending -> claimed -> completed | failed | dead-lettered.

    TaskQueue
        A durable priority queue with deadline semantics. Items are
        enqueued/dequeued (with a lease) and a ``peek`` / ``stats`` view.

    SchedulerBus
        Combines scheduling with resilient message dispatch: handlers are
        registered per topic, messages are scheduled as durable tasks, and
        delivery is retried with backoff up to a bound before being routed to a
        dead-letter table.

Design notes (Temporal pattern ripped):
    * Work is stored durably BEFORE it is handed to a worker (write-ahead).
    * A worker owns a unit of work only for the duration of its lease; the
      lease is the liveness signal, not the worker process.
    * Failure is expressed as retry-able (bounded) or terminal (dead-letter),
      never as silent data loss.
    * All persistence is restart-safe: reopening the same ``db_path`` reloads
      every pending / in-flight / dead-lettered unit.

Injectable clock: pass ``clock`` (a zero-arg callable returning epoch seconds,
or an object with a ``now()`` method) for deterministic tests. Defaults to
``time.time``.

Config: ``db_path``. Pass ``None`` for an in-memory database (ideal for tests).
Pass a directory path to persist a ``tasks.sqlite`` file inside it. Pass a
file path ending in ``.db``/``.sqlite`` to use that exact file.
"""

from __future__ import annotations

import contextlib
import json
import sqlite3
import threading
import time
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable

__all__ = [
    "DurableScheduler",
    "TaskQueue",
    "SchedulerBus",
    "TaskStatus",
    "SchedulerError",
    "LeaseError",
    "TaskNotFoundError",
    "DeadLetterError",
]


# ---------------------------------------------------------------------------
# Statuses / errors
# ---------------------------------------------------------------------------


class TaskStatus(StrEnum):
    PENDING = "pending"
    CLAIMED = "claimed"
    COMPLETED = "completed"
    FAILED = "failed"
    DEAD_LETTERED = "dead_lettered"
    CANCELLED = "cancelled"


class SchedulerError(Exception):
    """Base error for the durable scheduler."""


class LeaseError(SchedulerError):
    """Raised when a worker tries to mutate a task it does not own."""


class TaskNotFoundError(SchedulerError):
    """Raised when an operation targets a task_id that does not exist."""


class DeadLetterError(SchedulerError):
    """Raised when a task exceeds its retry budget and is dead-lettered."""


# ---------------------------------------------------------------------------
# Clock helpers
# ---------------------------------------------------------------------------


class _RealClock:
    """Default clock: real wall-clock epoch seconds."""

    def now(self) -> float:
        return time.time()

    def __call__(self) -> float:
        return self.now()


def _normalize_clock(clock: Callable[[], float] | None) -> Callable[[], float]:
    """Accept a zero-arg callable OR an object with a ``now()`` method."""
    if clock is None:
        return _RealClock()
    if hasattr(clock, "now") and callable(clock.now):
        now = clock.now
        return lambda: now()
    if callable(clock):
        return clock
    msg = "clock must be a zero-arg callable or have a now() method"
    raise TypeError(msg)


# ---------------------------------------------------------------------------
# SQLite plumbing
# ---------------------------------------------------------------------------


def _resolve_db_path(db_path: str | Path | None) -> str:
    """Return a sqlite3 connect string for the requested db_path.

    * None            -> ':memory:' (in-memory, for tests).
    * a directory     -> <dir>/tasks.sqlite
    * a file ending in
      .db / .sqlite   -> that exact file
    """
    if db_path is None:
        return ":memory:"
    path = Path(db_path)
    if path.suffix in (".db", ".sqlite", ".sqlite3"):
        path.parent.mkdir(parents=True, exist_ok=True)
        return str(path)
    # Treat as directory.
    path.mkdir(parents=True, exist_ok=True)
    return str(path / "tasks.sqlite")


_SCHEMA = """
CREATE TABLE IF NOT EXISTS tasks (
    task_id       TEXT PRIMARY KEY,
    fn_payload    TEXT NOT NULL,
    eta           REAL NOT NULL,
    priority      INTEGER NOT NULL DEFAULT 0,
    max_retries   INTEGER NOT NULL DEFAULT 0,
    retry_count   INTEGER NOT NULL DEFAULT 0,
    dedupe_key    TEXT,
    status        TEXT NOT NULL DEFAULT 'pending',
    worker_id     TEXT,
    lease_until   REAL,
    created_at    REAL NOT NULL,
    updated_at    REAL NOT NULL,
    last_error    TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_tasks_dedupe
    ON tasks(dedupe_key) WHERE dedupe_key IS NOT NULL;

CREATE TABLE IF NOT EXISTS queue_items (
    item_id     TEXT PRIMARY KEY,
    payload     TEXT NOT NULL,
    priority    INTEGER NOT NULL DEFAULT 0,
    deadline    REAL,
    status      TEXT NOT NULL DEFAULT 'pending',
    worker_id   TEXT,
    lease_until REAL,
    created_at  REAL NOT NULL,
    updated_at  REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS dead_letters (
    dead_id     TEXT PRIMARY KEY,
    task_id     TEXT,
    topic       TEXT,
    payload     TEXT,
    attempts    INTEGER NOT NULL,
    last_error  TEXT,
    created_at  REAL NOT NULL,
    updated_at  REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_tasks_claim
    ON tasks(status, eta, priority);
"""


# ---------------------------------------------------------------------------
# Task record
# ---------------------------------------------------------------------------


@dataclass
class TaskRecord:
    """A snapshot of one scheduled task."""

    task_id: str
    fn_payload: str
    eta: float
    priority: int
    max_retries: int
    retry_count: int
    status: str
    worker_id: str | None = None
    lease_until: float | None = None
    dedupe_key: str | None = None
    created_at: float = 0.0
    updated_at: float = 0.0
    last_error: str | None = None

    @property
    def payload(self) -> Any:  # noqa: ANN401  # JSON-decoded dynamic payload
        try:
            return json.loads(self.fn_payload)
        except (TypeError, ValueError):
            return self.fn_payload

    @property
    def expired(self) -> bool:
        return False  # convenience stub; lease expiry handled by scheduler


# ---------------------------------------------------------------------------
# DurableScheduler
# ---------------------------------------------------------------------------


class DurableScheduler:
    """A durable, restart-safe task scheduler with lease-based ownership.

    Thread-safe. Every mutation is wrapped in a transaction.
    """

    def __init__(
        self,
        db_path: str | Path | None = None,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self._conn_str = _resolve_db_path(db_path)
        self._clock = _normalize_clock(clock)
        self._lock = threading.RLock()
        # check_same_thread=False + our own lock lets workers on other threads
        # share one scheduler safely; sqlite serialises internally.
        self._conn = sqlite3.connect(self._conn_str, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._conn:
            self._conn.executescript(_SCHEMA)

    # -- clock -----------------------------------------------------------

    def now(self) -> float:
        return self._clock()

    # -- low-level helpers --------------------------------------------------

    def _exec(self, sql: str, params: tuple[Any, ...] = ()) -> sqlite3.Cursor:
        with self._lock:
            cur = self._conn.execute(sql, params)
            self._conn.commit()
            return cur

    def _row_to_task(self, row: sqlite3.Row) -> TaskRecord:
        return TaskRecord(
            task_id=row["task_id"],
            fn_payload=row["fn_payload"],
            eta=row["eta"],
            priority=row["priority"],
            max_retries=row["max_retries"],
            retry_count=row["retry_count"],
            dedupe_key=row["dedupe_key"],
            status=row["status"],
            worker_id=row["worker_id"],
            lease_until=row["lease_until"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            last_error=row["last_error"],
        )

    # -- scheduling ----------------------------------------------------------

    def schedule(
        self,
        task_id: str,
        fn_payload: Any,  # noqa: ANN401  # arbitrary serializable payload
        eta: float | None = None,
        priority: int = 0,
        max_retries: int = 0,
        dedupe_key: str | None = None,
    ) -> str:
        """Register a durable task. Returns ``task_id``.

        If ``dedupe_key`` is given and a task with that key already exists,
        the schedule is idempotent: the existing task_id is returned and no
        duplicate is inserted.
        """
        if not isinstance(fn_payload, str):
            fn_payload = json.dumps(fn_payload)
        now = self.now()
        if eta is None:
            eta = now
        if max_retries < 0:
            msg = "max_retries must be >= 0"
            raise ValueError(msg)
        with self._lock:
            if dedupe_key is not None:
                row = self._conn.execute(
                    "SELECT task_id FROM tasks WHERE dedupe_key = ?",
                    (dedupe_key,),
                ).fetchone()
                if row is not None:
                    self._conn.commit()
                    return row["task_id"]
            try:
                self._conn.execute(
                    """
                    INSERT INTO tasks
                        (task_id, fn_payload, eta, priority, max_retries,
                         retry_count, dedupe_key, status, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, 0, ?, 'pending', ?, ?)
                    """,
                    (
                        task_id,
                        fn_payload,
                        eta,
                        priority,
                        max_retries,
                        dedupe_key,
                        now,
                        now,
                    ),
                )
                self._conn.commit()
            except sqlite3.IntegrityError:
                # Duplicate primary key OR duplicate dedupe_key raced in.
                self._conn.rollback()
                # If it was a dedupe collision, honour idempotency.
                if dedupe_key is not None:
                    row = self._conn.execute(
                        "SELECT task_id FROM tasks WHERE dedupe_key = ?",
                        (dedupe_key,),
                    ).fetchone()
                    if row is not None:
                        self._conn.commit()
                        return row["task_id"]
                msg = f"task_id {task_id!r} already exists"
                raise SchedulerError(msg) from None
            return task_id

    def get_task(self, task_id: str) -> TaskRecord | None:
        with self._lock:
            row = self._conn.execute("SELECT * FROM tasks WHERE task_id = ?", (task_id,)).fetchone()
            self._conn.commit()
            return self._row_to_task(row) if row is not None else None

    # -- leasing ----------------------------------------------------------

    def recover_expired_leases(self, now: float | None = None) -> int:
        """Reclaim tasks whose lease has expired.

        Any ``claimed`` task with ``lease_until <= now`` is put back to
        ``pending`` (worker/lease cleared). This is the crash-recovery path:
        a worker that died mid-run loses its lease and its work becomes
        available to others. Returns the number of tasks reclaimed.
        """
        if now is None:
            now = self.now()
        with self._lock:
            cur = self._conn.execute(
                """
                UPDATE tasks
                SET status = 'pending', worker_id = NULL, lease_until = NULL,
                    updated_at = ?
                WHERE status = 'claimed' AND lease_until IS NOT NULL
                      AND lease_until <= ?
                """,
                (now, now),
            )
            self._conn.commit()
            return cur.rowcount

    def claim_next(self, worker_id: str, lease_seconds: float = 30.0) -> TaskRecord | None:
        """Claim the highest-priority due task for ``worker_id``.

        Runs inside a transaction so two workers cannot claim the same task.
        Returns ``None`` when nothing is due. Higher ``priority`` wins; ties go
        to earliest ``eta``, then insertion order.
        """
        if lease_seconds < 0:
            msg = "lease_seconds must be >= 0"
            raise ValueError(msg)
        now = self.now()
        with self._lock:
            self.recover_expired_leases(now)  # reclaim stale work first
            row = self._conn.execute(
                """
                SELECT * FROM tasks
                WHERE status = 'pending' AND eta <= ?
                ORDER BY priority DESC, eta ASC, rowid ASC
                LIMIT 1
                """,
                (now,),
            ).fetchone()
            if row is None:
                self._conn.commit()
                return None
            task = self._row_to_task(row)
            self._conn.execute(
                """
                UPDATE tasks
                SET status = 'claimed', worker_id = ?, lease_until = ?,
                    updated_at = ?
                WHERE task_id = ?
                """,
                (worker_id, now + lease_seconds, now, task.task_id),
            )
            self._conn.commit()
            task.status = TaskStatus.CLAIMED.value
            task.worker_id = worker_id
            task.lease_until = now + lease_seconds
            task.updated_at = now
            return task

    def heartbeat(self, task_id: str, worker_id: str, lease_seconds: float = 30.0) -> bool:
        """Extend a task's lease, verifying the caller still owns it."""
        now = self.now()
        with self._lock:
            row = self._conn.execute("SELECT * FROM tasks WHERE task_id = ?", (task_id,)).fetchone()
            if row is None:
                self._conn.commit()
                raise TaskNotFoundError(task_id)
            if row["worker_id"] != worker_id:
                self._conn.commit()
                msg = f"task {task_id!r} is leased to {row['worker_id']!r}, not {worker_id!r}"
                raise LeaseError(msg)
            cur = self._conn.execute(
                """
                UPDATE tasks
                SET lease_until = ?, updated_at = ?
                WHERE task_id = ?
                """,
                (now + lease_seconds, now, task_id),
            )
            self._conn.commit()
            return cur.rowcount == 1

    # -- completion / failure -------------------------------------------------

    def _require_owner(self, task_id: str, worker_id: str | None) -> sqlite3.Row:
        row = self._conn.execute("SELECT * FROM tasks WHERE task_id = ?", (task_id,)).fetchone()
        if row is None:
            self._conn.commit()
            raise TaskNotFoundError(task_id)
        if worker_id is not None and row["worker_id"] != worker_id:
            self._conn.commit()
            msg = f"task {task_id!r} is leased to {row['worker_id']!r}, not {worker_id!r}"
            raise LeaseError(msg)
        return row

    def complete(self, task_id: str, worker_id: str | None = None, result: Any = None) -> bool:  # noqa: ARG002, ANN401
        """Mark a task completed (optionally verifying lease ownership)."""
        with self._lock:
            self._require_owner(task_id, worker_id)
            cur = self._conn.execute(
                """
                UPDATE tasks
                SET status = 'completed', worker_id = NULL, lease_until = NULL,
                    updated_at = ?
                WHERE task_id = ?
                """,
                (self.now(), task_id),
            )
            self._conn.commit()
            return cur.rowcount == 1

    def retry(
        self,
        task_id: str,
        worker_id: str | None = None,
        error: str | None = None,
        eta: float | None = None,
    ) -> str:
        """Increment the retry budget.

        If ``retry_count`` is still below ``max_retries``, the task returns to
        ``pending`` (optionally at a future ``eta`` for backoff). If the budget
        is exhausted the task is moved to ``failed``. Returns the resulting
        status: ``'pending'`` or ``'failed'``.
        """
        with self._lock:
            row = self._require_owner(task_id, worker_id)
            retries = row["retry_count"] + 1
            max_retries = row["max_retries"]
            now = self.now()
            if retries > max_retries:
                self._conn.execute(
                    """
                    UPDATE tasks
                    SET status = 'failed', worker_id = NULL, lease_until = NULL,
                        retry_count = ?, last_error = ?, updated_at = ?
                    WHERE task_id = ?
                    """,
                    (retries, error, now, task_id),
                )
                self._conn.commit()
                return TaskStatus.FAILED.value
            self._conn.execute(
                """
                UPDATE tasks
                SET status = 'pending', worker_id = NULL, lease_until = NULL,
                    retry_count = ?, last_error = ?, eta = ?, updated_at = ?
                WHERE task_id = ?
                """,
                (retries, error, eta if eta is not None else now, now, task_id),
            )
            self._conn.commit()
            return TaskStatus.PENDING.value

    def fail(
        self,
        task_id: str,
        worker_id: str | None = None,
        error: str | None = None,
        max_retries: int | None = None,
    ) -> str:
        """Force-fail a task immediately (no further retries).

        Respects ``max_retries``: if the task still has budget, it is retried;
        otherwise it becomes ``failed``. This gives callers a single escape
        hatch for deterministic failures while preserving bounded retry.
        """
        with self._lock:
            row = self._require_owner(task_id, worker_id)
            if max_retries is None:
                max_retries = row["max_retries"]
            if row["retry_count"] < max_retries:
                return self.retry(task_id, worker_id, error)
            now = self.now()
            self._conn.execute(
                """
                UPDATE tasks
                SET status = 'failed', worker_id = NULL, lease_until = NULL,
                    last_error = ?, updated_at = ?
                WHERE task_id = ?
                """,
                (error, now, task_id),
            )
            self._conn.commit()
            return TaskStatus.FAILED.value

    def cancel(self, task_id: str) -> bool:
        """Cancel a pending task (no-op if it is not pending)."""
        with self._lock:
            cur = self._conn.execute(
                """
                UPDATE tasks
                SET status = 'cancelled', worker_id = NULL, lease_until = NULL,
                    updated_at = ?
                WHERE task_id = ? AND status = 'pending'
                """,
                (self.now(), task_id),
            )
            self._conn.commit()
            return cur.rowcount == 1

    # -- stats / inspection ------------------------------------------------

    def stats(self) -> dict[str, int]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT status, COUNT(*) AS n FROM tasks GROUP BY status"
            ).fetchall()
            self._conn.commit()
            counts: dict[str, int] = {s.value: 0 for s in TaskStatus}
            for r in rows:
                counts[r["status"]] = r["n"]
            return counts

    def tasks_in_status(self, status: TaskStatus | str) -> list[TaskRecord]:
        st = status.value if isinstance(status, TaskStatus) else status
        with self._lock:
            rows = self._conn.execute("SELECT * FROM tasks WHERE status = ?", (st,)).fetchall()
            self._conn.commit()
            return [self._row_to_task(r) for r in rows]

    def all_tasks(self) -> list[TaskRecord]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM tasks ORDER BY priority DESC, eta ASC"
            ).fetchall()
            self._conn.commit()
            return [self._row_to_task(r) for r in rows]

    # -- lifecycle ---------------------------------------------------------

    def close(self) -> None:
        with self._lock, contextlib.suppress(sqlite3.Error):
            self._conn.close()

    def __enter__(self) -> DurableScheduler:
        return self

    def __exit__(self, *exc: Any) -> None:  # noqa: ANN401  # signal frame/exc tuple is dynamic
        self.close()


# ---------------------------------------------------------------------------
# TaskQueue
# ---------------------------------------------------------------------------


class TaskQueue:
    """A durable priority queue with deadline semantics.

    Backed by SQLite (shared ``db_path``) so the queue survives restarts.
    Items past their ``deadline`` are excluded from ``dequeue``/``peek`` and
    can be swept with ``expire_overdue``.
    """

    def __init__(
        self,
        db_path: str | Path | None = None,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self._conn_str = _resolve_db_path(db_path)
        self._clock = _normalize_clock(clock)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(self._conn_str, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._conn:
            self._conn.executescript(_SCHEMA)

    def now(self) -> float:
        return self._clock()

    def enqueue(
        self,
        item_id: str,
        payload: Any,  # noqa: ANN401  # arbitrary serializable payload
        priority: int = 0,
        deadline: float | None = None,
    ) -> str:
        if not isinstance(payload, str):
            payload = json.dumps(payload)
        now = self.now()
        with self._lock:
            try:
                self._conn.execute(
                    """
                    INSERT INTO queue_items
                        (item_id, payload, priority, deadline, status,
                         created_at, updated_at)
                    VALUES (?, ?, ?, ?, 'pending', ?, ?)
                    """,
                    (item_id, payload, priority, deadline, now, now),
                )
                self._conn.commit()
            except sqlite3.IntegrityError:
                self._conn.rollback()
                msg = f"item_id {item_id!r} already exists"
                raise SchedulerError(msg) from None
            return item_id

    def peek(self) -> tuple[str, Any] | None:
        """Return the next dispatchable item without removing it."""
        now = self.now()
        with self._lock:
            row = self._conn.execute(
                """
                SELECT * FROM queue_items
                WHERE status = 'pending'
                  AND (deadline IS NULL OR deadline > ?)
                ORDER BY priority DESC, created_at ASC, rowid ASC
                LIMIT 1
                """,
                (now,),
            ).fetchone()
            self._conn.commit()
            if row is None:
                return None
            try:
                payload = json.loads(row["payload"])
            except (TypeError, ValueError):
                payload = row["payload"]
            return (row["item_id"], payload)

    def dequeue(self, worker_id: str, lease_seconds: float = 30.0) -> tuple[str, Any] | None:
        """Atomically remove and lease the next item. Returns ``None`` if empty."""
        now = self.now()
        with self._lock:
            row = self._conn.execute(
                """
                SELECT * FROM queue_items
                WHERE status = 'pending'
                  AND (deadline IS NULL OR deadline > ?)
                ORDER BY priority DESC, created_at ASC, rowid ASC
                LIMIT 1
                """,
                (now,),
            ).fetchone()
            if row is None:
                self._conn.commit()
                return None
            self._conn.execute(
                """
                UPDATE queue_items
                SET status = 'leased', worker_id = ?, lease_until = ?,
                    updated_at = ?
                WHERE item_id = ?
                """,
                (worker_id, now + lease_seconds, now, row["item_id"]),
            )
            self._conn.commit()
            try:
                payload = json.loads(row["payload"])
            except (TypeError, ValueError):
                payload = row["payload"]
            return (row["item_id"], payload)

    def release(self, item_id: str, worker_id: str | None = None) -> bool:  # noqa: ARG002
        """Return a leased item to ``pending`` (e.g. worker died, retry)."""
        now = self.now()
        with self._lock:
            cur = self._conn.execute(
                """
                UPDATE queue_items
                SET status = 'pending', worker_id = NULL, lease_until = NULL,
                    updated_at = ?
                WHERE item_id = ?
                """,
                (now, item_id),
            )
            self._conn.commit()
            return cur.rowcount == 1

    def ack(self, item_id: str, worker_id: str | None = None) -> bool:  # noqa: ARG002
        """Mark an item as completed and remove it from the active queue."""
        now = self.now()
        with self._lock:
            cur = self._conn.execute(
                """
                UPDATE queue_items
                SET status = 'completed', worker_id = NULL, lease_until = NULL,
                    updated_at = ?
                WHERE item_id = ?
                """,
                (now, item_id),
            )
            self._conn.commit()
            return cur.rowcount == 1

    def expire_overdue(self, now: float | None = None) -> int:
        """Mark items past their deadline as timed-out. Returns count."""
        if now is None:
            now = self.now()
        with self._lock:
            cur = self._conn.execute(
                """
                UPDATE queue_items
                SET status = 'timed_out', worker_id = NULL, lease_until = NULL,
                    updated_at = ?
                WHERE deadline IS NOT NULL AND deadline <= ? AND status = 'pending'
                """,
                (now, now),
            )
            self._conn.commit()
            return cur.rowcount

    def stats(self) -> dict[str, int]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT status, COUNT(*) AS n FROM queue_items GROUP BY status"
            ).fetchall()
            self._conn.commit()
            counts: dict[str, int] = {
                "pending": 0,
                "leased": 0,
                "completed": 0,
                "timed_out": 0,
            }
            for r in rows:
                counts[r["status"]] = r["n"]
            return counts

    def close(self) -> None:
        with self._lock, contextlib.suppress(sqlite3.Error):
            self._conn.close()


# ---------------------------------------------------------------------------
# SchedulerBus
# ---------------------------------------------------------------------------


class SchedulerBus:
    """Resilient message dispatch built on the durable scheduler.

    Combine scheduling with message handling:

        * ``publish(topic, payload)`` schedules a durable dispatch task.
        * ``register_handler(topic, fn)`` binds a topic to a handler.
        * ``process(worker_id, lease_seconds, max_dispatch=None)`` claims due
          dispatch tasks, invokes the matching handler, and on success marks
          them complete; on failure it retries (bounded by the task's
          ``max_retries``) then routes to a durable dead-letter table.
        * ``dead_letters()`` lists undeliverable messages.

    ``dedupe_key`` on publish guarantees at-least-once without duplicate spam:
    re-publishing the same key is idempotent.
    """

    #: Key used to mark a task as a bus dispatch message in its fn_payload.
    _TOPIC_FIELD = "__topic__"
    _MSG_FIELD = "__message__"

    def __init__(
        self,
        db_path: str | Path | None = None,
        clock: Callable[[], float] | None = None,
        scheduler: DurableScheduler | None = None,
    ) -> None:
        self._scheduler = scheduler or DurableScheduler(db_path=db_path, clock=clock)
        self._handlers: dict[str, Callable[[Any], Any]] = {}
        self._lock = threading.RLock()

    @property
    def scheduler(self) -> DurableScheduler:
        return self._scheduler

    def register_handler(self, topic: str, fn: Callable[[Any], Any]) -> None:
        with self._lock:
            self._handlers[topic] = fn

    def publish(
        self,
        topic: str,
        payload: Any,  # noqa: ANN401  # arbitrary serializable payload
        eta: float | None = None,
        priority: int = 0,
        max_retries: int = 2,
        dedupe_key: str | None = None,
    ) -> str:
        """Schedule a durable dispatch for ``topic``. Returns the task_id."""
        msg = {self._TOPIC_FIELD: topic, self._MSG_FIELD: payload}
        task_id = f"msg::{topic}::{self._scheduler.now()}::{abs(hash(str(payload)))}"
        self._scheduler.schedule(
            task_id=task_id,
            fn_payload=msg,
            eta=eta,
            priority=priority,
            max_retries=max_retries,
            dedupe_key=dedupe_key,
        )
        return task_id

    def _dead_letter(
        self,
        task: TaskRecord,
        topic: str,
        error: str,
        attempts: int,
    ) -> None:
        now = self._scheduler.now()
        with self._lock:
            self._scheduler._conn.execute(
                """
                INSERT INTO dead_letters
                    (dead_id, task_id, topic, payload, attempts, last_error,
                     created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    task.task_id,
                    task.task_id,
                    topic,
                    task.fn_payload,
                    attempts,
                    error,
                    now,
                    now,
                ),
            )
            self._scheduler._conn.commit()

    def process(
        self,
        worker_id: str,
        lease_seconds: float = 30.0,
        max_dispatch: int | None = None,
    ) -> int:
        """Dispatch due messages until none remain (or ``max_dispatch`` hit).

        Returns the number of dispatch tasks processed.
        """
        dispatched = 0
        while max_dispatch is None or dispatched < max_dispatch:
            task = self._scheduler.claim_next(worker_id, lease_seconds)
            if task is None:
                break
            topic = None
            try:
                payload = task.payload
                if isinstance(payload, dict):
                    topic = payload.get(self._TOPIC_FIELD)
                    message = payload.get(self._MSG_FIELD, payload)
                else:
                    topic = None
                    message = payload
                if topic is None or topic not in self._handlers:
                    self._scheduler.complete(task.task_id, worker_id)
                    dispatched += 1
                    continue
                handler = self._handlers[topic]
                handler(message)
                self._scheduler.complete(task.task_id, worker_id)
            except Exception as exc:  # noqa: BLE001 - route to retry/dead-letter
                error = f"{type(exc).__name__}: {exc}"
                if topic is None:
                    topic = "<unparsed>"
                outcome = self._scheduler.retry(task.task_id, worker_id, error=error)
                if outcome == TaskStatus.FAILED.value:
                    self._dead_letter(task, topic, error, task.retry_count + 1)
            dispatched += 1
        return dispatched

    def dead_letters(self) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._scheduler._conn.execute(
                "SELECT * FROM dead_letters ORDER BY created_at DESC"
            ).fetchall()
            self._scheduler._conn.commit()
            return [dict(r) for r in rows]

    def outstanding(self) -> list[TaskRecord]:
        """Pending + claimed (in-flight) dispatch tasks."""
        return [
            t
            for t in self._scheduler.all_tasks()
            if t.status in (TaskStatus.PENDING.value, TaskStatus.CLAIMED.value)
        ]

    def close(self) -> None:
        self._scheduler.close()


# ---------------------------------------------------------------------------
# Convenience factory
# ---------------------------------------------------------------------------


def create_durable_scheduler(
    db_path: str | Path | None = None,
    clock: Callable[[], float] | None = None,
) -> DurableScheduler:
    """Factory returning a ``DurableScheduler`` (db_path None => in-memory)."""
    return DurableScheduler(db_path=db_path, clock=clock)
