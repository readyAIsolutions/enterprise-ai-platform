"""hybrid_rag_kg — Agentic RAG + Knowledge Graph Hybrid Retrieval Module.

Grounded in ColeMedin's "Introducing RAG 2.0: Agentic RAG + Knowledge Graphs"
(https://www.youtube.com/watch?v=p0FERNkpyHE).

Exports:
  HybridRagKgModule     — @module-decorated Module subclass
  VectorStore           — In-memory deterministic vector store (TF cosine)
  KnowledgeGraph        — In-memory typed directed graph with temporal edges
  AgenticRouter         — Routes queries to vector/graph/hybrid and fuses results
  RetrievalResult       — Fused hit with provenance
  RELATIONAL_CUES       — Keywords that trigger graph routing

Version: 1.0.0
Python: 3.10+
"""

from __future__ import annotations

import logging
import threading
from typing import Any, List, Optional

from enterprise.platform_kernel import (
    EventBus,
    Event,
    HealthStatus,
    Module,
    module,
)

from .hybrid_rag_kg import (
    AgenticRouter,
    KnowledgeGraph,
    RELATIONAL_CUES,
    RetrievalResult,
    VectorStore,
    tokenize,
)

_logger: logging.Logger = logging.getLogger("enterprise.hybrid_rag_kg")

__version__ = "1.0.0"
__module__ = "hybrid_rag_kg"


@module(name="hybrid_rag_kg", version="1.0.0")
class HybridRagKgModule(Module):
    """Enterprise Hybrid RAG + Knowledge Graph Module.

    Wraps the pure-stdlib hybrid retrieval engine (VectorStore + KnowledgeGraph +
    AgenticRouter) as a registered Platform Kernel module with lifecycle,
    health checks, and event bus integration.

    Events published:
      - hybrid_rag_kg.document_indexed
      - hybrid_rag_kg.entity_added
      - hybrid_rag_kg.relation_added
      - hybrid_rag_kg.query_served
      - hybrid_rag_kg.health.status
    """

    def __init__(self, config: Optional[dict[str, Any]] = None) -> None:
        super().__init__(config)
        self._router: Optional[AgenticRouter] = None
        self._event_bus: Optional[EventBus] = None
        self._lock: threading.RLock = threading.RLock()
        self._router_config: dict[str, Any] = {}

    # ── Lifecycle ────────────────────────────────────────────────────────

    async def initialize(self) -> None:
        """Initialize the Hybrid RAG + KG module."""
        with self._lock:
            self._status = HealthStatus.STARTING
            self._router_config = {
                "default_top_k": self._config.get("default_top_k", 5),
                "max_hops": self._config.get("max_hops", 2),
            }

        try:
            _logger.info(
                "Hybrid RAG + KG module initializing (default_top_k=%s, max_hops=%s)",
                self._router_config["default_top_k"],
                self._router_config["max_hops"],
            )

            # Instantiate the router (which contains VectorStore + KnowledgeGraph)
            self._router = AgenticRouter()

            self._status = HealthStatus.HEALTHY
            _logger.info("Hybrid RAG + KG module initialized successfully")

        except Exception as exc:
            _logger.exception("Failed to initialize Hybrid RAG + KG module: %s", exc)
            self._status = HealthStatus.UNHEALTHY
            raise

    async def health_check(self) -> HealthStatus:
        """Perform a health check on the hybrid retrieval engine."""
        if self._router is None:
            self._status = HealthStatus.UNKNOWN
            return self._status

        try:
            # Quick functional probe: add a chunk, add an entity, run a query
            self._router.vector_store.add_chunk("health:probe", "health check probe chunk")
            self._router.graph.add_entity("health:entity", "probe")
            self._router.graph.add_relation("health:entity", "related_to", "health:entity")
            bundle = self._router.retrieve("health check", top_k=1)
            assert isinstance(bundle, dict)
            assert "strategy" in bundle
            assert "results" in bundle

            self._status = HealthStatus.HEALTHY
            return self._status

        except Exception as exc:
            _logger.exception("Health check failed: %s", exc)
            self._status = HealthStatus.UNHEALTHY
            return self._status

    async def shutdown(self) -> None:
        """Gracefully shut down the hybrid retrieval module."""
        with self._lock:
            self._status = HealthStatus.STOPPING

        _logger.info("Shutting down Hybrid RAG + KG module...")

        try:
            self._router = None
            self._status = HealthStatus.HEALTHY
            _logger.info("Hybrid RAG + KG module shut down successfully")

        except Exception as exc:
            _logger.exception("Error during Hybrid RAG + KG shutdown: %s", exc)
            self._status = HealthStatus.UNHEALTHY
            raise

    # ── Event Bus Wiring ────────────────────────────────────────────────

    def set_event_bus(self, event_bus: EventBus) -> None:
        """Wire the platform EventBus into this module.

        Called by the Platform Kernel after module discovery but
        before initialize(). If an event bus is already active,
        it is replaced gracefully.

        Args:
            event_bus: The platform EventBus instance.
        """
        with self._lock:
            self._event_bus = event_bus

    def _publish(self, topic: str, payload: dict[str, Any]) -> None:
        if self._event_bus is not None:
            self._event_bus.publish(
                Event.create(
                    topic=topic,
                    source=self.name,
                    payload=payload,
                )
            )

    # ── Facade methods ──────────────────────────────────────────────────

    def add_chunk(
        self, chunk_id: str, text: str, metadata: Optional[dict[str, Any]] = None
    ) -> None:
        """Ingest a text chunk into the vector store."""
        assert self._router is not None
        self._router.vector_store.add_chunk(chunk_id, text, metadata)
        self._publish(
            "hybrid_rag_kg.document_indexed",
            {"chunk_id": chunk_id, "metadata": metadata or {}},
        )

    def add_document(
        self, doc_id: str, text: str, chunk_size: int = 500, chunk_overlap: int = 50
    ) -> List[str]:
        """Split a document into overlapping chunks and add them. Returns chunk IDs."""
        assert self._router is not None
        chunk_ids = self._router.vector_store.add_document(
            doc_id, text, chunk_size, chunk_overlap
        )
        self._publish(
            "hybrid_rag_kg.document_indexed",
            {"doc_id": doc_id, "chunk_ids": chunk_ids},
        )
        return chunk_ids

    def add_entity(
        self, id: str, type: str = "", props: Optional[dict[str, Any]] = None
    ) -> None:
        """Add an entity to the knowledge graph."""
        assert self._router is not None
        self._router.graph.add_entity(id, type, props)
        self._publish("hybrid_rag_kg.entity_added", {"id": id, "type": type})

    def add_relation(
        self,
        src: str,
        rel: str,
        dst: str,
        props: Optional[dict[str, Any]] = None,
        valid_at: Optional[str] = None,
    ) -> None:
        """Add a typed directed relation to the knowledge graph with optional temporal validity."""
        assert self._router is not None
        self._router.graph.add_relation(src, rel, dst, props, valid_at)
        self._publish(
            "hybrid_rag_kg.relation_added",
            {"src": src, "rel": rel, "dst": dst, "valid_at": valid_at},
        )

    def classify(self, query: str) -> str:
        """Classify a query into 'vector', 'graph', or 'hybrid'."""
        assert self._router is not None
        return self._router.classify(query)

    def retrieve(self, query: str, top_k: Optional[int] = None) -> dict[str, Any]:
        """Execute the hybrid retrieval pipeline and return a ranked bundle."""
        assert self._router is not None
        k = top_k if top_k is not None else self._router_config.get("default_top_k", 5)
        bundle = self._router.retrieve(query, top_k=k)
        self._publish(
            "hybrid_rag_kg.query_served",
            {
                "query": query,
                "strategy": bundle["strategy"],
                "num_results": len(bundle["results"]),
            },
        )
        return bundle


def create_hybrid_rag_kg_module(
    config: Optional[dict[str, Any]] = None,
) -> HybridRagKgModule:
    """Create a :class:`HybridRagKgModule` from an optional config dict.

    The config may contain:
      - default_top_k (int): default number of results to return
      - max_hops (int): default max hops for graph traversal

    Args:
        config: Optional module configuration dictionary.

    Returns:
        A fully constructed :class:`HybridRagKgModule`.
    """
    cfg = dict(config or {})
    return HybridRagKgModule(
        config={
            "default_top_k": cfg.get("default_top_k", 5),
            "max_hops": cfg.get("max_hops", 2),
        }
    )


__all__ = [
    "__version__",
    "HybridRagKgModule",
    "VectorStore",
    "KnowledgeGraph",
    "AgenticRouter",
    "RetrievalResult",
    "RELATIONAL_CUES",
    "tokenize",
    "create_hybrid_rag_kg_module",
]