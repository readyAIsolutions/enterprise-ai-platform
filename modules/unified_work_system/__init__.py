"""ENI Unified Work System Module

Enterprise-grade module that runs creative, technical/software, and business
work as ONE system — grounded in the JEVanClief one-system thesis.

At the heart of the module is a :class:`WorkSystem` that centers on a single
*artifact* and renders it through multiple *lenses* (creative, technical,
business).  Each lens derives structured facts from the same artifact, and a
lens-consistency check verifies that the lenses are actually telling the same
story (flagging disagreements).  The module also implements the transcript's
memory model: an external AI :class:`MemoryStore` with position/link/content
addressing plus an explicit :class:`HumanMemory` that stays in the loop.

Exports:
  UnifiedWorkSystemModule  — @module-decorated Module subclass
  WorkSystem               — artifact-centered multi-lens core
  Artifact, Lens           — shared model
  CreativeLens, TechnicalLens, BusinessLens
  MemoryStore, MemoryItem, HumanMemory, ContextResolver
  create_unified_work_system_module

Version: 1.0.0
Python: 3.10+
"""

from __future__ import annotations

__version__ = "1.0.0"
__module__ = "unified_work_system"

import logging
import threading
from typing import Any

from enterprise.platform_kernel import (
    EventBus,
    EventPriority,  # noqa: F401
    HealthStatus,
    Module,
    module,
)

from .unified_work_system import (
    Artifact,
    BusinessLens,
    COMMON_STORY_DIMENSIONS,
    ConsistencyReport,
    ContextResolver,
    CreativeLens,
    HumanMemory,
    Lens,
    LensView,
    MemoryItem,
    MemoryStore,
    TechnicalLens,
    WorkSystem,
    build_artifact,
)

__all__ = [
    "__version__",
    "UnifiedWorkSystemModule",
    "create_unified_work_system_module",
    # core
    "COMMON_STORY_DIMENSIONS",
    "WorkSystem",
    "Artifact",
    "Lens",
    "CreativeLens",
    "TechnicalLens",
    "BusinessLens",
    "LensView",
    "ConsistencyReport",
    # memory model
    "MemoryItem",
    "MemoryStore",
    "HumanMemory",
    "ContextResolver",
]

_logger: logging.Logger = logging.getLogger("enterprise.unified_work_system")

#: Events this module publishes on the platform EventBus.
_EVENT_LENS_RENDERED = "unified_work_system.lens.rendered"
_EVENT_CONSISTENCY = "unified_work_system.consistency"
_EVENT_MEMORY_STORED = "unified_work_system.memory.stored"
_EVENT_MEMORY_CONTRADICTION = "unified_work_system.memory.contradiction"
_EVENT_HEALTH = "unified_work_system.health.status"


@module(name="unified_work_system", version="1.0.0")
class UnifiedWorkSystemModule(Module):
    """Unified Work System Module.

    Owns a :class:`WorkSystem` that centers on one artifact and renders it
    through the creative, technical and business lenses as a single system —
    not three consultancies.  Also owns the external AI memory store and the
    human context that stays in the loop.

    Events published:
      - unified_work_system.lens.rendered
      - unified_work_system.consistency
      - unified_work_system.memory.stored
      - unified_work_system.memory.contradiction
      - unified_work_system.health.status
    """

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        super().__init__(config)
        self._work_system: WorkSystem | None = None
        self._event_bus: EventBus | None = None
        self._lock: threading.RLock = threading.RLock()

    # ── Properties ────────────────────────────────────────────────────────

    @property
    def work_system(self) -> WorkSystem | None:
        """Return the active WorkSystem, if initialized."""
        with self._lock:
            return self._work_system

    # ── Lifecycle ─────────────────────────────────────────────────────────

    async def initialize(self) -> None:
        """Initialize the Unified Work System module.

        Builds the :class:`WorkSystem` (with the configured artifact facts and
        any seeded memory) and runs an initial consistency check.
        """
        with self._lock:
            self._status = HealthStatus.STARTING

        try:
            cfg = self._config
            artifact = build_artifact(
                name=cfg.get("artifact_name", "untitled"),
                kind=cfg.get("artifact_kind", "project"),
                client=cfg.get("artifact_client", ""),
                description=cfg.get("artifact_description", ""),
                **cfg.get("facts", {}),
            )
            ws = WorkSystem(artifact=artifact)
            for fact in cfg.get("seed_memory", []):
                item = MemoryItem(**fact)
                ws.memory.add(item)
            ws.human.direct(cfg.get("focus", ""))

            self._work_system = ws
            self._status = HealthStatus.HEALTHY
            _logger.info("Unified Work System module initialized (artifact=%r)", artifact.name)

            self._emit(_EVENT_HEALTH, {"status": self._status.value})
            self._emit(_EVENT_CONSISTENCY, {
                "artifact": artifact.name,
                **self._consistency_payload(),
            })
        except Exception as exc:  # pragma: no cover - defensive
            _logger.exception("Unified Work System initialize failed: %s", exc)
            self._status = HealthStatus.UNHEALTHY
            raise

    async def health_check(self) -> HealthStatus:
        """Health check: healthy when a WorkSystem is initialized."""
        with self._lock:
            if self._work_system is None:
                self._status = HealthStatus.UNKNOWN
            elif self._status in (HealthStatus.UNKNOWN, HealthStatus.STARTING):
                self._status = HealthStatus.HEALTHY
            self._emit(_EVENT_HEALTH, {"status": self._status.value})
            return self._status

    async def shutdown(self) -> None:
        """Gracefully shut down the module."""
        with self._lock:
            self._status = HealthStatus.STOPPING
        self._emit(_EVENT_HEALTH, {"status": HealthStatus.STOPPING.value})
        _logger.info("Unified Work System module shutting down")
        with self._lock:
            self._work_system = None
            self._status = HealthStatus.HEALTHY

    # ── Event Bus Wiring ──────────────────────────────────────────────────

    def set_event_bus(self, event_bus: EventBus) -> None:
        """Wire the platform EventBus into this module.

        Called by the Platform Kernel after module discovery but before
        initialize().  A ``None`` event bus is accepted (events are skipped
        until a real bus arrives).
        """
        with self._lock:
            self._event_bus = event_bus

    def _emit(self, topic: str, payload: dict[str, Any]) -> None:
        bus = self._event_bus
        if bus is not None:
            bus.publish(_make_event(topic, payload))

    # ── Operational Facade ────────────────────────────────────────────────

    def render(self) -> dict[str, LensView]:
        """Render the shared artifact through every lens."""
        ws = self._require_ws()
        views = ws.render()
        self._emit(_EVENT_LENS_RENDERED, {
            "artifact": ws.artifact.name,
            "lenses": list(views),
        })
        return views

    def check_consistency(self) -> ConsistencyReport:
        """Check whether all lenses tell the same story."""
        ws = self._require_ws()
        report = ws.check_consistency()
        self._emit(_EVENT_CONSISTENCY, self._consistency_payload(report))
        return report

    def store_memory(self, item: MemoryItem) -> str:
        """Store an item in the external AI memory and emit events."""
        ws = self._require_ws()
        item_id = ws.memory.add(item)
        self._emit(_EVENT_MEMORY_STORED, {"item_id": item_id, "namespace": item.namespace})
        contradictions = ws.memory.contradictions()
        if contradictions:
            self._emit(_EVENT_MEMORY_CONTRADICTION, {"count": len(contradictions)})
        return item_id

    # ── Helpers ───────────────────────────────────────────────────────────

    def _require_ws(self) -> WorkSystem:
        ws = self._work_system
        if ws is None:
            raise RuntimeError("UnifiedWorkSystemModule is not initialized")
        return ws

    def _consistency_payload(self, report: ConsistencyReport | None = None) -> dict[str, Any]:
        report = report or self._require_ws().check_consistency()
        return {
            "consistent": report.consistent,
            "agreements": report.agreements,
            "disagreements": report.disagreements,
            "unstated": report.unstated,
        }


def _make_event(topic: str, payload: dict[str, Any]) -> Any:
    """Fallback Event constructor when the bus lacks ``create_event``."""
    from enterprise.platform_kernel import Event

    return Event.create(topic, "unified_work_system", payload, priority=EventPriority.NORMAL)


def create_unified_work_system_module(
    config: dict[str, Any] | None = None,
) -> UnifiedWorkSystemModule:
    """Create a :class:`UnifiedWorkSystemModule` from an optional config dict.

    Supported config keys (all optional):
      * ``artifact_name``        — artifact name (default "untitled")
      * ``artifact_kind``        — artifact kind (default "project")
      * ``artifact_client``      — client name
      * ``artifact_description`` — description
      * ``facts``                — dict of artifact facts, following lens field
                                   conventions (e.g. ``creative_audience``,
                                   ``business_revenue``, ``stack``)
      * ``seed_memory``          — list of MemoryItem constructor kwargs to
                                   pre-load into the external memory store
      * ``focus``                — a human-context focus term

    Args:
        config: Optional module configuration dictionary.

    Returns:
        A fully constructed :class:`UnifiedWorkSystemModule`.
    """
    cfg = dict(config or {})
    return UnifiedWorkSystemModule(config=cfg)
