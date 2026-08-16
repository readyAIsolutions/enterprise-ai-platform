"""Position-addressed memory — *folder-as-memory* for AI context.

Grounded in the JEVanClief transcript *"How I Run Creative, Software, and
Business Work as One System"* (https://www.youtube.com/watch?v=hALln9wrrQo).
The transcript contrasts three bets on what memory means for an LLM —
OpenBrain vector embeddings (**content**-addressed), Karpathy's LLM wiki
(**link**-addressed), and **the folder system** (**position**-addressed). This
module implements the position-addressed cascade — a root ``CLAUDE.md`` whose
rules cascade down, per-project ``Context.md`` layered on top, and per-file
convention docs — so "by the time Claude reads the scene, it has already
inherited the brand voice, the production rules, the specific shot list."

The deterministic core lives in
:mod:`enterprise.modules.position_addressed_memory.position_addressed_memory`
(:class:`ContextRule`, :class:`ContextStack`, :class:`PathResolver`,
:class:`MemoryAddressing`); this package exposes it as a registered Platform
Kernel module with an initialize / health_check / shutdown lifecycle and a
thin facade. Stdlib-only and network-free.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from enterprise.platform_kernel import Event, HealthStatus, Module, module

from .position_addressed_memory import (
    CONTENT_ADDRESSED,
    CONVENTION_CONTEXT_FILES,
    DEFAULT_RULE_FILES,
    LINK_ADDRESSED,
    POSITION_ADDRESSED,
    PROJECT_CONTEXT_FILE,
    ROOT_CONTEXT_FILE,
    AddressingMode,
    ContentHit,
    ContentStore,
    ContextLayer,
    ContextRule,
    ContextStack,
    LinkHit,
    LinkStore,
    MemoryAddressing,
    PathResolution,
    PathResolver,
    PositionHit,
    Precedence,
    Resolution,
    parse_markdown_context,
)

logger = logging.getLogger("eni.position_addressed_memory_module")

__version__ = "1.0.0"
__module__ = "position_addressed_memory"


@module(
    name="position_addressed_memory",
    version=__version__,
    config_defaults={
        "root": None,
        "rule_files": list(DEFAULT_RULE_FILES),
        "precedence": Precedence.DEEPEST.value,
    },
)
class PositionAddressedMemoryModule(Module):
    """Kernel module exposing the position-addressed memory model.

    Wraps :class:`MemoryAddressing` behind a small facade. Publishes
    ``position_addressed_memory.*`` events on the platform EventBus when one
    is wired (via :meth:`set_event_bus`).
    """

    def __init__(self, config: Optional[dict[str, Any]] = None) -> None:
        super().__init__(config)
        self._addressing: Optional[MemoryAddressing] = None
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
        """Build the MemoryAddressing model and mark the module healthy."""
        try:
            root = self.config.get("root")
            if not root:
                raise ValueError(
                    "position_addressed_memory requires a 'root' filesystem path"
                )
            precedence = Precedence(
                self.config.get("precedence", Precedence.DEEPEST.value)
            )
            self._addressing = MemoryAddressing(
                root=str(root),
                rule_files=tuple(self.config.get("rule_files", DEFAULT_RULE_FILES)),
                precedence=precedence,
            )
            self._init_error = None
            self.status = HealthStatus.HEALTHY
            logger.info(
                "position_addressed_memory initialized at root=%s",
                self._addressing.root,
            )
            self._publish(
                "position_addressed_memory.initialized",
                {"root": self._addressing.root},
            )
        except Exception as exc:  # defensively unhealthy, never crash the kernel
            self._init_error = str(exc)
            self.status = HealthStatus.UNHEALTHY
            logger.warning("position_addressed_memory init failed: %s", exc)
            raise

    async def health_check(self) -> HealthStatus:
        """Report health based on init success."""
        if self._init_error:
            self.status = HealthStatus.UNHEALTHY
        elif self._addressing is not None:
            self.status = HealthStatus.HEALTHY
        else:
            self.status = HealthStatus.UNHEALTHY
        return self.status

    async def shutdown(self) -> None:
        """Tear down the model (no network resources to release)."""
        self._addressing = None
        self.status = HealthStatus.UNKNOWN
        logger.info("position_addressed_memory module shutdown")
        self._publish("position_addressed_memory.shutdown", {"ok": True})

    # ------------------------------------------------------------- wiring
    def set_event_bus(self, event_bus: Any) -> None:
        """Wire the platform EventBus into this module."""
        self._event_bus = event_bus

    # ------------------------------------------------------------------ core
    @property
    def addressing(self) -> MemoryAddressing:
        """Return the live :class:`MemoryAddressing` (lazily created)."""
        if self._addressing is None:
            self._addressing = MemoryAddressing(
                root=str(self.config.get("root") or ".")
            )
        return self._addressing

    # ---------------------------------------------------------------- facade
    def resolve_position(self, path: str) -> PositionHit:
        """Resolve a file by its filesystem position (inherited context)."""
        hit = self.addressing.resolve_position(path)
        self._publish(
            "position_addressed_memory.position",
            {"path": hit.path, "rules": len(hit.context)},
        )
        return hit

    def resolve_content(self, query: str) -> ContentHit:
        """Resolve content by SHA-256 digest."""
        return self.addressing.resolve_content(query)

    def resolve_link(self, name: str) -> LinkHit:
        """Resolve a wiki-style entity name by link addressing."""
        return self.addressing.resolve_link(name)

    def resolve(self, query: str) -> Resolution:
        """Deterministically resolve an opaque query across addressing modes."""
        res = self.addressing.resolve(query)
        self._publish(
            "position_addressed_memory.resolved",
            {"query": query, "mode": res.mode.value},
        )
        return res

    def inherited_context(self, path: str) -> dict[str, str]:
        """Return the full cascading context a file inherits from its path."""
        return self.addressing.inherited_context(path)

    def store_position(self, path: str, content: str) -> str:
        """Store a file's content addressed by its position."""
        return self.addressing.store_position(path, content)

    def store_content(self, content: str) -> str:
        """Store content and return its content (SHA-256) address."""
        return self.addressing.store_content(content)

    def store_link(self, name: str, content: str) -> None:
        """Define a wiki-style entity page by name."""
        self.addressing.store_link(name, content)

    def stats(self) -> dict[str, Any]:
        """Return operational statistics for the addressing stores."""
        return {
            "root": self.addressing.root,
            "position_files": len(self.addressing.position_store),
            "content_digests": len(self.addressing.content),
            "link_pages": len(self.addressing.links),
            "orphan_pages": len(self.addressing.links.orphans()),
            "contradictions": len(self.addressing.links.contradictions()),
        }


def create_position_addressed_memory_module(
    config: Optional[dict[str, Any]] = None,
) -> PositionAddressedMemoryModule:
    """Create (but do not initialize) a :class:`PositionAddressedMemoryModule`."""
    return PositionAddressedMemoryModule(config=config or {})


__all__ = [
    "__version__",
    "PositionAddressedMemoryModule",
    "create_position_addressed_memory_module",
    "AddressingMode",
    "ContentHit",
    "ContentStore",
    "ContextLayer",
    "ContextRule",
    "ContextStack",
    "LinkHit",
    "LinkStore",
    "MemoryAddressing",
    "PathResolution",
    "PathResolver",
    "PositionHit",
    "Precedence",
    "Resolution",
    "parse_markdown_context",
    "POSITION_ADDRESSED",
    "CONTENT_ADDRESSED",
    "LINK_ADDRESSED",
    "ROOT_CONTEXT_FILE",
    "PROJECT_CONTEXT_FILE",
    "CONVENTION_CONTEXT_FILES",
    "DEFAULT_RULE_FILES",
]
