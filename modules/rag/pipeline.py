"""
Unified RAG Pipeline.

Composes the RAG submodules (chunking + embeddings + retrieval + re-ranking +
context assembly + citations) into a single deterministic, stdlib-only
pipeline. Uses the :class:`~embeddings.HashEmbedder` for all vector work so it
runs completely offline with no ML dependencies.

Typical usage::

    pipeline = RAGPipeline(RAGConfig())
    pipeline.index_documents(["The sky is blue on clear days.",
                              "Water freezes at zero degrees Celsius."])
    result = pipeline.query("What color is the sky?")
    print(result.answer)
    print(result.citations)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Sequence, Union

from .chunking import (
    Chunk,
    ChunkingStrategy,
    FixedChunker,
    SemanticChunker,
    create_chunker,
)
from .embeddings import (
    EmbeddingConfig,
    EmbeddingProvider,
    HashEmbedder,
    create_embedder,
)
from .retrieval import (
    RetrievalResult,
    RetrievalStrategy,
    VectorRetriever,
    create_retriever,
)
from .reranking import (
    RerankResult,
    RerankingStrategy,
    create_reranker,
)
from .context_assembly import (
    ContextAssembler,
    ContextResult,
    create_assembler,
)
from .citations import (
    Citation,
    CitationManager,
    CitationStyle,
    create_citation_manager,
)


# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #
@dataclass
class RAGConfig:
    """Configuration for the :class:`RAGPipeline`.

    Attributes:
        chunk_strategy: Chunking strategy (fixed | semantic).
        chunk_size: Target chunk size in characters.
        chunk_overlap: Overlap between chunks.
        min_chunk_size: Minimum chunk size to keep.
        embedding_dimension: Dimension for the hash embedder (small for speed).
        retrieval_strategy: Retrieval strategy (vector | keyword | hybrid).
        top_k: Number of results pulled from retrieval.
        rerank_strategy: Re-ranking strategy (none | gradual | incremental).
        assembler_strategy: Context assembly strategy
            (concatenate | summarization | cross_document).
        citation_style: Default citation style for the pipeline.
        include_scores: Whether to prefix chunks with scores in the context.
    """

    chunk_strategy: Union[ChunkingStrategy, str] = ChunkingStrategy.FIXED
    chunk_size: int = 200
    chunk_overlap: int = 20
    min_chunk_size: int = 1
    embedding_dimension: int = 8
    retrieval_strategy: Union[RetrievalStrategy, str] = RetrievalStrategy.VECTOR
    top_k: int = 2
    rerank_strategy: Union[RerankingStrategy, str] = RerankingStrategy.NONE
    assembler_strategy: Union[str, "Any"] = "concatenate"
    citation_style: Union[CitationStyle, str] = CitationStyle.APA
    include_scores: bool = False


# --------------------------------------------------------------------------- #
# Result dataclass
# --------------------------------------------------------------------------- #
@dataclass
class PipelineResult:
    """The output of a single pipeline query."""

    query: str
    context: str
    answer: str
    retrieval_results: List[RetrievalResult] = field(default_factory=list)
    rerank_results: List[RerankResult] = field(default_factory=list)
    context_result: Optional[ContextResult] = None
    citations: List[Citation] = field(default_factory=list)
    sources: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def char_count(self) -> int:
        return len(self.context)

    @property
    def token_estimate(self) -> int:
        return max(1, len(self.context) // 4)


# --------------------------------------------------------------------------- #
# Pipeline
# --------------------------------------------------------------------------- #
class RAGPipeline:
    """End-to-end retrieval-augmented generation pipeline.

    Compose the submodules once in the constructor, then call
    :meth:`index_documents` to load the corpus and :meth:`query` to answer.
    """

    def __init__(self, config: Optional[RAGConfig] = None) -> None:
        self.config = config or RAGConfig()
        self.chunker = self._build_chunker()
        self.embedder = self._build_embedder()
        self.retriever = self._build_retriever()
        self.reranker = self._build_reranker()
        self.assembler = self._build_assembler()
        self.citation_manager: CitationManager = create_citation_manager(
            style=self.config.citation_style
        )
        self._next_doc_id = 0

    # -- component construction ------------------------------------------ #
    @staticmethod
    def _enum_value(value: Any) -> Any:
        """Return the raw value of a strategy (handles str-mixin Enums)."""
        if isinstance(value, Enum):
            return value.value
        return value

    def _build_chunker(self):
        strategy = self._enum_value(self.config.chunk_strategy)
        if isinstance(strategy, str):
            strategy = ChunkingStrategy(str(strategy).lower())
        if strategy == ChunkingStrategy.FIXED:
            return FixedChunker(
                chunk_size=self.config.chunk_size,
                chunk_overlap=self.config.chunk_overlap,
                min_chunk_size=self.config.min_chunk_size,
            )
        if strategy == ChunkingStrategy.SEMANTIC:
            return SemanticChunker(
                chunk_size=self.config.chunk_size,
                chunk_overlap=self.config.chunk_overlap,
                min_chunk_size=self.config.min_chunk_size,
                embedder=self.embedder,
            )
        raise ValueError(f"Unknown chunking strategy: {self.config.chunk_strategy}")

    def _build_embedder(self) -> HashEmbedder:
        cfg = EmbeddingConfig(
            provider=EmbeddingProvider.HASH,
            dimension=self.config.embedding_dimension,
        )
        return create_embedder(cfg)  # type: ignore[return-value]

    def _build_retriever(self):
        return create_retriever(
            self._enum_value(self.config.retrieval_strategy),
            embedder=self.embedder,
        )

    def _build_reranker(self):
        return create_reranker(self._enum_value(self.config.rerank_strategy))

    def _build_assembler(self) -> ContextAssembler:
        return create_assembler(self._enum_value(self.config.assembler_strategy))

    # -- ingestion --------------------------------------------------------- #
    def index_documents(
        self,
        documents: Sequence[Union[str, Chunk]],
    ) -> int:
        """Chunk and index a set of documents or pre-chunked Chunks.

        Args:
            documents: Either raw text strings (which will be chunked with a
                per-document ``source`` metadata assigned) or existing
                :class:`~chunking.Chunk` objects.

        Returns:
            The number of chunks indexed.
        """
        chunks: List[Chunk] = []
        for doc in documents:
            if isinstance(doc, Chunk):
                chunks.append(doc)
                continue
            doc_id = f"doc_{self._next_doc_id}"
            self._next_doc_id += 1
            parts = self.chunker.chunk(doc, metadata={"source": doc_id})
            chunks.extend(parts)

        self.retriever.add_documents(chunks)
        return len(chunks)

    def index_text(self, text: str, source: str) -> int:
        """Index a single text under a named source."""
        chunks = self.chunker.chunk(text, metadata={"source": source})
        self.retriever.add_documents(chunks)
        return len(chunks)

    # -- query ------------------------------------------------------------ #
    def query(self, question: str, k: Optional[int] = None) -> PipelineResult:
        """Run the full RAG pipeline for a question.

        Args:
            question: The user query.
            k: Optional override for the number of results to consider.

        Returns:
            A :class:`PipelineResult` with the assembled context, citations and
            the raw retrieval/re-ranking evidence.
        """
        top_k = k if k is not None else self.config.top_k

        retrieved = self.retriever.retrieve(question, k=top_k)
        reranked = self.reranker.rerank(retrieved, question)
        context_result = self.assembler.assemble(retrieved, question)
        citations = self._build_citations(retrieved, context_result.sources)

        # Register citations (de-duplicated by the manager).
        self.citation_manager.add_many(citations)

        source_ids = [c.source_id for c in citations]
        answer = self._compose_answer(question, context_result, source_ids)

        return PipelineResult(
            query=question,
            context=context_result.context,
            answer=answer,
            retrieval_results=retrieved,
            rerank_results=reranked,
            context_result=context_result,
            citations=citations,
            sources=context_result.sources,
            metadata={
                "retrieved": len(retrieved),
                "reranked": len(reranked),
                "citation_style": self.config.citation_style.value
                if isinstance(self.config.citation_style, CitationStyle)
                else str(self.config.citation_style),
            },
        )

    def _build_citations(
        self,
        results: Sequence[RetrievalResult],
        sources: Sequence[str],
    ) -> List[Citation]:
        citations: List[Citation] = []
        seen: set[str] = set()
        for r in results:
            src = r.chunk.metadata.get("source") or r.chunk.id
            if src in seen or (sources and src not in set(sources)):
                continue
            seen.add(src)
            citations.append(
                Citation(
                    source_id=str(src),
                    title=r.chunk.metadata.get("title", f"Source {src}"),
                    author=r.chunk.metadata.get("author", "Unknown"),
                    year=str(r.chunk.metadata.get("year", "")),
                    publisher=r.chunk.metadata.get("publisher", ""),
                    url=r.chunk.metadata.get("url", ""),
                    page=r.chunk.metadata.get("page", ""),
                    metadata={"chunk_id": r.chunk.id, "score": r.score},
                )
            )
        return citations

    def _compose_answer(
        self,
        question: str,
        context_result: ContextResult,
        source_ids: Sequence[str],
    ) -> str:
        style = self.config.citation_style
        inline = self.citation_manager.format(style=style)
        lines = [
            f"Question: {question}",
            "",
            "Based on the retrieved evidence:",
            context_result.context,
        ]
        if inline:
            lines.extend(["", "References:", inline])
        return "\n".join(lines)

    def formatted_citations(self) -> str:
        """Return the reference list in the configured style."""
        return self.citation_manager.format()


__all__ = ["RAGPipeline", "RAGConfig", "PipelineResult"]
