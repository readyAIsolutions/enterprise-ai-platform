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
from .hybrid import (
    AddResult,
    HybridRetriever,
    HybridSemanticMemory,
    keyword_score,
    tokenize,
)

__version__ = "2.0.0"
__module__ = "semantic_memory"

__all__ = [
    "__version__",
    "SemanticMemoryModule",
    # Core classes
    "SemanticMemory",
    "HybridSemanticMemory",
    "HybridRetriever",
    "AddResult",
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
    "keyword_score",
    "tokenize",
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
        db_path (str): Optional SQLite database path for persistence. When
            unset the module runs in-memory. A bare filename (no directory)
            is resolved under ``data/``.

    Events published (when an event bus is wired via ``set_event_bus``):
        - memory.doc.indexed  — a document was added to the index
        - memory.query       — a recall/query was performed
    """

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        super().__init__(config)
        self._memory: SemanticMemory | None = None
        self._event_bus: EventBus | None = None
        self._lock = threading.RLock()
        self._dim: int = int(self._config.get("dim", 256) or 256)
        self._top_k: int = int(self._config.get("top_k", 5) or 5)
        self._db_path: str | None = (self._config.get("db_path") or None)
        if self._db_path is not None:
            self._db_path = str(self._db_path)

    # -- Properties ---------------------------------------------------------

    @property
    def memory(self) -> SemanticMemory | None:
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

    @property
    def db_path(self) -> str | None:
        """Configured SQLite persistence path (None = in-memory)."""
        return self._db_path

    # -- Lifecycle ----------------------------------------------------------

    async def initialize(self) -> None:
        """Build the hybrid SemanticMemory store and its default hash embedder.

        Uses :class:`~.HybridSemanticMemory` (mem0-style change detection +
        hybrid vector/keyword retrieval) with optional SQLite persistence.

        On success the module status becomes :data:`HealthStatus.HEALTHY`;
        on failure it becomes :data:`HealthStatus.UNHEALTHY` and the error is
        re-raised so the platform can react.
        """
        with self._lock:
            self._status = HealthStatus.STARTING

        _logger.info(
            "Semantic memory initializing (dim=%s, top_k=%s, db_path=%s)",
            self._dim,
            self._top_k,
            self._db_path,
        )
        try:
            embedder = HashEmbedder(dim=self._dim)
            self._memory = HybridSemanticMemory(
                embedder=embedder, db_path=self._db_path
            )
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
            mem = self._memory
            self._memory = None
        if mem is not None:
            close = getattr(mem, "close", None)
            if callable(close):
                try:
                    close()
                except Exception:  # pragma: no cover - defensive
                    _logger.warning("Failed to close semantic memory store", exc_info=True)
        with self._lock:
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
        metadata: dict[str, Any] | None = None,
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
        k: int | None = None,
        metadata_filter: dict[str, Any] | None = None,
    ) -> list[ScoredDoc]:
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

    def _publish(self, topic: str, payload: dict[str, Any]) -> None:
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

    # -- Temporal memory + consolidation passthroughs ------------------------

    def recall_since(self, since: Any) -> list[dict[str, Any]]:
        """Pass-through: memories created at/after ``since`` (temporal recall)."""
        if self._memory is None:
            raise RuntimeError("Semantic memory module is not initialized")
        fn = getattr(self._memory, "recall_since")
        if not callable(fn):
            raise AttributeError("memory does not support recall_since")
        return fn(since)

    def group_by_time_bucket(
        self, bucket: str = "day", key: str = "updated_at"
    ) -> dict[str, Any]:
        """Pass-through: group memories into time buckets (Zep temporal recall)."""
        if self._memory is None:
            raise RuntimeError("Semantic memory module is not initialized")
        fn = getattr(self._memory, "group_by_time_bucket")
        if not callable(fn):
            raise AttributeError("memory does not support group_by_time_bucket")
        return fn(bucket, key=key)

    def ranking(self, limit=None, **kwargs) -> list[dict[str, Any]]:
        """Pass-through: rank memories by recency + importance (mem0-style)."""
        if self._memory is None:
            raise RuntimeError("Semantic memory module is not initialized")
        fn = getattr(self._memory, "ranking")
        if not callable(fn):
            raise AttributeError("memory does not support ranking")
        return fn(limit=limit, **kwargs)

    def consolidate(self, max_age=None, min_importance=None, merge_threshold=0.7) -> dict[str, Any]:
        """Pass-through: prune/merge stale + low-importance memories."""
        if self._memory is None:
            raise RuntimeError("Semantic memory module is not initialized")
        fn = getattr(self._memory, "consolidate")
        if not callable(fn):
            raise AttributeError("memory does not support consolidate")
        return fn(max_age=max_age, min_importance=min_importance, merge_threshold=merge_threshold)
