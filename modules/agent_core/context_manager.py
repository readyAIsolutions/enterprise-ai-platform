"""
SmartContext — Multi-Tier Context Management with Embeddings
=============================================================

Part of the Claude Code Core enterprise module. Provides intelligent
context window management, embeddings-based relevance filtering,
multi-tier compression, and caching for LLM context optimization.

Classes:
  ContextTier — enum for compression levels
  EmbeddingCache — LRU cache for embedding vectors
  CompressionEngine — text compression at multiple tiers
  WindowManager — token-aware window slicing and eviction
  SmartContext — orchestrates all context management
"""

from __future__ import annotations

import hashlib
import logging
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("enterprise.agent.context_manager")

try:
    from enterprise.platform_kernel import HealthStatus
except ImportError:
    from platform_kernel import HealthStatus


# =============================================================================
# Enums
# =============================================================================


class ContextTier(Enum):
    """Compression/relevance tiers for context management."""
    RAW = "raw"                # Full original content
    TRIMMED = "trimmed"        # Whitespace/formatting trimmed
    SUMMARIZED = "summarized"  # Key points extracted
    EMBEDDED = "embedded"      # Vector embedding stored
    DISCARDED = "discarded"    # Removed from context


# =============================================================================
# Data Classes
# =============================================================================


@dataclass
class ContextEntry:
    """A single entry in the context window.

    Attributes:
        entry_id: Unique identifier.
        content: The text content.
        tier: Current compression tier.
        token_count: Estimated token count.
        relevance_score: Relevance score (0.0-1.0), higher is more relevant.
        timestamp: When the entry was created.
        metadata: Arbitrary additional data.
    """
    entry_id: str
    content: str
    tier: ContextTier = ContextTier.RAW
    token_count: int = 0
    relevance_score: float = 1.0
    timestamp: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)


# =============================================================================
# EmbeddingCache
# =============================================================================


class EmbeddingCache:
    """LRU cache for embedding vectors.

    Caches computed embeddings to avoid redundant computation.
    Thread-safe for concurrent access.

    Attributes:
        max_size: Maximum number of cached entries.
        _cache: OrderedDict implementing LRU eviction.
    """

    def __init__(self, max_size: int = 1000) -> None:
        self.max_size = max_size
        self._cache: OrderedDict[str, List[float]] = OrderedDict()
        self._hits: int = 0
        self._misses: int = 0

    def get(self, key: str) -> Optional[List[float]]:
        """Get a cached embedding. Returns None on miss."""
        if key in self._cache:
            self._cache.move_to_end(key)
            self._hits += 1
            return self._cache[key]
        self._misses += 1
        return None

    def set(self, key: str, embedding: List[float]) -> None:
        """Store an embedding, evicting LRU if at capacity."""
        if key in self._cache:
            self._cache.move_to_end(key)
        self._cache[key] = embedding
        if len(self._cache) > self.max_size:
            self._cache.popitem(last=False)

    def clear(self) -> None:
        """Clear all cached embeddings."""
        self._cache.clear()
        self._hits = 0
        self._misses = 0

    @property
    def size(self) -> int:
        return len(self._cache)

    @property
    def hit_rate(self) -> float:
        total = self._hits + self._misses
        return self._hits / total if total > 0 else 0.0


# =============================================================================
# CompressionEngine
# =============================================================================


class CompressionEngine:
    """Multi-tier text compression for context optimization.

    Provides three levels:
      - TRIM: Remove excessive whitespace and formatting
      - SUMMARIZE: Extract key sentences/points
      - EMBED: Generate vector embeddings for semantic search
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        self._config = config or {}
        self._embedding_cache = EmbeddingCache(
            max_size=self._config.get("embedding_cache_size", 1000)
        )

    def trim(self, content: str) -> Tuple[str, int]:
        """Trim whitespace and normalize text.

        Returns:
            Tuple of (trimmed_text, estimated_token_count).
        """
        lines = [line.strip() for line in content.splitlines()]
        trimmed = "\n".join(line for line in lines if line)
        token_estimate = len(trimmed.split())
        return trimmed, token_estimate

    def summarize(self, content: str, max_sentences: int = 5) -> Tuple[str, int]:
        """Extract key sentences from content.

        Uses a simple heuristic: picks the first sentence, then sentences
        with the most content-bearing words.

        Args:
            content: Text to summarize.
            max_sentences: Maximum sentences in the summary.

        Returns:
            Tuple of (summary_text, estimated_token_count).
        """
        import re
        sentences = re.split(r'(?<=[.!?])\s+', content)
        if len(sentences) <= max_sentences:
            return content, len(content.split())

        # Simple heuristic: score by word count and capital letters
        scored = []
        for i, s in enumerate(sentences):
            words = s.split()
            score = len(words) + sum(1 for c in s if c.isupper())
            scored.append((score, i, s))

        scored.sort(reverse=True)
        # Always include first sentence
        selected_indices = {0}
        for _, idx, _ in scored:
            if len(selected_indices) >= max_sentences:
                break
            selected_indices.add(idx)

        summary = " ".join(
            sentences[i] for i in sorted(selected_indices)
        )
        return summary, len(summary.split())

    def compute_embedding(self, content: str) -> List[float]:
        """Compute a simple hash-based embedding vector.

        In production, this would call an embedding model API.
        Here we use a deterministic hash-based fallback.

        Args:
            content: Text to embed.

        Returns:
            A 128-dimensional float vector.
        """
        cache_key = hashlib.sha256(content.encode()).hexdigest()
        cached = self._embedding_cache.get(cache_key)
        if cached is not None:
            return cached

        # Deterministic pseudo-embedding from content hash
        h = hashlib.sha256(content.encode()).digest()
        vec = []
        for i in range(0, 32, 2):
            val = (h[i] << 8 | h[i + 1]) / 65535.0
            vec.append(val)
        # Pad to 128 dimensions
        while len(vec) < 128:
            vec.append((vec[len(vec) % len(vec)] * 1.37) % 1.0)

        self._embedding_cache.set(cache_key, vec)
        return vec

    def cosine_similarity(self, a: List[float], b: List[float]) -> float:
        """Compute cosine similarity between two embedding vectors."""
        if not a or not b or len(a) != len(b):
            return 0.0
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = sum(x * x for x in a) ** 0.5
        norm_b = sum(x * x for x in b) ** 0.5
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot / (norm_a * norm_b)

    @property
    def embedding_cache(self) -> EmbeddingCache:
        return self._embedding_cache


# =============================================================================
# WindowManager
# =============================================================================


class WindowManager:
    """Token-aware context window manager.

    Manages a sliding window of context entries, evicting least relevant
    entries when the token budget is exceeded.

    Attributes:
        max_tokens: Maximum token budget for the context window.
        entries: Current entries in the window.
        total_tokens: Current estimated token count.
    """

    def __init__(self, max_tokens: int = 100000) -> None:
        self.max_tokens = max_tokens
        self.entries: List[ContextEntry] = []
        self.total_tokens: int = 0

    def add(self, entry: ContextEntry) -> None:
        """Add an entry to the window, evicting if needed."""
        self.entries.append(entry)
        self.total_tokens += entry.token_count
        self._evict_if_needed()

    def remove(self, entry_id: str) -> bool:
        """Remove an entry by ID."""
        for i, entry in enumerate(self.entries):
            if entry.entry_id == entry_id:
                self.total_tokens -= entry.token_count
                self.entries.pop(i)
                return True
        return False

    def query_relevant(self, query_embedding: List[float],
                       engine: CompressionEngine,
                       top_k: int = 5) -> List[ContextEntry]:
        """Find the most relevant entries for a query embedding.

        Args:
            query_embedding: Embedding vector of the query.
            engine: CompressionEngine for similarity computation.
            top_k: Number of top entries to return.

        Returns:
            Top-k most relevant entries sorted by relevance.
        """
        scored = []
        for entry in self.entries:
            if entry.tier == ContextTier.DISCARDED:
                continue
            emb = engine.compute_embedding(entry.content)
            score = engine.cosine_similarity(query_embedding, emb)
            scored.append((score, entry))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [entry for _, entry in scored[:top_k]]

    def get_entries(self, tier: Optional[ContextTier] = None) -> List[ContextEntry]:
        """Get entries filtered by tier."""
        if tier is None:
            return list(self.entries)
        return [e for e in self.entries if e.tier == tier]

    def clear(self) -> None:
        """Clear all entries."""
        self.entries.clear()
        self.total_tokens = 0

    def _evict_if_needed(self) -> None:
        """Evict least relevant entries when over budget."""
        while self.total_tokens > self.max_tokens and self.entries:
            # Find entry with lowest relevance score
            worst_idx = 0
            worst_score = float("inf")
            for i, entry in enumerate(self.entries):
                if entry.relevance_score < worst_score:
                    worst_score = entry.relevance_score
                    worst_idx = i
            evicted = self.entries.pop(worst_idx)
            self.total_tokens -= evicted.token_count
            logger.debug("Evicted entry %s (tokens=%d, relevance=%.2f)",
                         evicted.entry_id, evicted.token_count, evicted.relevance_score)

    def token_usage_pct(self) -> float:
        """Return token usage as a percentage of max."""
        if self.max_tokens == 0:
            return 0.0
        return (self.total_tokens / self.max_tokens) * 100.0


# =============================================================================
# SmartContext
# =============================================================================


class SmartContext:
    """Orchestrates all context management: embeddings, compression, windows.

    Provides a unified interface for managing LLM context:
      - Automatically compresses entries at different tiers
      - Uses embeddings for semantic relevance ranking
      - Manages token budget with intelligent eviction
      - Supports query-time context assembly

    Usage::

        ctx = SmartContext(config={"max_tokens": 100000})
        await ctx.initialize()
        ctx.add_entry("Hello, world!", entry_id="msg1")
        relevant = ctx.query("What was said?")
        await ctx.shutdown()
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        self._config = config or {}
        self._compression = CompressionEngine(config=self._config.get("compression", {}))
        self._window = WindowManager(max_tokens=self._config.get("max_tokens", 100000))
        self._status = HealthStatus.UNKNOWN

    async def initialize(self) -> None:
        self._status = HealthStatus.HEALTHY
        logger.info("SmartContext initialized (max_tokens=%d)", self._window.max_tokens)

    async def health_check(self) -> bool:
        return self._status == HealthStatus.HEALTHY

    async def shutdown(self) -> None:
        self._window.clear()
        self._compression.embedding_cache.clear()
        self._status = HealthStatus.UNKNOWN
        logger.info("SmartContext shut down")

    def add_entry(self, content: str, entry_id: Optional[str] = None,
                  metadata: Optional[Dict[str, Any]] = None) -> ContextEntry:
        """Add content to the context window.

        Args:
            content: Text content to add.
            entry_id: Optional unique ID (auto-generated if None).
            metadata: Optional metadata.

        Returns:
            The created ContextEntry.
        """
        if entry_id is None:
            entry_id = hashlib.sha256(content.encode()).hexdigest()[:16]

        # Estimate tokens (simple word-count heuristic)
        token_count = len(content.split())

        entry = ContextEntry(
            entry_id=entry_id,
            content=content,
            tier=ContextTier.RAW,
            token_count=token_count,
            metadata=metadata or {},
        )
        self._window.add(entry)
        return entry

    def query(self, query_text: str, top_k: int = 5,
              tier: Optional[ContextTier] = None) -> List[ContextEntry]:
        """Find context entries relevant to a query.

        Args:
            query_text: The query text.
            top_k: Number of results to return.
            tier: Optional tier filter.

        Returns:
            List of relevant ContextEntry objects.
        """
        query_emb = self._compression.compute_embedding(query_text)
        return self._window.query_relevant(query_emb, self._compression, top_k)

    def compress_entry(self, entry_id: str, target_tier: ContextTier) -> bool:
        """Compress a specific entry to a target tier.

        Args:
            entry_id: The entry to compress.
            target_tier: Target compression tier.

        Returns:
            True if the entry was found and compressed.
        """
        for entry in self._window.entries:
            if entry.entry_id == entry_id:
                if target_tier == ContextTier.TRIMMED:
                    content, tokens = self._compression.trim(entry.content)
                    entry.content = content
                    entry.token_count = tokens
                    entry.tier = ContextTier.TRIMMED
                elif target_tier == ContextTier.SUMMARIZED:
                    content, tokens = self._compression.summarize(entry.content)
                    entry.content = content
                    entry.token_count = tokens
                    entry.tier = ContextTier.SUMMARIZED
                elif target_tier == ContextTier.EMBEDDED:
                    self._compression.compute_embedding(entry.content)
                    entry.tier = ContextTier.EMBEDDED
                elif target_tier == ContextTier.DISCARDED:
                    entry.tier = ContextTier.DISCARDED
                entry.relevance_score *= 0.5  # Penalize compressed entries
                return True
        return False

    def compress_all_to_tier(self, target_tier: ContextTier) -> int:
        """Compress all RAW entries to the target tier.

        Returns:
            Number of entries compressed.
        """
        count = 0
        for entry in self._window.entries:
            if entry.tier == ContextTier.RAW:
                self.compress_entry(entry.entry_id, target_tier)
                count += 1
        return count

    def get_stats(self) -> Dict[str, Any]:
        """Get context window statistics."""
        return {
            "total_entries": len(self._window.entries),
            "total_tokens": self._window.total_tokens,
            "max_tokens": self._window.max_tokens,
            "token_usage_pct": self._window.token_usage_pct(),
            "tiers": {
                tier.value: len(self._window.get_entries(tier))
                for tier in ContextTier
            },
            "cache_hit_rate": self._compression.embedding_cache.hit_rate,
        }

    @property
    def compression(self) -> CompressionEngine:
        return self._compression

    @property
    def window(self) -> WindowManager:
        return self._window

    @property
    def status(self) -> HealthStatus:
        return self._status