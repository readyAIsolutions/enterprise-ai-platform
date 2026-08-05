"""
InfraStatus - Unified Health/Status Facade for agent_infra
==========================================================

Single deterministic status surface that aggregates every major component
of the agent_infra module (tui, server, plugin_system, buddy, voice,
bootstrap) into one report, and migrates the scattered per-file health
checks behind a cohesive InfraStatus registry.

Design goals:
  - Cohesion: one object owns the health picture; callers stop reaching
    into each subsystem's private health_check.
  - Determinism: status_report() returns a fixed-shape, ordered,
    JSON-serialisable dict (stable key order, sorted components).
  - Aggregation: overall status is HEALTHY only when every core component
    is OK; a single failing core component yields DEGRADED; total failure
    yields UNHEALTHY.
  - Accessor: component(name) lets any caller pull one component's status
    without owning the whole report.

Stdlib only (dataclasses, enum, datetime, json, threading).
"""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Optional, Tuple

from enterprise.platform_kernel import HealthStatus

# Core components that collectively define the module's health. Ordered for
# deterministic iteration.
CORE_COMPONENTS: Tuple[str, ...] = (
    "tui",
    "server",
    "plugin_system",
    "buddy",
    "voice",
    "bootstrap",
)


# =============================================================================
# ComponentState
# =============================================================================

class ComponentState(Enum):
    """Lifecycle / health state of a single component."""

    UNKNOWN = "unknown"
    INITIALIZING = "initializing"
    OK = "ok"
    DEGRADED = "degraded"
    FAILED = "failed"
    STOPPED = "stopped"

    @property
    def is_ok(self) -> bool:
        return self is ComponentState.OK


# =============================================================================
# ComponentStatus
# =============================================================================

@dataclass
class ComponentStatus:
    """Per-component health record tracked inside the registry."""

    name: str
    state: ComponentState = ComponentState.UNKNOWN
    ok: bool = False
    last_check: str = ""  # ISO-8601 UTC timestamp of the most recent update
    message: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Deterministic, ordered dict representation (JSON-safe)."""
        return {
            "name": self.name,
            "state": self.state.value,
            "ok": bool(self.ok),
            "last_check": self.last_check,
            "message": self.message,
        }

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(timezone.utc).isoformat(timespec="seconds")

    def update(self, *, ok: bool, state: Optional[ComponentState] = None,
               message: Optional[str] = None) -> "ComponentStatus":
        """Refresh this component's status in place and stamp last_check."""
        self.ok = bool(ok)
        if state is not None:
            self.state = state
        else:
            self.state = ComponentState.OK if ok else ComponentState.FAILED
        if message is not None:
            self.message = message
        self.last_check = self._now_iso()
        return self


# =============================================================================
# InfraStatus facade + registry
# =============================================================================

class InfraStatus:
    """Unified status facade + registry for the agent_infra module.

    Holds a ComponentStatus record per core component and exposes a
    deterministic aggregated status_report() plus a component(name)
    accessor. All updates are thread-safe.
    """

    def __init__(
        self,
        core: Tuple[str, ...] = CORE_COMPONENTS,
        module_name: str = "agent_infra",
    ) -> None:
        self._module_name = module_name
        self._core: Tuple[str, ...] = tuple(core)
        self._components: Dict[str, ComponentStatus] = {
            name: ComponentStatus(name=name) for name in self._core
        }
        self._lock = threading.RLock()

    # -- registry access ---------------------------------------------------

    @property
    def components(self) -> Dict[str, ComponentStatus]:
        """All registered components, keyed by name. Deterministic order."""
        with self._lock:
            return dict(self._components)

    def register(self, name: str) -> ComponentStatus:
        """Ensure a component exists in the registry (idempotent).

        Returns the (possibly newly created) ComponentStatus record.
        """
        with self._lock:
            if name not in self._components:
                self._components[name] = ComponentStatus(name=name)
            return self._components[name]

    def component(self, name: str) -> Optional[ComponentStatus]:
        """Accessor: get a single component's status, or None if unknown."""
        with self._lock:
            return self._components.get(name)

    def update(
        self,
        name: str,
        *,
        ok: bool,
        state: Optional[ComponentState] = None,
        message: Optional[str] = None,
    ) -> ComponentStatus:
        """Update the health record for one component and return it."""
        with self._lock:
            status = self.register(name)
            status.update(ok=ok, state=state, message=message)
            return status

    # -- aggregation -------------------------------------------------------

    def healthy(self) -> bool:
        """True only when every core component is OK."""
        with self._lock:
            return all(c.ok for c in self._components.values()
                       if c.name in self._core)

    def overall_status(self) -> HealthStatus:
        """Aggregate module health from core component health.

        Mapping:
          - all core components OK          -> HEALTHY
          - some core components not OK     -> DEGRADED
          - no core component OK            -> UNHEALTHY
        """
        with self._lock:
            core_statuses = [c for c in self._components.values()
                             if c.name in self._core]
            ok_count = sum(1 for c in core_statuses if c.ok)
            if ok_count == len(core_statuses):
                return HealthStatus.HEALTHY
            if ok_count == 0:
                return HealthStatus.UNHEALTHY
            return HealthStatus.DEGRADED

    def status_report(self) -> Dict[str, Any]:
        """Aggregate all components into one Deterministic JSON status dict.

        The returned dict has a fixed key order and is directly serialisable
        with json.dumps; component names are sorted for determinism.
        """
        with self._lock:
            components = {
                name: self._components[name].to_dict()
                for name in sorted(self._components)
            }
            core_ok = all(c.ok for c in self._components.values()
                          if c.name in self._core)
            report = {
                "module": self._module_name,
                "overall": self.overall_status().value,
                "healthy": core_ok,
                "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "components": components,
            }
        return report

    def to_json(self) -> str:
        """Serialise the status report as compact, deterministic JSON."""
        return json.dumps(self.status_report(), sort_keys=True)

    def __repr__(self) -> str:
        return (f"<InfraStatus overall={self.overall_status().value} "
                f"components={sorted(self._components)}>")


__all__ = [
    "CORE_COMPONENTS",
    "ComponentState",
    "ComponentStatus",
    "InfraStatus",
]
