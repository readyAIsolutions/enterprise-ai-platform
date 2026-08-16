"""Work broker: task queueing, assignment, heartbeat-timeout requeue, retry.

Responsibilities
----------------
* Maintain the QUEUED task list and hand tasks to capacity-capable clients.
* Assign round-robin by client load (fewest RUNNING first) while respecting each
  client's max_concurrent_tasks and model/provider/tag capabilities.
* Watch client heartbeats; if a client holding an ASSIGNED/RUNNING task goes
  quiet for HEARTBEAT_TIMEOUT (60s), requeue its tasks.
* Retry-once policy: a task that FAILS with attempt 1 is re-queued; a second
  failure is terminal.
* Persist the queue to data/multiplayer_queue.jsonl (append JSONL) so a server
  restart resumes in-flight QUEUED/ASSIGNED tasks.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from typing import Any, Callable, Dict, List, Optional

from ..protocol import TaskState, validate
from .state import Board, TaskRecord, new_id

HEARTBEAT_TIMEOUT = 60.0        # seconds before a silent client is considered down
DEFAULT_MAX_CONCURRENT = 2      # default client concurrency accepted
MAX_RETRIES = 1                 # a task may fail once and be retried once

# Server -> client message send callback, wired by server.py.
SendFn = Callable[[str, Dict[str, Any]], None]


class Broker:
    def __init__(self, board: Board, data_dir: str, on_send: Optional[SendFn] = None) -> None:
        self.board = board
        self.data_dir = data_dir
        self.on_send = on_send or (lambda cid, msg: None)  # noqa: E731
        self._queue_file = os.path.join(data_dir, "multiplayer_queue.jsonl")
        self._round_robin: Dict[str, int] = {}  # client_id -> last assignment count
        os.makedirs(data_dir, exist_ok=True)

    # ------------------------------------------------------------------ task
    def _make_task(self, goal: str, **fields) -> TaskRecord:
        rec = TaskRecord(
            task_id=new_id("t"),
            goal=goal,
            status=TaskState.QUEUED,
            created_at=time.time(),
            prompt=fields.get("prompt", ""),
            repo=fields.get("repo", ""),
            artifacts=fields.get("artifacts", []) or [],
            model_hint=fields.get("model_hint", ""),
            provider=fields.get("provider", ""),
            tags=fields.get("tags", []) or [],
            priority=fields.get("priority", 5),
            attempt=int(fields.get("attempt", 1)),
            requeue_of=fields.get("requeue_of"),
        )
        return rec

    async def submit(self, goal: str, **fields) -> TaskRecord:
        """Queue a new task and record it in the persisted queue log."""
        rec = self._make_task(goal, **fields)
        await self.board.add_task(rec)
        self._append_log(rec)
        await self.board.log("submit", rec.task_id, "", message=f"submitted goal={goal!r}")
        return rec

    async def requeue(self, task_id: str, reason: str) -> Optional[TaskRecord]:
        """Return a RUNNING/ASSIGNED task to the QUEUED pool (retry policy)."""
        rec = await self.board.get_task(task_id)
        if rec is None:
            return None
        rec.attempt += 1
        if rec.attempt > MAX_RETRIES + 1:
            await self.board.update_task(task_id, result_status="failed",
                                         error=f"max retries exceeded: {reason}")
            await self.board.set_status(task_id, TaskState.FAILED)
            await self._finish_task_on_client(rec, final=True)
            await self.board.log("requeue", task_id, str(rec.assigned_client or ""),
                                 message=f"terminal failure after retries: {reason}")
            return rec
        # Release client holding it.
        await self._finish_task_on_client(rec, final=False)
        await self.board.queue_append(task_id)
        await self.board.set_status(task_id, TaskState.QUEUED)
        await self.board.log("requeue", task_id, str(rec.assigned_client or ""),
                             message=f"requeued attempt={rec.attempt}: {reason}")
        self._send(rec.assigned_client or "", {
            "type": "requeue", "task_id": task_id, "reason": reason,
            "attempt": rec.attempt,
        })
        self._append_log(rec)
        return rec

    async def _finish_task_on_client(self, rec: TaskRecord, final: bool) -> None:
        if rec.assigned_client:
            client = await self.board.get_client(rec.assigned_client)
            if client is not None and rec.task_id in client.running:
                client.running.remove(rec.task_id)

    async def _send(self, client_id: str, message: Dict[str, Any]) -> None:
        ok, reason = validate(message)
        if not ok:
            await self.board.log("error", message.get("task_id", ""), client_id,
                                 message=f"dropped invalid outbound message: {reason}")
            return
        self.on_send(client_id, message)

    # ------------------------------------------------------------- assignment
    async def assign(self) -> None:
        """Assign queued tasks to capable clients round-robin by load.

        Each client gets at most one new task per assign() pass, chosen to keep
        the busiest clients from hogging the queue.
        """
        queue_ids = await self.board.queued_ids()
        if not queue_ids:
            return
        clients = [c for c in await self.board.clients()
                   if not c.disconnected and c.transport is not None]
        if not clients:
            return

        # Order clients by fewest RUNNING first, then by fewest total assigned.
        clients.sort(key=lambda c: (c.load(), self._round_robin.get(c.client_id, 0)))

        assigned_this_pass = 0
        for task_id in list(queue_ids):
            rec = await self.board.get_task(task_id)
            if rec is None or rec.status != TaskState.QUEUED:
                continue
            target = None
            # Prefer the least-loaded capable client.
            for c in clients:
                if c.can_run(rec):
                    target = c
                    break
            if target is None:
                continue  # no client can currently handle it; leave queued

            # Atomic claim: re-check capacity just before claiming.
            if target.load() >= target.max_concurrent_tasks:
                continue
            if rec.assigned_client is not None and not rec.assigned_client.startswith("claim"):
                await self._finish_task_on_client(rec, final=False)

            await self.board.queue_remove(task_id)
            await self.board.update_task(task_id,
                                         assigned_client=target.client_id,
                                         assigned_at=time.time())
            await self.board.set_status(task_id, TaskState.ASSIGNED)
            target.running.append(task_id)
            await self.board.touch_client(target.client_id)
            self._round_robin[target.client_id] = self._round_robin.get(target.client_id, 0) + 1
            await self.board.log("assign", task_id, target.client_id,
                                 message=f"assigned to {target.client_id}")

            msg = {
                "type": "task",
                "task_id": rec.task_id,
                "goal": rec.goal,
                "status": TaskState.ASSIGNED.value,
                "prompt": rec.prompt,
                "repo": rec.repo,
                "artifacts": rec.artifacts,
                "model_hint": rec.model_hint,
                "attempt": rec.attempt,
                "priority": rec.priority,
            }
            await self._send(target.client_id, msg)
            assigned_this_pass += 1

    # ------------------------------------------------- heartbeat/requeue
    async def check_heartbeats(self, now_ts: Optional[float] = None) -> None:
        """Requeue tasks whose assigned client has been silent too long."""
        now_ts = now_ts if now_ts is not None else time.time()
        for client in await self.board.clients():
            if client.disconnected:
                continue
            if now_ts - client.last_seen > HEARTBEAT_TIMEOUT:
                client.disconnected = True
                await self.board.log("timeout", "", client.client_id,
                                     message=f"heartbeat timeout after "
                                             f"{now_ts - client.last_seen:.0f}s")
                for task_id in list(client.running):
                    rec = await self.board.get_task(task_id)
                    if rec is not None and rec.status in (TaskState.ASSIGNED, TaskState.RUNNING):
                        await self.requeue(task_id, "client heartbeat timeout")

    # ------------------------------------------------------------ persistence
    def _append_log(self, rec: TaskRecord) -> None:
        try:
            with open(self._queue_file, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(rec.as_dict()) + "\n")
        except OSError as exc:  # pragma: no cover - best effort persistence
            print(f"[broker] warn: could not persist task: {exc}")

    async def resume_from_disk(self) -> int:
        """Reload persisted tasks into the board. Returns number restored."""
        if not os.path.exists(self._queue_file):
            return 0
        restored = 0
        with open(self._queue_file, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    d = json.loads(line)
                except json.JSONDecodeError:
                    continue
                rec = TaskRecord(task_id=d.get("task_id"), goal=d.get("goal", ""),
                                 status=TaskState(d.get("status", "QUEUED")),
                                 created_at=d.get("created_at", time.time()),
                                 prompt=d.get("prompt", ""), repo=d.get("repo", ""),
                                 artifacts=d.get("artifacts", []) or [],
                                 model_hint=d.get("model_hint", ""),
                                 provider=d.get("provider", ""),
                                 tags=d.get("tags", []) or [],
                                 priority=d.get("priority", 5),
                                 attempt=d.get("attempt", 1),
                                 requeue_of=d.get("requeue_of"))
                if rec.status in (TaskState.ASSIGNED, TaskState.RUNNING):
                    # No client connected during restart; put back in the queue.
                    rec.status = TaskState.QUEUED
                    await self.board.add_task(rec)
                    restored += 1
                elif rec.status == TaskState.QUEUED:
                    await self.board.add_task(rec)
                    restored += 1
        return restored


async def run_assign_loop(broker: Broker, interval: float = 1.0,
                          stop: Optional[asyncio.Event] = None) -> None:
    """Background loop: assign tasks then prune stale heartbeat clients."""
    while not (stop is not None and stop.is_set()):
        try:
            await broker.assign()
            await broker.check_heartbeats()
        except asyncio.CancelledError:
            return
        except Exception as exc:  # pragma: no cover - defensive
            print(f"[broker] loop error: {exc}")
        await asyncio.sleep(interval)