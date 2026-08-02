"""
Token Budget Manager - Enterprise-grade token optimization system.

Capabilities:
- Token budget allocation and tracking
- Context summarization for token reduction
- Intelligent truncation strategies
- Retrieval ranking for dynamic context inclusion
- Prompt caching awareness
- Semantic compression
- Model routing based on budget requirements
- Dynamic retrieval triggering
- Shared instruction reuse
- Real-time token usage monitoring
"""

from __future__ import annotations

import hashlib
import re
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set, Tuple, Union
from collections import OrderedDict, defaultdict


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class TruncationStrategy(str, Enum):
    """Strategies for truncating content to fit budget."""
    HEAD = "head"                # Keep the beginning
    TAIL = "tail"                # Keep the end
    MIDDLE = "middle"            # Keep beginning + end, truncate middle
    SMART = "smart"              # Semantic-aware truncation
    PRIORITY = "priority"        # Truncate lowest priority first
    RELEVANCE = "relevance"      # Truncate least relevant first
    SLIDING_WINDOW = "sliding"   # Keep a sliding window of context


class BudgetAllocation(str, Enum):
    """Budget allocation strategies."""
    PROPORTIONAL = "proportional"    # Allocate proportionally by type
    FIXED = "fixed"                  # Fixed allocation per type
    PRIORITY_WEIGHTED = "priority"   # Allocate by priority
    DYNAMIC = "dynamic"              # Adjust based on task
    RESERVED_FIRST = "reserved"      # Reserve for critical types first


class CacheStrategy(str, Enum):
    """Prompt caching strategies."""
    NONE = "none"
    EXACT = "exact"                  # Cache exact prompt prefixes
    SEMANTIC = "semantic"            # Cache semantically similar prompts
    TEMPLATE = "template"            # Cache based on template ID
    VARIABLE = "variable"            # Cache template with variable slots
    SESSION = "session"              # Cache within a session


# ---------------------------------------------------------------------------
# Data Classes
# ---------------------------------------------------------------------------

@dataclass
class TokenBudget:
    """Token budget configuration and state."""
    total: int
    allocated: Dict[str, int] = field(default_factory=dict)
    used: Dict[str, int] = field(default_factory=dict)
    reserved: int = 0
    allocation_strategy: BudgetAllocation = BudgetAllocation.PROPORTIONAL

    @property
    def available(self) -> int:
        return max(0, self.total - sum(self.used.values()) - self.reserved)

    @property
    def utilization_pct(self) -> float:
        if self.total == 0:
            return 0.0
        return round(sum(self.used.values()) / self.total * 100, 1)

    def reset_usage(self) -> None:
        self.used = {k: 0 for k in self.used}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total": self.total,
            "allocated": self.allocated,
            "used": self.used,
            "reserved": self.reserved,
            "available": self.available,
            "utilization_pct": self.utilization_pct,
            "allocation_strategy": self.allocation_strategy.value,
        }


@dataclass
class CacheEntry:
    """A cached prompt fragment."""
    key: str
    content: str
    token_count: int
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_accessed: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    access_count: int = 0
    template_id: Optional[str] = None
    variables_hash: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def touch(self) -> None:
        self.last_accessed = datetime.now(timezone.utc)
        self.access_count += 1


@dataclass
class BudgetReport:
    """Token usage report."""
    budget: TokenBudget
    compression_saved: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    truncations: int = 0
    summaries: int = 0
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def cache_hit_rate(self) -> float:
        total = self.cache_hits + self.cache_misses
        return round(self.cache_hits / total * 100, 1) if total > 0 else 0.0


@dataclass
class ModelRoute:
    """Model routing recommendation."""
    model_name: str
    max_tokens: int
    cost_per_1k_input: float
    cost_per_1k_output: float
    latency_tier: str  # 'low', 'medium', 'high'
    suitable: bool
    reason: str


# ---------------------------------------------------------------------------
# Token Budget Manager
# ---------------------------------------------------------------------------

class TokenBudgetError(Exception):
    """Base exception for token budget errors."""


class BudgetExceededError(TokenBudgetError):
    """Raised when token budget is exceeded."""


class TokenBudgetManager:
    """
    Enterprise-grade token budget manager.

    Features:
    - Budget allocation and tracking
    - Multiple truncation strategies
    - Prompt caching with multiple strategies
    - Semantic compression
    - Model routing
    - Dynamic retrieval triggering
    - Real-time usage monitoring
    - Cache statistics and eviction

    Usage::

        tbm = TokenBudgetManager(total_budget=100_000)
        tbm.allocate("system", 5_000)
        tbm.allocate("context", 80_000)
        tbm.allocate("response", 15_000)

        # Optimize context to fit budget
        optimized = tbm.fit_to_budget(context_text, "context")

        # Cache and reuse
        cached = tbm.cache_get("greeting_template")
        if cached is None:
            cached = "Hello, {{name}}!"
            tbm.cache_set("greeting_template", cached)
    """

    # Default budget allocations by type
    DEFAULT_ALLOCATIONS: Dict[str, float] = {
        "system": 0.05,         # 5% for system instructions
        "task": 0.03,           # 3% for task description
        "security": 0.02,       # 2% for security rules
        "compliance": 0.02,     # 2% for compliance
        "knowledge": 0.20,      # 20% for retrieved knowledge
        "conversation": 0.15,   # 15% for conversation history
        "memory": 0.10,         # 10% for long-term memory
        "tools": 0.08,          # 8% for tool definitions
        "output": 0.25,         # 25% reserved for output
        "overhead": 0.05,       # 5% overhead/misc
        "reserved": 0.05,       # 5% safety margin
    }

    # Model routing table
    MODEL_TABLE: List[Dict[str, Any]] = [
        {
            "name": "claude-3-haiku",
            "max_tokens": 200_000,
            "cost_input": 0.25,
            "cost_output": 1.25,
            "latency": "low",
        },
        {
            "name": "claude-3-sonnet",
            "max_tokens": 200_000,
            "cost_input": 3.00,
            "cost_output": 15.00,
            "latency": "medium",
        },
        {
            "name": "claude-3-opus",
            "max_tokens": 200_000,
            "cost_input": 15.00,
            "cost_output": 75.00,
            "latency": "high",
        },
        {
            "name": "gpt-4o-mini",
            "max_tokens": 128_000,
            "cost_input": 0.15,
            "cost_output": 0.60,
            "latency": "low",
        },
        {
            "name": "gpt-4o",
            "max_tokens": 128_000,
            "cost_input": 2.50,
            "cost_output": 10.00,
            "latency": "medium",
        },
        {
            "name": "deepseek-v3",
            "max_tokens": 128_000,
            "cost_input": 0.27,
            "cost_output": 1.10,
            "latency": "low",
        },
    ]

    def __init__(
        self,
        total_budget: int = 100_000,
        allocation_strategy: BudgetAllocation = BudgetAllocation.PROPORTIONAL,
        cache_strategy: CacheStrategy = CacheStrategy.TEMPLATE,
        max_cache_entries: int = 1000,
        enable_monitoring: bool = True,
    ):
        self.budget = TokenBudget(
            total=total_budget,
            allocation_strategy=allocation_strategy,
        )
        self.cache_strategy = cache_strategy
        self.max_cache_entries = max_cache_entries
        self.enable_monitoring = enable_monitoring

        self._cache: OrderedDict[str, CacheEntry] = OrderedDict()
        self._lock = threading.RLock()
        self._usage_history: List[BudgetReport] = []
        self._compression_stats: Dict[str, int] = defaultdict(int)

        # Initialize default allocations
        self._init_default_allocations()

    def _init_default_allocations(self) -> None:
        """Set up default budget allocations."""
        for category, fraction in self.DEFAULT_ALLOCATIONS.items():
            tokens = int(self.budget.total * fraction)
            self.budget.allocated[category] = tokens
            self.budget.used[category] = 0

    # ------------------------------------------------------------------
    # Budget Management
    # ------------------------------------------------------------------

    def allocate(self, category: str, tokens: int) -> None:
        """Allocate tokens to a specific category."""
        with self._lock:
            self.budget.allocated[category] = tokens
            if category not in self.budget.used:
                self.budget.used[category] = 0

    def reserve(self, tokens: int) -> None:
        """Reserve tokens (safety margin)."""
        with self._lock:
            self.budget.reserved = tokens

    def consume(self, category: str, tokens: int) -> bool:
        """
        Consume tokens from a category's allocation.

        Returns True if consumption succeeded, False if exceeded.
        """
        with self._lock:
            if category not in self.budget.allocated:
                self.budget.allocated[category] = self.budget.available
                self.budget.used[category] = 0

            allocated = self.budget.allocated[category]
            used = self.budget.used[category]

            if used + tokens > allocated:
                return False

            self.budget.used[category] = used + tokens
            return True

    def can_fit(self, tokens: int, category: Optional[str] = None) -> bool:
        """Check if tokens can fit in the budget."""
        with self._lock:
            if category:
                allocated = self.budget.allocated.get(category, 0)
                used = self.budget.used.get(category, 0)
                return (used + tokens) <= allocated
            return tokens <= self.budget.available

    def get_available(self, category: Optional[str] = None) -> int:
        """Get available tokens, optionally for a specific category."""
        with self._lock:
            if category:
                allocated = self.budget.allocated.get(category, 0)
                used = self.budget.used.get(category, 0)
                return max(0, allocated - used)
            return self.budget.available

    def reset(self) -> None:
        """Reset all usage counters."""
        with self._lock:
            self.budget.reset_usage()

    # ------------------------------------------------------------------
    # Truncation
    # ------------------------------------------------------------------

    def truncate(
        self,
        text: str,
        max_tokens: int,
        strategy: TruncationStrategy = TruncationStrategy.SMART,
        preserve_patterns: Optional[List[str]] = None,
    ) -> Tuple[str, int]:
        """
        Truncate text to fit within a token budget.

        Args:
            text: The text to truncate.
            max_tokens: Maximum tokens allowed.
            strategy: Truncation strategy to use.
            preserve_patterns: Regex patterns to preserve during truncation.

        Returns:
            Tuple of (truncated_text, tokens_saved).
        """
        current_tokens = self._estimate_tokens(text)
        if current_tokens <= max_tokens:
            return text, 0

        preserve = preserve_patterns or []

        handlers = {
            TruncationStrategy.HEAD: lambda t, m: t[:m * 4],
            TruncationStrategy.TAIL: lambda t, m: t[-(m * 4):],
            TruncationStrategy.MIDDLE: lambda t, m: self._truncate_middle(t, m),
            TruncationStrategy.SMART: lambda t, m: self._truncate_smart(t, m, preserve),
            TruncationStrategy.PRIORITY: lambda t, m: self._truncate_by_priority(t, m),
            TruncationStrategy.RELEVANCE: lambda t, m: self._truncate_by_relevance(t, m),
            TruncationStrategy.SLIDING_WINDOW: lambda t, m: self._truncate_sliding(t, m),
        }

        handler = handlers.get(strategy, handlers[TruncationStrategy.SMART])
        truncated = handler(text, max_tokens)
        saved = current_tokens - self._estimate_tokens(truncated)

        return truncated, saved

    def fit_to_budget(
        self,
        content: str,
        category: str,
        strategy: TruncationStrategy = TruncationStrategy.SMART,
    ) -> str:
        """
        Fit content to the available budget for a category.
        """
        available = self.get_available(category)
        truncated, _ = self.truncate(content, available, strategy=strategy)
        return truncated

    def fit_all_to_budget(
        self,
        content_blocks: List[Tuple[str, str]],  # [(category, content), ...]
        strategy: TruncationStrategy = TruncationStrategy.PRIORITY,
    ) -> List[str]:
        """
        Fit multiple content blocks to their respective budgets.
        """
        results = []
        for category, content in content_blocks:
            fitted = self.fit_to_budget(content, category, strategy)
            results.append(fitted)
        return results

    # ------------------------------------------------------------------
    # Context Summarization
    # ------------------------------------------------------------------

    def summarize(
        self,
        text: str,
        target_tokens: int,
        method: str = "extractive",
    ) -> str:
        """
        Summarize text to fit within target token count.

        Methods:
        - 'extractive': Keep most important sentences
        - 'abstractive_header': Add a header summary + key details
        - 'hierarchical': Build a hierarchical outline
        """
        current_tokens = self._estimate_tokens(text)
        if current_tokens <= target_tokens:
            return text

        if method == "extractive":
            return self._summarize_extractive(text, target_tokens)
        elif method == "abstractive_header":
            return self._summarize_abstractive(text, target_tokens)
        elif method == "hierarchical":
            return self._summarize_hierarchical(text, target_tokens)
        else:
            return self._summarize_extractive(text, target_tokens)

    # ------------------------------------------------------------------
    # Prompt Caching
    # ------------------------------------------------------------------

    def cache_set(
        self,
        key: str,
        content: str,
        template_id: Optional[str] = None,
        variables: Optional[Dict[str, str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        ttl_seconds: Optional[int] = None,
    ) -> None:
        """Store content in the prompt cache."""
        with self._lock:
            # Evict if at capacity
            if len(self._cache) >= self.max_cache_entries:
                self._cache.popitem(last=False)  # FIFO eviction

            variables_hash = None
            if variables:
                var_str = json.dumps(variables, sort_keys=True)
                variables_hash = hashlib.md5(var_str.encode()).hexdigest()[:12]

            entry = CacheEntry(
                key=key,
                content=content,
                token_count=self._estimate_tokens(content),
                template_id=template_id,
                variables_hash=variables_hash,
                metadata=metadata or {},
            )
            self._cache[key] = entry

    def cache_get(self, key: str) -> Optional[str]:
        """Retrieve content from the prompt cache."""
        with self._lock:
            entry = self._cache.get(key)
            if entry:
                entry.touch()
                return entry.content
            return None

    def cache_lookup_by_template(
        self, template_id: str, variables: Dict[str, str]
    ) -> Optional[str]:
        """Look up cached content by template and variables."""
        var_str = json.dumps(variables, sort_keys=True)
        var_hash = hashlib.md5(var_str.encode()).hexdigest()[:12]

        with self._lock:
            for entry in self._cache.values():
                if (
                    entry.template_id == template_id
                    and entry.variables_hash == var_hash
                ):
                    entry.touch()
                    return entry.content
            return None

    def cache_invalidate(self, key: Optional[str] = None) -> int:
        """Invalidate cache entries. If key is None, clear all."""
        with self._lock:
            if key:
                if key in self._cache:
                    del self._cache[key]
                    return 1
                return 0
            count = len(self._cache)
            self._cache.clear()
            return count

    def cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        with self._lock:
            entries = list(self._cache.values())
            if not entries:
                return {"entries": 0, "total_tokens": 0, "hit_rate": 0.0}

            total_accesses = sum(e.access_count for e in entries)
            hits = total_accesses - len(entries)  # First access is not a hit
            return {
                "entries": len(entries),
                "total_tokens": sum(e.token_count for e in entries),
                "avg_token_count": round(sum(e.token_count for e in entries) / len(entries), 1),
                "total_accesses": total_accesses,
                "hit_rate": round(hits / max(1, total_accesses) * 100, 1),
                "oldest_entry": min(e.created_at for e in entries).isoformat(),
                "cache_hits": hits,
                "cache_misses": max(0, total_accesses - len(entries)),
            }

    # ------------------------------------------------------------------
    # Semantic Compression
    # ------------------------------------------------------------------

    def semantic_compress(
        self,
        text: str,
        target_ratio: float = 0.5,
        preserve_keywords: Optional[List[str]] = None,
    ) -> str:
        """
        Apply semantic compression to reduce token count while preserving meaning.

        Techniques:
        - Remove filler words and redundancies
        - Compress common phrases
        - Use abbreviations where unambiguous
        - Preserve key terminology
        """
        if target_ratio >= 1.0:
            return text

        keywords = set(preserve_keywords or [])
        compressed = text

        # Remove filler phrases
        filler_patterns = [
            r"\b(it is worth noting that|it should be noted that|it is important to note that)\b",
            r"\b(in order to|for the purpose of)\b",
            r"\b(due to the fact that|because of the fact that)\b",
            r"\b(at this point in time|at the present time)\b",
            r"\b(in the event that|in case of)\b",
            r"\b(with regard to|in reference to|with respect to)\b",
        ]
        replacements = [
            "note:",
            "to",
            "because",
            "now",
            "if",
            "regarding",
        ]
        for pattern, replacement in zip(filler_patterns, replacements):
            compressed = re.sub(pattern, replacement, compressed, flags=re.IGNORECASE)

        # Remove redundant modifiers
        compressed = re.sub(r'\b(very|really|quite|extremely|highly)\s+', '', compressed)

        # Keep compressing until target ratio is reached
        current_tokens = self._estimate_tokens(compressed)
        original_tokens = self._estimate_tokens(text)
        target_tokens = int(original_tokens * target_ratio)

        if current_tokens <= target_tokens:
            return compressed

        # Sentence-level compression: remove less informative sentences
        sentences = re.split(r'(?<=[.!?])\s+', compressed)
        if len(sentences) <= 3:
            return compressed

        # Score sentences: keep ones with keywords and sentence positions
        scored = []
        for i, s in enumerate(sentences):
            score = 0.0
            # Position bonus: first and last sentences are important
            if i == 0:
                score += 3.0
            elif i == len(sentences) - 1:
                score += 2.0
            # Keyword bonus
            kw_matches = sum(1 for kw in keywords if kw.lower() in s.lower())
            score += kw_matches * 2.0
            # Length penalty: medium sentences are better
            s_tokens = self._estimate_tokens(s)
            if 5 <= s_tokens <= 50:
                score += 1.0
            scored.append((score, s_tokens, s))

        # Sort by score descending, keep until budget met
        scored.sort(key=lambda x: -x[0])
        kept = []
        token_count = 0
        for score, s_tokens, s in scored:
            if token_count + s_tokens <= target_tokens:
                kept.append((score, s_tokens, s))
                token_count += s_tokens
            if token_count >= target_tokens:
                break

        # Re-sort by original position
        original_positions = {s: i for i, (_, _, s) in enumerate(scored)}
        kept.sort(key=lambda x: original_positions.get(x[2], 999))

        return " ".join(s for _, _, s in kept)

    # ------------------------------------------------------------------
    # Model Routing
    # ------------------------------------------------------------------

    def route_model(
        self,
        estimated_input_tokens: int,
        estimated_output_tokens: int = 4000,
        latency_requirement: Optional[str] = None,  # 'low', 'medium', 'high'
        max_cost_per_request: Optional[float] = None,
    ) -> List[ModelRoute]:
        """
        Recommend model(s) based on budget and requirements.

        Returns list of suitable models sorted by suitability.
        """
        routes = []
        for model_info in self.MODEL_TABLE:
            if estimated_input_tokens > model_info["max_tokens"]:
                routes.append(ModelRoute(
                    model_name=model_info["name"],
                    max_tokens=model_info["max_tokens"],
                    cost_per_1k_input=model_info["cost_input"],
                    cost_per_1k_output=model_info["cost_output"],
                    latency_tier=model_info["latency"],
                    suitable=False,
                    reason=f"Input tokens ({estimated_input_tokens}) exceed model limit ({model_info['max_tokens']})",
                ))
                continue

            # Calculate cost
            input_cost = (estimated_input_tokens / 1000) * model_info["cost_input"]
            output_cost = (estimated_output_tokens / 1000) * model_info["cost_output"]
            total_cost = (input_cost + output_cost) / 100  # Convert cents to dollars

            if max_cost_per_request and total_cost > max_cost_per_request:
                routes.append(ModelRoute(
                    model_name=model_info["name"],
                    max_tokens=model_info["max_tokens"],
                    cost_per_1k_input=model_info["cost_input"],
                    cost_per_1k_output=model_info["cost_output"],
                    latency_tier=model_info["latency"],
                    suitable=False,
                    reason=f"Cost (${total_cost:.4f}) exceeds max (${max_cost_per_request:.4f})",
                ))
                continue

            if latency_requirement:
                latency_order = {"low": 0, "medium": 1, "high": 2}
                if latency_order.get(model_info["latency"], 99) > latency_order.get(latency_requirement, 99):
                    routes.append(ModelRoute(
                        model_name=model_info["name"],
                        max_tokens=model_info["max_tokens"],
                        cost_per_1k_input=model_info["cost_input"],
                        cost_per_1k_output=model_info["cost_output"],
                        latency_tier=model_info["latency"],
                        suitable=False,
                        reason=f"Latency tier ({model_info['latency']}) exceeds requirement ({latency_requirement})",
                    ))
                    continue

            routes.append(ModelRoute(
                model_name=model_info["name"],
                max_tokens=model_info["max_tokens"],
                cost_per_1k_input=model_info["cost_input"],
                cost_per_1k_output=model_info["cost_output"],
                latency_tier=model_info["latency"],
                suitable=True,
                reason="Meets all requirements",
            ))

        # Sort: suitable first, then by cost (cheapest first), then by latency
        routes.sort(key=lambda r: (
            not r.suitable,
            r.cost_per_1k_input + r.cost_per_1k_output,
            {"low": 0, "medium": 1, "high": 2}.get(r.latency_tier, 99),
        ))

        return routes

    # ------------------------------------------------------------------
    # Dynamic Retrieval
    # ------------------------------------------------------------------

    def should_retrieve(
        self,
        current_context_tokens: int,
        retrieval_cost_tokens: int = 500,
        retrieval_benefit_score: float = 0.5,
    ) -> bool:
        """
        Decide whether to dynamically retrieve more context.

        Returns True if retrieval is worth the token cost.
        """
        available = self.budget.available

        # Can't retrieve if not enough budget
        if retrieval_cost_tokens > available:
            return False

        # Benefit must outweigh cost
        # Simple heuristic: benefit_score * available_tokens > cost_tokens
        value = retrieval_benefit_score * available
        return value > retrieval_cost_tokens

    def compute_retrieval_quota(
        self,
        task_complexity: float = 0.5,  # 0.0 - 1.0
        context_fullness: Optional[float] = None,
    ) -> int:
        """
        Compute how many tokens to allocate for dynamic retrieval.

        More complex tasks and emptier contexts get larger quotas.
        """
        fullness = context_fullness or (self.budget.utilization_pct / 100)
        empty_space_factor = max(0.1, 1.0 - fullness)
        quota = int(self.budget.available * task_complexity * empty_space_factor)
        return max(100, quota)  # Minimum 100 tokens

    # ------------------------------------------------------------------
    # Compression Statistics
    # ------------------------------------------------------------------

    def record_compression(self, strategy: str, tokens_saved: int) -> None:
        """Record compression savings for statistics."""
        self._compression_stats[strategy] += tokens_saved

    def get_compression_stats(self) -> Dict[str, Any]:
        """Get compression statistics."""
        with self._lock:
            total_saved = sum(self._compression_stats.values())
            return {
                "total_tokens_saved": total_saved,
                "by_strategy": dict(self._compression_stats),
                "estimated_cost_saved": self._estimate_cost_saved(total_saved),
            }

    def generate_report(self) -> BudgetReport:
        """Generate a comprehensive budget report."""
        cache_stats = self.cache_stats()
        return BudgetReport(
            budget=self.budget,
            compression_saved=sum(self._compression_stats.values()),
            cache_hits=cache_stats.get("cache_hits", 0),
            cache_misses=cache_stats.get("cache_misses", 0),
            metadata={
                "cache_entries": cache_stats.get("entries", 0),
                "cache_tokens": cache_stats.get("total_tokens", 0),
            },
        )

    # ------------------------------------------------------------------
    # Internal Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _estimate_tokens(text: str) -> int:
        """Rough token estimate."""
        return max(1, len(text) // 4)

    @staticmethod
    def _truncate_middle(text: str, max_tokens: int) -> str:
        """Keep beginning and end, truncate middle."""
        max_chars = max_tokens * 4
        if len(text) <= max_chars:
            return text
        half = max_chars // 2
        return text[:half - 10] + "\n... [content truncated] ...\n" + text[-half + 10:]

    @staticmethod
    def _truncate_smart(
        text: str, max_tokens: int, preserve_patterns: List[str]
    ) -> str:
        """Smart truncation: preserve matched patterns, truncate elsewhere."""
        max_chars = max_tokens * 4
        if len(text) <= max_chars:
            return text

        # Find all preserved sections
        preserved_ranges: List[Tuple[int, int]] = []
        for pattern in preserve_patterns:
            for m in re.finditer(pattern, text, re.IGNORECASE | re.DOTALL):
                preserved_ranges.append((m.start(), m.end()))

        # Merge overlapping ranges
        preserved_ranges.sort()
        merged: List[Tuple[int, int]] = []
        for start, end in preserved_ranges:
            if merged and start <= merged[-1][1]:
                merged[-1] = (merged[-1][0], max(merged[-1][1], end))
            else:
                merged.append((start, end))

        # Build truncated text: keep preserved sections, trim others
        result_parts = []
        pos = 0
        for start, end in merged:
            if start > pos:
                gap = text[pos:start]
                gap_chars = max_chars - sum(len(p) for p in result_parts) - (end - start)
                if gap_chars > 0 and len(gap) > 0:
                    result_parts.append(gap[:gap_chars])
            result_parts.append(text[start:end])
            pos = end

        if pos < len(text):
            remaining_chars = max_chars - sum(len(p) for p in result_parts)
            if remaining_chars > 0:
                result_parts.append(text[pos:pos + remaining_chars])

        return "".join(result_parts) if result_parts else text[:max_chars]

    @staticmethod
    def _truncate_by_priority(text: str, max_tokens: int) -> str:
        """Truncate assuming front-loaded priority (head truncation)."""
        return text[:max_tokens * 4]

    @staticmethod
    def _truncate_by_relevance(text: str, max_tokens: int) -> str:
        """Truncate keeping sentences with high information density."""
        sentences = re.split(r'(?<=[.!?])\s+', text)
        if len(sentences) <= 3:
            return text[:max_tokens * 4]

        # Score sentences by information density (unique words / total words)
        scored = []
        for s in sentences:
            words = s.lower().split()
            if not words:
                scored.append((0, 0, s))
                continue
            unique_ratio = len(set(words)) / len(words)
            scored.append((unique_ratio, len(s), s))

        scored.sort(key=lambda x: -x[0])

        kept = []
        char_count = 0
        max_chars = max_tokens * 4
        for _, s_len, s in scored:
            if char_count + s_len <= max_chars:
                kept.append(s)
                char_count += s_len
            if char_count >= max_chars:
                break

        return " ".join(kept) if kept else text[:max_chars]

    @staticmethod
    def _truncate_sliding(text: str, max_tokens: int) -> str:
        """Keep a sliding window from the end (most recent content)."""
        return text[-(max_tokens * 4):]

    @staticmethod
    def _summarize_extractive(text: str, target_tokens: int) -> str:
        """Extractive summarization keeping most important sentences."""
        max_chars = target_tokens * 4
        if len(text) <= max_chars:
            return text

        paragraphs = text.split("\n\n")
        if len(paragraphs) <= 1:
            # Single block: keep first + key sentences
            sentences = re.split(r'(?<=[.!?])\s+', text)
            if len(sentences) <= 3:
                return text[:max_chars]

            result = sentences[0]  # Always keep first
            char_count = len(result)

            # Keep sentences with important keywords
            important_words = {
                "important", "critical", "key", "must", "required",
                "essential", "primary", "significant", "crucial", "vital",
                "conclusion", "therefore", "result", "summary", "overview",
            }
            for s in sentences[1:]:
                score = sum(1 for w in important_words if w in s.lower())
                if score > 0 and char_count + len(s) <= max_chars:
                    result += " " + s
                    char_count += len(s)

            if char_count < max_chars and len(sentences) > 1:
                result += " " + sentences[-1]

            return result[:max_chars]
        else:
            # Multi-paragraph: keep first para + first sentence of others
            result = paragraphs[0]
            char_count = len(result)
            for para in paragraphs[1:]:
                sentences = re.split(r'(?<=[.!?])\s+', para)
                first_sent = sentences[0] if sentences else para
                if char_count + len(first_sent) <= max_chars:
                    result += "\n\n" + first_sent
                    char_count += len(first_sent) + 2
                else:
                    break
            return result[:max_chars]

    @staticmethod
    def _summarize_abstractive(text: str, target_tokens: int) -> str:
        """Create an abstractive-style summary (header + key points)."""
        # Extract key sentences as proxy for abstractive
        sentences = re.split(r'(?<=[.!?])\s+', text)
        if len(sentences) <= 5:
            return text[:target_tokens * 4]

        # Header
        first_sentence = sentences[0]
        # Key points from remaining
        key_points = []
        for s in sentences[1:]:
            if any(kw in s.lower() for kw in ["key", "important", "critical", "must", "should", "requires", "need"]):
                key_points.append(f"- {s.strip()}")

        result = f"[Summary] {first_sentence}\n"
        if key_points:
            result += "\nKey Points:\n" + "\n".join(key_points[:10])

        return result[:target_tokens * 4]

    @staticmethod
    def _summarize_hierarchical(text: str, target_tokens: int) -> str:
        """Build a hierarchical outline summary."""
        lines = text.strip().split("\n")
        # Group by heading-like lines (ALL CAPS, Title Case, numbered)
        sections = []
        current_section = []
        current_heading = "Overview"

        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue
            # Detect heading
            if (
                stripped.isupper()
                or re.match(r'^[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*$', stripped)
                or re.match(r'^\d+[\.\)]\s', stripped)
            ):
                if current_section:
                    sections.append((current_heading, current_section))
                current_heading = stripped
                current_section = []
            else:
                current_section.append(stripped)

        if current_section or current_heading != "Overview":
            sections.append((current_heading, current_section))

        # Build outline
        result = []
        for heading, content_lines in sections:
            result.append(f"## {heading}")
            if content_lines:
                # Take first meaningful line
                for cl in content_lines:
                    if len(cl) > 20:
                        result.append(f"  - {cl[:200]}")
                        break

        return "\n".join(result)[:target_tokens * 4]

    @staticmethod
    def _estimate_cost_saved(tokens_saved: int, avg_cost_per_1k: float = 0.003) -> float:
        """Estimate cost savings from token reduction."""
        return round((tokens_saved / 1000) * avg_cost_per_1k, 6)

    def __repr__(self) -> str:
        return (
            f"TokenBudgetManager(budget={self.budget.total}, "
            f"used={sum(self.budget.used.values())}, "
            f"available={self.budget.available})"
        )


import json  # noqa: E402 - used in cache methods