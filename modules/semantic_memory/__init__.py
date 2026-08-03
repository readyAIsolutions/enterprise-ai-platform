"""ENI Semantic Memory OS Module.

Cognee-style graph/persistent memory + semantic retrieval capability:
a lightweight, dependency-free semantic retrieval layer built on sparse
feature-hash embeddings (deterministic), cosine similarity ranking, metadata
filtering, and an optional adapter into the existing knowledge-graph store.

The module is a registered Platform Kernel module implementing the standard
lifecycle (``initialize`` / ``health_check`` / ``shutdown``) and the event-bus
wiring contract (``set_event_bus``).

Version: 1.0.0
Python: 3.10+
"""

from __future__ import annotations

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

from .semantic_memory import (
    Document,
    Embedder,
    HashEmbedder,
    KnowledgeGraphAdapter,
    ScoredDoc,
    SemanticIndex,
    SemanticMemory,
    cosine_similarity,
    dot,
    normalize,
)

__version__ = "1.0.0"
__module__ = "semantic_memory"

__all__ = [
    "__version__",
    "SemanticMemoryModule",
    # Core classes
    "SemanticMemory",
    "SemanticIndex",
    "KnowledgeGraphAdapter",
    "HashEmbedder",
    "Document",
    "ScoredDoc",
    # Protocol + helpers
    "Embedder",
    "normalize",
    "dot",
    "cosine_similarity",
]

_logger = logging.getLogger("enterprise.semantic_memory")


@module(name="semantic_memory", version="1.0.0")
class SemanticMemoryModule(Module):
    """Enterprise Semantic Memory Module.

    Provides dependency-free semantic retrieval over persistent memory and
    knowledge-graph triples. Wraps a :class:`~.SemanticMemory` facade and
    exposes its index through a clean lifecycle.

    Configuration (dict passed to ``__init__``):
        dim (int): Embedding dimensionality for the default hash embedder
            (default 256).
        top_k (int): Default number of results returned by ``recall`` when no
            ``k`` is supplied (default 5).

    Events published (when an event bus is wired via ``set_event_bus``):
        - memory.doc.indexed  — a document was added to the index
        - memory.query       — a recall/query was performed
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(config)
        self._memory: Optional[SemanticMemory] = None
        self._event_bus: Optional[EventBus] = None
        self._lock = threading.RLock()
        self._dim: int = int(self._config.get("dim", 256) or 256)
        self._top_k: int = int(self._config.get("top_k", 5) or 5)

    # -- Properties ---------------------------------------------------------

    @property
    def memory(self) -> Optional[SemanticMemory]:
        """Return the active SemanticMemory facade, if initialized."""
        with self._lock:
            return self._memory

    @property
    def dim(self) -> int:
        """Configured embedding dimensionality."""
        return self._dim

    @property
    def top_k(self) -> int:
        """Configured default retrieval result count."""
        return self._top_k

    # -- Lifecycle ----------------------------------------------------------

    async def initialize(self) -> None:
        """Build the SemanticMemory index and its default hash embedder.

        On success the module status becomes :data:`HealthStatus.HEALTHY`;
        on failure it becomes :data:`HealthStatus.UNHEALTHY` and the error is
        re-raised so the platform can react.
        """
        with self._lock:
            self._status = HealthStatus.STARTING

        _logger.info(
            "Semantic memory initializing (dim=%s, top_k=%s)", self._dim, self._top_k
        )
        try:
            embedder = HashEmbedder(dim=self._dim)
            self._memory = SemanticMemory(embedder=embedder)
            self._status = HealthStatus.HEALTHY
            _logger.info("Semantic memory initialized successfully")
        except Exception as exc:
            _logger.exception("Failed to initialize semantic memory: %s", exc)
            self._status = HealthStatus.UNHEALTHY
            raise

    async def health_check(self) -> HealthStatus:
        """Return the module health status.

        HEALTHY if the semantic memory facade has been built, UNHEALTHY if
        initialization failed, UNKNOWN if never initialized.
        """
        with self._lock:
            if self._memory is not None and self._status is HealthStatus.HEALTHY:
                return HealthStatus.HEALTHY
            if self._status is HealthStatus.UNHEALTHY:
                return HealthStatus.UNHEALTHY
            self._status = HealthStatus.UNKNOWN
            return self._status

    async def shutdown(self) -> None:
        """Gracefully shut down the module, releasing the index."""
        with self._lock:
            self._status = HealthStatus.STOPPING
            _logger.info("Shutting down semantic memory module...")
            self._memory = None
            self._status = HealthStatus.HEALTHY

    # -- Event Bus Wiring ---------------------------------------------------

    def set_event_bus(self, event_bus: EventBus) -> None:
        """Wire the platform EventBus into this module.

        Called by the Platform Kernel after module discovery but before
        ``initialize()``. If an event bus is already active it is replaced
        gracefully.
        """
        with self._lock:
            self._event_bus = event_bus

    # -- Public operations --------------------------------------------------

    def remember(
        self,
        id: str,
        text: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Store a document into semantic memory and return its id.

        Emits ``memory.doc.indexed`` on the event bus when available.
        """
        if self._memory is None:
            raise RuntimeError("Semantic memory module is not initialized")
        doc_id = self._memory.remember(id, text, metadata)
        self._publish(
            "memory.doc.indexed",
            {"id": doc_id, "text": text, "metadata": metadata or {}},
        )
        return doc_id

    def recall(
        self,
        query: str,
        k: Optional[int] = None,
        metadata_filter: Optional[Dict[str, Any]] = None,
    ) -> List[ScoredDoc]:
        """Retrieve the top-k documents most semantically similar to ``query``.

        Emits ``memory.query`` on the event bus when available.
        """
        if self._memory is None:
            raise RuntimeError("Semantic memory module is not initialized")
        limit = k if k is not None else self._top_k
        results = self._memory.recall(query, k=limit, metadata_filter=metadata_filter)
        self._publish(
            "memory.query",
            {"query": query, "k": limit, "count": len(results)},
        )
        return results

    def _publish(self, topic: str, payload: Dict[str, Any]) -> None:
        """Publish an event on the wired bus (no-op if none is set)."""
        bus = self._event_bus
        if bus is None:
            return
        try:
            from enterprise.platform_kernel import Event

            bus.publish(
                Event.create(
                    topic,
                    source=self.name,
                    payload=payload,
                    priority=EventPriority.NORMAL,
                )
            )
        except Exception as exc:  # pragma: no cover - defensive
            _logger.warning("Failed to publish event %s: %s", topic, exc)
