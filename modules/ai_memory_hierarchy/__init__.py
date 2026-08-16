"""AI Memory Hierarchy — an enterprise module modeling the AI memory hierarchy.

Grounded in the JEVanClief transcript *"How a 1953 Word Game Explains AI
Memory"* (https://www.youtube.com/watch?v=S3fXSc5z2n4). The transcript maps the
hardware memory hierarchy (speed-vs-capacity tradeoff, locality-based staging)
onto AI memory:

  - model weights  ~ ROM            (read-only, fixed at training time)
  - context window ~ working memory / RAM (temporary, per-conversation)
  - system prompt  ~ firmware       (operating parameters)
  - retrieved ctx  ~ disk -> RAM on demand (query-driven loading)
  - persistent mem ~ selectively loaded summaries kept between conversations

Key insight implemented here: in AI, code and data are the *same* — everything
is text processed identically, so a single string-typed store with a
locality/access-count promotion policy models the whole hierarchy.

The deterministic core lives in
:mod:`enterprise.modules.ai_memory_hierarchy.ai_memory_hierarchy`
(``MemoryHierarchy``); this package exposes it as a registered Platform Kernel
module with an initialize / health_check / shutdown lifecycle and a thin
facade. Stdlib-only and network-free.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from enterprise.platform_kernel import Event, HealthStatus, Module, module

from .ai_memory_hierarchy import (
    DEFAULT_CAPACITIES,
    DEFAULT_PROMOTE_THRESHOLD,
    TIERS,
    MemoryEntry,
    MemoryHierarchy,
    Tier,
    TierLockedError,
    overlap_score,
    tokenize,
)

logger = logging.getLogger("eni.ai_memory_hierarchy_module")

__version__ = "1.0.0"
__module__ = "ai_memory_hierarchy"


@module(
    name="ai_memory_hierarchy",
    version=__version__,
    config_defaults={
        "promote_threshold": DEFAULT_PROMOTE_THRESHOLD,
        "capacities": {t.value: cap for t, cap in DEFAULT_CAPACITIES.items()},
    },
)
class AiMemoryHierarchyModule(Module):
    """Kernel module exposing the AI memory hierarchy model.

    Wraps :class:`MemoryHierarchy` behind a small facade. Publishes
    ``ai_memory_hierarchy.*`` events on the platform EventBus when one is
    wired (via :meth:`set_event_bus`).
    """

    def __init__(self, config: Optional[dict[str, Any]] = None) -> None:
        super().__init__(config)
        self._hierarchy: Optional[MemoryHierarchy] = None
        self._event_bus: Optional[Any] = None
        self._init_error: Optional[str] = None

    # ------------------------------------------------------------------ pub
    def _publish(self, topic: str, payload: dict[str, Any]) -> None:
        """Publish an event only when an event bus is wired."""
        if self._event_bus is None:
            return
        self._event_bus.publish(
            Event.create(
                topic=topic,
                source=self.name,
                payload=payload,
            )
        )

    # ------------------------------------------------------------ lifecycle
    async def initialize(self) -> None:
        """Build the MemoryHierarchy and mark the module healthy."""
        try:
            cap_cfg = self.config.get("capacities") or {}
            capacities = {}
            for t in Tier:
                try:
                    capacities[t] = int(cap_cfg.get(t.value, DEFAULT_CAPACITIES[t]))
                except (TypeError, ValueError):
                    capacities[t] = DEFAULT_CAPACITIES[t]
            self._hierarchy = MemoryHierarchy(
                capacities=capacities,
                promote_threshold=int(
                    self.config.get("promote_threshold", DEFAULT_PROMOTE_THRESHOLD)
                ),
            )
            self._init_error = None
            self.status = HealthStatus.HEALTHY
            logger.info("ai_memory_hierarchy initialized: %s", self._hierarchy.stats())
            self._publish("ai_memory_hierarchy.initialized", {"ok": True})
        except Exception as exc:  # defensively unhealthy, never crash the kernel
            self._init_error = str(exc)
            self.status = HealthStatus.UNHEALTHY
            logger.warning("ai_memory_hierarchy init failed: %s", exc)
            raise

    async def health_check(self) -> HealthStatus:
        """Report health based on init success."""
        if self._init_error:
            self.status = HealthStatus.UNHEALTHY
        elif self._hierarchy is not None:
            self.status = HealthStatus.HEALTHY
        else:
            self.status = HealthStatus.UNHEALTHY
        return self.status

    async def shutdown(self) -> None:
        """Tear down the hierarchy (no network resources to release)."""
        self._hierarchy = None
        self.status = HealthStatus.UNKNOWN
        logger.info("ai_memory_hierarchy module shutdown")
        self._publish("ai_memory_hierarchy.shutdown", {"ok": True})

    # ------------------------------------------------------------- wiring
    def set_event_bus(self, event_bus: Any) -> None:
        """Wire the platform EventBus into this module."""
        self._event_bus = event_bus

    # ------------------------------------------------------------------ core
    @property
    def hierarchy(self) -> MemoryHierarchy:
        """Return the live :class:`MemoryHierarchy` (lazily created)."""
        if self._hierarchy is None:
            self._hierarchy = MemoryHierarchy()
        return self._hierarchy

    # ---------------------------------------------------------------- facade
    def insert(
        self,
        key: str,
        content: str,
        tier: Optional[Tier] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> MemoryEntry:
        """Insert a memory entry; see :meth:`MemoryHierarchy.insert`."""
        entry = self.hierarchy.insert(key, content, tier=tier, metadata=metadata)
        self._publish("ai_memory_hierarchy.inserted", {"key": key, "tier": entry.tier.value})
        return entry

    def retrieve(self, query: str, limit: int = 5) -> list[MemoryEntry]:
        """Retrieve entries ranked by query relevance (query-driven loading)."""
        hits = self.hierarchy.retrieve(query, limit=limit)
        self._publish(
            "ai_memory_hierarchy.retrieved",
            {"query": query, "count": len(hits)},
        )
        return hits

    def promote(self, key: str) -> Optional[MemoryEntry]:
        return self.hierarchy.promote(key)

    def demote(self, key: str) -> Optional[MemoryEntry]:
        return self.hierarchy.demote(key)

    def tier_summary(self) -> dict[str, dict[str, Any]]:
        return self.hierarchy.tier_summary()

    def health(self) -> dict[str, Any]:
        """Return a health/statistics dict for operational tooling."""
        return self.hierarchy.stats()

    def set_prompt(self, key: str, content: str) -> MemoryEntry:
        "Write a system-prompt (firmware) operating-parameter entry."
        return self.hierarchy.set_prompt(key, content)

    def set_weights(self, key: str, content: str) -> MemoryEntry:
        """"Train" a model weight before weights are locked (ROM)."""
        return self.hierarchy.set_weights(key, content)

    def lock_weights(self) -> None:
        self.hierarchy.lock_weights()


def create_ai_memory_hierarchy_module(
    config: Optional[dict[str, Any]] = None,
) -> AiMemoryHierarchyModule:
    """Create (but do not initialize) an :class:`AiMemoryHierarchyModule`."""
    return AiMemoryHierarchyModule(config=config or {})


__all__ = [
    "__version__",
    "AiMemoryHierarchyModule",
    "create_ai_memory_hierarchy_module",
    "MemoryHierarchy",
    "MemoryEntry",
    "Tier",
    "TierLockedError",
    "TIERS",
    "DEFAULT_CAPACITIES",
    "DEFAULT_PROMOTE_THRESHOLD",
    "overlap_score",
    "tokenize",
]
