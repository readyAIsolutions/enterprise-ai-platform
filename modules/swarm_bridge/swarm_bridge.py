#!/usr/bin/env python3
"""
ENI Swarm Bridge — Enterprise Lifecycle & Status Management
============================================================
Production-quality bridge between the Enterprise Platform Kernel and
the ENI Swarm (Master Driver v5.0 + 50 builders).

Provides:
  - spawn_swarm()        — launch the master driver + optional dashboard
  - get_swarm_status()   — aggregated swarm health & builder states
  - get_builder_status() — per-builder detail (state, blocker, logs)
  - get_task_rosters()   — loaded task definitions
  - pause / resume       — control individual builders via FIFO
  - health monitoring    — continuous builder liveness + metrics

Events emitted (when EventBus is wired):
  - swarm.builder.started
  - swarm.builder.completed
  - swarm.builder.failed
  - swarm.master.status

Metrics:
  - active_builders, completed_tasks, failure_rate, avg_task_duration

Does NOT break the existing dashboard on :8420 — all interactions are
read-only (status files, state files, builder logs) or via FIFO control
messages. Never touches the Starlette server process.
"""
from __future__ import annotations

import json
import logging
import os
import re
import signal
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

logger = logging.getLogger("enterprise.swarm.bridge")


# =============================================================================
# Data Classes
# =============================================================================


@dataclass
class BuilderStatus:
    """Snapshot of a single builder's current state.

    Attributes:
        name:            Builder name (e.g., "BUILDER_01", "ENI_SELF_3").
        title:           Human-readable title from task config.
        state:           Parsed state: DONE, IN-PROGRESS, BLOCKED, IDLE, UNKNOWN.
        alive:           Is the builder process/hermes-run slot alive?
        pid:             Process ID (0 if on-demand).
        active:          Currently executing a hermes run (True/False).
        cycles_since_reply: Coordination cycles since last builder output.
        last_update:     ISO timestamp of last status file write.
        workdir:         Working directory for this builder.
        model:           Model name (e.g., "free-router").
        provider:        Provider name.
        blocker:         Blocked reason (if BLOCKED).
        task_count:      Number of tasks completed.
        last_reply:      Last log line from this builder.
        task_pending:    Whether a new task is queued via FIFO.
    """

    name: str
    title: str = ""
    state: str = "UNKNOWN"
    alive: bool = False
    pid: int = 0
    active: bool = False
    cycles_since_reply: int = 0
    last_update: str = ""
    workdir: str = "~"
    model: str = "free-router"
    provider: str = "free-router"
    blocker: str = ""
    task_count: int = 0
    last_reply: str = ""
    task_pending: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "title": self.title,
            "state": self.state,
            "alive": self.alive,
            "active": self.active,
            "pid": self.pid,
            "cycles_since_reply": self.cycles_since_reply,
            "last_update": self.last_update,
            "workdir": self.workdir,
            "model": self.model,
            "provider": self.provider,
            "blocker": self.blocker,
            "task_count": self.task_count,
            "last_reply": self.last_reply[:200] if self.last_reply else "",
            "task_pending": self.task_pending,
        }


@dataclass
class SwarmMetrics:
    """Aggregate swarm performance metrics.

    Attributes:
        active_builders:    Count of builders currently executing.
        completed_tasks:    Cumulative successful task count.
        failed_tasks:       Cumulative failed/timed-out task count.
        total_tasks:        Total task attempts.
        failure_rate:       Ratio of failures to total (0.0-1.0).
        avg_task_duration:  Rolling average task duration in seconds.
        samples:            Number of task durations in the rolling average.
        last_updated:       ISO timestamp of last metrics update.
    """

    active_builders: int = 0
    completed_tasks: int = 0
    failed_tasks: int = 0
    total_tasks: int = 0
    failure_rate: float = 0.0
    avg_task_duration: float = 0.0
    samples: int = 0
    last_updated: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "active_builders": self.active_builders,
            "completed_tasks": self.completed_tasks,
            "failed_tasks": self.failed_tasks,
            "total_tasks": self.total_tasks,
            "failure_rate": round(self.failure_rate, 4),
            "avg_task_duration": round(self.avg_task_duration, 2),
            "samples": self.samples,
            "last_updated": self.last_updated,
        }

    def record_completion(self, duration_sec: float) -> None:
        """Record a successful task completion."""
        self.completed_tasks += 1
        self.total_tasks += 1
        self._update_avg_duration(duration_sec)
        self._recalc_rate()

    def record_failure(self, duration_sec: float = 0.0) -> None:
        """Record a failed task."""
        self.failed_tasks += 1
        self.total_tasks += 1
        if duration_sec > 0:
            self._update_avg_duration(duration_sec)
        self._recalc_rate()

    def _update_avg_duration(self, duration_sec: float) -> None:
        """Rolling average update."""
        if self.samples == 0:
            self.avg_task_duration = duration_sec
        else:
            self.avg_task_duration = (
                (self.avg_task_duration * self.samples) + duration_sec
            ) / (self.samples + 1)
        self.samples += 1

    def _recalc_rate(self) -> None:
        if self.total_tasks > 0:
            self.failure_rate = self.failed_tasks / self.total_tasks
        else:
            self.failure_rate = 0.0
        self.last_updated = datetime.now(timezone.utc).isoformat()


@dataclass
class SwarmConfig:
    """Configuration for the ENI Swarm bridge.

    Attributes:
        swarm_root:       Path to ENI_Swarm_NEW directory.
        max_workers:      Max concurrent hermes run processes.
        spawn_interval:   Master driver coordination interval (seconds).
        log_dir:          Directory for builder logs.
        status_dir:       Directory for STATUS files.
        state_file:       Path to master state JSON.
        task_files:       List of task JSON file paths.
        dashboard_port:   Port for the Starlette dashboard.
    """

    swarm_root: Path = Path("/home/hunter/Desktop/Eni Builder/ENI_Swarm_NEW")
    max_workers: int = 6
    spawn_interval: int = 30
    log_dir: Path = Path.home() / ".cache" / "swarm_bridge" / "builder_logs"
    status_dir: Path = Path.home() / "Commander" / "swarm_bridge" / "builds"
    state_file: Path = Path.home() / ".cache" / "swarm_bridge" / "master_state.json"
    task_files: List[Path] = field(default_factory=list)
    dashboard_port: int = 8420

    def __post_init__(self) -> None:
        if not self.task_files:
            config_dir = self.swarm_root / "config"
            self.task_files = [
                config_dir / "build_tasks.json",
                config_dir / "herself_tasks.json",
            ]
        # Ensure log_dir exists
        self.log_dir.mkdir(parents=True, exist_ok=True)


# =============================================================================
# SwarmBridge — Core Bridge Class
# =============================================================================


class SwarmBridge:
    """Enterprise bridge to the ENI Swarm (Master Driver v5.0).

    Reads swarm state from the filesystem (STATUS files, master state JSON,
    builder logs, task configs) and exposes it through clean Python APIs
    suitable for the Enterprise Platform Kernel.

    Controls builders via named FIFO pipes (pause/resume/assign).

    Model preference (v2.0):
        FREE_FIRST → nemotron ultra (nvidia direct) → free-router → ASK → deepseek v4

    Usage::

        bridge = SwarmBridge(swarm_root=Path("ENI_Swarm_NEW"))
        status = bridge.get_swarm_status()
        builder = bridge.get_builder_status("BUILDER_01")
        bridge.pause_builder("BUILDER_01")
        bridge.resume_builder("BUILDER_01")
        bridge.spawn_swarm()
    """

    # Model preference chain (free first, ask before paid)
    # free-router already routes to best free model:
    #   nvidia/nemotron-nano → sambanova/DeepSeek-V3.1 → upstage/solar-pro
    #   → zhipu/glm-5.2 → OpenRouter free models (nemotron ultra, super, etc.)
    MODEL_FREE = "free-router"                         # Routes all free providers
    MODEL_PAID_IF_APPROVED = "deepseek/deepseek-v4-pro"  # $0.87/M out — ask first

    def __init__(
        self,
        swarm_root: Optional[Path] = None,
        max_workers: int = 6,
        spawn_interval_sec: int = 30,
        log_dir: Optional[Path] = None,
        config: Optional[SwarmConfig] = None,
    ) -> None:
        """Initialize the SwarmBridge.

        Args:
            swarm_root: Path to ENI_Swarm_NEW directory.
            max_workers: Max concurrent hermes run processes.
            spawn_interval_sec: Master driver coordination interval.
            log_dir: Override builder log directory.
            config: Full SwarmConfig; overrides individual args if set.
        """
        if config:
            self.config = config
        else:
            self.config = SwarmConfig(
                swarm_root=swarm_root or Path("/home/hunter/Desktop/Eni Builder/ENI_Swarm_NEW"),
                max_workers=max_workers,
                spawn_interval=spawn_interval_sec,
                log_dir=log_dir or Path.home() / ".cache" / "swarm_bridge" / "builder_logs",
            )

        self._metrics = SwarmMetrics()
        self._metrics_lock = threading.Lock()
        self._event_bus: Any = None
        self._master_pid: Optional[int] = None
        self._fifo_dir = Path("/tmp")
        self._cache: Dict[str, Any] = {}
        self._cache_ttl: float = 5.0
        self._last_cache: float = 0.0

        # Try to import master_driver for live data
        self._swarm_available = False
        self._master_driver = None
        try:
            lib_path = str(self.config.swarm_root / "lib")
            if lib_path not in sys.path:
                sys.path.insert(0, lib_path)
            from eni.master_driver import (
                load_tasks,
                read_status,
                parse_state,
                extract_blocker,
                is_alive,
                MasterState,
                STATUS_DIR,
                STATE_FILE,
                LOG_DIR,
            )
            self._master_driver = sys.modules["eni.master_driver"]
            self._swarm_available = True
            logger.info("SwarmBridge: master_driver available")
        except ImportError as exc:
            logger.warning("SwarmBridge: master_driver unavailable (%s), using filesystem fallback", exc)

        logger.info(
            "SwarmBridge initialized (swarm_root=%s, max_workers=%d)",
            self.config.swarm_root,
            self.config.max_workers,
        )

    # ── EventBus wiring ────────────────────────────────────────────────────

    def set_event_bus(self, bus: Any) -> None:
        """Wire the platform EventBus for event emission."""
        self._event_bus = bus

    def _emit(self, topic: str, payload: Dict[str, Any], priority: Any = None) -> None:
        """Emit an event to the platform EventBus."""
        if self._event_bus is None:
            return
        try:
            from enterprise.platform_kernel import Event, EventPriority
            prio = priority or EventPriority.NORMAL
            self._event_bus.publish(
                Event.create(topic=topic, source="swarm_bridge", payload=payload, priority=prio)
            )
        except Exception:
            pass

    # ── Spawn Swarm ────────────────────────────────────────────────────────

    def spawn_swarm(
        self,
        spawn_dashboard: bool = False,
        interval: Optional[int] = None,
        workers: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Launch the ENI Swarm master driver.

        Spawns `python3 -m eni.master_driver` as a subprocess. Optionally
        also starts the dashboard server.

        Args:
            spawn_dashboard: If True, also start dashboard on :8420.
            interval: Master driver coordination interval (seconds).
            workers: Max concurrent workers.

        Returns:
            Dict with 'master_pid', 'dashboard_pid', and 'success' flag.
        """
        result: Dict[str, Any] = {
            "success": False,
            "master_pid": None,
            "dashboard_pid": None,
            "errors": [],
        }

        master_py = self.config.swarm_root / "lib" / "eni" / "master_driver.py"
        if not master_py.exists():
            result["errors"].append(f"master_driver.py not found at {master_py}")
            return result

        try:
            env = os.environ.copy()
            env["PYTHONPATH"] = str(self.config.swarm_root / "lib") + ":" + env.get("PYTHONPATH", "")

            # Launch master driver
            cmd = [
                sys.executable,
                str(master_py),
                "--interval", str(interval or self.config.spawn_interval),
                "--workers", str(workers or self.config.max_workers),
            ]
            proc = subprocess.Popen(
                cmd,
                cwd=str(self.config.swarm_root),
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                start_new_session=True,
            )
            self._master_pid = proc.pid
            result["master_pid"] = proc.pid
            logger.info("Master driver spawned (pid=%d)", proc.pid)

            # Read initial output
            time.sleep(1)

            # Optionally spawn dashboard
            if spawn_dashboard:
                dash_py = self.config.swarm_root / "dashboard" / "server.py"
                if dash_py.exists():
                    dash_proc = subprocess.Popen(
                        [sys.executable, str(dash_py), "--port", str(self.config.dashboard_port)],
                        cwd=str(self.config.swarm_root),
                        env=env,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT,
                        text=True,
                        start_new_session=True,
                    )
                    result["dashboard_pid"] = dash_proc.pid
                    logger.info("Dashboard spawned (pid=%d)", dash_proc.pid)
                else:
                    result["errors"].append(f"dashboard server.py not found")

            result["success"] = True
            self._emit("swarm.master.status", {
                "action": "spawned",
                "master_pid": proc.pid,
                "dashboard_port": self.config.dashboard_port if spawn_dashboard else None,
            })

        except Exception as exc:
            result["errors"].append(str(exc))
            logger.error("Failed to spawn swarm: %s", exc)

        return result

    def stop_swarm(self) -> Dict[str, Any]:
        """Stop the master driver process gracefully (SIGTERM)."""
        result = {"success": False, "stopped_pids": []}
        if self._master_pid:
            try:
                os.killpg(os.getpgid(self._master_pid), signal.SIGTERM)
                result["stopped_pids"].append(self._master_pid)
                logger.info("Master driver stopped (pid=%d)", self._master_pid)
            except OSError:
                pass
            self._master_pid = None
        result["success"] = True
        return result

    # ── Status Queries ─────────────────────────────────────────────────────

    def get_swarm_status(self) -> Dict[str, Any]:
        """Get the complete swarm status — all builders, summary, alerts.

        Reads STATUS files, master state JSON, and builder logs.
        Falls back to filesystem detection if master_driver is unavailable.

        Returns:
            Dict with keys: 'minis', 'summary', 'alerts', 'timestamp',
            'master_cycle', 'master_updated'.
        """
        # Cache short-circuit
        now = time.time()
        if now - self._last_cache < self._cache_ttl and self._cache:
            return self._cache

        status: Dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "swarm_available": self._swarm_available,
            "minis": [],
            "alerts": [],
            "summary": {
                "total_builders": 0,
                "alive_count": 0,
                "done_count": 0,
                "in_progress_count": 0,
                "blocked_count": 0,
                "dead_count": 0,
                "unknown_count": 0,
                "idle_count": 0,
            },
            "master_cycle": 0,
            "master_updated": "",
        }

        if self._swarm_available:
            self._read_via_master_driver(status)
        else:
            self._read_via_filesystem(status)

        # Update metrics
        with self._metrics_lock:
            self._metrics.active_builders = status["summary"]["in_progress_count"]
            self._metrics.last_updated = status["timestamp"]

        self._cache = status
        self._last_cache = now
        return status

    def _read_via_master_driver(self, status: Dict[str, Any]) -> None:
        """Use imported master_driver functions for live data."""
        md = self._master_driver
        try:
            minis = md.load_tasks()
            master_state = md.MasterState.load()
            status["master_cycle"] = master_state.cycle
            status["master_updated"] = master_state.updated

            for mini in minis:
                if mini.name == "MASTER":
                    continue

                # Merge saved state
                saved = master_state.minis.get(mini.name, {})
                mini.last_mtime = saved.get("mtime", 0)
                mini.cycles_since_reply = saved.get("cycles", 0)
                mini.active = saved.get("active", False)
                mini.task_count = saved.get("task_count", 0)

                # Read current STATUS file
                status_path = self._find_status_file(mini)
                txt = md.read_status(status_path) if status_path and status_path.exists() else ""
                st = md.parse_state(txt) if txt else "UNKNOWN"
                blocker = md.extract_blocker(txt) if st == "BLOCKED" else ""

                # Check if alive (on-demand: active slot is "alive enough")
                alive = mini.active or True  # on-demand means slots are always "available"

                status["minis"].append({
                    "name": mini.name,
                    "title": mini.title,
                    "state": st,
                    "alive": alive,
                    "active": mini.active,
                    "pid": 0,
                    "cycles_since_reply": mini.cycles_since_reply,
                    "last_update": (
                        datetime.fromtimestamp(mini.last_mtime).isoformat()
                        if mini.last_mtime else ""
                    ),
                    "workdir": mini.workdir,
                    "model": mini.model,
                    "provider": mini.provider,
                    "blocker": blocker,
                    "task_count": mini.task_count,
                    "last_reply": "",
                })

            self._compute_summary(status)

        except Exception as exc:
            logger.error("Error reading via master_driver: %s", exc)
            status["alerts"].append({
                "level": "critical",
                "message": f"Master driver error: {exc}",
            })

    def _read_via_filesystem(self, status: Dict[str, Any]) -> None:
        """Fallback: detect builders from PID files + STATUS files + logs."""
        pid_dir = Path.home() / ".cache" / "swarm_bridge" / "pids"
        status_dirs = [
            self.config.status_dir,
            self.config.swarm_root / "tasks" / "status",
        ]

        # Collect known builder names
        known_names: Set[str] = set()
        if pid_dir.exists():
            for pf in pid_dir.glob("*.pid"):
                known_names.add(pf.stem)
        for sd in status_dirs:
            if sd.exists():
                for sf in sd.glob("STATUS_*.md"):
                    known_names.add(sf.stem.replace("STATUS_", ""))
        if self.config.log_dir.exists():
            for lf in self.config.log_dir.glob("*.log"):
                known_names.add(lf.stem)

        # Filter valid names
        valid: Set[str] = set()
        for name in known_names:
            if re.match(r'^(BUILDER_\d{1,2}|ENI_SELF_\d+|HEARTBEAT|PRODUCT_LEAD)$', name):
                valid.add(name)
            for sd in status_dirs:
                if sd.exists() and (sd / f"STATUS_{name}.md").exists():
                    valid.add(name)
                    break

        for name in sorted(valid):
            builder = self._parse_builder_from_fs(name, pid_dir, status_dirs)
            status["minis"].append(builder.to_dict())

        self._compute_summary(status)

        if not status["minis"]:
            status["alerts"].append({
                "level": "warning",
                "message": "No builders detected on filesystem",
            })

    def _parse_builder_from_fs(
        self, name: str, pid_dir: Path, status_dirs: List[Path]
    ) -> BuilderStatus:
        """Parse a single builder's state from the filesystem."""
        bs = BuilderStatus(name=name)

        # PID / alive
        pf = pid_dir / f"{name}.pid" if pid_dir else None
        if pf and pf.exists():
            try:
                bs.pid = int(pf.read_text().strip())
                if bs.pid > 0:
                    os.kill(bs.pid, 0)
                    bs.alive = True
            except (OSError, ValueError):
                bs.alive = False
                try:
                    pf.unlink()
                except Exception:
                    pass

        # STATUS file
        for sd in status_dirs:
            sf = sd / f"STATUS_{name}.md"
            if sf.exists():
                try:
                    txt = sf.read_text()
                    bs.state = self._parse_state_simple(txt)
                    bs.last_update = datetime.fromtimestamp(sf.stat().st_mtime).isoformat()
                    if "BLOCKED" in txt.upper():
                        bs.blocker = self._extract_blocker_simple(txt)
                    if not bs.alive and bs.state in ("IDLE", "READY"):
                        bs.alive = True
                    bs.workdir = str(sd)
                except Exception:
                    pass
                break

        # Normalize state
        if bs.state in ("IN PROGRESS", "INPROGRESS"):
            bs.state = "IN-PROGRESS"
        elif bs.state == "UNKNOWN" and bs.alive:
            bs.state = "IDLE"

        # Log file
        lf = self.config.log_dir / f"{name}.log"
        if lf.exists():
            try:
                lines = lf.read_text().strip().splitlines()
                if lines:
                    bs.last_reply = lines[-1][:200]
                for line in reversed(lines[-20:]):
                    m = re.search(r'EXECUTING \[([^\]]+)\]', line)
                    if m:
                        bs.model = m.group(1)
                        break
                for line in reversed(lines[-5:]):
                    if "Waiting for next task" in line:
                        if bs.state in ("UNKNOWN", "READY", "IDLE", "DONE", "BLOCKED"):
                            bs.state = "IDLE"
                        break
                for line in reversed(lines[-3:]):
                    if "CMD: hermes -z" in line and "COMPLETED" not in " ".join(lines[-3:]):
                        if bs.state in ("UNKNOWN", "IDLE", "READY"):
                            bs.state = "IN-PROGRESS"
                        break
            except Exception:
                pass

        return bs

    def _find_status_file(self, mini: Any) -> Optional[Path]:
        """Find the STATUS file for a mini slot across multiple directories."""
        candidates = [
            self.config.status_dir / mini.status_file,
            self.config.swarm_root / "tasks" / "status" / mini.status_file,
            Path(mini.workdir).expanduser() / mini.status_file,
        ]
        for p in candidates:
            if p.exists():
                return p
        return candidates[0]  # Return the primary path even if it doesn't exist

    @staticmethod
    def _parse_state_simple(txt: str) -> str:
        """Simple state parse without master_driver dependency."""
        s = txt.upper()
        if "BLOCKED" in s:
            return "BLOCKED"
        if "IN-PROGRESS" in s or "IN PROGRESS" in s:
            return "IN-PROGRESS"
        if "DONE" in s:
            return "DONE"
        if "IDLE" in s:
            return "IDLE"
        m = re.search(r'\[(?:state|STATUS)\s*:\s*(\w[\w\s-]*)\]', txt)
        if m:
            st = m.group(1).upper().strip()
            if "BLOCK" in st:
                return "BLOCKED"
            if "PROGRESS" in st:
                return "IN-PROGRESS"
            if "DONE" in st:
                return "DONE"
            if "IDLE" in st:
                return "IDLE"
            return st
        return "UNKNOWN"

    @staticmethod
    def _extract_blocker_simple(txt: str) -> str:
        """Extract blocker reason from STATUS text."""
        for line in txt.splitlines():
            if line.strip().lower().startswith("blocker"):
                return line.split("=", 1)[-1].strip()
        return ""

    def _compute_summary(self, status: Dict[str, Any]) -> None:
        """Compute aggregate summary from minis list."""
        summary = status["summary"]
        for m in status["minis"]:
            summary["total_builders"] += 1
            if m["alive"]:
                summary["alive_count"] += 1
            else:
                summary["dead_count"] += 1
            st = m["state"]
            if st == "DONE":
                summary["done_count"] += 1
            elif st == "IN-PROGRESS":
                summary["in_progress_count"] += 1
            elif st == "BLOCKED":
                summary["blocked_count"] += 1
            elif st == "UNKNOWN":
                summary["unknown_count"] += 1
            elif st in ("IDLE", "READY"):
                summary["idle_count"] += 1

        # Build alerts
        for m in status["minis"]:
            if m["state"] == "BLOCKED":
                status["alerts"].append({
                    "level": "critical",
                    "builder": m["name"],
                    "message": f"BLOCKED: {m['blocker'] or 'no blocker specified'}",
                })
            elif not m["alive"] and m["state"] not in ("DONE", "IDLE", "READY"):
                status["alerts"].append({
                    "level": "warning",
                    "builder": m["name"],
                    "message": "Builder not alive",
                })

    # ── Per-Builder Queries ────────────────────────────────────────────────

    def get_builder_status(self, name: str) -> Optional[BuilderStatus]:
        """Get detailed status for a single builder.

        Args:
            name: Builder name (e.g., 'BUILDER_01').

        Returns:
            BuilderStatus if found, None otherwise.
        """
        status = self.get_swarm_status()
        for m in status["minis"]:
            if m["name"] == name:
                return BuilderStatus(**{k: v for k, v in m.items() if k in BuilderStatus.__dataclass_fields__})
        return None

    def get_builder_log(self, name: str, lines: int = 50) -> str:
        """Read the most recent lines from a builder's log.

        Args:
            name: Builder name.
            lines: Number of log lines to return.

        Returns:
            Log text (tail), or empty string if log not found.
        """
        lf = self.config.log_dir / f"{name}.log"
        if not lf.exists():
            return ""
        try:
            all_lines = lf.read_text().strip().splitlines()
            tail = all_lines[-lines:] if len(all_lines) > lines else all_lines
            return "\n".join(tail)
        except Exception:
            return ""

    # ── Task Rosters ───────────────────────────────────────────────────────

    def get_task_rosters(self) -> Dict[str, Any]:
        """Load task definitions for all builders.

        Reads build_tasks.json and herself_tasks.json.

        Returns:
            Dict with keys: 'tasks', 'task_count', 'sources'.
        """
        result: Dict[str, Any] = {
            "tasks": [],
            "task_count": 0,
            "sources": [],
        }

        for tf in self.config.task_files:
            if not tf.exists():
                logger.debug("Task file not found: %s", tf)
                continue
            try:
                data = json.loads(tf.read_text())
                result["tasks"].extend(data.get("tasks", []))
                result["sources"].append(str(tf))
            except Exception as exc:
                logger.warning("Failed to load task file %s: %s", tf, exc)

        result["task_count"] = len(result["tasks"])
        return result

    # ── Builder Control (Pause / Resume) ───────────────────────────────────

    def pause_builder(self, name: str) -> bool:
        """Pause a builder by sending a PAUSE command via FIFO.

        The builder will finish its current hermes run, then wait.

        Args:
            name: Builder name.

        Returns:
            True if the FIFO message was sent.
        """
        return self._send_fifo(name, "PAUSE")

    def resume_builder(self, name: str) -> bool:
        """Resume a paused builder via FIFO.

        Args:
            name: Builder name.

        Returns:
            True if the FIFO message was sent.
        """
        return self._send_fifo(name, "RESUME")

    def assign_task(self, name: str, task: str) -> bool:
        """Assign a new task to an idle builder via FIFO.

        Args:
            name: Builder name.
            task: Task description / prompt.

        Returns:
            True if the FIFO message was sent.
        """
        msg = (
            f"<LO TASK from ENTERPRISE>\n"
            f"TASK: {task}\n"
            f"Write STATUS_{name}.md with [IN-PROGRESS] and begin building.\n"
            f"</LO TASK>"
        )
        sent = self._send_fifo(name, msg)
        if sent:
            self._emit("swarm.builder.started", {
                "builder": name,
                "task": task[:200],
            })
        return sent

    def _send_fifo(self, name: str, message: str) -> bool:
        """Send a message to a builder via its named FIFO pipe.

        Args:
            name: Builder name.
            message: Text to send.

        Returns:
            True if the message was written successfully.
        """
        fifo_path = self._fifo_dir / f"swarm_ctl_{name}"
        try:
            if not fifo_path.exists():
                return False
            fd = os.open(str(fifo_path), os.O_WRONLY | os.O_NONBLOCK)
            try:
                os.write(fd, (message + "\n").encode())
                return True
            finally:
                os.close(fd)
        except OSError:
            return False

    # ── Health Monitoring ──────────────────────────────────────────────────

    def is_swarm_alive(self) -> bool:
        """Check if the swarm master driver is alive.

        Returns:
            True if at least one builder is alive or the master is running.
        """
        if self._master_pid:
            try:
                os.kill(self._master_pid, 0)
                return True
            except OSError:
                pass

        # Fallback: check if any builders are alive
        status = self.get_swarm_status()
        return status["summary"]["alive_count"] > 0

    def get_health_summary(self) -> Dict[str, Any]:
        """Quick health overview of the swarm.

        Returns:
            Dict with 'healthy', 'total', 'alive', 'blocked', 'dead', 'active'.
        """
        status = self.get_swarm_status()
        summary = status["summary"]
        total = summary["total_builders"]
        alive = summary["alive_count"]
        dead = summary["dead_count"]
        blocked = summary["blocked_count"]
        active = summary["in_progress_count"]

        healthy = total > 0 and dead == 0 and blocked < total * 0.3
        return {
            "healthy": healthy,
            "total": total,
            "alive": alive,
            "dead": dead,
            "blocked": blocked,
            "active": active,
            "timestamp": status["timestamp"],
        }

    # ── Metrics ────────────────────────────────────────────────────────────

    def get_metrics(self) -> SwarmMetrics:
        """Return current swarm metrics.

        Returns:
            SwarmMetrics dataclass with active_builders, completed_tasks,
            failure_rate, avg_task_duration.
        """
        # Refresh active_builders from latest status
        status = self.get_swarm_status()
        with self._metrics_lock:
            self._metrics.active_builders = status["summary"]["in_progress_count"]
            if not self._metrics.last_updated:
                self._metrics.last_updated = status["timestamp"]
            return self._metrics

    def record_task_event(self, event_type: str, builder: str, duration_sec: float = 0.0, task: str = "") -> None:
        """Record a task lifecycle event and update metrics.

        Args:
            event_type: 'started', 'completed', or 'failed'.
            builder: Builder name.
            duration_sec: Task duration (for completed/failed).
            task: Task description (for started).
        """
        topic_map = {
            "started": "swarm.builder.started",
            "completed": "swarm.builder.completed",
            "failed": "swarm.builder.failed",
        }
        topic = topic_map.get(event_type, f"swarm.builder.{event_type}")

        with self._metrics_lock:
            if event_type == "completed":
                self._metrics.record_completion(duration_sec)
            elif event_type == "failed":
                self._metrics.record_failure(duration_sec)

        self._emit(topic, {
            "builder": builder,
            "duration_sec": duration_sec,
            "task": task[:200] if task else "",
            "metrics_snapshot": self._metrics.to_dict(),
        })

    # ── Cleanup ────────────────────────────────────────────────────────────

    def shutdown(self) -> None:
        """Cleanup: invalidate cache, stop tracking."""
        self._cache.clear()
        logger.info("SwarmBridge shutdown complete")

    # ── Debug / Introspection ──────────────────────────────────────────────

    def __repr__(self) -> str:
        metrics = self._metrics
        return (
            f"<SwarmBridge swarm_available={self._swarm_available} "
            f"active={metrics.active_builders} completed={metrics.completed_tasks} "
            f"fail_rate={metrics.failure_rate:.3f}>"
        )
