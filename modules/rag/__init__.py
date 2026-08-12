"""
Production RAG System — Enterprise-grade Retrieval-Augmented Generation.

This module provides a complete, production-ready RAG system with:
1. Chunking Strategies (Semantic + Fixed)
2. Embedding Model Selection (Pre-trained + Custom)
3. Retrieval (Vector + Keyword + Hybrid)
4. Re-Ranking (Gradual + Incremental)
5. Context Assembly (Summarization + Cross-Document Fusion)
6. Citation Handling (Research Integrity)

All components are designed to work independently or as a unified pipeline,
with full integration into the ENI Enterprise Platform (kb_bridge, memory,
semantic_memory, compression_bridge, eval_gate, agent_core).
"""

from __future__ import annotations

import logging
from typing import Any

__version__ = "1.0.0"
__author__ = "ENI Enterprise Platform"

# Event-bus types used by the module-level hook below.
from enterprise.platform_kernel import Event, EventBus  # noqa: E402

# Core components
from .chunking import (
    ChunkingStrategy,
    FixedChunker,
    SemanticChunker,
    Chunk,
    create_chunker,
)
from .embeddings import (
    EmbeddingProvider,
    PretrainedEmbedder,
    CustomEmbedder,
    EmbeddingConfig,
    create_embedder,
)
from .retrieval import (
    RetrievalStrategy,
    VectorRetriever,
    KeywordRetriever,
    HybridRetriever,
    RetrievalResult,
    create_retriever,
)
from .reranking import (
    RerankingStrategy,
    GradualReranker,
    IncrementalReranker,
    RerankResult,
    create_reranker,
)
# Context Assembly
from .context_assembly import (
    ContextAssembler,
    SummarizationAssembler,
    CrossDocumentFusionAssembler,
    ContextResult,
    create_assembler,
)

# Citations
from .citations import (
    CitationManager,
    CitationStyle,
    Citation,
    create_citation_manager,
)

# Unified pipeline
from .pipeline import (
    RAGPipeline,
    RAGConfig,
    PipelineResult,
)

# Platform Kernel module registration (auto-registers via @module on import)
from .module import RAGModule, create_rag_module

# --------------------------------------------------------------------------- #
# Module-level event-bus hook
# --------------------------------------------------------------------------- #
# A lightweight, optional hook so the RAG module can publish events on the
# platform EventBus without forcing a circular import. The kernel wires this at
# startup via set_event_bus() on the RAGModule; the module-level emit() below is
# a convenience for components that only have access to the ``rag`` package.
_ACTIVE_EVENT_BUS: "EventBus | None" = None


def set_event_bus(event_bus: "EventBus") -> None:
    """Set the module-level event bus used by :func:`emit`."""
    global _ACTIVE_EVENT_BUS
    _ACTIVE_EVENT_BUS = event_bus


def _emit(topic: str, payload: dict[str, Any]) -> None:
    """Publish an event on the module-level event bus (no-op if unset)."""
    bus = _ACTIVE_EVENT_BUS
    if bus is None:
        return
    try:
        bus.publish(Event.create(topic=topic, source=_RAG_SOURCE, payload=payload))
    except Exception:  # noqa: BLE001 - best-effort event publishing
        _logger.exception("RAG module failed to publish event %s", topic)


_RAG_SOURCE = "rag"
_logger = logging.getLogger("eni.rag")

__all__ = [
    # Chunking
    "ChunkingStrategy",
    "FixedChunker",
    "SemanticChunker",
    "Chunk",
    "create_chunker",
    # Embeddings
    "EmbeddingProvider",
    "PretrainedEmbedder",
    "CustomEmbedder",
    "EmbeddingConfig",
    "create_embedder",
    # Retrieval
    "RetrievalStrategy",
    "VectorRetriever",
    "KeywordRetriever",
    "HybridRetriever",
    "RetrievalResult",
    "create_retriever",
    # Re-ranking
    "RerankingStrategy",
    "GradualReranker",
    "IncrementalReranker",
    "RerankResult",
    "create_reranker",
    # Context Assembly
    "ContextAssembler",
    "SummarizationAssembler",
    "CrossDocumentFusionAssembler",
    "ContextResult",
    "create_assembler",
    # Citations
    "CitationManager",
    "CitationStyle",
    "Citation",
    "create_citation_manager",
    # Pipeline
    "RAGPipeline",
    "RAGConfig",
    "PipelineResult",
    # Kernel module registration
    "RAGModule",
    "create_rag_module",
]