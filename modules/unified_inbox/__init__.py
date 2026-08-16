"""Enterprise Platform Unified Inbox module package.

Grounded in the JEVanClief "Clawdbot (Moltbot) Has 100K Stars. It Has Zero AI."
transcript: a zero-AI universal assistant that consolidates every messaging
platform (Slack, Discord, WhatsApp, Telegram, email, calendar, Teams) into one
place and routes messages deterministically — no neural model required.

Exports:
  UnifiedInboxModule      — @module-decorated Module subclass registered with
                            the Platform Kernel.
  CrossChannelInbox       — pure-stdlib zero-AI routing/triage/consolidation core.
  ChannelAdapter          — named channel adapter descriptor.
  InboundMessage          — a message arriving from any channel.
  TriageDecision          — deterministic routing/triage verdict for a message.
  create_unified_inbox_module — factory for the registered module.

Version: 1.0.0
Python: 3.10+
"""

from __future__ import annotations

__version__ = "1.0.0"
__module__ = "unified_inbox"

import asyncio
import logging
import threading
from typing import Any, Optional  # noqa: F401

from enterprise.platform_kernel import (
    Event,
    EventBus,
    EventPriority,  # noqa: F401
    HealthStatus,
    Module,
    module,
)

from .unified_inbox import (
    ChannelAdapter,
    CrossChannelInbox,
    InboundMessage,
    TriageDecision,
)

__all__ = [
    "__version__",
    "UnifiedInboxModule",
    "CrossChannelInbox",
    "ChannelAdapter",
    "InboundMessage",
    "TriageDecision",
    "create_unified_inbox_module",
]

# Logger for the module.
_logger: logging.Logger = logging.getLogger("enterprise.unified_inbox")


@module(name="unified_inbox", version=__version__)
class UnifiedInboxModule(Module):
    """Enterprise Unified Inbox Module.

    Wraps the zero-AI :class:`CrossChannelInbox`: a deterministic gateway that
    consolidates messages from every messaging platform into one unified inbox,
    runs rule-based routing/triage (no ML), manages conversation sessions, and
    applies attention/notification triage — mirroring the Moltbot/Clawdbot
    "one assistant, one place" thesis where ~60% of value is plumbing and ~30%
    is rule-based routing, with AI kept as an external, optional hook.

    Events published (via the platform EventBus when wired):
      - unified_inbox.ingested   -- a new accepted message entered the inbox
      - unified_inbox.routed     -- a message was routed to a channel/action
      - unified_inbox.rejected   -- a message failed authentication (allowlist)
      - unified_inbox.duplicate  -- a message was dropped as a duplicate
    """

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        super().__init__(config)
        self._inbox: CrossChannelInbox | None = None
        self._event_bus: EventBus | None = None
        self._lock: threading.RLock = threading.RLock()

    # ── Properties ───────────────────────────────────────────────────────

    @property
    def inbox(self) -> CrossChannelInbox | None:
        """Return the active :class:`CrossChannelInbox`, if initialized."""
        with self._lock:
            return self._inbox

    # ── Lifecycle ────────────────────────────────────────────────────────

    async def initialize(self) -> None:
        """Initialize the Unified Inbox module.

        Builds the CrossChannelInbox from module config, wires the optional
        event sink, and performs an initial health verification before marking
        HEALTHY.
        """
        with self._lock:
            self._status = HealthStatus.STARTING
            cfg = dict(self._config or {})

        try:
            _logger.info("Initializing unified_inbox module ...")
            self._inbox = CrossChannelInbox(cfg.get("inbox", cfg))
            # The sink guards on event_bus being None before publishing.
            self._inbox.set_event_sink(self._publish_core_event)
            report = self._inbox.health()
            self._status = (
                HealthStatus.HEALTHY if report["healthy"] else HealthStatus.UNHEALTHY
            )
            _logger.info(
                "unified_inbox initialized: %d channels, %d active sessions",
                report["channels"],
                report["sessions"],
            )
        except Exception as exc:  # pragma: no cover - defensive
            _logger.exception("Failed to initialize unified_inbox module: %s", exc)
            self._status = HealthStatus.UNHEALTHY
            raise

    async def health_check(self) -> HealthStatus:
        """Return the current health of the unified inbox core.

        The core is pure in-memory (no network / no DB), so health reflects
        whether the inbox is constructed and its channel registry is healthy.

        Returns:
            HealthStatus: HEALTHY when the core is operational, UNKNOWN before
            initialization, UNHEALTHY on any error.
        """
        inbox = self._inbox
        if inbox is None:
            self._status = HealthStatus.UNKNOWN
            return self._status

        try:
            report = inbox.health()
            self._status = (
                HealthStatus.HEALTHY if report["healthy"] else HealthStatus.UNHEALTHY
            )
        except Exception:  # pragma: no cover - defensive
            _logger.exception("unified_inbox health check failed")
            self._status = HealthStatus.UNHEALTHY
        return self._status

    async def shutdown(self) -> None:
        """Gracefully shut the unified inbox module down."""
        with self._lock:
            self._status = HealthStatus.STOPPING

        try:
            _logger.info("Shutting down unified_inbox module ...")
            if self._inbox is not None:
                self._inbox.set_event_sink(None)
                self._inbox.clear()
            self._inbox = None
            with self._lock:
                self._status = HealthStatus.STOPPING
            _logger.info("unified_inbox module shut down successfully")
        except Exception as exc:  # pragma: no cover - defensive
            _logger.exception("Error during unified_inbox shutdown: %s", exc)
            with self._lock:
                self._status = HealthStatus.UNHEALTHY
            raise

    # ── Event Bus Wiring ─────────────────────────────────────────────────

    def set_event_bus(self, event_bus: EventBus) -> None:
        """Wire the platform EventBus into this module.

        Called by the Platform Kernel after module discovery but before
        initialize().  The core event sink guards on ``event_bus is not None``
        before publishing, so callers may safely leave the bus unset.

        Args:
            event_bus: The platform EventBus instance.
        """
        with self._lock:
            self._event_bus = event_bus

    def _publish_core_event(self, topic: str, payload: dict[str, Any]) -> None:
        """Event sink wired into the core: publish onto the platform EventBus.

        Guards against a missing/unset event bus before publishing.
        """
        if self._event_bus is None:
            return
        try:
            self._event_bus.publish(
                Event.create(
                    topic=topic,
                    source="unified_inbox",
                    payload=payload,
                )
            )
        except Exception:  # pragma: no cover - defensive
            _logger.warning("Failed to publish unified_inbox event %s", topic)


def create_unified_inbox_module(
    config: dict[str, Any] | None = None,
) -> UnifiedInboxModule:
    """Create a :class:`UnifiedInboxModule` from an optional config dict.

    The config may contain module-level keys (``publish_events``) and/or an
    ``inbox`` sub-dict with core tuning such as ``weights``, ``allowed_senders``,
    ``urgent_keywords``, ``dedup_window``, ``high_priority_senders`` and
    ``calendar_keywords``.

    Args:
        config: Optional module configuration dictionary.

    Returns:
        A fully constructed :class:`UnifiedInboxModule`.
    """
    cfg = dict(config or {})
    module_config: dict[str, Any] = {
        "publish_events": cfg.get("publish_events", True),
    }
    if "inbox" in cfg:
        module_config["inbox"] = cfg["inbox"]
    return UnifiedInboxModule(config=module_config)
