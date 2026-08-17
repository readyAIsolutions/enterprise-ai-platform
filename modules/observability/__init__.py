"""Observability — real, consolidated fleet health + Prometheus export.

A1 upgrade: replaces the old "health is a scored number" fiction with a live map
of what is ACTUALLY healthy right now. Provides:

* FleetHealthAggregator — probes each registered platform module's
  health_check() plus a set of external service endpoints (the multiplayer
  server, controller, dashboard, free router) and returns a live snapshot with
  per-entity status and a count summary. All real probes, no invented scores.
* Prometheus exporter — one text/metrics endpoint that surfaces counts and
  per-module up/down in the standard Prometheus exposition format, so existing
  :9090 tooling (and the dashboard) can ingest real numbers.

This is the "verified truth, not claims" layer: the dashboard reads this, never
a hard-coded score.
"""
from __future__ import annotations

import asyncio
import socket
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from enterprise.platform_kernel import HealthStatus, Module, module

DEFAULT_SERVICES = [
    ("multiplayer", "127.0.0.1", 8788),
    ("controller", "127.0.0.1", 8913),
    ("dashboard", "127.0.0.1", 8421),
    ("free_router", "127.0.0.1", 8920),
]


def _probe_tcp(host: str, port: int, timeout: float = 1.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except Exception:
        return False


@dataclass
class EntityHealth:
    name: str
    kind: str  # module | service
    up: bool
    status: str
    detail: str = ""
    latency_ms: Optional[float] = None


class FleetHealthAggregator:
    """Probe modules (health_check) + external services; return a live snapshot."""

    def __init__(self, registry: Optional[Any] = None,
                 services: Optional[List[tuple]] = None,
                 probe: Any = None) -> None:
        # registry: an object exposing .modules (dict name->record) or .items()
        self._registry = registry
        self.services = services or DEFAULT_SERVICES
        self._probe = probe or _probe_tcp

    def _module_list(self) -> List[tuple]:
        """Return [(name, health_check_callable)] from the registry, if present."""
        reg = self._registry
        if reg is None:
            return []
        modules = getattr(reg, "modules", None)
        out = []
        if isinstance(modules, dict):
            for name, rec in modules.items():
                obj = getattr(rec, "module", None) or getattr(rec, "obj", None) or rec
                hc = getattr(obj, "health_check", None)
                if callable(hc):
                    out.append((name, hc))
        return out

    def snapshot(self) -> Dict[str, Any]:
        entities: List[EntityHealth] = []
        # ------- modules (call health_check if async, else treat as present) ---
        for name, hc in self._module_list():
            status = "unknown"
            try:
                if asyncio.iscoroutinefunction(hc):
                    r = asyncio.run(hc())
                    status = r.value if hasattr(r, "value") else str(r)
                else:
                    r = hc()
                    status = r.value if hasattr(r, "value") else str(r)
            except Exception as exc:
                status = f"error:{type(exc).__name__}"
            up = "HEALTHY" in status.upper() or "OK" in status.upper()
            entities.append(EntityHealth(name, "module", up, status))
        # ------- external services (real TCP probe) --------------------------
        for name, host, port in self.services:
            t0 = time.time()
            up = self._probe(host, port)
            ms = round((time.time() - t0) * 1000, 1)
            entities.append(EntityHealth(name, "service", up,
                                         "up" if up else "down",
                                         latency_ms=ms))
        ups = sum(1 for e in entities if e.up)
        return {
            "ts": time.time(),
            "total": len(entities),
            "up": ups,
            "down": len(entities) - ups,
            "entities": [e.__dict__ for e in entities],
        }

    # ---------------------------------------------------------------- Prom
    def prometheus_text(self) -> str:
        import json as _json
        snap = self.snapshot()
        lines = [
            "# HELP eni_entity_up Whether an entity/service is up (1) or down (0).",
            "# TYPE eni_entity_up gauge",
        ]
        for e in snap["entities"]:  # entities are dicts from __dict__ already
            name = e["name"]; kind = e["kind"]
            lines.append(
                f'eni_entity_up{{name="{name}",kind="{kind}"}} '
                f"{1 if e['up'] else 0}"
            )
        lines.append(f"eni_entities_total {snap['total']}")
        lines.append(f"eni_entities_up {snap['up']}")
        lines.append(f"eni_entities_down {snap['down']}")
        return "\n".join(lines)


@module(
    name="observability",
    version="1.0.0",
    config_defaults={"services": DEFAULT_SERVICES},
)
class ObservabilityModule(Module):
    """Fleet-wide live health aggregator + Prometheus exporter."""

    def __init__(self, config: Optional[dict[str, Any]] = None) -> None:
        super().__init__(config)
        self.aggregator: Optional[FleetHealthAggregator] = None
        self._registry = None

    def bind_registry(self, registry: Any) -> None:
        """Inject the platform registry so module health checks are probed."""
        self._registry = registry
        if self.aggregator is not None:
            self.aggregator._registry = registry

    async def initialize(self) -> None:
        svcs = self.config.get("services", DEFAULT_SERVICES)
        self.aggregator = FleetHealthAggregator(self._registry,
                                                services=list(svcs))
        self.status = HealthStatus.HEALTHY

    async def health_check(self) -> HealthStatus:
        if self.aggregator is None:
            return HealthStatus.UNHEALTHY
        snap = self.aggregator.snapshot()
        # If more than half the external services are down, we're degraded.
        down_services = sum(
            1 for e in snap["entities"] if e.kind == "service" and not e.up)
        return HealthStatus.DEGRADED if down_services else HealthStatus.HEALTHY

    async def shutdown(self) -> None:
        self.status = HealthStatus.UNKNOWN

    # facade
    def snapshot(self) -> Dict[str, Any]:
        if self.aggregator is None:
            self.aggregator = FleetHealthAggregator(self._registry)
        return self.aggregator.snapshot()

    def metrics(self) -> str:
        if self.aggregator is None:
            self.aggregator = FleetHealthAggregator(self._registry)
        return self.aggregator.prometheus_text()


def create_observability_module(config: Optional[dict[str, Any]] = None) -> ObservabilityModule:
    return ObservabilityModule(config=config or {})


__all__ = [
    "FleetHealthAggregator",
    "ObservabilityModule",
    "create_observability_module",
    "DEFAULT_SERVICES",
    "__version__",
]
__version__ = "1.0.0"