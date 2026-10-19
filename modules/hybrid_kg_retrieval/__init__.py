"""hybrid_kg_retrieval — an agentic RAG 2.0 retrieval engine that combines a
vector/semantic index with an in-memory knowledge graph, routing each query to
vector, graph, or BOTH strategies and fusing the results with provenance.

Grounded in ColeMedin's "Introducing RAG 2.0: Agentic RAG + Knowledge Graphs"
(https://www.youtube.com/watch?v=p0FERNkpyHE).

This module is distinct from `agentic_rag` and `knowledge_graph`: its facade is
focused on the HYBRID combination + agentic per-query routing + rank fusion,
computed locally with pure stdlib (no network, no embeddings, no LLM calls).
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from enterprise.platform_kernel import Event, HealthStatus, Module, module

from .core import (  # noqa: F401
    RELATIONAL_CUES,
    HybridRetriever,
    KnowledgeGraph,
    RetrievalResult,
    VectorIndex,
    tokenize,
)

logger = logging.getLogger("eni.hybrid_kg_retrieval_module")
__version__ = "1.0.0"


def create_hybrid_retriever(config: Optional[Dict[str, Any]] = None) -> HybridRetriever:
    """Facade: construct and return a fresh HybridRetriever."""
    _ = config or {}
    return HybridRetriever()


@module(
    name="hybrid_kg_retrieval",
    version="1.0.0",
    config_defaults={"default_top_k": 5, "max_hops": 2},
)
class HybridKgRetrievalModule(Module):
    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(config)
        self.retriever: Optional[HybridRetriever] = None
        self._event_bus = None

    async def initialize(self) -> None:
        try:
            self.retriever = create_hybrid_retriever(self.config)
            self._status = HealthStatus.HEALTHY
        except Exception:  # pragma: no cover - defensive
            self._status = HealthStatus.UNHEALTHY
            raise

    async def health_check(self) -> HealthStatus:
        return self._status

    async def shutdown(self) -> None:
        self._status = HealthStatus.STOPPING

    def set_event_bus(self, event_bus: Any) -> None:
        """Attach the platform event bus; events are only emitted when present."""
        self._event_bus = event_bus

    def _publish(self, topic: str, payload: Dict[str, Any]) -> None:
        if self._event_bus is not None:
            self._event_bus.publish(
                Event.create(topic=topic, source=self.name, payload=payload)
            )

    # ── facade methods ──────────────────────────────────────────────────────
    def index_document(self, doc_id: str, text: str) -> None:
        self.retriever.vector_index.add_document(doc_id, text)
        self._publish("hybrid_kg_retrieval.document_indexed", {"doc_id": doc_id})

    def add_entity(self, id: str, type: str = "", props: Optional[Dict[str, Any]] = None) -> None:
        self.retriever.graph.add_entity(id, type, props)
        self._publish("hybrid_kg_retrieval.entity_added", {"id": id, "type": type})

    def add_relation(self, src: str, rel: str, dst: str) -> None:
        self.retriever.graph.add_relation(src, rel, dst)
        self._publish(
            "hybrid_kg_retrieval.relation_added",
            {"src": src, "rel": rel, "dst": dst},
        )

    def classify(self, query: str) -> str:
        return self.retriever.classify(query)

    def retrieve(self, query: str, top_k: Optional[int] = None) -> Dict[str, Any]:
        k = top_k if top_k is not None else self.config.get("default_top_k", 5)
        bundle = self.retriever.retrieve(query, top_k=k)
        self._publish(
            "hybrid_kg_retrieval.query_served",
            {
                "query": query,
                "strategy": bundle["strategy"],
                "num_results": len(bundle["results"]),
            },
        )
        return bundle


def create_hybrid_kg_retrieval_module(
    config: Optional[Dict[str, Any]] = None,
) -> HybridKgRetrievalModule:
    return HybridKgRetrievalModule(config=config or {})


__all__ = [
    "HybridKgRetrievalModule",
    "HybridRetriever",
    "KnowledgeGraph",
    "RELATIONAL_CUES",
    "RetrievalResult",
    "VectorIndex",
    "create_hybrid_kg_retrieval_module",
    "create_hybrid_retriever",
    "tokenize",
    "__version__",
]
