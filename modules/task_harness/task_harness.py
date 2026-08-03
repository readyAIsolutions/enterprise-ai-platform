"""
task_harness — Maestro-style long-running task harness.

Enterprise-grade SQLite-backed task cards that let an agent pause, resume,
and track deep refactors.  Structured state machine with dependency ordering,
priority scheduling, and heartbeat liveness so a background agent can manage
long-running work without losing context.

Design notes:
  - Pure-stdlib (sqlite3 only; no external deps).
  - The SQLite layer takes an explicit `db_path`, so tests can inject
    `tmp_path` and never touch real IO.
  - All state transitions are guarded; illegal transitions raise
    `TaskHarnessError`.

Python: 3.10+
"""

from __future__ import annotations

import builtins
import json
import logging
import sqlite3
import threading
import uuid
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Logger
# ---------------------------------------------------------------------------
_log: logging.Logger = logging.getLogger("enterprise.task_harness")


# ===========================================================================
# Exceptions
# ===========================================================================
class TaskHarnessError(Exception):
    """Base error for all task-harness failures."""


class TaskNotFoundError(TaskHarnessError):
    """Raised when a task id does not exist in the store."""


class InvalidTransitionError(TaskHarnessError):
    """Raised when a task status transition is not permitted."""


class DependencyNotSatisfiedError(TaskHarnessError):
    """Raised when a task cannot run because dependencies are unfinished."""


# ===========================================================================
# Enums & dataclasses
# ===========================================================================
class TaskStatus(Enum):
    """Lifecycle state of a task card."""

    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.value


# Allowed state-machine transitions.
#   current -> { allowed next states }
_ALLOWED_TRANSITIONS: dict[TaskStatus, set] = {
    TaskStatus.PENDING: {
        TaskStatus.RUNNING,     # start work
        TaskStatus.CANCELLED,   # abandon before starting
        TaskStatus.FAILED,      # doomed up front
    },
    TaskStatus.RUNNING: {
        TaskStatus.PAUSED,      # pause long-running work
        TaskStatus.COMPLETED,   # finished
        TaskStatus.FAILED,      # errored
        TaskStatus.CANCELLED,   # aborted mid-flight
    },
    TaskStatus.PAUSED: {
        TaskStatus.RUNNING,     # resume
        TaskStatus.FAILED,      # give up while paused
        TaskStatus.CANCELLED,   # drop while paused
    },
    TaskStatus.COMPLETED: set(),   # terminal
    TaskStatus.FAILED: set(),      # terminal
    TaskStatus.CANCELLED: set(),   # terminal
}

# Statuses that count as "satisfying" a dependency.
_SATISFYING_STATUSES: frozenset = frozenset(
    {TaskStatus.COMPLETED, TaskStatus.CANCELLED}
)


def _utcnow() -> str:
    """UTC timestamp as ISO-8601 string."""
    return datetime.now(UTC).isoformat()


@dataclass
class TaskCard:
    """A single long-running task card.

    Attributes:
        id: Unique string identifier (uuid4).
        title: Human-readable task title.
        description: Free-form description of the work.
        status: Current lifecycle status.
        priority: Scheduling priority (higher = more urgent).
        depends_on: Ids of tasks that must finish before this one runs.
        steps: Ordered steps that make up the task (list of strings).
        notes: Free-form scratch/context notes for the agent.
        result: Optional final result payload string once completed.
        created_at / updated_at: ISO-8601 UTC timestamps.
    """

    id: str
    title: str
    description: str
    status: TaskStatus = TaskStatus.PENDING
    priority: int = 0
    depends_on: list[str] = field(default_factory=list)
    steps: list[str] = field(default_factory=list)
    notes: str = ""
    result: str | None = None
    created_at: str = field(default_factory=_utcnow)
    updated_at: str = field(default_factory=_utcnow)

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> TaskCard:
        """Build a TaskCard from a raw sqlite3.Row."""
        d: dict[str, Any] = dict(row)
        raw_status = d.pop("status")
        try:
            status = TaskStatus(raw_status)
        except ValueError:
            status = TaskStatus.PENDING
        depends_on = _json_loads_list(d.pop("depends_on"))
        steps = _json_loads_list(d.pop("steps"))
        notes = _json_loads_str(d.pop("notes"))
        result = _json_loads_optional(d.pop("result"))
        return cls(
            id=d.pop("id"),
            title=d.pop("title"),
            description=d.pop("description", ""),
            status=status,
            priority=int(d.pop("priority", 0)),
            depends_on=depends_on,
            steps=steps,
            notes=notes,
            result=result,
            created_at=d.pop("created_at", ""),
            updated_at=d.pop("updated_at", ""),
        )

    @property
    def is_terminal(self) -> bool:
        return self.status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-friendly dict."""
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "status": self.status.value,
            "priority": self.priority,
            "depends_on": list(self.depends_on),
            "steps": list(self.steps),
            "notes": self.notes,
            "result": self.result,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


def _json_loads_list(raw: str | None) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, list):
        return [str(x) for x in raw]
    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return []
    if isinstance(parsed, list):
        return [str(x) for x in parsed]
    return []


def _json_loads_str(raw: str | None) -> str:
    if raw is None:
        return ""
    if isinstance(raw, str):
        # Stored via json.dumps(...) so it may be a quoted string.
        try:
            decoded = json.loads(raw)
            return decoded if isinstance(decoded, str) else raw
        except (json.JSONDecodeError, TypeError):
            return raw
    return str(raw)


def _json_loads_optional(raw: str | None) -> str | None:
    if raw is None:
        return None
    if isinstance(raw, str):
        try:
            decoded = json.loads(raw)
            return decoded if isinstance(decoded, str) else raw
        except (json.JSONDecodeError, TypeError):
            return raw
    return str(raw)


# ===========================================================================
# SQLite-backed task store
# ===========================================================================
_SCHEMA = """
CREATE TABLE IF NOT EXISTS task_cards (
    id           TEXT PRIMARY KEY,
    title        TEXT NOT NULL,
    description  TEXT NOT NULL DEFAULT '',
    status       TEXT NOT NULL,
    priority     INTEGER NOT NULL DEFAULT 0,
    depends_on   TEXT NOT NULL DEFAULT '[]',
    steps        TEXT NOT NULL DEFAULT '[]',
    notes        TEXT NOT NULL DEFAULT '""',
    result       TEXT,
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL
);
"""


class TaskHarness:
    """Maestro-style SQLite-backed task card harness.

    Thread-safe (per-connection lock).  All persistence lives in an
    SQLite database at ``db_path``.  Pass an explicit path so callers
    (and tests) control storage location.
    """

    def __init__(
        self,
        db_path: str,
        *,
        auto_create_parent: bool = True,
    ) -> None:
        self._db_path: str = db_path
        self._lock: threading.RLock = threading.RLock()
        if auto_create_parent:
            parent = Path(db_path).parent
            if str(parent) not in (".", ""):
                parent.mkdir(parents=True, exist_ok=True)
        self._conn: sqlite3.Connection = sqlite3.connect(
            db_path, check_same_thread=False
        )
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._conn.execute(_SCHEMA)
            self._conn.commit()
        self._closed: bool = False

    # ── Low-level helpers ────────────────────────────────────────────────

    def _row_to_card(self, row: sqlite3.Row | None) -> TaskCard | None:
        return TaskCard.from_row(row) if row is not None else None

    def _now(self) -> str:
        return _utcnow()

    def _fetch(self, task_id: str) -> TaskCard | None:
        cur = self._conn.execute(
            "SELECT * FROM task_cards WHERE id = ?", (task_id,)
        )
        return self._row_to_card(cur.fetchone())

    def _update_status_row(self, task_id: str, status: TaskStatus, result: str | None = None) -> TaskCard:
        now = self._now()
        if result is not None:
            self._conn.execute(
                "UPDATE task_cards SET status=?, result=?, updated_at=? WHERE id=?",
                (status.value, json.dumps(result), now, task_id),
            )
        else:
            self._conn.execute(
                "UPDATE task_cards SET status=?, updated_at=? WHERE id=?",
                (status.value, now, task_id),
            )
        self._conn.commit()
        card = self._fetch(task_id)
        if card is None:  # pragma: no cover - guarded earlier
            raise TaskNotFoundError(task_id)
        return card

    # ── Public API ───────────────────────────────────────────────────────

    def create_card(
        self,
        title: str,
        description: str = "",
        *,
        priority: int = 0,
        depends_on: Iterable[str] | None = None,
        steps: Sequence[str] | None = None,
    ) -> TaskCard:
        """Create and persist a new task card.

        Dependency ids that do not yet exist are recorded but allowed
        (future dependencies), matching the harness's tolerant ordering.
        """
        if not title or not str(title).strip():
            raise TaskHarnessError("title must be a non-empty string")

        task_id = str(uuid.uuid4())
        dep_list: list[str] = list(dict.fromkeys(depends_on or []))
        step_list: list[str] = list(steps or [])
        now = self._now()

        with self._lock:
            self._conn.execute(
                """
                INSERT INTO task_cards
                    (id, title, description, status, priority, depends_on,
                     steps, notes, result, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    task_id,
                    str(title),
                    str(description),
                    TaskStatus.PENDING.value,
                    int(priority),
                    json.dumps(dep_list),
                    json.dumps([str(s) for s in step_list]),
                    json.dumps(""),
                    None,
                    now,
                    now,
                ),
            )
            self._conn.commit()

        return self._fetch(task_id)  # type: ignore[return-value]

    def get(self, task_id: str) -> TaskCard:
        """Return a task card by id, raising TaskNotFoundError if absent."""
        with self._lock:
            card = self._fetch(task_id)
        if card is None:
            raise TaskNotFoundError(task_id)
        return card

    def list(self, status: TaskStatus | None = None) -> builtins.list[TaskCard]:
        """List task cards, optionally filtered by status."""
        with self._lock:
            if status is None:
                cur = self._conn.execute("SELECT * FROM task_cards")
            else:
                cur = self._conn.execute(
                    "SELECT * FROM task_cards WHERE status = ?", (status.value,)
                )
            rows = cur.fetchall()
        return [self._row_to_card(r) for r in rows if r is not None]  # type: ignore[misc]

    def _validate_transition(self, task_id: str, new_status: TaskStatus) -> TaskCard:
        card = self.get(task_id)
        allowed = _ALLOWED_TRANSITIONS.get(card.status, set())
        if new_status not in allowed:
            raise InvalidTransitionError(
                f"illegal transition {task_id}: {card.status.value} -> {new_status.value}"
            )
        return card

    def update_status(self, task_id: str, status: TaskStatus) -> TaskCard:
        """Update a card's status with full transition guarding."""
        with self._lock:
            self._validate_transition(task_id, status)
            return self._update_status_row(task_id, status)

    def start(self, task_id: str) -> TaskCard:
        """Transition pending -> running (validate deps first)."""
        if not self.can_start(task_id):
            card = self.get(task_id)
            bad = [
                d for d in card.depends_on
                if self._dep_unsatisfied(d)
            ]
            raise DependencyNotSatisfiedError(
                f"task {task_id} cannot start; unsatisfied deps: {bad}"
            )
        with self._lock:
            card = self._validate_transition(task_id, TaskStatus.RUNNING)
            if card.status != TaskStatus.PENDING:
                raise InvalidTransitionError(
                    f"task {task_id} cannot start from {card.status.value}"
                )
            return self._update_status_row(task_id, TaskStatus.RUNNING)

    def pause(self, task_id: str) -> TaskCard:
        """Transition running -> paused."""
        with self._lock:
            self._validate_transition(task_id, TaskStatus.PAUSED)
            return self._update_status_row(task_id, TaskStatus.PAUSED)

    def resume(self, task_id: str) -> TaskCard:
        """Transition paused -> running."""
        with self._lock:
            self._validate_transition(task_id, TaskStatus.RUNNING)
            return self._update_status_row(task_id, TaskStatus.RUNNING)

    def cancel(self, task_id: str) -> TaskCard:
        """Cancel a task (pending/running/paused -> cancelled)."""
        with self._lock:
            self._validate_transition(task_id, TaskStatus.CANCELLED)
            return self._update_status_row(task_id, TaskStatus.CANCELLED)

    def mark_completed(self, task_id: str, result: str | None = None) -> TaskCard:
        """Record a task as completed with an optional result payload."""
        with self._lock:
            self._validate_transition(task_id, TaskStatus.COMPLETED)
            return self._update_status_row(task_id, TaskStatus.COMPLETED, result=result)

    def mark_failed(self, task_id: str, result: str | None = None) -> TaskCard:
        """Record a task as failed with an optional error payload."""
        with self._lock:
            self._validate_transition(task_id, TaskStatus.FAILED)
            return self._update_status_row(task_id, TaskStatus.FAILED, result=result)

    def add_step_progress(self, task_id: str, step: str) -> TaskCard:
        """Append a completed step to a task's steps list."""
        with self._lock:
            card = self.get(task_id)
            steps = list(card.steps)
            steps.append(str(step))
            now = self._now()
            self._conn.execute(
                "UPDATE task_cards SET steps=?, updated_at=? WHERE id=?",
                (json.dumps(steps), now, task_id),
            )
            self._conn.commit()
        return self.get(task_id)

    def set_note(self, task_id: str, text: str) -> TaskCard:
        """Set (overwrite) the free-form notes on a task."""
        with self._lock:
            self.get(task_id)
            now = self._now()
            self._conn.execute(
                "UPDATE task_cards SET notes=?, updated_at=? WHERE id=?",
                (json.dumps(str(text)), now, task_id),
            )
            self._conn.commit()
        return self.get(task_id)

    def heartbeat(self, task_id: str) -> TaskCard:
        """Bump the updated_at timestamp (liveness for background tasks)."""
        with self._lock:
            self.get(task_id)
            now = self._now()
            self._conn.execute(
                "UPDATE task_cards SET updated_at=? WHERE id=?",
                (now, task_id),
            )
            self._conn.commit()
        return self.get(task_id)

    # ── Dependency ordering ──────────────────────────────────────────────

    def _dep_unsatisfied(self, dep_id: str) -> bool:
        """Return True if dep_id is absent or not in a satisfying state."""
        with self._lock:
            dep = self._fetch(dep_id)
        if dep is None:
            # Future / missing dependency is treated as unsatisfied so that
            # we never run work before its prerequisites exist & finish.
            return True
        return dep.status not in _SATISFYING_STATUSES

    def can_start(self, task_id: str) -> bool:
        """Return True if every dependency is completed (or cancelled)."""
        card = self.get(task_id)
        if not card.depends_on:
            return True
        for dep in card.depends_on:
            if self._dep_unsatisfied(dep):
                return False
        return True

    def next_runnable(self) -> builtins.list[TaskCard]:
        """Return pending tasks whose dependencies are satisfied.

        Ordered by priority descending, then created_at ascending.
        """
        with self._lock:
            cards = self._list_pending_locked()
        runnable = [
            c for c in cards
            if all(not self._dep_unsatisfied(d) for d in c.depends_on)
        ]
        runnable.sort(key=lambda c: (-c.priority, c.created_at))
        return runnable

    def _list_pending_locked(self) -> builtins.list[TaskCard]:
        cur = self._conn.execute(
            "SELECT * FROM task_cards WHERE status = ?", (TaskStatus.PENDING.value,)
        )
        rows = cur.fetchall()
        return [self._row_to_card(r) for r in rows if r is not None]  # type: ignore[misc]

    # ── Resource management ──────────────────────────────────────────────

    def close(self) -> None:
        """Close the underlying SQLite connection."""
        with self._lock:
            if not self._closed:
                self._conn.close()
                self._closed = True

    def __enter__(self) -> TaskHarness:
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()
