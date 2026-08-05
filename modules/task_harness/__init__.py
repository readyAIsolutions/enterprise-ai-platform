"""
ENI Task Harness OS Module

Maestro-style long-running task harness: SQLite-backed task cards with
pause/resume, dependency ordering, priority scheduling, heartbeat liveness,
and structured state so an agent can pause, resume, and track deep refactors.

Exports:
  TaskHarnessModule — @module-decorated Module subclass
  TaskHarness       — SQLite-backed task store
  TaskCard          — task card dataclass
  TaskStatus        — lifecycle enum
  TaskHarnessError  — base error for the module

Version: 1.0.0
Python: 3.10+
"""

from __future__ import annotations

__version__ = "1.0.0"
__module__ = "task_harness"

import asyncio
import logging
import threading
from pathlib import Path
from typing import Any, Dict, Optional

from enterprise.platform_kernel import (
    Event,
    EventBus,
    EventPriority,
    HealthStatus,
    Module,
    module,
)

from .task_harness import (
    TaskCard,
    TaskHarness,
    TaskHarnessError,
    TaskStatus,
)

__all__ = [
    "__version__",
    "TaskHarnessModule",
    "TaskHarness",
    "TaskCard",
    "TaskStatus",
    "TaskHarnessError",
]

# ---------------------------------------------------------------------------
# Module logger
# ---------------------------------------------------------------------------
_logger: logging.Logger = logging.getLogger("enterprise.task_harness")

# Default DB location relative to repo root (../../data/tasks.sqlite when
# this module lives at <repo>/modules/task_harness/__init__.py).
_DEFAULT_DB_RELATIVE: Path = Path("data") / "tasks.sqlite"


def _resolve_repo_root() -> Path:
    """Resolve the repository root from this module's location."""
    return Path(__file__).resolve().parents[2]


@module(name="task_harness", version="1.0.0")
class TaskHarnessModule(Module):
    """Enterprise Task Harness module.

    Wraps the SQLite-backed :class:`TaskHarness` store, exposing task-card
    lifecycle management, dependency-ordered scheduling, and health checks
    as a registered Platform Kernel module.

    Events published (when an event bus is wired):
      - task.created
      - task.state_changed
    """

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        super().__init__(config)
        self._harness: TaskHarness | None = None
        self._event_bus: EventBus | None = None
        self._lock: threading.RLock = threading.RLock()

    # ── Properties ───────────────────────────────────────────────────────

    @property
    def harness(self) -> TaskHarness | None:
        """Return the active TaskHarness store, if initialized."""
        with self._lock:
            return self._harness

    # ── Lifecycle ────────────────────────────────────────────────────────

    async def initialize(self) -> None:
        """Initialize the Task Harness module.

        Builds the TaskHarness store from configuration (``db_path``),
        creating parent directories if missing.
        """
        with self._lock:
            self._status = HealthStatus.STARTING

        try:
            configured: str = self._config.get("db_path", "")
            if configured:
                db_path: str = str(configured)
            else:
                db_path = str(_resolve_repo_root() / _DEFAULT_DB_RELATIVE)

            _logger.info("Task Harness initializing (db_path=%s)", db_path)
            self._harness = await asyncio.to_thread(TaskHarness, db_path)
            self._status = HealthStatus.HEALTHY
            _logger.info("Task Harness initialized successfully")
        except Exception as exc:  # pragma: no cover - defensive
            _logger.exception("Failed to initialize Task Harness module: %s", exc)
            self._status = HealthStatus.UNHEALTHY
            raise

    async def health_check(self) -> HealthStatus:
        """Verify the SQLite store opens and can be queried."""
        harness = self.harness
        if harness is None:
            self._status = HealthStatus.UNKNOWN
            return self._status

        def _probe() -> bool:
            try:
                harness.list()
                return True
            except Exception:  # pragma: no cover - defensive
                return False

        try:
            ok = await asyncio.to_thread(_probe)
            self._status = HealthStatus.HEALTHY if ok else HealthStatus.UNHEALTHY
        except Exception:  # pragma: no cover - defensive
            self._status = HealthStatus.UNHEALTHY
        return self._status

    async def shutdown(self) -> None:
        """Gracefully shut down the Task Harness module (close the store)."""
        with self._lock:
            self._status = HealthStatus.STOPPING

        _logger.info("Shutting down Task Harness module...")
        harness = self._harness
        self._harness = None
        try:
            if harness is not None:
                await asyncio.to_thread(harness.close)
        except Exception as exc:  # pragma: no cover - defensive
            _logger.exception("Error during Task Harness shutdown: %s", exc)
            self._status = HealthStatus.UNHEALTHY
            raise
        self._status = HealthStatus.STOPPING
        _logger.info("Task Harness module shut down")

    # ── Event Bus Wiring ─────────────────────────────────────────────────

    def set_event_bus(self, event_bus: EventBus) -> None:
        """Wire the platform EventBus into this module.

        Args:
            event_bus: The platform EventBus instance.
        """
        with self._lock:
            self._event_bus = event_bus

    # ── Event publishing ─────────────────────────────────────────────────

    def _publish(self, topic: str, payload: dict[str, Any]) -> None:
        """Publish a task event if an event bus is wired."""
        bus = self._event_bus
        if bus is None:
            return
        try:
            event = Event.create(
                topic=topic,
                source="task_harness",
                payload=payload,
                priority=EventPriority.NORMAL,
            )
            bus.publish(event)
        except Exception as exc:  # pragma: no cover - defensive
            _logger.warning("Failed to publish event %s: %s", topic, exc)
