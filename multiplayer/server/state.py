"""In-memory board state for the multiplayer server.

Holds the canonical view of connected clients, tasks, and a time-ordered ledger.
All access is guarded by an ``asyncio.Lock`` so the async server threads can
mutate state safely. This is the source feeding ``/api/board`` and the SSE
``/api/stream`` channel.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

from ..protocol import TaskState


def new_id(prefix: str) -> str:
    """Generate a short, URL-safe unique id with a textual prefix."""
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


@dataclass
class TaskRecord:
    task_id: str
    goal: str
    status: TaskState
    created_at: float
    prompt: str = ""
    repo: str = ""
    artifacts: List[Dict[str, str]] = field(default_factory=list)
    model_hint: str = ""
    provider: str = ""
    tags: List[str] = field(default_factory=list)
    priority: int = 5
    attempt: int = 1
    requeue_of: Optional[str] = None
    assigned_client: Optional[str] = None
    assigned_at: Optional[float] = None
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    result_status: Optional[str] = None
    summary: str = ""
    stdout: str = ""
    error: str = ""
    merged_paths: List[str] = field(default_factory=list)
    conflicts: List[Dict[str, str]] = field(default_factory=list)

    def as_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["status"] = self.status.value
        return d


@dataclass
class ClientRecord:
    client_id: str
    connected_at: float
    last_seen: float
    hostname: str = ""
    max_concurrent_tasks: int = 1
    models: List[str] = field(default_factory=list)
    providers: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    gpu: bool = False
    transport: Any = None  # server-side WS protocol object; not serialized
    running: List[str] = field(default_factory=list)  # task_ids currently running
    disconnected: bool = False

    def load(self) -> int:
        """Number of tasks this client is currently running."""
        return len(self.running)

    def can_run(self, task: TaskRecord) -> bool:
        """True if this client can accept the given task given its caps."""
        if self.load() >= self.max_concurrent_tasks:
            return False
        if task.model_hint and self.models and "*" not in self.models:
            if task.model_hint not in self.models:
                return False
        if task.provider and self.providers and "*" not in self.providers:
            if task.provider not in self.providers:
                return False
        if task.tags and self.tags and "*" not in self.tags:
            if not set(task.tags).intersection(self.tags):
                return False
        return True

    def as_dict(self) -> Dict[str, Any]:
        return {
            "client_id": self.client_id,
            "hostname": self.hostname,
            "connected_at": self.connected_at,
            "last_seen": self.last_seen,
            "max_concurrent_tasks": self.max_concurrent_tasks,
            "models": self.models,
            "providers": self.providers,
            "tags": self.tags,
            "gpu": self.gpu,
            "running": list(self.running),
            "load": self.load(),
            "disconnected": self.disconnected,
        }


@dataclass
class LedgerEntry:
    ts: float
    kind: str
    task_id: str
    client_id: str
    message: str = ""
    detail: str = ""

    def as_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        return d


class Board:
    """Thread/async-safe store holding clients, tasks, and the ledger."""

    def __init__(self) -> None:
        self.lock = asyncio.Lock()
        self._clients: Dict[str, ClientRecord] = {}
        self._tasks: Dict[str, TaskRecord] = {}
        self._queue_order: List[str] = []  # ordered task_ids in QUEUED state
        self._ledger: List[LedgerEntry] = []

    # -- clients -----------------------------------------------------------
    async def add_client(self, rec: ClientRecord) -> None:
        async with self.lock:
            self._clients[rec.client_id] = rec
            self._ledger.append(LedgerEntry(
                ts=time.time(), kind="client_connected", task_id="",
                client_id=rec.client_id, message=f"client connected"))

    async def touch_client(self, client_id: str, now_ts: Optional[float] = None) -> None:
        async with self.lock:
            c = self._clients.get(client_id)
            if c is not None:
                c.last_seen = now_ts if now_ts is not None else time.time()

    async def remove_client(self, client_id: str) -> None:
        async with self.lock:
            self._clients.pop(client_id, None)
            self._ledger.append(LedgerEntry(
                ts=time.time(), kind="client_disconnected", task_id="",
                client_id=client_id, message="client disconnected"))

    async def get_client(self, client_id: str) -> Optional[ClientRecord]:
        async with self.lock:
            return self._clients.get(client_id)

    async def clients(self) -> List[ClientRecord]:
        async with self.lock:
            return list(self._clients.values())

    # -- tasks -------------------------------------------------------------
    async def add_task(self, rec: TaskRecord) -> None:
        async with self.lock:
            self._tasks[rec.task_id] = rec
            if rec.status == TaskState.QUEUED:
                self._queue_order.append(rec.task_id)
            self._ledger.append(LedgerEntry(
                ts=time.time(), kind="task_queued", task_id=rec.task_id,
                client_id="", message=f"task queued (goal={rec.goal!r})"))

    async def get_task(self, task_id: str) -> Optional[TaskRecord]:
        async with self.lock:
            return self._tasks.get(task_id)

    async def tasks(self) -> List[TaskRecord]:
        async with self.lock:
            return list(self._tasks.values())

    async def queued_ids(self) -> List[str]:
        async with self.lock:
            return [t for t in self._queue_order
                    if self._tasks[t].status == TaskState.QUEUED]

    async def queue_remove(self, task_id: str) -> None:
        async with self.lock:
            if task_id in self._queue_order:
                self._queue_order.remove(task_id)

    async def queue_append(self, task_id: str) -> None:
        async with self.lock:
            if task_id not in self._queue_order:
                self._queue_order.append(task_id)

    async def set_status(self, task_id: str, status: TaskState) -> None:
        async with self.lock:
            t = self._tasks.get(task_id)
            if t is not None and t.status != status:
                t.status = status
                self._ledger.append(LedgerEntry(
                    ts=time.time(), kind="status", task_id=task_id,
                    client_id=str(t.assigned_client or ""),
                    message=f"status -> {status.value}"))

    async def update_task(self, task_id: str, **kwargs) -> None:
        async with self.lock:
            t = self._tasks.get(task_id)
            if t is not None:
                for k, v in kwargs.items():
                    setattr(t, k, v)

    # -- ledger ------------------------------------------------------------
    async def log(self, kind: str, task_id: str, client_id: str,
                  message: str = "", detail: str = "") -> None:
        async with self.lock:
            self._ledger.append(LedgerEntry(
                ts=time.time(), kind=kind, task_id=task_id,
                client_id=client_id, message=message, detail=detail))

    async def ledger(self) -> List[LedgerEntry]:
        async with self.lock:
            return list(self._ledger)

    # -- board snapshot ----------------------------------------------------
    async def board_snapshot(self) -> Dict[str, Any]:
        """Full board used by /api/board and the SSE stream."""
        async with self.lock:
            clients = [c.as_dict() for c in self._clients.values()]
            queue = []
            active = []
            done = []
            for t in self._tasks.values():
                d = t.as_dict()
                if t.status == TaskState.QUEUED:
                    queue.append(d)
                elif t.status in (TaskState.ASSIGNED, TaskState.RUNNING):
                    active.append(d)
                elif t.status in (TaskState.COMPLETED, TaskState.FAILED):
                    done.append(d)
            ledger = [e.as_dict() for e in self._ledger]
            return {
                "clients": clients,
                "queue": queue,
                "active": active,
                "done": done,
                "ledger": ledger,
                "stats": {
                    "clients": len(clients),
                    "queue": len(queue),
                    "active": len(active),
                    "done": len(done),
                    "ledger_len": len(ledger),
                },
            }