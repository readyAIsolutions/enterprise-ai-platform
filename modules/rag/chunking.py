"""
Chunking Strategies for RAG System.

Provides two chunking approaches:
- Fixed Chunking: Equal-sized segments with configurable overlap
- Semantic Chunking: Meaningful boundaries based on semantic similarity

Both implement a common ChunkingStrategy interface for seamless swapping.
"""

from __future__ import annotations

import hashlib
import re
import math
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, List, Optional, Sequence

# Optional: use numpy for semantic chunking if available
try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False
    np = None  # type: ignore


class ChunkingStrategy(str, Enum):
    """Available chunking strategies."""
    FIXED = "fixed"
    SEMANTIC = "semantic"


@dataclass
class Chunk:
    """A single chunk of text with metadata."""
    id: str
    text: str
    start_char: int
    end_char: int
    chunk_index: int
    metadata: dict[str, Any] = field(default_factory=dict)
    
    @property
    def length(self) -> int:
        return len(self.text)
    
    @property
    def token_estimate(self) -> int:
        """Rough token estimate (4 chars per token)."""
        return max(1, len(self.text) // 4)


class BaseChunker(ABC):
    """Abstract base class for all chunkers."""
    
    def __init__(
        self,
        chunk_size: int = 512,
        chunk_overlap: int = 50,
        min_chunk_size: int = 50,
    ):
        """
        Initialize chunker.
        
        Args:
            chunk_size: Target size for each chunk (characters)
            chunk_overlap: Overlap between adjacent chunks (characters)
            min_chunk_size: Minimum chunk size to keep (characters)
        """
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.min_chunk_size = min_chunk_size
    
    @abstractmethod
    def chunk(self, text: str, metadata: Optional[dict[str, Any]] = None) -> List[Chunk]:
        """Split text into chunks."""
        pass
    
    def _generate_chunk_id(self, text: str, index: int) -> str:
        """Generate deterministic chunk ID."""
        content_hash = hashlib.md5(text.encode()).hexdigest()[:8]
        return f"chunk_{index}_{content_hash}"
    
    def _filter_chunks(self, chunks: List[Chunk]) -> List[Chunk]:
        """Filter out chunks smaller than min_chunk_size."""
        return [c for c in chunks if c.length >= self.min_chunk_size]


class FixedChunker(BaseChunker):
    """
    Fixed-size chunking with configurable overlap.
    
    Divides text into equal-sized segments regardless of semantic boundaries.
    Simple, fast, and predictable - good for uniform content or when
    semantic chunking is too resource-intensive.
    """
    
    def __init__(
        self,
        chunk_size: int = 512,
        chunk_overlap: int = 50,
        min_chunk_size: int = 50,
        separators: Optional[List[str]] = None,
    ):
        """
        Initialize fixed chunker.
        
        Args:
            chunk_size: Target chunk size in characters
            chunk_overlap: Overlap between chunks in characters
            min_chunk_size: Minimum chunk size to keep
            separators: Preferred split points (newlines, sentences, etc.)
        """
        super().__init__(chunk_size, chunk_overlap, min_chunk_size)
        self.separators = separators or ["\n\n", "\n", ". ", "! ", "? ", " ", ""]
    
    def chunk(self, text: str, metadata: Optional[dict[str, Any]] = None) -> List[Chunk]:
        """Split text into fixed-size chunks with overlap."""
        if not text or not text.strip():
            return []
        
        metadata = metadata or {}
        chunks: List[Chunk] = []
        
        # Recursive splitting using separators
        def _split_recursive(text: str, separators: List[str]) -> List[str]:
            if not separators:
                return [text]
            
            sep = separators[0]
            if sep == "":
                return list(text)
            
            parts = text.split(sep)
            if len(parts) == 1:
                return _split_recursive(text, separators[1:])
            
            # Rejoin with separator
            result = []
            for i, part in enumerate(parts):
                if i > 0:
                    result.append(sep)
                result.append(part)
            return result
        
        # Get initial splits
        splits = _split_recursive(text, self.separators)
        
        # Build chunks
        current_chunk = ""
        current_start = 0
        chunk_index = 0
        
        for split in splits:
            # Check if adding this split would exceed chunk_size
            if len(current_chunk) + len(split) > self.chunk_size and current_chunk:
                # Finalize current chunk
                chunk_id = self._generate_chunk_id(current_chunk, chunk_index)
                chunks.append(Chunk(
                    id=chunk_id,
                    text=current_chunk.strip(),
                    start_char=current_start,
                    end_char=current_start + len(current_chunk),
                    chunk_index=chunk_index,
                    metadata={**metadata, "strategy": "fixed"},
                ))
                chunk_index += 1
                
                # Start new chunk with overlap
                overlap_text = current_chunk[-self.chunk_overlap:] if self.chunk_overlap > 0 else ""
                current_chunk = overlap_text + split
                current_start = current_start + len(current_chunk) - len(overlap_text) - len(split)
            else:
                current_chunk += split
        
        # Don't forget the last chunk
        if current_chunk.strip():
            chunk_id = self._generate_chunk_id(current_chunk, chunk_index)
            chunks.append(Chunk(
                id=chunk_id,
                text=current_chunk.strip(),
                start_char=current_start,
                end_char=current_start + len(current_chunk),
                chunk_index=chunk_index,
                metadata={**metadata, "strategy": "fixed"},
            ))
        
        return self._filter_chunks(chunks)


class SemanticChunker(BaseChunker):
    """
    Semantic chunking based on embedding similarity.
    
    Divides content into meaningful chunks by detecting semantic boundaries
    using embedding similarity. More accurate but requires embedding computation.
    
    Uses a sliding window approach with similarity threshold to find
    natural topic boundaries.
    """
    
    def __init__(
        self,
        chunk_size: int = 512,
        chunk_overlap: int = 50,
        min_chunk_size: int = 50,
        similarity_threshold: float = 0.7,
        window_size: int = 3,
        embedder: Optional[Any] = None,
    ):
        """
        Initialize semantic chunker.
        
        Args:
            chunk_size: Target chunk size in characters
            chunk_overlap: Overlap between chunks
            min_chunk_size: Minimum chunk size
            similarity_threshold: Cosine similarity threshold for boundaries (0-1)
            window_size: Number of sentences to consider for similarity
            embedder: Custom embedder (must have .embed(texts) -> List[List[float]])
        """
        super().__init__(chunk_size, chunk_overlap, min_chunk_size)
        self.similarity_threshold = similarity_threshold
        self.window_size = window_size
        self.embedder = embedder
        self._sentence_splitter = re.compile(r'(?<=[.!?])\s+')
    
    def _split_sentences(self, text: str) -> List[str]:
        """Split text into sentences."""
        sentences = self._sentence_splitter.split(text.strip())
        return [s.strip() for s in sentences if s.strip()]
    
    def _embed_texts(self, texts: List[str]) -> List[List[float]]:
        """Embed texts using provided embedder or fallback."""
        if self.embedder and hasattr(self.embedder, 'embed'):
            return self.embedder.embed(texts)
        
        # Fallback: simple hash-based embedding (deterministic, no deps)
        return [self._hash_embed(t) for t in texts]
    
    def _hash_embed(self, text: str, dim: int = 384) -> List[float]:
        """Deterministic hash-based embedding (feature hashing)."""
        vec = [0.0] * dim
        words = text.lower().split()
        for word in words:
            h = hash(word)
            idx = abs(h) % dim
            sign = 1.0 if h >= 0 else -1.0
            vec[idx] += sign
        
        # L2 normalize
        norm = math.sqrt(sum(v * v for v in vec))
        if norm > 0:
            vec = [v / norm for v in vec]
        return vec
    
    def _cosine_similarity(self, a: List[float], b: List[float]) -> float:
        """Compute cosine similarity between two vectors."""
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = math.sqrt(sum(x * x for x in a))
        norm_b = math.sqrt(sum(y * y for y in b))
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot / (norm_a * norm_b)
    
    def _find_boundaries(self, sentences: List[str]) -> List[int]:
        """Find semantic boundaries between sentences."""
        if len(sentences) <= 1:
            return [0]
        
        # Embed all sentences
        embeddings = self._embed_texts(sentences)
        
        boundaries = [0]
        
        for i in range(1, len(sentences)):
            # Compute similarity with previous window
            window_start = max(0, i - self.window_size)
            window_embeddings = embeddings[window_start:i]
            
            if window_embeddings:
                # Average embedding of window
                avg_emb = [
                    sum(e[d] for e in window_embeddings) / len(window_embeddings)
                    for d in range(len(window_embeddings[0]))
                ]
                
                sim = self._cosine_similarity(avg_emb, embeddings[i])
                
                # Boundary if similarity drops below threshold
                if sim < self.similarity_threshold:
                    boundaries.append(i)
        
        return boundaries
    
    def chunk(self, text: str, metadata: Optional[dict[str, Any]] = None) -> List[Chunk]:
        """Split text into semantically meaningful chunks."""
        if not text or not text.strip():
            return []
        
        metadata = metadata or {}
        sentences = self._split_sentences(text)
        
        if not sentences:
            return []
        
        # Find semantic boundaries
        boundaries = self._find_boundaries(sentences)
        boundaries.append(len(sentences))  # End boundary
        
        chunks: List[Chunk] = []
        char_offset = 0
        chunk_index = 0
        
        for i in range(len(boundaries) - 1):
            start_idx = boundaries[i]
            end_idx = boundaries[i + 1]
            
            chunk_sentences = sentences[start_idx:end_idx]
            chunk_text = " ".join(chunk_sentences)
            
            # If chunk is too large, split it further using fixed chunking
            if len(chunk_text) > self.chunk_size * 2:
                # Fallback to fixed chunking for oversized semantic chunks
                fixed_chunker = FixedChunker(
                    chunk_size=self.chunk_size,
                    chunk_overlap=self.chunk_overlap,
                    min_chunk_size=self.min_chunk_size,
                )
                sub_chunks = fixed_chunker.chunk(chunk_text, metadata)
                for sc in sub_chunks:
                    sc.chunk_index = chunk_index
                    sc.metadata["strategy"] = "semantic"
                    sc.metadata["sub_strategy"] = "fixed_fallback"
                    chunks.append(sc)
                    chunk_index += 1
            else:
                # Find character positions in original text
                start_pos = text.find(chunk_sentences[0], char_offset)
                if start_pos == -1:
                    start_pos = char_offset
                end_pos = start_pos + len(chunk_text)
                
                chunk_id = self._generate_chunk_id(chunk_text, chunk_index)
                chunks.append(Chunk(
                    id=chunk_id,
                    text=chunk_text,
                    start_char=start_pos,
                    end_char=end_pos,
                    chunk_index=chunk_index,
                    metadata={**metadata, "strategy": "semantic"},
                ))
                chunk_index += 1
                char_offset = end_pos
        
        return self._filter_chunks(chunks)


def create_chunker(
    strategy: ChunkingStrategy | str,
    **kwargs
) -> BaseChunker:
    """
    Factory function to create a chunker.
    
    Args:
        strategy: ChunkingStrategy.FIXED, ChunkingStrategy.SEMANTIC, or string
        **kwargs: Arguments passed to chunker constructor
        
    Returns:
        Configured chunker instance
    """
    if isinstance(strategy, str):
        strategy = ChunkingStrategy(strategy.lower())
    
    if strategy == ChunkingStrategy.FIXED:
        return FixedChunker(**kwargs)
    elif strategy == ChunkingStrategy.SEMANTIC:
        return SemanticChunker(**kwargs)
    else:
        raise ValueError(f"Unknown chunking strategy: {strategy}")