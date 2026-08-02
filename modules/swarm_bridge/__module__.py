#!/usr/bin/env python3
"""
ENI Swarm — Enterprise Platform Kernel Module (Module Implementation)
=====================================================================
Implements the Module ABC with @module registration, health checking,
and lifecycle management for the ENI Swarm as an enterprise module.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from enterprise.platform_kernel import (
    Module,
    module,
    HealthStatus,
    Event,
    EventPriority,
    HealthReport,
)

from .swarm_bridge import SwarmBridge, SwarmMetrics, BuilderStatus

logger = logging.getLogger("enterprise.swarm.module")


# =============================================================================
# SwarmHealthCheck — continuous health monitoring
# =============================================================================

@dataclass
class SwarmHealthCheck:
    """Performs continuous health monitoring of the ENI Swarm.

    Tracks builder liveliness, failure counts, degradation thresholds,
    and emits health events on state transitions.

    Attributes:
        bridge: Reference to the SwarmBridge for data access.
        check_interval_sec: How often to poll health (default 15s).
        failure_threshold: Consecutive unhealthy cycles before DEGRADED.
        recovery_threshold: Consecutive healthy cycles before HEALTHY.
    """

    bridge: SwarmBridge
    check_interval_sec: float = 15.0
    failure_threshold: int = 3
    recovery_threshold: int = 2

    # Private state
    _last_check: float = field(default=0.0, init=False)
    _consecutive_failures: int = field(default=0, init=False)
    _consecutive_successes: int = field(default=0, init=False)
    _current_status: HealthStatus = field(default=HealthStatus.UNKNOWN, init=False)
    _event_bus: Any = field(default=None, init=False)
    _running: bool = field(default=False, init=False)
    _task: Optional[asyncio.Task] = field(default=None, init=False)

    def set_event_bus(self, bus: Any) -> None:
        """Wire the EventBus for health event emission."""
        self._event_bus = bus

    @property
    def status(self) -> HealthStatus:
        return self._current_status

    async def start(self) -> None:
        """Begin the periodic health-check loop."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._check_loop())
        logger.info("SwarmHealthCheck started (interval=%ss)", self.check_interval_sec)

    async def stop(self) -> None:
        """Stop the health-check loop."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("SwarmHealthCheck stopped")

    async def run_check(self) -> HealthReport:
        """Run a single health check synchronously (no loop)."""
        start = time.monotonic()
        try:
            status = self.bridge.get_swarm_status()
            summary = status.get("summary", {})

            total = summary.get("total_builders", summary.get("total_minis", 0))
            alive = summary.get("alive_count", 0)
            blocked = summary.get("blocked_count", 0)
            dead = summary.get("dead_count", 0)
            active = summary.get("in_progress_count", 0)
            metrics = self.bridge.get_metrics()

            # Determine health
            if total == 0:
                hstatus = HealthStatus.UNKNOWN
            elif dead > total * 0.3 or blocked > total * 0.5:
                hstatus = HealthStatus.UNHEALTHY
            elif dead > 0 or blocked > total * 0.2:
                hstatus = HealthStatus.DEGRADED
            elif alive == total:
                hstatus = HealthStatus.HEALTHY
            else:
                hstatus = HealthStatus.DEGRADED

            elapsed_ms = (time.monotonic() - start) * 1000
            report = HealthReport(
                module_name="swarm_bridge",
                status=hstatus,
                response_time_ms=elapsed_ms,
                timestamp=datetime.now(timezone.utc),
                details={
                    "total_builders": total,
                    "alive": alive,
                    "dead": dead,
                    "blocked": blocked,
                    "active": active,
                    "failure_rate": metrics.failure_rate,
                    "completed_tasks": metrics.completed_tasks,
                    "avg_task_duration": metrics.avg_task_duration,
                },
                consecutive_failures=self._consecutive_failures,
                consecutive_successes=self._consecutive_successes,
            )
        except Exception as exc:
            elapsed_ms = (time.monotonic() - start) * 1000
            report = HealthReport(
                module_name="swarm_bridge",
                status=HealthStatus.UNHEALTHY,
                response_time_ms=elapsed_ms,
                timestamp=datetime.now(timezone.utc),
                details={"error": str(exc)},
                consecutive_failures=self._consecutive_failures,
                consecutive_successes=self._consecutive_successes,
            )
        return report

    async def _check_loop(self) -> None:
        """Internal async loop that runs periodic health checks."""
        while self._running:
            report = await self.run_check()
            prev_status = self._current_status

            if report.status.is_operational():
                self._consecutive_successes += 1
                self._consecutive_failures = 0
            else:
                self._consecutive_failures += 1
                self._consecutive_successes = 0

            # Apply thresholds
            new_status = report.status
            if self._consecutive_failures >= self.failure_threshold:
                new_status = HealthStatus.UNHEALTHY
            elif self._consecutive_successes >= self.recovery_threshold:
                if report.status == HealthStatus.DEGRADED:
                    new_status = HealthStatus.DEGRADED
                else:
                    new_status = HealthStatus.HEALTHY

            # Emit event on status change
            if new_status != prev_status:
                self._emit_status_change(prev_status, new_status, report)
                self._current_status = new_status
            else:
                self._current_status = report.status

            # Emit regular status event
            self._emit_status_event(report)

            self._last_check = time.time()
            await asyncio.sleep(self.check_interval_sec)

    def _emit_status_change(
        self, old: HealthStatus, new: HealthStatus, report: HealthReport
    ) -> None:
        """Emit event when swarm health status transitions."""
        if self._event_bus is None:
            return
        topic = (
            "swarm.health.degraded"
            if new in (HealthStatus.DEGRADED, HealthStatus.UNHEALTHY)
            else "swarm.health.recovered"
        )
        self._event_bus.publish(
            Event.create(
                topic=topic,
                source="swarm_health_check",
                payload={
                    "previous": old.value,
                    "current": new.value,
                    "details": report.details,
                    "consecutive_failures": self._consecutive_failures,
                    "consecutive_successes": self._consecutive_successes,
                },
                priority=EventPriority.HIGH if not new.is_operational() else EventPriority.NORMAL,
            )
        )

    def _emit_status_event(self, report: HealthReport) -> None:
        """Emit a periodic swarm.master.status event."""
        if self._event_bus is None:
            return
        self._event_bus.publish(
            Event.create(
                topic="swarm.master.status",
                source="swarm_health_check",
                payload={
                    "status": report.status.value,
                    "details": report.details,
                    "response_time_ms": report.response_time_ms,
                    "timestamp": report.timestamp.isoformat(),
                },
                priority=EventPriority.NORMAL,
            )
        )


# =============================================================================
# ENISwarmModule — @module decorated enterprise module
# =============================================================================

@module(name="swarm_bridge", version="5.0.0")
class ENISwarmModule(Module):
    """Enterprise Platform Kernel module for the ENI Swarm.

    Wires the SwarmBridge, PromptForgeBridge, and SwarmHealthCheck
    into the platform's lifecycle (initialize → health_check → shutdown).

    Lifecycle:
      initialize() → creates SwarmBridge + prompts, starts health check
      health_check() → delegates to SwarmHealthCheck
      shutdown() → stops health check, cleans up

    The existing swarm dashboard on :8420 is NEVER touched — this module
    only reads data (via master_driver and filesystem) and emits events.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(config)
        self._bridge: Optional[SwarmBridge] = None
        self._prompt_forge: Any = None  # PromptForgeBridge
        self._health_check: Optional[SwarmHealthCheck] = None
        self._event_bus: Any = None

    # ── Properties ─────────────────────────────────────────────────────────

    @property
    def bridge(self) -> Optional[SwarmBridge]:
        return self._bridge

    @property
    def prompt_forge(self) -> Any:
        return self._prompt_forge

    # ── Lifecycle ──────────────────────────────────────────────────────────

    async def initialize(self) -> None:
        """Initialize the ENI Swarm enterprise module.

        1. Create SwarmBridge with config-driven paths
        2. Create PromptForgeBridge for task enhancement
        3. Wire health checker
        4. Begin periodic health monitoring
        """
        logger.info("ENISwarmModule v5.0.0 initializing...")

        # ── SwarmBridge ──────────────────────────────────────────────────
        cfg = self._config or {}
        swarm_root = cfg.get(
            "swarm_root",
            str(Path(__file__).resolve().parents[2] / "ENI_Swarm_NEW"),
        )
        swarm_config = cfg.get("swarm", {})
        self._bridge = SwarmBridge(
            swarm_root=Path(swarm_root),
            max_workers=swarm_config.get("max_workers", 6),
            spawn_interval_sec=swarm_config.get("spawn_interval_sec", 30),
            log_dir=swarm_config.get("log_dir"),
        )

        # ── PromptForgeBridge ────────────────────────────────────────────
        try:
            from .prompt_forge_bridge import PromptForgeBridge

            pf_config = cfg.get("prompt_forge", {})
            self._prompt_forge = PromptForgeBridge(
                enable_web=pf_config.get("enable_web", True),
                enable_youtube=pf_config.get("enable_youtube", False),
                enable_swarm=pf_config.get("enable_swarm", True),
            )
            logger.info("PromptForgeBridge initialized")
        except Exception as exc:
            logger.warning("PromptForgeBridge unavailable: %s", exc)
            self._prompt_forge = None

        # ── Health Check ────────────────────────────────────────────────
        health_cfg = cfg.get("health", {})
        self._health_check = SwarmHealthCheck(
            bridge=self._bridge,
            check_interval_sec=health_cfg.get("check_interval_sec", 15.0),
            failure_threshold=health_cfg.get("failure_threshold", 3),
            recovery_threshold=health_cfg.get("recovery_threshold", 2),
        )
        # EventBus is wired later by the PlatformOS

        self._started_at = datetime.now(timezone.utc)
        self._status = HealthStatus.STARTING
        logger.info("ENISwarmModule v5.0.0 initialized successfully")

    async def start(self) -> None:
        """Start the health-check loop (called after EventBus is wired)."""
        if self._health_check:
            await self._health_check.start()
        self._status = HealthStatus.HEALTHY

    async def health_check(self) -> HealthStatus:
        """Run a health check via SwarmHealthCheck."""
        if self._health_check is None:
            self._status = HealthStatus.UNKNOWN
            return HealthStatus.UNKNOWN

        report = await self._health_check.run_check()
        self._status = report.status
        return report.status

    async def shutdown(self) -> None:
        """Gracefully shut down the ENI Swarm module."""
        logger.info("ENISwarmModule shutting down...")
        self._status = HealthStatus.STOPPING

        if self._health_check:
            await self._health_check.stop()

        if self._prompt_forge:
            try:
                self._prompt_forge.shutdown()
            except Exception:
                pass

        if self._bridge:
            try:
                self._bridge.shutdown()
            except Exception:
                pass

        self._status = HealthStatus.UNKNOWN
        logger.info("ENISwarmModule shut down")

    # ── EventBus wiring ──────────────────────────────────────────────────

    def set_event_bus(self, bus: Any) -> None:
        """Wire the platform EventBus for event emission."""
        self._event_bus = bus
        if self._health_check:
            self._health_check.set_event_bus(bus)
        if self._bridge:
            self._bridge.set_event_bus(bus)