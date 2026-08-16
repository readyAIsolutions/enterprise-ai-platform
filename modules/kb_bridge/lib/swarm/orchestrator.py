#!/usr/bin/env python3
"""
SwarmOrchestrator — Central Coordination Engine
=================================================

The SwarmOrchestrator is the brain of the parallel ENI swarm. It:
  1. Loads task configurations from config/eni_build_tasks.json and config/eni_herself_tasks.json
  2. Manages a pool of mini-ENI agents launched via the PTY bridge (eni_agent_term.py)
  3. Distributes tasks with round-robin load balancing across model pools
  4. Tracks task completion, staleness, and zombie detection
  5. Provides start/stop/pause/resume for individual minis and groups
  6. Integrates with the heartbeat/telemetry system
  7. Interfaces with WorkerPool, TaskScheduler, and SwarmMonitor

Usage:
  orchestrator = SwarmOrchestrator()
  orchestrator.start_all()
  orchestrator.run_loop()
"""

from __future__ import annotations

import os
import sys
import json
import time
import signal
import logging
import threading
import subprocess
from pathlib import Path
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import Dict, List, Optional, Any, Set, Tuple
from collections import defaultdict, deque

# ─── Setup logging ──────────────────────────────────────────────────────────
logger = logging.getLogger("swarm.orchestrator")
logger.setLevel(logging.DEBUG)
if not logger.handlers:
    h = logging.StreamHandler()
    h.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
    logger.addHandler(h)

# ─── Paths ──────────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parents[2]  # .../ENI_Swarm_NEW
CONFIG_DIR = ROOT / "config"
TASKS_BUILD = CONFIG_DIR / "eni_build_tasks.json"
TASKS_HERSELF = CONFIG_DIR / "eni_herself_tasks.json"
SWARM_DIR = ROOT / "tasks" / "swarm"
STATUS_DIR = ROOT / "tasks" / "status"
FIFO_DIR = Path("/tmp")
STATE_FILE = Path.home() / ".cache" / "eni_swarm" / "orchestrator_state.json"
BRIDGE_SCRIPT = ROOT / "bin" / "eni_agent_term.py"

for d in (SWARM_DIR, STATUS_DIR, STATE_FILE.parent):
    d.mkdir(parents=True, exist_ok=True)


# ─── Enums ──────────────────────────────────────────────────────────────────
class MiniState(Enum):
    """Possible states for a mini agent."""
    IDLE = auto()
    STARTING = auto()
    RUNNING = auto()
    PAUSED = auto()
    COMPLETED = auto()
    BLOCKED = auto()
    DEAD = auto()
    ZOMBIE = auto()  # process exists but no heartbeat
    STOPPED = auto()


class OrchestratorState(Enum):
    """Global orchestrator state."""
    INIT = auto()
    RUNNING = auto()
    PAUSED = auto()
    SHUTDOWN = auto()


# ─── Mini State ─────────────────────────────────────────────────────────────
@dataclass
class MiniInfo:
    """Runtime information about a single mini agent."""
    name: str
    title: str
    workdir: str
    model: str
    provider: str
    task: str
    priority: int
    dependencies: List[str]
    status_file: str = ""
    fifo_path: str = ""
    pid: int = 0
    state: MiniState = MiniState.IDLE
    last_heartbeat: float = 0.0
    last_status_change: float = 0.0
    cycles_since_heartbeat: int = 0
    tasks_completed: int = 0
    errors: int = 0
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    group: str = "default"

    def __post_init__(self):
        if not self.status_file:
            self.status_file = f"STATUS_{self.name}.md"
        if not self.fifo_path:
            self.fifo_path = str(FIFO_DIR / f"eni_ctl_{self.name}")


# ─── Zombie/Staleness Configuration ────────────────────────────────────────
@dataclass
class HealthConfig:
    """Configuration for health monitoring thresholds."""
    heartbeat_timeout: float = 120.0        # seconds without heartbeat -> suspect
    zombie_timeout: float = 300.0           # seconds without heartbeat -> zombie
    staleness_timeout: float = 600.0        # seconds without progress -> stale
    max_restart_attempts: int = 5           # max consecutive restarts
    restart_cooldown: float = 30.0          # seconds between restart attempts
    heartbeat_interval: float = 10.0        # how often to check heartbeats


# ─── FIFO Utilities ─────────────────────────────────────────────────────────
def ensure_fifo(path: str) -> bool:
    """Create a named FIFO at path, removing any non-FIFO file first."""
    p = Path(path)
    try:
        if p.exists() and not p.is_fifo():
            p.unlink()
        if not p.exists():
            os.mkfifo(p, 0o666)
        return True
    except Exception as e:
        logger.error(f"Failed to create FIFO {path}: {e}")
        return False


def send_fifo(path: str, msg: str) -> bool:
    """Non-blocking write to a control FIFO. Returns True on success."""
    try:
        fd = os.open(path, os.O_WRONLY | os.O_NONBLOCK)
        try:
            os.write(fd, (msg + "\n").encode())
            return True
        finally:
            os.close(fd)
    except OSError:
        return False


def is_process_alive(pid: int) -> bool:
    """Check if a process with given PID exists."""
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


# ─── Round-Robin Allocator ──────────────────────────────────────────────────
class ModelPoolAllocator:
    """
    Manages model pools and assigns tasks round-robin across
    available models to balance API load.
    """

    def __init__(self):
        self._model_queues: Dict[str, deque] = defaultdict(deque)
        self._model_lock = threading.Lock()
        self._model_usage: Dict[str, int] = defaultdict(int)
        self._ratelimit_map: Dict[str, float] = {}  # model -> next_available_at

    def register_model(self, model: str) -> None:
        """Register a model in the allocation pool."""
        with self._model_lock:
            identifier = model.split("/")[-1] if "/" in model else model
            if identifier not in self._model_queues:
                self._model_queues[identifier] = deque()

    def get_next_slot(self, model: str) -> bool:
        """
        Check if a model has an available slot (not rate-limited).
        Returns True if the model can accept a task.
        """
        now = time.time()
        if model in self._ratelimit_map and now < self._ratelimit_map[model]:
            return False
        return True

    def mark_used(self, model: str) -> None:
        """Mark a model as having been assigned one task."""
        with self._model_lock:
            identifier = model.split("/")[-1] if "/" in model else model
            self._model_usage[identifier] += 1

    def mark_ratelimited(self, model: str, backoff_seconds: float) -> None:
        """Mark a model as rate-limited for a duration."""
        self._ratelimit_map[model] = time.time() + backoff_seconds
        logger.warning(f"Model {model} rate-limited for {backoff_seconds}s")

    def get_usage_stats(self) -> Dict[str, int]:
        """Return per-model usage counts."""
        with self._model_lock:
            return dict(self._model_usage)


# ─── SwarmOrchestrator ─────────────────────────────────────────────────────
class SwarmOrchestrator:
    """
    Central coordination engine for the ENI Swarm.

    Loads task configs, manages mini agents, distributes tasks
    with load balancing, tracks health, and integrates with
    WorkerPool, TaskScheduler, and SwarmMonitor subsystems.
    """

    def __init__(
        self,
        config_dir: Optional[Path] = None,
        health_config: Optional[HealthConfig] = None,
        monitor=None,
        scheduler=None,
        worker_pool=None,
    ):
        """
        Initialize the orchestrator.

        Args:
            config_dir: Override config directory path
            health_config: Custom health monitoring thresholds
            monitor: Optional SwarmMonitor instance for metrics
            scheduler: Optional TaskScheduler instance
            worker_pool: Optional WorkerPool instance
        """
        global CONFIG_DIR
        if config_dir:
            CONFIG_DIR = Path(config_dir)

        self.config_dir = CONFIG_DIR
        self.health_config = health_config or HealthConfig()
        self.monitor = monitor
        self.scheduler = scheduler
        self.worker_pool = worker_pool

        # Mini management
        self._minis: Dict[str, MiniInfo] = {}
        self._mini_lock = threading.RLock()
        self._groups: Dict[str, List[str]] = defaultdict(list)  # group -> [mini_names]

        # Model pool allocator for load balancing
        self._allocator = ModelPoolAllocator()

        # Orchestrator state
        self._state = OrchestratorState.INIT
        self._state_lock = threading.Lock()
        self._cycle_count = 0
        self._stop_event = threading.Event()
        self._heartbeat_thread: Optional[threading.Thread] = None

        # Restart tracking
        self._restart_attempts: Dict[str, int] = defaultdict(int)
        self._restart_timestamps: Dict[str, float] = {}

        # Completion tracking
        self._completed_tasks: Set[str] = set()
        self._failed_tasks: Dict[str, str] = {}  # name -> reason

        logger.info("SwarmOrchestrator initialized (v4.0.0)")

    # ─── Task Loading ───────────────────────────────────────────────────
    def load_tasks(self, build_path: Optional[Path] = None,
                   herself_path: Optional[Path] = None) -> List[MiniInfo]:
        """
        Load task configurations from JSON files.

        Args:
            build_path: Override path to eni_build_tasks.json
            herself_path: Override path to eni_herself_tasks.json

        Returns:
            List of loaded MiniInfo objects
        """
        build = build_path or (self.config_dir / "eni_build_tasks.json")
        herself = herself_path or (self.config_dir / "eni_herself_tasks.json")

        loaded = []
        for path, group in [(build, "build"), (herself, "herself")]:
            if not path.exists():
                logger.warning(f"Task file not found: {path}")
                continue
            try:
                data = json.loads(path.read_text())
                for t in data.get("tasks", []):
                    mini = MiniInfo(
                        name=t["name"],
                        title=t.get("title", t["name"]),
                        workdir=os.path.expanduser(t.get("workdir", "~")),
                        model=t.get("model", "tencent/hy3:free"),
                        provider=t.get("provider", "openrouter"),
                        task=t.get("task", ""),
                        priority=t.get("priority", 1),
                        dependencies=t.get("dependencies", []),
                        group=group,
                    )
                    loaded.append(mini)
                    self._allocator.register_model(mini.model)
                    self._groups[group].append(mini.name)
                    logger.debug(f"Loaded task: {mini.name} (group={group}, priority={mini.priority})")
            except Exception as e:
                logger.error(f"Failed to load {path}: {e}")

        with self._mini_lock:
            for mini in loaded:
                self._minis[mini.name] = mini

        logger.info(f"Total tasks loaded: {len(loaded)} across {len(self._groups)} groups")
        return loaded

    # ─── Mini Lifecycle ────────────────────────────────────────────────
    def launch_mini(self, mini: MiniInfo) -> int:
        """
        Launch a mini agent via the PTY bridge.

        Args:
            mini: MiniInfo with task configuration

        Returns:
            PID of the launched process, or 0 on failure
        """
        with self._mini_lock:
            if not ensure_fifo(mini.fifo_path):
                logger.error(f"Cannot create FIFO for {mini.name}")
                return 0

            # Write task file for the bridge to pre-type
            task_file = SWARM_DIR / f"{mini.name}.txt"
            task_file.write_text(mini.task)

            cmd = [
                sys.executable, str(BRIDGE_SCRIPT),
                f"@{task_file}", mini.workdir,
                "-m", mini.model,
                "--provider", mini.provider,
                "--fifo", mini.fifo_path,
                "--name", mini.name,
            ]

            try:
                proc = subprocess.Popen(
                    cmd,
                    start_new_session=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                mini.pid = proc.pid
                mini.state = MiniState.RUNNING
                mini.started_at = time.time()
                mini.last_heartbeat = time.time()
                logger.info(f"[LAUNCH] {mini.name} pid={proc.pid} model={mini.model}")
                return proc.pid
            except Exception as e:
                logger.error(f"Failed to launch {mini.name}: {e}")
                mini.state = MiniState.DEAD
                return 0

    def stop_mini(self, name: str, graceful: bool = True) -> bool:
        """Stop a specific mini agent."""
        with self._mini_lock:
            mini = self._minis.get(name)
            if not mini or mini.pid <= 0:
                return False

            try:
                if graceful:
                    send_fifo(mini.fifo_path, "STOP: graceful shutdown requested")
                    time.sleep(2)
                    os.kill(mini.pid, signal.SIGTERM)
                    # Wait briefly
                    for _ in range(10):
                        if not is_process_alive(mini.pid):
                            break
                        time.sleep(0.5)
                    if is_process_alive(mini.pid):
                        os.kill(mini.pid, signal.SIGKILL)
                else:
                    try:
                        os.killpg(os.getpgid(mini.pid), signal.SIGKILL)
                    except Exception:
                        os.kill(mini.pid, signal.SIGKILL)

                mini.state = MiniState.STOPPED
                mini.pid = 0
                logger.info(f"[STOP] {name} stopped")
                return True
            except Exception as e:
                logger.error(f"Error stopping {name}: {e}")
                mini.state = MiniState.DEAD
                return False

    def pause_mini(self, name: str) -> bool:
        """Pause a mini agent (send SIGSTOP)."""
        with self._mini_lock:
            mini = self._minis.get(name)
            if not mini or mini.pid <= 0:
                return False
            try:
                send_fifo(mini.fifo_path, "PAUSE: hold current work")
                os.kill(mini.pid, signal.SIGSTOP)
                mini.state = MiniState.PAUSED
                logger.info(f"[PAUSE] {name}")
                return True
            except Exception as e:
                logger.error(f"Failed to pause {name}: {e}")
                return False

    def resume_mini(self, name: str) -> bool:
        """Resume a paused mini agent (send SIGCONT)."""
        with self._mini_lock:
            mini = self._minis.get(name)
            if not mini or mini.pid <= 0:
                return False
            try:
                os.kill(mini.pid, signal.SIGCONT)
                send_fifo(mini.fifo_path, "RESUME: continue your task")
                mini.state = MiniState.RUNNING
                mini.last_heartbeat = time.time()
                logger.info(f"[RESUME] {name}")
                return True
            except Exception as e:
                logger.error(f"Failed to resume {name}: {e}")
                return False

    def restart_mini(self, name: str) -> bool:
        """Restart a mini agent (stop + relaunch)."""
        mini = self._minis.get(name)
        if not mini:
            return False

        # Check cooldown
        now = time.time()
        if name in self._restart_timestamps:
            elapsed = now - self._restart_timestamps[name]
            if elapsed < self.health_config.restart_cooldown:
                logger.warning(f"{name}: restart cooldown active ({elapsed:.0f}s < {self.health_config.restart_cooldown}s)")
                return False

        attempts = self._restart_attempts.get(name, 0)
        if attempts >= self.health_config.max_restart_attempts:
            logger.error(f"{name}: max restart attempts ({self.health_config.max_restart_attempts}) exceeded")
            mini.state = MiniState.DEAD
            return False

        self.stop_mini(name, graceful=False)
        self._restart_attempts[name] = attempts + 1
        self._restart_timestamps[name] = now
        pid = self.launch_mini(mini)
        return pid > 0

    # ─── Group Operations ──────────────────────────────────────────────
    def start_group(self, group: str) -> List[str]:
        """Start all minis in a group. Returns list of names that started."""
        started = []
        with self._mini_lock:
            for name in self._groups.get(group, []):
                mini = self._minis.get(name)
                if mini and mini.state in (MiniState.IDLE, MiniState.STOPPED, MiniState.DEAD):
                    pid = self.launch_mini(mini)
                    if pid > 0:
                        started.append(name)
        logger.info(f"Started group '{group}': {len(started)} minis")
        return started

    def stop_group(self, group: str) -> List[str]:
        """Stop all minis in a group. Returns list of names stopped."""
        stopped = []
        for name in list(self._groups.get(group, [])):
            if self.stop_mini(name):
                stopped.append(name)
        logger.info(f"Stopped group '{group}': {len(stopped)} minis")
        return stopped

    def pause_group(self, group: str) -> List[str]:
        """Pause all minis in a group."""
        paused = []
        for name in self._groups.get(group, []):
            if self.pause_mini(name):
                paused.append(name)
        logger.info(f"Paused group '{group}': {len(paused)} minis")
        return paused

    def resume_group(self, group: str) -> List[str]:
        """Resume all minis in a group."""
        resumed = []
        for name in self._groups.get(group, []):
            if self.resume_mini(name):
                resumed.append(name)
        logger.info(f"Resumed group '{group}': {len(resumed)} minis")
        return resumed

    # ─── Global Lifecycle ──────────────────────────────────────────────
    def start_all(self) -> int:
        """Launch all non-MASTER minis. Returns count of launched processes."""
        with self._state_lock:
            if self._state == OrchestratorState.RUNNING:
                logger.warning("Orchestrator already running")
                return 0
            self._state = OrchestratorState.RUNNING
            self._stop_event.clear()

        count = 0
        with self._mini_lock:
            for name, mini in self._minis.items():
                if name == "MASTER":
                    continue
                if mini.state in (MiniState.IDLE, MiniState.STOPPED):
                    pid = self.launch_mini(mini)
                    if pid > 0:
                        count += 1

        logger.info(f"[ORCHESTRATOR] Started with {count} minis, state=RUNNING")
        self._start_heartbeat_thread()
        return count

    def stop_all(self) -> None:
        """Stop all running minis and enter SHUTDOWN state."""
        logger.info("[ORCHESTRATOR] Shutting down all minis")
        with self._state_lock:
            self._state = OrchestratorState.SHUTDOWN
            self._stop_event.set()

        if self._heartbeat_thread and self._heartbeat_thread.is_alive():
            self._heartbeat_thread.join(timeout=5)

        with self._mini_lock:
            for name, mini in list(self._minis.items()):
                if mini.pid > 0 and is_process_alive(mini.pid):
                    self.stop_mini(name, graceful=True)

        logger.info("[ORCHESTRATOR] All minis stopped")

    def pause_all(self) -> None:
        """Pause all running minis."""
        with self._state_lock:
            if self._state != OrchestratorState.RUNNING:
                return
            self._state = OrchestratorState.PAUSED

        with self._mini_lock:
            for name in list(self._minis.keys()):
                self.pause_mini(name)

        logger.info("[ORCHESTRATOR] All minis paused")

    def resume_all(self) -> None:
        """Resume all paused minis."""
        with self._state_lock:
            if self._state != OrchestratorState.PAUSED:
                return
            self._state = OrchestratorState.RUNNING

        with self._mini_lock:
            for name in list(self._minis.keys()):
                self.resume_mini(name)

        logger.info("[ORCHESTRATOR] All minis resumed")

    # ─── Heartbeat & Health ────────────────────────────────────────────
    def _start_heartbeat_thread(self) -> None:
        """Start the background heartbeat monitoring thread."""
        if self._heartbeat_thread and self._heartbeat_thread.is_alive():
            return
        self._heartbeat_thread = threading.Thread(
            target=self._heartbeat_loop, daemon=True,
            name="orchestrator-heartbeat"
        )
        self._heartbeat_thread.start()

    def _heartbeat_loop(self) -> None:
        """Background loop that checks mini health periodically."""
        logger.info("Heartbeat monitor started")
        while not self._stop_event.is_set():
            self._health_check()
            self._stop_event.wait(self.health_config.heartbeat_interval)

    def _health_check(self) -> None:
        """Check all minis for health, staleness, and zombies."""
        now = time.time()
        with self._mini_lock:
            for name, mini in list(self._minis.items()):
                if mini.state in (MiniState.IDLE, MiniState.STOPPED, MiniState.COMPLETED):
                    continue

                # Check if process is alive
                if mini.pid > 0:
                    if not is_process_alive(mini.pid):
                        logger.warning(f"[HEALTH] {name}: process {mini.pid} is dead")
                        mini.state = MiniState.DEAD
                        self._handle_dead_mini(name)
                        continue
                elif mini.state not in (MiniState.IDLE, MiniState.COMPLETED):
                    mini.state = MiniState.DEAD
                    self._handle_dead_mini(name)
                    continue

                # Check heartbeat staleness
                elapsed = now - mini.last_heartbeat
                if elapsed > self.health_config.zombie_timeout:
                    if mini.state != MiniState.ZOMBIE:
                        logger.warning(f"[HEALTH] {name}: ZOMBIE (no heartbeat for {elapsed:.0f}s)")
                        mini.state = MiniState.ZOMBIE
                        if self.monitor:
                            self.monitor.record_alert(
                                "zombie_detected",
                                f"{name} is a zombie: no heartbeat for {elapsed:.0f}s",
                            )
                elif elapsed > self.health_config.heartbeat_timeout:
                    if mini.state == MiniState.RUNNING:
                        logger.warning(f"[HEALTH] {name}: stalled (no heartbeat for {elapsed:.0f}s)")

                # Check staleness
                if elapsed > self.health_config.staleness_timeout:
                    logger.warning(f"[HEALTH] {name}: stale (no progress for {elapsed:.0f}s), attempting restart")
                    self._handle_dead_mini(name)

    def _handle_dead_mini(self, name: str) -> None:
        """Handle a dead or zombie mini by attempting restart."""
        mini = self._minis.get(name)
        if not mini:
            return

        if self._restart_attempts.get(name, 0) < self.health_config.max_restart_attempts:
            logger.info(f"[HEAL] Attempting to restart {name}")
            self.restart_mini(name)
            if self.monitor:
                self.monitor.record_alert(
                    "mini_restarted",
                    f"{name} was restarted (attempt {self._restart_attempts.get(name, 0)})",
                )
        else:
            logger.error(f"[HEAL] {name}: max restart attempts reached, marking as dead")
            mini.state = MiniState.DEAD
            if self.monitor:
                self.monitor.record_alert(
                    "mini_dead_permanent",
                    f"{name} is permanently dead after {self._restart_attempts.get(name, 0)} restart attempts",
                )

    def heartbeat(self, name: str) -> None:
        """
        Record a heartbeat from a mini agent.
        Call this when a mini sends a status update or responds.
        """
        with self._mini_lock:
            mini = self._minis.get(name)
            if mini:
                mini.last_heartbeat = time.time()
                mini.cycles_since_heartbeat = 0
                if mini.state == MiniState.ZOMBIE:
                    mini.state = MiniState.RUNNING
                    logger.info(f"[HEALTH] {name}: recovered from zombie state")

    # ─── Status Reading ────────────────────────────────────────────────
    def read_mini_status(self, name: str) -> Tuple[str, str]:
        """
        Read a mini's STATUS_*.md file.

        Returns:
            Tuple of (raw_text, parsed_state_string)
            parsed_state_string is one of: DONE, IN-PROGRESS, BLOCKED, UNKNOWN, or empty string
        """
        mini = self._minis.get(name)
        if not mini:
            return ("", "")

        status_path = Path(mini.workdir) / mini.status_file
        try:
            txt = status_path.read_text()
        except Exception:
            return ("", "")

        s = txt.upper()
        if "BLOCKED" in s:
            state = "BLOCKED"
        elif "DONE" in s:
            state = "DONE"
        elif "IN-PROGRESS" in s or "IN PROGRESS" in s:
            state = "IN-PROGRESS"
        else:
            state = "UNKNOWN"

        return (txt, state)

    def mark_completed(self, name: str) -> None:
        """Mark a mini's task as completed."""
        with self._mini_lock:
            mini = self._minis.get(name)
            if mini:
                mini.state = MiniState.COMPLETED
                mini.completed_at = time.time()
                mini.tasks_completed += 1
                self._completed_tasks.add(name)
                logger.info(f"[DONE] {name}: task completed")

    def mark_blocked(self, name: str, reason: str = "") -> None:
        """Mark a mini as blocked."""
        with self._mini_lock:
            mini = self._minis.get(name)
            if mini:
                mini.state = MiniState.BLOCKED
                self._failed_tasks[name] = reason or "no reason provided"
                logger.warning(f"[BLOCKED] {name}: {reason or 'no reason provided'}")

    # ─── Round-Robin Task Assignment ───────────────────────────────────
    def assign_task_round_robin(self, task_list: List[Dict[str, Any]]) -> Dict[str, str]:
        """
        Distribute tasks to available minis using round-robin across model pools.

        Args:
            task_list: List of task dicts with keys: name, model, task, workdir, etc.

        Returns:
            Dict mapping task_name -> assigned_mini_name
        """
        assignments = {}
        # Sort by priority (lower = higher priority)
        sorted_tasks = sorted(task_list, key=lambda t: t.get("priority", 99))

        for task in sorted_tasks:
            model = task.get("model", "tencent/hy3:free")

            # Skip if model is rate-limited
            if not self._allocator.get_next_slot(model):
                logger.debug(f"Skipping task {task['name']}: model {model} rate-limited")
                continue

            # Find an available mini matching this model or any idle mini
            with self._mini_lock:
                available = [
                    (n, m) for n, m in self._minis.items()
                    if m.state in (MiniState.IDLE, MiniState.RUNNING)
                    and m.name != "MASTER"
                ]

            if not available:
                logger.warning(f"No available minis for task {task['name']}")
                continue

            # Prefer minis with matching model, then any idle
            match = None
            for name, mini in available:
                if mini.model == model and mini.state == MiniState.IDLE:
                    match = mini
                    break
            if not match:
                for name, mini in available:
                    if mini.state == MiniState.IDLE:
                        match = mini
                        break
            if not match and available:
                match = available[0][1]

            if match:
                # Assign the task by sending it to the mini's FIFO
                task_prompt = self._build_task_prompt(task)
                send_fifo(match.fifo_path, task_prompt)
                assignments[task["name"]] = match.name
                self._allocator.mark_used(match.model)
                logger.info(f"[ASSIGN] Task '{task['name']}' -> mini '{match.name}' (model={match.model})")

        return assignments

    def _build_task_prompt(self, task: Dict[str, Any]) -> str:
        """Build a prompt string for sending to a mini agent."""
        parts = [
            f"TASK: {task.get('name', 'unnamed')}",
            f"TITLE: {task.get('title', task.get('name', ''))}",
            f"PRIORITY: {task.get('priority', 1)}",
        ]
        if task.get("dependencies"):
            parts.append(f"DEPENDS_ON: {', '.join(task['dependencies'])}")
        parts.append(f"\n{task.get('task', '')}")
        parts.append(f"\nWrite STATUS_{task.get('name', 'mini')}.md with your progress.")
        return "\n".join(parts)

    # ─── Dependency Resolution ────────────────────────────────────────
    def get_ready_tasks(self) -> List[str]:
        """
        Return list of mini names whose dependencies are all satisfied.

        A dependency is satisfied if the dependent mini is COMPLETED.
        """
        ready = []
        with self._mini_lock:
            for name, mini in self._minis.items():
                if mini.state == MiniState.COMPLETED:
                    continue
                if mini.state == MiniState.BLOCKED:
                    continue
                deps_met = all(
                    dep in self._completed_tasks
                    for dep in mini.dependencies
                )
                if deps_met:
                    ready.append(name)
        return ready

    # ─── Monitoring Integration ────────────────────────────────────────
    def get_status_summary(self) -> Dict[str, Any]:
        """
        Generate a comprehensive status summary for monitoring.

        Returns:
            Dict with keys: total, running, completed, blocked, dead, zombie,
            idle, stopped, paused, minis (list of per-mini status)
        """
        now = time.time()
        summary = {
            "timestamp": datetime.now().isoformat(),
            "orchestrator_state": self._state.name,
            "cycle": self._cycle_count,
            "total": 0,
            "running": 0,
            "completed": 0,
            "blocked": 0,
            "dead": 0,
            "zombie": 0,
            "idle": 0,
            "stopped": 0,
            "paused": 0,
            "model_usage": self._allocator.get_usage_stats(),
            "minis": [],
        }

        with self._mini_lock:
            summary["total"] = len(self._minis)
            for name, mini in self._minis.items():
                state_name = mini.state.name
                if state_name in summary:
                    summary[state_name.lower()] = summary.get(state_name.lower(), 0) + 1

                uptime = (now - mini.started_at) if mini.started_at else 0
                summary["minis"].append({
                    "name": mini.name,
                    "title": mini.title,
                    "state": state_name,
                    "model": mini.model,
                    "pid": mini.pid,
                    "priority": mini.priority,
                    "dependencies": mini.dependencies,
                    "group": mini.group,
                    "uptime_seconds": round(uptime, 1),
                    "tasks_completed": mini.tasks_completed,
                    "errors": mini.errors,
                    "last_heartbeat_ago": round(now - mini.last_heartbeat, 1) if mini.last_heartbeat else None,
                })

        return summary

    # ─── Main Loop ────────────────────────────────────────────────────
    def run_loop(self, interval: float = 30.0, single_cycle: bool = False) -> None:
        """
        Run the main coordination loop.

        Args:
            interval: Seconds between coordination cycles
            single_cycle: If True, run exactly one cycle and return
        """
        lgr = logger
        lgr.info(f"[ORCHESTRATOR] Coordination loop starting (interval={interval}s)")

        while not self._stop_event.is_set():
            self._cycle_count += 1
            self._run_cycle()

            # Push status to monitor
            if self.monitor:
                try:
                    self.monitor.update_status(self.get_status_summary())
                except Exception as e:
                    lgr.debug(f"Monitor update failed: {e}")

            # Notify scheduler
            if self.scheduler:
                try:
                    ready = self.get_ready_tasks()
                    self.scheduler.notify_ready_tasks(ready)
                except Exception as e:
                    lgr.debug(f"Scheduler notify failed: {e}")

            # Feed worker pool with tasks
            if self.worker_pool:
                try:
                    ready = self.get_ready_tasks()
                    for name in ready:
                        mini = self._minis.get(name)
                        if mini and mini.state == MiniState.IDLE:
                            self.worker_pool.submit_task({
                                "name": name,
                                "task": mini.task,
                                "workdir": mini.workdir,
                                "model": mini.model,
                            })
                except Exception as e:
                    lgr.debug(f"Worker pool submit failed: {e}")

            if single_cycle:
                break

            self._stop_event.wait(interval)

        lgr.info("[ORCHESTRATOR] Coordination loop ended")

    def _run_cycle(self) -> None:
        """Execute one coordination cycle: health check, status reads, completion tracking."""
        # Health checks are done by heartbeat thread, but do a pass here too
        self._health_check()

        with self._mini_lock:
            for name, mini in list(self._minis.items()):
                if mini.state in (MiniState.COMPLETED, MiniState.STOPPED, MiniState.IDLE):
                    continue

                txt, state = self.read_mini_status(name)
                if txt:
                    self.heartbeat(name)  # status update counts as heartbeat

                    if state == "DONE":
                        self.mark_completed(name)
                    elif state == "BLOCKED":
                        # Extract blocker reason
                        blocker = ""
                        for line in txt.splitlines():
                            if line.strip().lower().startswith("blocker"):
                                blocker = line.split("=", 1)[-1].strip()
                                break
                        self.mark_blocked(name, blocker)

    def get_state(self) -> OrchestratorState:
        """Get current orchestrator state."""
        with self._state_lock:
            return self._state

    def __repr__(self) -> str:
        return (f"SwarmOrchestrator(state={self._state.name}, minis={len(self._minis)}, "
                f"cycle={self._cycle_count})")


# ─── CLI entry ─────────────────────────────────────────────────────────────
def main():
    """CLI entry point for standalone orchestrator usage."""
    import argparse
    parser = argparse.ArgumentParser(description="ENI Swarm Orchestrator")
    parser.add_argument("--config-dir", type=Path, help="Config directory path")
    parser.add_argument("--interval", type=float, default=30.0, help="Coordination interval in seconds")
    parser.add_argument("--single", action="store_true", help="Run a single cycle and exit")
    parser.add_argument("--no-launch", action="store_true", help="Load tasks only, don't launch")
    args = parser.parse_args()

    orch = SwarmOrchestrator(config_dir=args.config_dir)
    orch.load_tasks()

    if not args.no_launch:
        orch.start_all()
        try:
            orch.run_loop(interval=args.interval, single_cycle=args.single)
        except KeyboardInterrupt:
            print("\n[ORCHESTRATOR] Interrupted, shutting down...")
        finally:
            orch.stop_all()
    else:
        print(f"Loaded {len(orch._minis)} tasks (no-launch mode)")
        for name, mini in orch._minis.items():
            print(f"  {name}: {mini.title} [{mini.model}] priority={mini.priority}")


if __name__ == "__main__":
    main()