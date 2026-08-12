"""
Context Assembly for the RAG System.

Transforms raw retrieval results into a coherent context block that can be fed
to an LLM (or used directly). Provides three strategies:

- Concatenation (default): joins the retrieved chunk texts in rank order.
- Summarization: produce a compact, extractive summary of the evidence while
  retaining the most informative sentences from the top chunks.
- Cross-Document Fusion: de-duplicates overlapping content across multiple
  source documents and groups evidence by origin so the final context is
  non-redundant.

All implementations are stdlib-only and deterministic.
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Sequence

from .retrieval import RetrievalResult


# --------------------------------------------------------------------------- #
# Strategy enum + result dataclass
# --------------------------------------------------------------------------- #
class AssemblyStrategy(str, Enum):
    """Available context assembly strategies."""

    CONCATENATE = "concatenate"
    SUMMARIZATION = "summarization"
    CROSS_DOCUMENT = "cross_document"


@dataclass
class ContextResult:
    """The output of a context assembler.

    Attributes:
        context: The assembled context text ready for an LLM.
        chunks: The ordered chunks that contributed to the context.
        sources: Unique source document identifiers referenced by the context.
        strategy: The assembly strategy used.
        metadata: Assembler-specific metadata.
    """

    context: str
    chunks: List["Any"] = field(default_factory=list)
    sources: List[str] = field(default_factory=list)
    strategy: str = "concatenate"
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def char_count(self) -> int:
        """Number of characters in the assembled context."""
        return len(self.context)

    @property
    def token_estimate(self) -> int:
        """Rough token estimate (4 chars per token)."""
        return max(1, len(self.context) // 4)


# --------------------------------------------------------------------------- #
# Base assembler
# --------------------------------------------------------------------------- #
class ContextAssembler(ABC):
    """Abstract base class for all context assemblers."""

    strategy: str = "concatenate"

    @abstractmethod
    def assemble(
        self,
        results: Sequence[RetrievalResult],
        query: str = "",
        **kwargs: Any,
    ) -> ContextResult:
        """Assemble a context block from retrieval results.

        Args:
            results: Ordered retrieval results (highest score first).
            query: The original user query (used by some strategies).
            **kwargs: Strategy-specific options.

        Returns:
            A :class:`ContextResult` with the assembled context.
        """

    # -- helpers shared by subclasses ------------------------------------ #
    @staticmethod
    def _extract_sources(results: Sequence[RetrievalResult]) -> List[str]:
        """Collect unique source ids from a list of retrieval results."""
        sources: List[str] = []
        seen: set[str] = set()
        for r in results:
            src = r.chunk.metadata.get("source") or r.chunk.metadata.get("doc_id")
            if not src:
                src = r.chunk.id
            if src not in seen:
                seen.add(src)
                sources.append(str(src))
        return sources


class ConcatenateAssembler(ContextAssembler):
    """Assemble context by concatenating chunk texts in rank order."""

    strategy: str = "concatenate"

    def __init__(
        self,
        separator: str = "\n\n",
        max_chars: Optional[int] = None,
        include_scores: bool = False,
    ) -> None:
        self.separator = separator
        self.max_chars = max_chars
        self.include_scores = include_scores

    def assemble(
        self,
        results: Sequence[RetrievalResult],
        query: str = "",
        **kwargs: Any,
    ) -> ContextResult:
        parts: List[str] = []
        used: List[RetrievalResult] = []
        for r in results:
            piece = r.chunk.text.strip()
            if self.include_scores:
                piece = f"[{r.score:.3f}] {piece}"
            if self.max_chars is not None and self.max_chars > 0:
                budget = self.max_chars - sum(len(p) + len(self.separator) for p in parts)
                if budget <= 0:
                    break
                if len(piece) > budget:
                    piece = piece[:budget]
                    parts.append(piece)
                    used.append(r)
                    break
            parts.append(piece)
            used.append(r)
        context = self.separator.join(parts)
        return ContextResult(
            context=context,
            chunks=[r.chunk for r in used],
            sources=self._extract_sources(used),
            strategy=self.strategy,
            metadata={"separator": self.separator},
        )


# --------------------------------------------------------------------------- #
# Summarization assembler
# --------------------------------------------------------------------------- #
class SummarizationAssembler(ContextAssembler):
    """Produce a compact extractive summary from the retrieved evidence.

    Uses a lightweight, deterministic extractive approach: the most salient
    sentences are selected based on term frequency relative to the query and
    their position. No external NLP libraries are required.
    """

    strategy: str = "summarization"

    _SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")

    def __init__(
        self,
        max_sentences: int = 6,
        min_chars_per_sentence: int = 20,
        include_raw: bool = False,
    ) -> None:
        self.max_sentences = max_sentences
        self.min_chars_per_sentence = min_chars_per_sentence
        self.include_raw = include_raw

    @staticmethod
    def _tokenize(text: str) -> List[str]:
        return [w for w in re.split(r"[^a-zA-Z0-9]+", text.lower()) if w]

    def _scoring_terms(self, query: str) -> set[str]:
        """Query terms that give a relevance boost to sentences."""
        return set(self._tokenize(query))

    def _score_sentence(self, sentence: str, boost_terms: set[str]) -> float:
        words = self._tokenize(sentence)
        if not words:
            return 0.0
        query_hits = sum(1 for w in words if w in boost_terms)
        # Slightly prefer sentence length to avoid trivial shards.
        return float(query_hits) + (min(len(words), 12) / 100.0)

    def _extract_sentences(self, text: str) -> List[str]:
        text = text.strip()
        if not text:
            return []
        return [s.strip() for s in self._SENTENCE_SPLIT.split(text) if s.strip()]

    def assemble(
        self,
        results: Sequence[RetrievalResult],
        query: str = "",
        **kwargs: Any,
    ) -> ContextResult:
        max_sentences = int(kwargs.get("max_sentences", self.max_sentences))
        include_raw = bool(kwargs.get("include_raw", self.include_raw))
        boost_terms = self._scoring_terms(query)

        candidates: List[Dict[str, Any]] = []
        raw_parts: List[str] = []
        for r in results:
            raw_parts.append(r.chunk.text.strip())
            source = r.chunk.metadata.get("source") or r.chunk.id
            for sentence in self._extract_sentences(r.chunk.text):
                if len(sentence) < self.min_chars_per_sentence:
                    continue
                candidates.append(
                    {
                        "text": sentence,
                        "score": self._score_sentence(sentence, boost_terms),
                        "source": str(source),
                        "rank": r.score,
                    }
                )

        # Deterministic: sort by (sentence relevance desc, original rank desc).
        candidates.sort(key=lambda c: (-c["score"], -c["rank"]))
        summary_parts: List[str] = []
        used_sources: List[str] = []
        for c in candidates[:max_sentences]:
            summary_parts.append(c["text"])
            if c["source"] not in used_sources:
                used_sources.append(c["source"])

        summary = " ".join(summary_parts)
        if include_raw:
            context = f"{summary}{chr(10)}{chr(10)}**Raw evidence:**{chr(10)}" + "\n\n".join(raw_parts)
        else:
            context = summary

        return ContextResult(
            context=context,
            chunks=[r.chunk for r in results],
            sources=used_sources or self._extract_sources(results),
            strategy=self.strategy,
            metadata={
                "summary_sentences": len(summary_parts),
                "candidate_sentences": len(candidates),
                "include_raw": include_raw,
            },
        )


# --------------------------------------------------------------------------- #
# Cross-document fusion assembler
# --------------------------------------------------------------------------- #
class CrossDocumentFusionAssembler(ContextAssembler):
    """Fuse evidence across documents, de-duplicating overlapping content.

    Identifies near-duplicate chunks from different documents (e.g. the same
    fact restated across sources) and keeps only the highest-scoring
    representative, so the final context is non-redundant.
    """

    strategy: str = "cross_document"

    def __init__(
        self,
        separator: str = "\n\n",
        similarity_threshold: float = 0.9,
    ) -> None:
        self.separator = separator
        self.similarity_threshold = similarity_threshold

    @staticmethod
    def _norm(text: str) -> str:
        return re.sub(r"[^a-z0-9 ]+", " ", text.lower()).strip()

    @staticmethod
    def _jaccard(a: str, b: str) -> float:
        """Jaccard similarity between two normalized texts."""
        sa = set(a.split())
        sb = set(b.split())
        if not sa and not sb:
            return 1.0
        union = sa | sb
        if not union:
            return 0.0
        return len(sa & sb) / len(union)

    def assemble(
        self,
        results: Sequence[RetrievalResult],
        query: str = "",
        **kwargs: Any,
    ) -> ContextResult:
        threshold = float(kwargs.get("similarity_threshold", self.similarity_threshold))

        kept: List[RetrievalResult] = []
        kept_norms: List[tuple[str, str]] = []  # (norm_text, source)

        for r in results:
            norm = self._norm(r.chunk.text)
            if not norm:
                continue
            duplicate = False
            for (existing_norm, existing_src) in kept_norms:
                if existing_src == r.chunk.metadata.get("source"):
                    # Same document: always keep (may be distinct facts).
                    continue
                if self._jaccard(norm, existing_norm) >= threshold:
                    duplicate = True
                    break
            if not duplicate:
                kept.append(r)
                kept_norms.append((norm, str(r.chunk.metadata.get("source") or r.chunk.id)))

        context = self.separator.join(r.chunk.text.strip() for r in kept)
        return ContextResult(
            context=context,
            chunks=[r.chunk for r in kept],
            sources=self._extract_sources(kept),
            strategy=self.strategy,
            metadata={
                "input_results": len(results),
                "kept_results": len(kept),
                "removed_duplicates": len(results) - len(kept),
                "threshold": threshold,
            },
        )


# --------------------------------------------------------------------------- #
# Factory
# --------------------------------------------------------------------------- #
def create_assembler(
    strategy: AssemblyStrategy | str = AssemblyStrategy.CONCATENATE,
    **kwargs: Any,
) -> ContextAssembler:
    """Create a context assembler by strategy name.

    Args:
        strategy: An :class:`AssemblyStrategy` value or a string such as
            ``"concatenate"``, ``"summarization"``, ``"cross_document"``.
        **kwargs: Strategy-specific constructor options.

    Raises:
        ValueError: If the strategy is unknown.
    """
    if not isinstance(strategy, AssemblyStrategy):
        try:
            strategy = AssemblyStrategy(str(strategy).lower())
        except ValueError as exc:
            raise ValueError(f"Unknown assembly strategy: {strategy}") from exc

    if strategy == AssemblyStrategy.CONCATENATE:
        return ConcatenateAssembler(**kwargs)
    if strategy == AssemblyStrategy.SUMMARIZATION:
        return SummarizationAssembler(**kwargs)
    if strategy == AssemblyStrategy.CROSS_DOCUMENT:
        return CrossDocumentFusionAssembler(**kwargs)
    raise ValueError(f"Unknown assembly strategy: {strategy}")


__all__ = [
    "AssemblyStrategy",
    "ContextAssembler",
    "ConcatenateAssembler",
    "SummarizationAssembler",
    "CrossDocumentFusionAssembler",
    "ContextResult",
    "create_assembler",
]
