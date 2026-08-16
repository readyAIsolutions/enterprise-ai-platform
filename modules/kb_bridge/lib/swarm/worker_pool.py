#!/usr/bin/env python3
"""
WorkerPool — Concurrent Worker Process Manager
================================================

Manages N concurrent worker processes that execute tasks.
Features:
  - Each worker runs a specific task type (build, compress, verify, etc.)
  - Work stealing between idle workers for balanced load distribution
  - Auto-scaling pool size based on load
  - Worker death detection and automatic restart
  - Per-worker metrics tracking (tasks completed, errors, uptime)

Usage:
  pool = WorkerPool(min_workers=2, max_workers=8)
  pool.start()
  pool.submit_task({"name": "compress_batch_1", "task": "..."})
  stats = pool.get_metrics()
"""

from __future__ import annotations

import os
import sys
import time
import signal
import logging
import threading
import multiprocessing
from multiprocessing import Process, Queue, Value, Event
from multiprocessing.managers import SyncManager
from queue import Empty, Full
from pathlib import Path
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import Dict, List, Optional, Any, Callable, Tuple
from collections import defaultdict, deque

logger = logging.getLogger("swarm.worker_pool")


# ─── Enums ──────────────────────────────────────────────────────────────────
class WorkerState(Enum):
    """Worker lifecycle states."""
    IDLE = auto()
    BUSY = auto()
    DEAD = auto()
    STARTING = auto()
    DRAINING = auto()  # finishing current task, not accepting new ones


class PoolState(Enum):
    """Worker pool states."""
    STOPPED = auto()
    STARTING = auto()
    RUNNING = auto()
    SCALING = auto()
    DRAINING = auto()
    STOPPING = auto()


# ─── Data Classes ───────────────────────────────────────────────────────────
@dataclass
class WorkerMetrics:
    """Per-worker metrics."""
    worker_id: int
    tasks_completed: int = 0
    tasks_failed: int = 0
    total_work_time: float = 0.0  # seconds spent working
    last_task_start: float = 0.0
    last_task_end: float = 0.0
    started_at: float = 0.0
    restarts: int = 0
    state: WorkerState = WorkerState.IDLE
    current_task: Optional[str] = None
    pid: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "worker_id": self.worker_id,
            "tasks_completed": self.tasks_completed,
            "tasks_failed": self.tasks_failed,
            "total_work_time": round(self.total_work_time, 3),
            "state": self.state.name,
            "current_task": self.current_task,
            "restarts": self.restarts,
            "pid": self.pid,
        }


@dataclass
class PoolMetrics:
    """Aggregate pool metrics."""
    total_workers: int
    idle_workers: int
    busy_workers: int
    dead_workers: int
    total_tasks_completed: int
    total_tasks_failed: int
    queued_tasks: int
    avg_task_time: float
    uptime_seconds: float
    scale_events: int
    workers: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_workers": self.total_workers,
            "idle_workers": self.idle_workers,
            "busy_workers": self.busy_workers,
            "dead_workers": self.dead_workers,
            "total_tasks_completed": self.total_tasks_completed,
            "total_tasks_failed": self.total_tasks_failed,
            "queued_tasks": self.queued_tasks,
            "avg_task_time": round(self.avg_task_time, 3),
            "uptime_seconds": round(self.uptime_seconds, 1),
            "scale_events": self.scale_events,
            "workers": self.workers,
        }


# ─── Task Types ─────────────────────────────────────────────────────────────
class TaskType:
    """Known task types for worker specialization."""
    BUILD = "build"
    COMPRESS = "compress"
    VERIFY = "verify"
    SYNC = "sync"
    EVOLVE = "evolve"
    EXPORT = "export"
    GENERIC = "generic"


# ─── Worker Process ─────────────────────────────────────────────────────────
def _worker_main(
    worker_id: int,
    task_queue: Queue,
    result_queue: Queue,
    control_event: Event,
    metrics_queue: Queue,
    worker_type: str,
):
    """
    Main function executed inside each worker process.
    Continuously fetches tasks from the queue and executes them.

    Args:
        worker_id: Unique worker identifier
        task_queue: Queue from which to pull tasks
        result_queue: Queue to which to push results
        control_event: Event to signal drain/stop
        metrics_queue: Queue for heartbeats and metrics
        worker_type: Type specialization for this worker
    """
    pid = os.getpid()
    local_completed = 0
    local_failed = 0
    local_work_time = 0.0

    # Signal we're alive
    metrics_queue.put({
        "type": "heartbeat",
        "worker_id": worker_id,
        "pid": pid,
        "state": "idle",
        "timestamp": time.time(),
    })

    while not control_event.is_set():
        try:
            # Try to get a task with timeout (so we can check control_event)
            task = task_queue.get(timeout=1.0)
        except Empty:
            # No task available - heartbeat and continue
            metrics_queue.put({
                "type": "heartbeat",
                "worker_id": worker_id,
                "pid": pid,
                "state": "idle",
                "timestamp": time.time(),
            })
            continue
        except (EOFError, OSError):
            # Queue closed
            break

        # We got a task - process it
        if task is None:  # poison pill
            break

        task_name = task.get("name", f"task_{id(task)}")
        start = time.time()

        metrics_queue.put({
            "type": "heartbeat",
            "worker_id": worker_id,
            "pid": pid,
            "state": "busy",
            "task": task_name,
            "timestamp": start,
        })

        try:
            result = _execute_task(task, worker_id, worker_type)
            elapsed = time.time() - start
            local_completed += 1
            local_work_time += elapsed

            result_queue.put({
                "worker_id": worker_id,
                "task_name": task_name,
                "success": True,
                "result": result,
                "elapsed": elapsed,
                "timestamp": time.time(),
            })
        except Exception as e:
            elapsed = time.time() - start
            local_failed += 1

            logger.error(f"Worker {worker_id}: task '{task_name}' failed: {e}", exc_info=True)
            result_queue.put({
                "worker_id": worker_id,
                "task_name": task_name,
                "success": False,
                "error": str(e),
                "elapsed": elapsed,
                "timestamp": time.time(),
            })

        # Final heartbeat after task
        metrics_queue.put({
            "type": "heartbeat",
            "worker_id": worker_id,
            "pid": pid,
            "state": "idle",
            "completed": local_completed,
            "failed": local_failed,
            "work_time": local_work_time,
            "timestamp": time.time(),
        })

    # Clean exit
    metrics_queue.put({
        "type": "exit",
        "worker_id": worker_id,
        "completed": local_completed,
        "failed": local_failed,
        "work_time": local_work_time,
        "timestamp": time.time(),
    })


def _execute_task(task: Dict[str, Any], worker_id: int, worker_type: str) -> Any:
    """
    Execute a single task inside a worker process.

    Dispatches to appropriate handler based on task_type or the worker's
    specialization. Returns the task result.
    """
    task_type = task.get("type", TaskType.GENERIC)
    task_body = task.get("task", "")

    # --- BUILD tasks ---
    if task_type == TaskType.BUILD:
        workdir = task.get("workdir", ".")
        name = task.get("name", "unnamed")
        # For build tasks, we may need to run verification commands
        if "verify_cmd" in task:
            import subprocess
            try:
                result = subprocess.run(
                    task["verify_cmd"], shell=True, capture_output=True,
                    text=True, timeout=task.get("timeout", 60),
                    cwd=workdir,
                )
                return {
                    "stdout": result.stdout.strip(),
                    "stderr": result.stderr.strip(),
                    "returncode": result.returncode,
                    "success": result.returncode == 0,
                }
            except subprocess.TimeoutExpired:
                return {"error": "timeout", "success": False}
            except Exception as e:
                return {"error": str(e), "success": False}
        else:
            return {"status": "executed", "task_name": name, "worker_type": worker_type}

    # --- COMPRESS tasks ---
    elif task_type == TaskType.COMPRESS:
        # Simulated compression; real implementation would call the compression pipeline
        import zlib
        data = task_body.encode() if task_body else b"ENI_Swarm_compression_test_data"
        compressed = zlib.compress(data)
        ratio = len(data) / len(compressed) if len(compressed) > 0 else 1.0
        return {"compressed_size": len(compressed), "original_size": len(data), "ratio": round(ratio, 3)}

    # --- VERIFY tasks ---
    elif task_type == TaskType.VERIFY:
        import subprocess
        cmd = task.get("verify_cmd", "echo 'no verification command'")
        try:
            result = subprocess.run(
                cmd, shell=True, capture_output=True,
                text=True, timeout=task.get("timeout", 30),
                cwd=task.get("workdir", "."),
            )
            return {"stdout": result.stdout.strip(), "returncode": result.returncode, "success": result.returncode == 0}
        except Exception as e:
            return {"error": str(e), "success": False}

    # --- SYNC tasks ---
    elif task_type == TaskType.SYNC:
        return {"status": "synced", "task_name": task.get("name", ""), "entries": task.get("count", 0)}

    # --- EVOLVE tasks ---
    elif task_type == TaskType.EVOLVE:
        generations = task.get("generations", 1)
        return {"status": "evolved", "generations": generations, "improvement": task.get("improvement", 0.0)}

    # --- GENERIC / default ---
    else:
        # Execute as a Python import check if specified
        if "import_check" in task:
            import subprocess
            try:
                result = subprocess.run(
                    task["import_check"], shell=True, capture_output=True,
                    text=True, timeout=task.get("timeout", 10),
                    cwd=task.get("workdir", "."),
                )
                return {"import_check": result.stdout.strip(), "success": result.returncode == 0}
            except Exception as e:
                return {"error": str(e), "success": False}
        return {"status": "completed", "task_name": task.get("name", ""), "worker_type": worker_type}


# ─── Worker Handle (Local Tracked State) ────────────────────────────────────
class _WorkerHandle:
    """Tracks a single worker process and its state."""

    def __init__(self, worker_id: int, process: Process, task_type: str):
        self.worker_id = worker_id
        self.process = process
        self.task_type = task_type
        self.metrics = WorkerMetrics(
            worker_id=worker_id,
            started_at=time.time(),
            pid=process.pid or 0,
        )
        self.last_heartbeat = time.time()
        self._assigned_tasks: deque = deque()

    @property
    def is_alive(self) -> bool:
        return self.process.is_alive() if self.process else False

    def assign_task(self, task_name: str) -> None:
        self._assigned_tasks.append(task_name)


# ─── WorkerPool ──────────────────────────────────────────────────────────
class WorkerPool:
    """
    Manages a pool of N concurrent worker processes.

    Supports auto-scaling, work stealing, death detection,
    and per-worker metrics collection.

    Args:
        min_workers: Minimum number of workers to maintain
        max_workers: Maximum number of workers (auto-scaling cap)
        task_types: List of task type specializations for workers
        scale_up_threshold: Queue depth that triggers scale-up
        scale_down_threshold: Idle worker count that triggers scale-down
        scale_check_interval: Seconds between scale checks
        heartbeat_timeout: Seconds without heartbeat before considering dead
        max_restart_attempts: Max consecutive restarts per worker
    """

    def __init__(
        self,
        min_workers: int = 2,
        max_workers: int = 8,
        task_types: Optional[List[str]] = None,
        scale_up_threshold: int = 5,
        scale_down_threshold: int = 3,
        scale_check_interval: float = 5.0,
        heartbeat_timeout: float = 30.0,
        max_restart_attempts: int = 3,
    ):
        self.min_workers = max(1, min_workers)
        self.max_workers = max(self.min_workers, max_workers)
        self.task_types = task_types or [
            TaskType.GENERIC, TaskType.BUILD,
            TaskType.COMPRESS, TaskType.VERIFY,
        ]
        self.scale_up_threshold = scale_up_threshold
        self.scale_down_threshold = scale_down_threshold
        self.scale_check_interval = scale_check_interval
        self.heartbeat_timeout = heartbeat_timeout
        self.max_restart_attempts = max_restart_attempts

        # Internal state
        self._state = PoolState.STOPPED
        self._state_lock = threading.Lock()
        self._workers: Dict[int, _WorkerHandle] = {}
        self._worker_counter = 0
        self._workers_lock = threading.RLock()

        # Queues - use multiprocessing-safe queues
        self._task_queue: Optional[Queue] = None
        self._result_queue: Optional[Queue] = None
        self._metrics_queue: Optional[Queue] = None
        self._control_events: Dict[int, Event] = {}

        # Tracking
        self._total_completed = 0
        self._total_failed = 0
        self._total_work_time = 0.0
        self._scale_events = 0
        self._task_times: deque = deque(maxlen=100)  # sliding window
        self._restart_attempts: Dict[int, int] = defaultdict(int)
        self._started_at: float = 0.0
        self._stop_event = threading.Event()
        self._monitor_thread: Optional[threading.Thread] = None
        self._result_thread: Optional[threading.Thread] = None

        # Result callbacks
        self._result_callbacks: List[Callable] = []
        self._steal_enabled = True

        logger.info(f"WorkerPool initialized: min={min_workers} max={max_workers}")

    # ─── Lifecycle ──────────────────────────────────────────────────────
    def start(self) -> None:
        """Start the worker pool with min_workers processes."""
        with self._state_lock:
            if self._state == PoolState.RUNNING:
                logger.warning("WorkerPool already running")
                return
            self._state = PoolState.STARTING

        # Create queues
        self._task_queue = Queue(maxsize=1000)
        self._result_queue = Queue()
        self._metrics_queue = Queue()
        self._started_at = time.time()
        self._stop_event.clear()

        # Start minimum workers
        for i in range(self.min_workers):
            wid = self._next_worker_id()
            task_type = self.task_types[i % len(self.task_types)]
            self._spawn_worker(wid, task_type)

        self._state = PoolState.RUNNING

        # Start monitoring threads
        self._monitor_thread = threading.Thread(
            target=self._monitor_loop, daemon=True, name="workerpool-monitor"
        )
        self._monitor_thread.start()

        self._result_thread = threading.Thread(
            target=self._result_collector, daemon=True, name="workerpool-results"
        )
        self._result_thread.start()

        logger.info(f"WorkerPool started with {len(self._workers)} workers")

    def stop(self, drain: bool = True) -> None:
        """
        Stop all workers in the pool.

        Args:
            drain: If True, wait for workers to finish current tasks first
        """
        with self._state_lock:
            if self._state == PoolState.STOPPED:
                return
            self._state = PoolState.DRAINING if drain else PoolState.STOPPING

        logger.info(f"WorkerPool stopping (drain={drain})")

        if drain:
            # Wait for task queue to empty
            while not self._task_queue.empty():
                time.sleep(0.5)

        # Signal all workers to stop
        self._stop_event.set()

        # Send poison pills
        with self._workers_lock:
            for _ in self._workers:
                try:
                    self._task_queue.put(None, timeout=1)
                except Full:
                    pass

        # Wait for workers
        deadline = time.time() + 10
        with self._workers_lock:
            for handle in list(self._workers.values()):
                remaining = deadline - time.time()
                if remaining > 0:
                    handle.process.join(timeout=remaining)
                if handle.process.is_alive():
                    handle.process.terminate()

        # Clean up
        self._workers.clear()
        self._control_events.clear()
        self._state = PoolState.STOPPED
        logger.info("WorkerPool stopped")

    # ─── Worker Management ──────────────────────────────────────────────
    def _next_worker_id(self) -> int:
        """Generate a unique worker ID."""
        self._worker_counter += 1
        return self._worker_counter

    def _spawn_worker(self, worker_id: int, task_type: str) -> Optional[_WorkerHandle]:
        """Spawn a single worker process."""
        if self._task_queue is None or self._result_queue is None or self._metrics_queue is None:
            logger.error("Queues not initialized")
            return None

        control_event = Event()
        self._control_events[worker_id] = control_event

        try:
            proc = Process(
                target=_worker_main,
                args=(
                    worker_id,
                    self._task_queue,
                    self._result_queue,
                    control_event,
                    self._metrics_queue,
                    task_type,
                ),
                daemon=True,
                name=f"eni-worker-{worker_id}",
            )
            proc.start()
            handle = _WorkerHandle(worker_id, proc, task_type)

            with self._workers_lock:
                self._workers[worker_id] = handle

            logger.debug(f"Spawned worker {worker_id} (pid={proc.pid}, type={task_type})")
            return handle
        except Exception as e:
            logger.error(f"Failed to spawn worker {worker_id}: {e}")
            return None

    def _kill_worker(self, worker_id: int) -> None:
        """Kill a specific worker process."""
        with self._workers_lock:
            handle = self._workers.pop(worker_id, None)
        if handle:
            ce = self._control_events.pop(worker_id, None)
            if ce:
                ce.set()
            if handle.process.is_alive():
                try:
                    handle.process.terminate()
                    handle.process.join(timeout=3)
                    if handle.process.is_alive():
                        handle.process.kill()
                except Exception:
                    pass

    def _restart_worker(self, worker_id: int) -> bool:
        """Restart a dead worker, respecting max attempts."""
        attempts = self._restart_attempts.get(worker_id, 0)
        if attempts >= self.max_restart_attempts:
            logger.warning(f"Worker {worker_id}: max restarts ({self.max_restart_attempts}) reached")
            return False

        self._restart_attempts[worker_id] = attempts + 1

        with self._workers_lock:
            old_handle = self._workers.pop(worker_id, None)
        old_type = old_handle.task_type if old_handle else TaskType.GENERIC
        self._control_events.pop(worker_id, None)

        new_handle = self._spawn_worker(worker_id, old_type)
        if new_handle:
            new_handle.metrics.restarts = attempts + 1
            logger.info(f"Worker {worker_id}: restarted (attempt {attempts + 1})")
            return True
        return False

    # ─── Task Submission ────────────────────────────────────────────────
    def submit_task(self, task: Dict[str, Any], timeout: float = 1.0) -> bool:
        """
        Submit a task to the worker pool.

        Args:
            task: Task dict with keys: name, task, type (optional), workdir (optional)
            timeout: Max seconds to wait if queue is full

        Returns:
            True if task was queued successfully
        """
        if self._state not in (PoolState.RUNNING, PoolState.DRAINING):
            logger.warning(f"Cannot submit task: pool state={self._state.name}")
            return False

        if self._task_queue is None:
            logger.error("Task queue not initialized")
            return False

        # Ensure task has required keys
        if "name" not in task:
            task["name"] = f"task_{id(task)}"
        if "type" not in task:
            task["type"] = TaskType.GENERIC

        try:
            self._task_queue.put(task, timeout=timeout)
            return True
        except Full:
            logger.warning("Task queue full, submission rejected")
            return False

    def submit_batch(self, tasks: List[Dict[str, Any]]) -> int:
        """
        Submit a batch of tasks to the pool.

        Args:
            tasks: List of task dicts

        Returns:
            Number of tasks successfully queued
        """
        count = 0
        for task in tasks:
            if self.submit_task(task):
                count += 1
        return count

    def queue_depth(self) -> int:
        """Get number of tasks currently in the queue."""
        if self._task_queue is None:
            return 0
        return self._task_queue.qsize()

    # ─── Work Stealing ──────────────────────────────────────────────────
    def enable_stealing(self, enabled: bool = True) -> None:
        """Enable or disable work stealing between workers."""
        self._steal_enabled = enabled
        logger.info(f"Work stealing: {'enabled' if enabled else 'disabled'}")

    def _try_steal_work(self) -> int:
        """
        Attempt to redistribute work from busy workers to idle ones.
        Returns number of tasks stolen/rebalanced.
        """
        if not self._steal_enabled:
            return 0

        stolen = 0

        # Work stealing is implicit in our architecture since all workers
        # pull from the same shared queue. However, we can implement
        # proactive work stealing by checking if any worker is starving
        # while the queue is non-empty.

        # The shared queue already provides natural work balancing.
        # Additional stealing would require per-worker queues.

        return stolen

    # ─── Auto-Scaling ───────────────────────────────────────────────────
    def _auto_scale(self) -> None:
        """
        Check load and scale the pool up or down accordingly.

        Scale up if queue depth exceeds threshold.
        Scale down if idle workers exceed threshold.
        """
        if self._state != PoolState.RUNNING:
            return

        qsize = self.queue_depth()
        with self._workers_lock:
            idle_count = sum(
                1 for h in self._workers.values()
                if h.metrics.state == WorkerState.IDLE
            )
            total = len(self._workers)

        # Scale up
        if qsize > self.scale_up_threshold and total < self.max_workers:
            with self._state_lock:
                self._state = PoolState.SCALING

            wid = self._next_worker_id()
            task_type = self.task_types[total % len(self.task_types)]
            if self._spawn_worker(wid, task_type):
                self._scale_events += 1
                logger.info(f"Scale UP: spawned worker {wid} (total={total + 1}, queue={qsize})")

            with self._state_lock:
                self._state = PoolState.RUNNING

        # Scale down
        elif idle_count > self.scale_down_threshold and total > self.min_workers:
            with self._state_lock:
                self._state = PoolState.SCALING

            # Kill the most recently idle worker
            with self._workers_lock:
                for wid, handle in list(self._workers.items())[::-1]:
                    if handle.metrics.state == WorkerState.IDLE:
                        self._kill_worker(wid)
                        self._scale_events += 1
                        logger.info(f"Scale DOWN: killed worker {wid} (total={total - 1}, idle={idle_count - 1})")
                        break

            with self._state_lock:
                self._state = PoolState.RUNNING

    # ─── Monitoring ────────────────────────────────────────────────────
    def _monitor_loop(self) -> None:
        """Background loop for health monitoring and auto-scaling."""
        while not self._stop_event.is_set():
            self._auto_scale()
            self._check_worker_health()
            self._stop_event.wait(self.scale_check_interval)

    def _check_worker_health(self) -> None:
        """Check all workers for death and restart as needed."""
        now = time.time()
        with self._workers_lock:
            for wid, handle in list(self._workers.items()):
                if not handle.is_alive:
                    logger.warning(f"Worker {wid} died, restarting...")
                    self._restart_worker(wid)
                    continue

                # Check heartbeat timeout
                if now - handle.last_heartbeat > self.heartbeat_timeout:
                    logger.warning(f"Worker {wid}: heartbeat timeout ({now - handle.last_heartbeat:.0f}s), killing")
                    self._kill_worker(wid)
                    self._restart_worker(wid)

    def _result_collector(self) -> None:
        """Background thread that reads results from the result queue."""
        while not self._stop_event.is_set():
            try:
                result = self._result_queue.get(timeout=1.0)
                self._process_result(result)
            except Empty:
                continue
            except (EOFError, OSError):
                break

    def _process_result(self, result: Dict[str, Any]) -> None:
        """Process a single task result."""
        worker_id = result.get("worker_id", -1)
        task_name = result.get("task_name", "unknown")
        success = result.get("success", False)
        elapsed = result.get("elapsed", 0)

        if success:
            self._total_completed += 1
        else:
            self._total_failed += 1

        self._total_work_time += elapsed
        self._task_times.append(elapsed)

        # Update worker metrics
        with self._workers_lock:
            handle = self._workers.get(worker_id)
            if handle:
                if success:
                    handle.metrics.tasks_completed += 1
                else:
                    handle.metrics.tasks_failed += 1
                handle.metrics.total_work_time += elapsed
                handle.metrics.state = WorkerState.IDLE
                handle.metrics.current_task = None

        # Call registered callbacks
        for cb in self._result_callbacks:
            try:
                cb(result)
            except Exception:
                pass

    def on_result(self, callback: Callable[[Dict[str, Any]], None]) -> None:
        """Register a callback for task results."""
        self._result_callbacks.append(callback)

    # ─── Metrics ────────────────────────────────────────────────────────
    def get_metrics(self) -> PoolMetrics:
        """Get current pool and per-worker metrics."""
        now = time.time()
        with self._workers_lock:
            workers = []
            idle = busy = dead = 0
            for wid, handle in self._workers.items():
                if not handle.is_alive:
                    dead += 1
                elif handle.metrics.state == WorkerState.BUSY:
                    busy += 1
                else:
                    idle += 1
                workers.append(handle.metrics.to_dict())
            total = len(self._workers)

        avg_time = 0.0
        if self._task_times:
            avg_time = sum(self._task_times) / len(self._task_times)

        return PoolMetrics(
            total_workers=total,
            idle_workers=idle,
            busy_workers=busy,
            dead_workers=dead,
            total_tasks_completed=self._total_completed,
            total_tasks_failed=self._total_failed,
            queued_tasks=self.queue_depth(),
            avg_task_time=avg_time,
            uptime_seconds=now - self._started_at if self._started_at else 0,
            scale_events=self._scale_events,
            workers=workers,
        )

    def get_state(self) -> PoolState:
        """Get current pool state."""
        return self._state

    def __repr__(self) -> str:
        m = self.get_metrics()
        return (f"WorkerPool(workers={m.total_workers}, idle={m.idle_workers}, "
                f"busy={m.busy_workers}, completed={m.total_tasks_completed}, "
                f"queued={m.queued_tasks})")


# ─── CLI ──────────────────────────────────────────────────────────────────
def main():
    """CLI entry for standalone worker pool testing."""
    import argparse
    parser = argparse.ArgumentParser(description="ENI Worker Pool")
    parser.add_argument("--min-workers", type=int, default=2)
    parser.add_argument("--max-workers", type=int, default=4)
    parser.add_argument("--tasks", type=int, default=10, help="Number of test tasks")
    parser.add_argument("--runtime", type=float, default=5.0, help="Runtime in seconds")
    args = parser.parse_args()

    pool = WorkerPool(min_workers=args.min_workers, max_workers=args.max_workers)
    pool.start()

    # Submit test tasks
    for i in range(args.tasks):
        task = {
            "name": f"test_task_{i}",
            "type": TaskType.BUILD if i % 2 == 0 else TaskType.COMPRESS,
            "task": f"Test task body {i}",
            "priority": i % 3 + 1,
        }
        pool.submit_task(task)

    print(f"Submitted {args.tasks} tasks. Pool: {pool}")

    # Let it run
    try:
        time.sleep(args.runtime)
    except KeyboardInterrupt:
        pass

    metrics = pool.get_metrics()
    print(f"\nFinal metrics:")
    print(f"  Completed: {metrics.total_tasks_completed}")
    print(f"  Failed: {metrics.total_tasks_failed}")
    print(f"  Avg time: {metrics.avg_task_time:.3f}s")
    print(f"  Workers: {metrics.total_workers} (idle={metrics.idle_workers}, busy={metrics.busy_workers})")
    print(f"  Scale events: {metrics.scale_events}")

    pool.stop()
    print("Done.")


if __name__ == "__main__":
    main()