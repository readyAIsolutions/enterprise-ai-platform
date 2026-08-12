"""
Retrieval Strategies for RAG System.

Provides three retrieval approaches:
- Vector Retrieval: Semantic similarity via embeddings
- Keyword Retrieval: Exact term matching (BM25/TF-IDF)
- Hybrid Retrieval: Combines both with configurable weighting

All implement a common RetrievalStrategy interface.
"""

from __future__ import annotations

import math
import re
from abc import ABC, abstractmethod
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from .chunking import Chunk
from .embeddings import BaseEmbedder, EmbeddingConfig, create_embedder, EmbeddingProvider


class RetrievalStrategy(str, Enum):
    """Available retrieval strategies."""
    VECTOR = "vector"
    KEYWORD = "keyword"
    HYBRID = "hybrid"


@dataclass
class RetrievalResult:
    """A single retrieval result with score and metadata."""
    chunk: Chunk
    score: float
    strategy: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def __lt__(self, other: "RetrievalResult") -> bool:
        return self.score > other.score  # Higher score first


class BaseRetriever(ABC):
    """Abstract base class for all retrievers."""
    
    def __init__(self, embedder: Optional[BaseEmbedder] = None):
        self.embedder = embedder
        self._documents: List[Chunk] = []
        self._doc_embeddings: List[List[float]] = []
    
    @abstractmethod
    def add_documents(self, documents: List[Chunk]) -> None:
        """Add documents to the retriever."""
        pass
    
    @abstractmethod
    def retrieve(
        self,
        query: str,
        k: int = 10,
        filter_metadata: Optional[Dict[str, Any]] = None,
    ) -> List[RetrievalResult]:
        """Retrieve top-k documents for query."""
        pass
    
    def clear(self) -> None:
        """Clear all documents."""
        self._documents = []
        self._doc_embeddings = []


class VectorRetriever(BaseRetriever):
    """
    Vector-based semantic retrieval using embeddings.
    
    Uses cosine similarity between query embedding and document embeddings.
    Best for semantic search, concept matching, and exploratory queries.
    """
    
    def __init__(
        self,
        embedder: Optional[BaseEmbedder] = None,
        embedding_config: Optional[EmbeddingConfig] = None,
    ):
        if embedder is None and embedding_config is None:
            embedding_config = EmbeddingConfig(provider=EmbeddingProvider.HASH)
        
        self.embedder = embedder or create_embedder(embedding_config)
        super().__init__(self.embedder)
    
    def add_documents(self, documents: List[Chunk]) -> None:
        """Add documents and compute embeddings."""
        self._documents = documents
        texts = [doc.text for doc in documents]
        self._doc_embeddings = self.embedder.embed(texts)
    
    def retrieve(
        self,
        query: str,
        k: int = 10,
        filter_metadata: Optional[Dict[str, Any]] = None,
    ) -> List[RetrievalResult]:
        """Retrieve using vector similarity."""
        if not self._documents:
            return []
        
        query_embedding = self.embedder.embed_single(query)
        
        # Compute similarities
        results = []
        for i, (doc, doc_emb) in enumerate(zip(self._documents, self._doc_embeddings)):
            # Apply metadata filter
            if filter_metadata:
                match = all(
                    doc.metadata.get(key) == value
                    for key, value in filter_metadata.items()
                )
                if not match:
                    continue
            
            score = self.embedder.similarity(query_embedding, doc_emb)
            results.append(RetrievalResult(
                chunk=doc,
                score=score,
                strategy="vector",
                metadata={"vector_score": score},
            ))
        
        # Sort by score descending
        results.sort()
        return results[:k]


class KeywordRetriever(BaseRetriever):
    """
    Keyword-based retrieval using BM25-style scoring.
    
    Uses term frequency and inverse document frequency for exact matching.
    Fast, interpretable, good for exact term lookup and structured queries.
    """
    
    def __init__(
        self,
        k1: float = 1.5,
        b: float = 0.75,
        tokenizer: Optional[callable] = None,
    ):
        """
        Initialize keyword retriever.
        
        Args:
            k1: BM25 term frequency saturation parameter
            b: BM25 document length normalization parameter
            tokenizer: Custom tokenizer function (text -> List[str])
        """
        super().__init__(None)
        self.k1 = k1
        self.b = b
        self.tokenizer = tokenizer or self._default_tokenizer
        self._doc_tokens: List[List[str]] = []
        self._doc_freqs: Dict[str, int] = defaultdict(int)
        self._avg_doc_len: float = 0.0
    
    def _default_tokenizer(self, text: str) -> List[str]:
        """Simple word tokenizer."""
        # Split on non-alphanumeric, lowercase
        return re.findall(r'\b\w+\b', text.lower())
    
    def add_documents(self, documents: List[Chunk]) -> None:
        """Add documents and build BM25 index."""
        self._documents = documents
        self._doc_tokens = []
        self._doc_freqs = defaultdict(int)
        total_len = 0
        
        # Tokenize all documents
        doc_term_sets: List[Set[str]] = []
        for doc in documents:
            tokens = self.tokenizer(doc.text)
            self._doc_tokens.append(tokens)
            total_len += len(tokens)
            doc_term_sets.append(set(tokens))
        
        # Compute document frequencies
        for term_set in doc_term_sets:
            for term in term_set:
                self._doc_freqs[term] += 1
        
        self._avg_doc_len = total_len / len(documents) if documents else 0.0
    
    def _bm25_score(self, query_tokens: List[str], doc_tokens: List[str]) -> float:
        """Compute BM25 score for query against document."""
        if not doc_tokens:
            return 0.0
        
        doc_len = len(doc_tokens)
        doc_counter = Counter(doc_tokens)
        score = 0.0
        num_docs = len(self._documents)
        
        for term in query_tokens:
            if term not in self._doc_freqs:
                continue
            
            # IDF
            df = self._doc_freqs[term]
            idf = math.log((num_docs - df + 0.5) / (df + 0.5) + 1.0)
            
            # TF
            tf = doc_counter.get(term, 0)
            numerator = tf * (self.k1 + 1)
            denominator = tf + self.k1 * (1 - self.b + self.b * doc_len / self._avg_doc_len)
            
            score += idf * (numerator / denominator)
        
        return score
    
    def retrieve(
        self,
        query: str,
        k: int = 10,
        filter_metadata: Optional[Dict[str, Any]] = None,
    ) -> List[RetrievalResult]:
        """Retrieve using BM25 keyword matching."""
        if not self._documents:
            return []
        
        query_tokens = self.tokenizer(query)
        
        results = []
        for i, (doc, doc_tokens) in enumerate(zip(self._documents, self._doc_tokens)):
            # Apply metadata filter
            if filter_metadata:
                match = all(
                    doc.metadata.get(key) == value
                    for key, value in filter_metadata.items()
                )
                if not match:
                    continue
            
            score = self._bm25_score(query_tokens, doc_tokens)
            results.append(RetrievalResult(
                chunk=doc,
                score=score,
                strategy="keyword",
                metadata={"bm25_score": score, "matched_terms": query_tokens},
            ))
        
        results.sort()
        return results[:k]


class HybridRetriever(BaseRetriever):
    """
    Hybrid retrieval combining vector and keyword search.
    
    Runs both retrievers and merges results with configurable weights.
    Best of both worlds: semantic understanding + exact matching.
    """
    
    def __init__(
        self,
        vector_weight: float = 0.7,
        keyword_weight: float = 0.3,
        vector_embedder: Optional[BaseEmbedder] = None,
        vector_config: Optional[EmbeddingConfig] = None,
        keyword_k1: float = 1.5,
        keyword_b: float = 0.75,
        fusion_method: str = "rrf",  # rrf (reciprocal rank fusion) or weighted
        rrf_k: int = 60,
    ):
        """
        Initialize hybrid retriever.
        
        Args:
            vector_weight: Weight for vector scores (0-1)
            keyword_weight: Weight for keyword scores (0-1)
            vector_embedder: Pre-configured vector embedder
            vector_config: EmbeddingConfig for vector embedder
            keyword_k1: BM25 k1 parameter
            keyword_b: BM25 b parameter
            fusion_method: "rrf" or "weighted"
            rrf_k: RRF constant
        """
        super().__init__(None)
        
        self.vector_weight = vector_weight
        self.keyword_weight = keyword_weight
        self.fusion_method = fusion_method
        self.rrf_k = rrf_k
        
        # Initialize sub-retrievers
        self.vector_retriever = VectorRetriever(
            embedder=vector_embedder,
            embedding_config=vector_config,
        )
        self.keyword_retriever = KeywordRetriever(
            k1=keyword_k1,
            b=keyword_b,
        )
    
    def add_documents(self, documents: List[Chunk]) -> None:
        """Add documents to both retrievers."""
        self.vector_retriever.add_documents(documents)
        self.keyword_retriever.add_documents(documents)
        self._documents = documents
    
    def retrieve(
        self,
        query: str,
        k: int = 10,
        filter_metadata: Optional[Dict[str, Any]] = None,
    ) -> List[RetrievalResult]:
        """Retrieve using hybrid approach."""
        # Get results from both retrievers (fetch more for better fusion)
        fetch_k = max(k * 3, 30)
        
        vector_results = self.vector_retriever.retrieve(query, fetch_k, filter_metadata)
        keyword_results = self.keyword_retriever.retrieve(query, fetch_k, filter_metadata)
        
        if self.fusion_method == "rrf":
            return self._reciprocal_rank_fusion(vector_results, keyword_results, k)
        else:
            return self._weighted_fusion(vector_results, keyword_results, k)
    
    def _reciprocal_rank_fusion(
        self,
        vector_results: List[RetrievalResult],
        keyword_results: List[RetrievalResult],
        k: int,
    ) -> List[RetrievalResult]:
        """Merge using Reciprocal Rank Fusion (RRF)."""
        # Build rank maps
        vector_ranks = {r.chunk.id: i + 1 for i, r in enumerate(vector_results)}
        keyword_ranks = {r.chunk.id: i + 1 for i, r in enumerate(keyword_results)}
        
        # All unique chunk IDs
        all_ids = set(vector_ranks.keys()) | set(keyword_ranks.keys())
        
        # Compute RRF scores
        fused_results = []
        for chunk_id in all_ids:
            v_rank = vector_ranks.get(chunk_id, len(vector_results) + 1)
            k_rank = keyword_ranks.get(chunk_id, len(keyword_results) + 1)
            
            rrf_score = (
                self.vector_weight / (self.rrf_k + v_rank) +
                self.keyword_weight / (self.rrf_k + k_rank)
            )
            
            # Find the chunk object
            chunk = None
            for r in vector_results:
                if r.chunk.id == chunk_id:
                    chunk = r.chunk
                    break
            if chunk is None:
                for r in keyword_results:
                    if r.chunk.id == chunk_id:
                        chunk = r.chunk
                        break
            
            if chunk:
                fused_results.append(RetrievalResult(
                    chunk=chunk,
                    score=rrf_score,
                    strategy="hybrid_rrf",
                    metadata={
                        "vector_rank": v_rank,
                        "keyword_rank": k_rank,
                        "rrf_score": rrf_score,
                    },
                ))
        
        fused_results.sort()
        return fused_results[:k]
    
    def _weighted_fusion(
        self,
        vector_results: List[RetrievalResult],
        keyword_results: List[RetrievalResult],
        k: int,
    ) -> List[RetrievalResult]:
        """Merge using weighted score combination."""
        # Normalize scores to 0-1 range
        def normalize(results: List[RetrievalResult]) -> Dict[str, float]:
            if not results:
                return {}
            scores = [r.score for r in results]
            min_s, max_s = min(scores), max(scores)
            if max_s == min_s:
                return {r.chunk.id: 1.0 for r in results}
            return {
                r.chunk.id: (r.score - min_s) / (max_s - min_s)
                for r in results
            }
        
        vector_norm = normalize(vector_results)
        keyword_norm = normalize(keyword_results)
        
        all_ids = set(vector_norm.keys()) | set(keyword_norm.keys())
        
        fused_results = []
        for chunk_id in all_ids:
            v_score = vector_norm.get(chunk_id, 0.0)
            k_score = keyword_norm.get(chunk_id, 0.0)
            
            combined = (
                self.vector_weight * v_score +
                self.keyword_weight * k_score
            )
            
            # Find chunk
            chunk = None
            for r in vector_results:
                if r.chunk.id == chunk_id:
                    chunk = r.chunk
                    break
            if chunk is None:
                for r in keyword_results:
                    if r.chunk.id == chunk_id:
                        chunk = r.chunk
                        break
            
            if chunk:
                fused_results.append(RetrievalResult(
                    chunk=chunk,
                    score=combined,
                    strategy="hybrid_weighted",
                    metadata={
                        "vector_score": v_score,
                        "keyword_score": k_score,
                        "combined_score": combined,
                    },
                ))
        
        fused_results.sort()
        return fused_results[:k]


def create_retriever(
    strategy: RetrievalStrategy | str,
    **kwargs
) -> BaseRetriever:
    """
    Factory function to create a retriever.
    
    Args:
        strategy: RetrievalStrategy.VECTOR, KEYWORD, HYBRID, or string
        **kwargs: Arguments passed to retriever constructor
        
    Returns:
        Configured retriever instance
    """
    if isinstance(strategy, str):
        strategy = RetrievalStrategy(strategy.lower())
    
    if strategy == RetrievalStrategy.VECTOR:
        return VectorRetriever(**kwargs)
    elif strategy == RetrievalStrategy.KEYWORD:
        return KeywordRetriever(**kwargs)
    elif strategy == RetrievalStrategy.HYBRID:
        return HybridRetriever(**kwargs)
    else:
        raise ValueError(f"Unknown retrieval strategy: {strategy}")