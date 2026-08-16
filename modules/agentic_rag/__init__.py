"""Agentic RAG module — agentic RAG + knowledge-graph retrieval engine.

Grounded in the real pulled transcript ``ColeMedin/p0FERNkpyHE.md``
("Introducing RAG 2.0: Agentic RAG + Knowledge Graphs (FREE Template)"). The
talk contrasts inflexible *vanilla RAG* (embed query -> top-K chunks -> feed
fixed context to the LLM) with *agentic RAG*, where an agent reasons about how
it explores the knowledge base: a vector-store lookup for single-entity/fact
questions, a knowledge-graph traversal for relational / multi-hop questions
about two or more entities, or a combination of both. Nodes are entities, edges
are typed relationships (e.g. Amazon --invested_in--> Anthropic --runs_on-->> AWS;
Microsoft --partnered_with--> OpenAI --hosted_on--> Azure).

The engine lives in :mod:`enterprise.modules.agentic_rag.agentic_rag` and is
pure, network-free and deterministic so it can be unit-tested in isolation.

Export surface:
  * AgenticRag      — query planning, multi-hop graph traversal, retrieval,
                      reranking and answer assembly engine.
  * KnowledgeGraph  — entities (nodes) + typed relationships (edges).
  * VectorStore     — in-memory chunk store with lexical-overlap retrieval.
  * Chunk           — a single retrievable document chunk.
  * AgenticRagModule — the ENI platform Module wrapper.
  * create_agentic_rag_module(config) — factory used by the platform.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from enterprise.platform_kernel import HealthStatus, Module, module

from .agentic_rag import (  # noqa: F401
    AgenticRag,
    Chunk,
    KnowledgeGraph,
    VectorStore,
    builtin_bigtech_graph,
    builtin_bigtech_store,
    make_agentic_rag,
)

logger = logging.getLogger("eni.agentic_rag")
__version__ = "1.0.0"


@module(
    name="agentic_rag",
    version="1.0.0",
    config_defaults={
        "max_hops": 3,
        "top_k": 3,
        "builtin_fixtures": True,  # wire the transcript's Big-Tech demo data
    },
)
class AgenticRagModule(Module):
    """ENI platform wrapper around the AgenticRag engine."""

    def __init__(self, config: Optional[dict[str, Any]] = None) -> None:
        super().__init__(config)
        self.engine: Optional[AgenticRag] = None

    async def initialize(self) -> None:
        self.engine = make_agentic_rag()
        self.status = HealthStatus.HEALTHY
        logger.info("agentic_rag module initialized")

    async def health_check(self) -> HealthStatus:
        return (HealthStatus.HEALTHY if self.engine is not None
                else HealthStatus.UNHEALTHY)

    async def shutdown(self) -> None:
        self.engine = None
        self.status = HealthStatus.UNKNOWN

    # ------------------------------------------------------------- facade
    def decompose(self, query: str) -> Dict[str, Any]:
        """Decompose a query into an agentic retrieval plan (entities + steps)."""
        return self.engine.decompose_query(query)

    def answer(self, query: str, top_k: Optional[int] = None) -> Dict[str, Any]:
        """Run the full agentic RAG loop and return the answer plan dict."""
        k = top_k or int(self._config.get("top_k", 3))
        return self.engine.answer(query, top_k=k)

    def traverse(self, start: str, goal: Optional[str] = None,
                 max_hops: Optional[int] = None) -> List[Dict[str, Any]]:
        """Multi-hop knowledge-graph traversal between two entities."""
        hops = max_hops or int(self._config.get("max_hops", 3))
        return self.engine.traverse(start, goal, max_hops=hops)

    def retrieve(self, query: str, k: Optional[int] = None) -> List[Dict[str, Any]]:
        """Retrieve candidate chunks from the vector store."""
        return self.engine.retrieve(query, k=k)

    def rerank(self, query: str, top_k: Optional[int] = None,
               entities: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """Rerank candidate chunks with graph-aware scoring."""
        k = top_k or int(self._config.get("top_k", 3))
        return self.engine.rerank(query, entities=entities, top_k=k)

    def graph_info(self) -> Dict[str, Any]:
        """Summary of the knowledge graph (nodes/edges) backing the engine."""
        g = self.engine.graph
        return {"num_nodes": g.num_nodes, "num_edges": g.num_edges,
                "nodes": sorted(g.node_names)}


def create_agentic_rag_module(config: Optional[dict[str, Any]] = None) -> AgenticRagModule:
    return AgenticRagModule(config=config or {})


__all__ = [
    "AgenticRag",
    "KnowledgeGraph",
    "VectorStore",
    "Chunk",
    "AgenticRagModule",
    "create_agentic_rag_module",
    "make_agentic_rag",
    "builtin_bigtech_graph",
    "builtin_bigtech_store",
    "__version__",
]
