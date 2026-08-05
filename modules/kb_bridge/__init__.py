from __future__ import annotations

"""ENI Knowledge Base OS Module

Enterprise-grade wrapper around Hermes KB Universal, providing
structured CRUD, search, vector search, metrics, and health checks
as a registered Platform Kernel module.

Exports:
  ENIKBModule        — @module-decorated Module subclass
  KnowledgeBaseBridge — Full KB wrapper with event publishing
  KBHealthCheck      — DB connectivity health verification

Version: 1.0.0
Python: 3.10+
"""

__version__ = "1.0.0"
__module__ = "kb_bridge"

import asyncio
import logging
import threading
from typing import Any, Dict, List, Optional

from enterprise.platform_kernel import (
    EventBus,
    EventPriority,
    HealthStatus,
    Module,
    module,
)

from .kb_bridge import KnowledgeBaseBridge, KBHealthCheck
from .sources import (
    KbDoc,
    SourceAdapter,
    FileSourceAdapter,
    SqliteSourceAdapter,
    JsonSourceAdapter,
    SourceRegistry,
    KbMerger,
    KbQueryBridge,
)

__all__ = [
    "__version__",
    "ENIKBModule",
    "KnowledgeBaseBridge",
    "KBHealthCheck",
    # pluggable knowledge-source adapters + merge facade
    "KbDoc",
    "SourceAdapter",
    "FileSourceAdapter",
    "SqliteSourceAdapter",
    "JsonSourceAdapter",
    "SourceRegistry",
    "KbMerger",
    "KbQueryBridge",
    "create_kb_bridge_module",
]

# ---------------------------------------------------------------------------
# Module logger
# ---------------------------------------------------------------------------
_logger: logging.Logger = logging.getLogger("enterprise.kb")


@module(name="kb_bridge", version="1.0.0")
class ENIKBModule(Module):
    """Enterprise Knowledge Base Module.

    Wraps the Hermes KB Universal library, exposing a full-featured
    knowledge base with pattern management, skill sync, vector search,
    operations tracking, and health monitoring.

    Events published:
      - kb.pattern.created
      - kb.pattern.updated
      - kb.pattern.deleted
      - kb.skill.updated
      - kb.skill.synced
      - kb.search.performed
      - kb.health.status
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(config)
        self._bridge: Optional[KnowledgeBaseBridge] = None
        self._health_checker: Optional[KBHealthCheck] = None
        self._event_bus: Optional[EventBus] = None
        self._lock: threading.RLock = threading.RLock()
        self._bridge_config: Dict[str, Any] = {}

    # ── Properties ───────────────────────────────────────────────────────

    @property
    def bridge(self) -> Optional[KnowledgeBaseBridge]:
        """Return the active KnowledgeBaseBridge, if initialized."""
        with self._lock:
            return self._bridge

    @property
    def health_checker(self) -> Optional[KBHealthCheck]:
        """Return the active KBHealthCheck, if initialized."""
        with self._lock:
            return self._health_checker

    # ── Lifecycle ────────────────────────────────────────────────────────

    async def initialize(self) -> None:
        """Initialize the ENI Knowledge Base module.

        Creates the KnowledgeBaseBridge, wires the event bus reference,
        and performs an initial health check.
        """
        with self._lock:
            self._status = HealthStatus.STARTING
            self._bridge_config = {
                "profile": self._config.get("profile", "default"),
                "auto_sync_skills": self._config.get("auto_sync_skills", True),
                "publish_events": self._config.get("publish_events", True),
            }

        try:
            _logger.info(
                "ENI KB module initializing (profile=%s)",
                self._bridge_config["profile"],
            )

            # Instantiate the bridge — this opens DB connections
            self._bridge = KnowledgeBaseBridge(
                event_bus=self._event_bus,
                profile=self._bridge_config["profile"],
                publish_events=self._bridge_config["publish_events"],
            )

            # Instantiate the health checker
            self._health_checker = KBHealthCheck(bridge=self._bridge)

            # Optionally sync skills on startup
            if self._bridge_config["auto_sync_skills"]:
                result = await asyncio.to_thread(self._bridge.sync_skills)
                _logger.info("Skills sync complete: %s", result)

            self._status = HealthStatus.HEALTHY
            _logger.info("ENI KB module initialized successfully")

        except Exception as exc:
            _logger.exception("Failed to initialize ENI KB module: %s", exc)
            self._status = HealthStatus.UNHEALTHY
            raise

    async def health_check(self) -> HealthStatus:
        """Perform a health check on the knowledge base.

        Returns:
            HealthStatus indicating connectivity and operational status.
        """
        if self._health_checker is None:
            self._status = HealthStatus.UNKNOWN
            return self._status

        try:
            report = await asyncio.to_thread(self._health_checker.run)
            self._status = report.status
            return self._status
        except Exception as exc:
            _logger.exception("Health check failed: %s", exc)
            self._status = HealthStatus.UNHEALTHY
            return self._status

    async def shutdown(self) -> None:
        """Gracefully shut down the knowledge base module.

        Closes all DB connections and cleans up resources.
        """
        with self._lock:
            self._status = HealthStatus.STOPPING

        _logger.info("Shutting down ENI KB module...")

        try:
            if self._bridge is not None:
                await asyncio.to_thread(self._bridge.close)
                self._bridge = None

            self._health_checker = None
            self._status = HealthStatus.HEALTHY
            _logger.info("ENI KB module shut down successfully")

        except Exception as exc:
            _logger.exception("Error during ENI KB shutdown: %s", exc)
            self._status = HealthStatus.UNHEALTHY
            raise

    # ── Event Bus Wiring ─────────────────────────────────────────────────

    def set_event_bus(self, event_bus: EventBus) -> None:
        """Wire the platform EventBus into this module.

        Called by the Platform Kernel after module discovery but
        before initialize().  If an event bus is already active,
        it is replaced gracefully.

        Args:
            event_bus: The platform EventBus instance.
        """
        with self._lock:
            self._event_bus = event_bus
            if self._bridge is not None:
                self._bridge.set_event_bus(event_bus)


def create_kb_bridge_module(
    config: Optional[Dict[str, Any]] = None,
) -> ENIKBModule:
    """Create an :class:`ENIKBModule` from an optional config dict.

    The config may contain ``profile`` (str), ``publish_events`` (bool) and/or
    ``sources`` (list of adapter constructor kwargs) to pre-wire pluggable
    knowledge source adapters onto the module.

    Args:
        config: Optional module configuration dictionary.

    Returns:
        A fully constructed :class:`ENIKBModule`.
    """
    cfg = dict(config or {})
    module = ENIKBModule(
        config={
            "profile": cfg.get("profile", "default"),
            "publish_events": cfg.get("publish_events", True),
        }
    )
    sources = cfg.get("sources")
    if sources:
        from .sources import KbQueryBridge

        bridge = KbQueryBridge()
        for source_cfg in sources:
            kind = source_cfg.get("type")
            if kind == "file":
                bridge.register(FileSourceAdapter(source_cfg["directory"]))
            elif kind == "sqlite":
                bridge.register(
                    SqliteSourceAdapter(
                        source_cfg["database"],
                        table=source_cfg.get("table", "docs"),
                    )
                )
            elif kind == "json":
                bridge.register(JsonSourceAdapter(source_cfg["path"]))
            else:  # pragma: no cover - defensive
                raise ValueError(f"Unknown source type: {kind!r}")
        module._kb_sources = bridge  # type: ignore[attr-defined]
    return module
