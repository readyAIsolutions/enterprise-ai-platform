"""
Context Optimizer - Enterprise-grade context optimization engine.

Optimization strategies:
- Remove duplicate context blocks
- Remove stale/expired information
- Compress repeated context patterns
- Merge similar instructions
- Rank by relevance
- Detect conflicts
- Detect outdated knowledge
- Preserve critical context (decisions, security, architecture)
"""

from __future__ import annotations

import hashlib
import re
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set, Tuple
from collections import Counter


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class OptimizationStrategy(str, Enum):
    """Available optimization strategies."""
    DEDUPLICATE = "deduplicate"          # Remove duplicate content
    REMOVE_STALE = "remove_stale"        # Remove expired/old content
    COMPRESS_REPEATED = "compress_repeated"  # Compress repeated patterns
    MERGE_SIMILAR = "merge_similar"      # Merge similar instructions
    RANK_RELEVANCE = "rank_relevance"    # Sort by relevance score
    DETECT_CONFLICTS = "detect_conflicts"  # Flag conflicting instructions
    DETECT_OUTDATED = "detect_outdated"  # Flag potentially outdated knowledge
    PRESERVE_CRITICAL = "preserve_critical"  # Ensure critical context is kept
    SUMMARIZE = "summarize"              # Summarize long blocks
    REMOVE_LOW_PRIORITY = "remove_low_priority"  # Remove low-priority blocks
    NORMALIZE = "normalize"              # Normalize formatting


class OptimizerPreset(str, Enum):
    """Pre-configured optimization presets."""
    AGGRESSIVE = "aggressive"      # Maximum compression
    BALANCED = "balanced"          # Good compression, keeps important context
    CONSERVATIVE = "conservative"  # Minimal changes, only clear wins
    SECURITY_FOCUSED = "security"  # Prioritizes security/compliance context
    LATENCY_OPTIMIZED = "latency"  # Optimizes for minimal token usage


# ---------------------------------------------------------------------------
# Data Classes
# ---------------------------------------------------------------------------

@dataclass
class OptimizationAction:
    """A single optimization action taken."""
    strategy: OptimizationStrategy
    target_id: str
    description: str
    before_size: int
    after_size: int
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class OptimizationResult:
    """Full result of an optimization run."""
    strategies_applied: List[OptimizationStrategy]
    actions: List[OptimizationAction]
    original_tokens: int
    optimized_tokens: int
    blocks_removed: int
    blocks_modified: int
    blocks_merged: int
    conflicts_detected: int
    duration_ms: float
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def tokens_saved(self) -> int:
        return self.original_tokens - self.optimized_tokens

    @property
    def compression_ratio(self) -> float:
        if self.original_tokens == 0:
            return 0.0
        return round(self.tokens_saved / self.original_tokens * 100, 2)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "strategies_applied": [s.value for s in self.strategies_applied],
            "actions": [
                {
                    "strategy": a.strategy.value,
                    "target_id": a.target_id,
                    "description": a.description,
                    "before_size": a.before_size,
                    "after_size": a.after_size,
                    "metadata": a.metadata,
                }
                for a in self.actions
            ],
            "original_tokens": self.original_tokens,
            "optimized_tokens": self.optimized_tokens,
            "tokens_saved": self.tokens_saved,
            "compression_ratio": self.compression_ratio,
            "blocks_removed": self.blocks_removed,
            "blocks_modified": self.blocks_modified,
            "blocks_merged": self.blocks_merged,
            "conflicts_detected": self.conflicts_detected,
            "duration_ms": self.duration_ms,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class OptimizerConfig:
    """Configuration for the context optimizer."""
    max_tokens: int = 100_000
    similarity_threshold: float = 0.85        # For deduplication
    staleness_threshold_seconds: int = 3600   # 1 hour
    min_relevance_score: float = 0.1
    max_compression_ratio: float = 0.8        # Max % to compress
    preserve_tags: List[str] = field(default_factory=lambda: [
        "security", "compliance", "immutable", "critical"
    ])
    merge_max_blocks: int = 5                  # Max blocks to merge into one
    summarize_min_tokens: int = 500            # Min tokens to consider summarizing
    summarize_target_ratio: float = 0.3        # Target compression when summarizing


# ---------------------------------------------------------------------------
# Context Optimizer
# ---------------------------------------------------------------------------

class OptimizerError(Exception):
    """Base exception for optimizer errors."""


class ContextOptimizer:
    """
    Enterprise-grade context optimizer.

    Applies multiple optimization strategies to reduce context size while
    preserving critical information. Designed to work with ContextManager
    blocks but can optimize any list of text blocks.

    Usage::

        optimizer = ContextOptimizer()
        result = optimizer.optimize(context_blocks)
        print(f"Saved {result.tokens_saved} tokens ({result.compression_ratio}%)")
    """

    # Predefined presets
    PRESETS: Dict[OptimizerPreset, List[OptimizationStrategy]] = {
        OptimizerPreset.AGGRESSIVE: [
            OptimizationStrategy.REMOVE_STALE,
            OptimizationStrategy.DEDUPLICATE,
            OptimizationStrategy.COMPRESS_REPEATED,
            OptimizationStrategy.MERGE_SIMILAR,
            OptimizationStrategy.REMOVE_LOW_PRIORITY,
            OptimizationStrategy.SUMMARIZE,
            OptimizationStrategy.NORMALIZE,
        ],
        OptimizerPreset.BALANCED: [
            OptimizationStrategy.REMOVE_STALE,
            OptimizationStrategy.DEDUPLICATE,
            OptimizationStrategy.MERGE_SIMILAR,
            OptimizationStrategy.RANK_RELEVANCE,
            OptimizationStrategy.NORMALIZE,
        ],
        OptimizerPreset.CONSERVATIVE: [
            OptimizationStrategy.REMOVE_STALE,
            OptimizationStrategy.DEDUPLICATE,
            OptimizationStrategy.PRESERVE_CRITICAL,
        ],
        OptimizerPreset.SECURITY_FOCUSED: [
            OptimizationStrategy.PRESERVE_CRITICAL,
            OptimizationStrategy.DETECT_CONFLICTS,
            OptimizationStrategy.DETECT_OUTDATED,
            OptimizationStrategy.DEDUPLICATE,
        ],
        OptimizerPreset.LATENCY_OPTIMIZED: [
            OptimizationStrategy.REMOVE_STALE,
            OptimizationStrategy.COMPRESS_REPEATED,
            OptimizationStrategy.RANK_RELEVANCE,
            OptimizationStrategy.REMOVE_LOW_PRIORITY,
            OptimizationStrategy.SUMMARIZE,
        ],
    }

    def __init__(self, config: Optional[OptimizerConfig] = None):
        self.config = config or OptimizerConfig()
        self._lock = threading.RLock()
        self._history: List[OptimizationResult] = []

    # ------------------------------------------------------------------
    # Main Optimization Entry Point
    # ------------------------------------------------------------------

    def optimize(
        self,
        blocks: List[Dict[str, Any]],
        strategies: Optional[List[OptimizationStrategy]] = None,
        preset: Optional[OptimizerPreset] = None,
        dry_run: bool = False,
    ) -> OptimizationResult:
        """
        Run optimization on a list of context blocks.

        Each block dict must have at minimum:
        - id: str
        - content: str
        Optional but recommended:
        - priority: int (higher = more important)
        - type: str (context type)
        - relevance: float (0-1)
        - is_immutable: bool
        - tags: List[str]
        - created_at: str/datetime

        Args:
            blocks: List of context block dicts.
            strategies: Specific strategies to apply.
            preset: Use a predefined strategy set.
            dry_run: If True, don't modify blocks, just report what would happen.

        Returns:
            OptimizationResult with details of all actions taken.
        """
        if preset and not strategies:
            strategies = self.PRESETS.get(preset, self.PRESETS[OptimizerPreset.BALANCED])
        elif not strategies:
            strategies = self.PRESETS[OptimizerPreset.BALANCED]

        start_time = datetime.now(timezone.utc)
        actions: List[OptimizationAction] = []
        original_tokens = sum(self._estimate_tokens(b.get("content", "")) for b in blocks)

        working = list(blocks) if not dry_run else [dict(b) for b in blocks]

        # Apply strategies in order
        for strategy in strategies:
            try:
                strategy_actions = self._apply_strategy(strategy, working, dry_run)
                actions.extend(strategy_actions)
            except Exception as e:
                # Log but continue with other strategies
                actions.append(OptimizationAction(
                    strategy=strategy,
                    target_id="*",
                    description=f"Strategy failed: {e}",
                    before_size=0,
                    after_size=0,
                    metadata={"error": str(e)},
                ))

        optimized_tokens = sum(self._estimate_tokens(b.get("content", "")) for b in working)
        duration = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000

        blocks_removed = sum(
            1 for a in actions
            if a.strategy in (
                OptimizationStrategy.REMOVE_STALE,
                OptimizationStrategy.REMOVE_LOW_PRIORITY,
                OptimizationStrategy.DEDUPLICATE,
            ) and a.after_size == 0
        )
        blocks_modified = sum(
            1 for a in actions
            if a.strategy in (
                OptimizationStrategy.COMPRESS_REPEATED,
                OptimizationStrategy.MERGE_SIMILAR,
                OptimizationStrategy.SUMMARIZE,
                OptimizationStrategy.NORMALIZE,
            )
        )
        blocks_merged = sum(
            1 for a in actions
            if a.strategy == OptimizationStrategy.MERGE_SIMILAR
        )

        result = OptimizationResult(
            strategies_applied=strategies,
            actions=actions,
            original_tokens=original_tokens,
            optimized_tokens=optimized_tokens,
            blocks_removed=blocks_removed,
            blocks_modified=blocks_modified,
            blocks_merged=blocks_merged,
            conflicts_detected=sum(
                1 for a in actions
                if a.strategy == OptimizationStrategy.DETECT_CONFLICTS
            ),
            duration_ms=duration,
        )

        with self._lock:
            self._history.append(result)

        return result

    def optimize_from_manager(
        self,
        context_manager,  # ContextManager instance
        strategies: Optional[List[OptimizationStrategy]] = None,
        preset: Optional[OptimizerPreset] = None,
    ) -> OptimizationResult:
        """
        Optimize directly from a ContextManager instance.
        Returns blocks as dicts, runs optimization, and optionally applies changes.
        """
        try:
            from .context_manager import ContextBlock
        except ImportError:
            from context_manager import ContextBlock

        blocks = []
        for block in context_manager.get_all():
            blocks.append({
                "id": block.id,
                "type": block.type.value if hasattr(block.type, 'value') else str(block.type),
                "content": block.content,
                "priority": block.priority.value if hasattr(block.priority, 'value') else int(block.priority),
                "relevance": block.relevance_score,
                "is_immutable": block.is_immutable,
                "tags": list(block.tags),
                "created_at": block.created_at.isoformat() if hasattr(block.created_at, 'isoformat') else str(block.created_at),
                "_block_ref": block,  # Keep reference to original block
            })

        # Detect conflicts first (informational)
        strategies = strategies or self.PRESETS[OptimizerPreset.BALANCED]

        # Run optimization
        result = self.optimize(blocks, strategies=strategies)

        # Apply some optimizations back to the context manager
        for action in result.actions:
            if action.strategy == OptimizationStrategy.REMOVE_STALE:
                target = next((b for b in blocks if b["id"] == action.target_id), None)
                if target and "_block_ref" in target:
                    try:
                        if not target["is_immutable"]:
                            context_manager.remove(action.target_id, force=False)
                    except Exception:
                        pass

        return result

    # ------------------------------------------------------------------
    # Strategy Implementations
    # ------------------------------------------------------------------

    def _apply_strategy(
        self,
        strategy: OptimizationStrategy,
        blocks: List[Dict[str, Any]],
        dry_run: bool,
    ) -> List[OptimizationAction]:
        """Apply a single optimization strategy."""
        handler = {
            OptimizationStrategy.DEDUPLICATE: self._deduplicate,
            OptimizationStrategy.REMOVE_STALE: self._remove_stale,
            OptimizationStrategy.COMPRESS_REPEATED: self._compress_repeated,
            OptimizationStrategy.MERGE_SIMILAR: self._merge_similar,
            OptimizationStrategy.RANK_RELEVANCE: self._rank_relevance,
            OptimizationStrategy.DETECT_CONFLICTS: self._detect_conflicts,
            OptimizationStrategy.DETECT_OUTDATED: self._detect_outdated,
            OptimizationStrategy.PRESERVE_CRITICAL: self._preserve_critical,
            OptimizationStrategy.SUMMARIZE: self._summarize,
            OptimizationStrategy.REMOVE_LOW_PRIORITY: self._remove_low_priority,
            OptimizationStrategy.NORMALIZE: self._normalize,
        }.get(strategy)

        if handler is None:
            return []

        return handler(blocks, dry_run)

    def _deduplicate(
        self, blocks: List[Dict[str, Any]], dry_run: bool
    ) -> List[OptimizationAction]:
        """Remove duplicate or near-duplicate blocks."""
        actions = []
        to_remove: Set[int] = set()

        for i in range(len(blocks)):
            if i in to_remove:
                continue
            if blocks[i].get("is_immutable"):
                continue
            for j in range(i + 1, len(blocks)):
                if j in to_remove:
                    continue
                if blocks[j].get("is_immutable"):
                    continue

                sim = self._text_similarity(
                    blocks[i].get("content", ""),
                    blocks[j].get("content", ""),
                )
                if sim >= self.config.similarity_threshold:
                    # Remove the lower priority one
                    pri_i = blocks[i].get("priority", 50)
                    pri_j = blocks[j].get("priority", 50)
                    if pri_i >= pri_j:
                        to_remove.add(j)
                    else:
                        to_remove.add(i)
                        break

                    actions.append(OptimizationAction(
                        strategy=OptimizationStrategy.DEDUPLICATE,
                        target_id=blocks[j]["id"] if pri_i >= pri_j else blocks[i]["id"],
                        description=f"Removed duplicate (similarity={sim:.2f})",
                        before_size=self._estimate_tokens(blocks[j]["content"]),
                        after_size=0,
                        metadata={"similarity": sim, "kept_id": blocks[i]["id"] if pri_i >= pri_j else blocks[j]["id"]},
                    ))

        if not dry_run:
            for idx in sorted(to_remove, reverse=True):
                blocks.pop(idx)

        return actions

    def _remove_stale(
        self, blocks: List[Dict[str, Any]], dry_run: bool
    ) -> List[OptimizationAction]:
        """Remove stale/expired context blocks."""
        actions = []
        now = datetime.now(timezone.utc)
        to_remove: Set[int] = set()

        for i, block in enumerate(blocks):
            if block.get("is_immutable"):
                continue
            created = block.get("created_at")
            if created:
                try:
                    if isinstance(created, str):
                        created_dt = datetime.fromisoformat(created)
                    else:
                        created_dt = created
                    age = (now - created_dt).total_seconds()
                    if age > self.config.staleness_threshold_seconds:
                        to_remove.add(i)
                        actions.append(OptimizationAction(
                            strategy=OptimizationStrategy.REMOVE_STALE,
                            target_id=block["id"],
                            description=f"Removed stale block (age={age:.0f}s)",
                            before_size=self._estimate_tokens(block.get("content", "")),
                            after_size=0,
                            metadata={"age_seconds": age},
                        ))
                except (ValueError, TypeError):
                    pass

        if not dry_run:
            for idx in sorted(to_remove, reverse=True):
                blocks.pop(idx)

        return actions

    def _compress_repeated(
        self, blocks: List[Dict[str, Any]], dry_run: bool
    ) -> List[OptimizationAction]:
        """Compress repeated patterns within and across blocks."""
        actions = []
        # Find common phrases repeated across blocks
        all_text = "\n".join(b.get("content", "") for b in blocks if not b.get("is_immutable"))
        phrase_counts = self._find_repeated_phrases(all_text)

        for phrase, count in phrase_counts.items():
            if count >= 3 and len(phrase) > 50:
                # This phrase appears multiple times; we can reference it instead
                for i, block in enumerate(blocks):
                    if block.get("is_immutable"):
                        continue
                    content = block.get("content", "")
                    if phrase in content:
                        old_tokens = self._estimate_tokens(content)
                        # Replace subsequent occurrences with a reference
                        new_content = content.replace(
                            phrase,
                            f"[See above: {phrase[:50]}...]",
                            1,  # Only first occurrence gets abbreviated
                        )
                        blocks[i]["content"] = new_content
                        actions.append(OptimizationAction(
                            strategy=OptimizationStrategy.COMPRESS_REPEATED,
                            target_id=block["id"],
                            description=f"Compressed repeated phrase (count={count})",
                            before_size=old_tokens,
                            after_size=self._estimate_tokens(new_content),
                            metadata={"phrase": phrase[:80], "occurrences": count},
                        ))

        return actions

    def _merge_similar(
        self, blocks: List[Dict[str, Any]], dry_run: bool
    ) -> List[OptimizationAction]:
        """Merge similar instruction blocks."""
        actions = []
        to_remove: Set[int] = set()
        merged: Set[str] = set()

        for i in range(len(blocks)):
            if i in to_remove or blocks[i].get("is_immutable"):
                continue
            group = [i]

            for j in range(i + 1, len(blocks)):
                if j in to_remove or blocks[j].get("is_immutable"):
                    continue
                if blocks[i].get("type") == blocks[j].get("type"):
                    sim = self._text_similarity(
                        blocks[i].get("content", ""),
                        blocks[j].get("content", ""),
                    )
                    if sim >= 0.6:  # Lower threshold for merging vs dedup
                        if len(group) < self.config.merge_max_blocks:
                            group.append(j)

            if len(group) > 1:
                # Merge the group
                merged_content_parts = []
                for idx in group:
                    merged_content_parts.append(blocks[idx].get("content", ""))
                    if idx != group[0]:
                        to_remove.add(idx)

                merged_content = "\n---\n".join(merged_content_parts)
                old_tokens = sum(
                    self._estimate_tokens(blocks[idx].get("content", ""))
                    for idx in group
                )

                blocks[group[0]]["content"] = (
                    f"[MERGED {len(group)} blocks of type {blocks[group[0]].get('type', 'unknown')}]\n"
                    f"{merged_content}"
                )
                merged.add(blocks[group[0]]["id"])

                actions.append(OptimizationAction(
                    strategy=OptimizationStrategy.MERGE_SIMILAR,
                    target_id=blocks[group[0]]["id"],
                    description=f"Merged {len(group)} similar blocks",
                    before_size=old_tokens,
                    after_size=self._estimate_tokens(blocks[group[0]]["content"]),
                    metadata={"merged_ids": [blocks[idx]["id"] for idx in group]},
                ))

        if not dry_run:
            for idx in sorted(to_remove, reverse=True):
                blocks.pop(idx)

        return actions

    def _rank_relevance(
        self, blocks: List[Dict[str, Any]], dry_run: bool
    ) -> List[OptimizationAction]:
        """Sort blocks by relevance and add relevance annotations."""
        actions = []
        for block in blocks:
            relevance = block.get("relevance", 0.5)
            if isinstance(relevance, (int, float)) and relevance < self.config.min_relevance_score:
                if not block.get("is_immutable"):
                    block["_low_relevance"] = True
                actions.append(OptimizationAction(
                    strategy=OptimizationStrategy.RANK_RELEVANCE,
                    target_id=block["id"],
                    description=f"Flagged low relevance (score={relevance:.2f})",
                    before_size=self._estimate_tokens(block.get("content", "")),
                    after_size=self._estimate_tokens(block.get("content", "")),
                    metadata={"relevance_score": relevance},
                ))

        # Sort by relevance descending
        if not dry_run:
            blocks.sort(
                key=lambda b: (
                    not b.get("is_immutable", False),
                    -(b.get("relevance", 0.5) if isinstance(b.get("relevance"), (int, float)) else 0.5),
                )
            )

        return actions

    def _detect_conflicts(
        self, blocks: List[Dict[str, Any]], dry_run: bool
    ) -> List[OptimizationAction]:
        """Detect conflicting instructions between blocks."""
        actions = []
        contradiction_markers = [
            ("must", "must not"),
            ("always", "never"),
            ("required", "prohibited"),
            ("allow", "deny"),
            ("include", "exclude"),
            ("enable", "disable"),
            ("grant", "revoke"),
        ]

        for i in range(len(blocks)):
            for j in range(i + 1, len(blocks)):
                a_content = blocks[i].get("content", "").lower()
                b_content = blocks[j].get("content", "").lower()

                for pos, neg in contradiction_markers:
                    if pos in a_content and neg in b_content:
                        actions.append(OptimizationAction(
                            strategy=OptimizationStrategy.DETECT_CONFLICTS,
                            target_id=f"{blocks[i]['id']}:{blocks[j]['id']}",
                            description=f"Potential conflict: '{pos}' vs '{neg}'",
                            before_size=0,
                            after_size=0,
                            metadata={
                                "block_a": blocks[i]["id"],
                                "block_b": blocks[j]["id"],
                                "pattern": f"{pos}/{neg}",
                                "severity": "high",
                            },
                        ))
                    elif neg in a_content and pos in b_content:
                        actions.append(OptimizationAction(
                            strategy=OptimizationStrategy.DETECT_CONFLICTS,
                            target_id=f"{blocks[j]['id']}:{blocks[i]['id']}",
                            description=f"Potential conflict: '{neg}' vs '{pos}'",
                            before_size=0,
                            after_size=0,
                            metadata={
                                "block_a": blocks[j]["id"],
                                "block_b": blocks[i]["id"],
                                "pattern": f"{neg}/{pos}",
                                "severity": "high",
                            },
                        ))

        return actions

    def _detect_outdated(
        self, blocks: List[Dict[str, Any]], dry_run: bool
    ) -> List[OptimizationAction]:
        """Detect potentially outdated knowledge blocks."""
        actions = []
        outdated_markers = [
            r"as of \d{4}",
            r"version \d+\.\d+",
            r"deprecated",
            r"no longer supported",
            r"legacy",
            r"obsolete",
            r"outdated",
        ]

        for block in blocks:
            content = block.get("content", "")
            for pattern in outdated_markers:
                if re.search(pattern, content, re.IGNORECASE):
                    actions.append(OptimizationAction(
                        strategy=OptimizationStrategy.DETECT_OUTDATED,
                        target_id=block["id"],
                        description=f"Potentially outdated: matches '{pattern}'",
                        before_size=self._estimate_tokens(content),
                        after_size=self._estimate_tokens(content),
                        metadata={
                            "pattern": pattern,
                            "match": re.search(pattern, content, re.IGNORECASE).group(),
                        },
                    ))
                    break  # One flag per block is enough

        return actions

    def _preserve_critical(
        self, blocks: List[Dict[str, Any]], dry_run: bool
    ) -> List[OptimizationAction]:
        """Ensure critical blocks are marked as preserved."""
        actions = []
        preserve_tags = set(self.config.preserve_tags)

        for block in blocks:
            tags = set(block.get("tags", []))
            is_immutable = block.get("is_immutable", False)
            priority = block.get("priority", 50)

            should_preserve = (
                is_immutable
                or bool(preserve_tags & tags)
                or priority >= 90  # Near-critical priority
            )

            if should_preserve and not block.get("_preserved"):
                block["_preserved"] = True
                actions.append(OptimizationAction(
                    strategy=OptimizationStrategy.PRESERVE_CRITICAL,
                    target_id=block["id"],
                    description="Marked as critical (preserved from eviction)",
                    before_size=self._estimate_tokens(block.get("content", "")),
                    after_size=self._estimate_tokens(block.get("content", "")),
                    metadata={"reason": "immutable" if is_immutable else "tag_or_priority"},
                ))

        return actions

    def _summarize(
        self, blocks: List[Dict[str, Any]], dry_run: bool
    ) -> List[OptimizationAction]:
        """Summarize long text blocks."""
        actions = []
        for i, block in enumerate(blocks):
            if block.get("is_immutable") or block.get("_preserved"):
                continue

            content = block.get("content", "")
            tokens = self._estimate_tokens(content)

            if tokens >= self.config.summarize_min_tokens:
                summary = self._extractive_summarize(
                    content,
                    target_ratio=self.config.summarize_target_ratio,
                )
                old_tokens = tokens
                blocks[i]["content"] = summary
                blocks[i]["_was_summarized"] = True

                actions.append(OptimizationAction(
                    strategy=OptimizationStrategy.SUMMARIZE,
                    target_id=block["id"],
                    description=f"Summarized ({old_tokens} -> {self._estimate_tokens(summary)} tokens)",
                    before_size=old_tokens,
                    after_size=self._estimate_tokens(summary),
                    metadata={
                        "original_tokens": old_tokens,
                        "summarized_tokens": self._estimate_tokens(summary),
                        "compression": round((1 - self._estimate_tokens(summary) / old_tokens) * 100, 1),
                    },
                ))

        return actions

    def _remove_low_priority(
        self, blocks: List[Dict[str, Any]], dry_run: bool
    ) -> List[OptimizationAction]:
        """Remove low-priority blocks when over budget."""
        actions = []
        total_tokens = sum(self._estimate_tokens(b.get("content", "")) for b in blocks)

        if total_tokens <= self.config.max_tokens:
            return actions

        # Sort by priority ascending, remove lowest first
        evictable = sorted(
            [b for b in blocks if not b.get("is_immutable") and not b.get("_preserved")],
            key=lambda b: b.get("priority", 50),
        )

        to_remove: Set[int] = set()
        for block in evictable:
            if total_tokens <= self.config.max_tokens:
                break
            idx = blocks.index(block)
            to_remove.add(idx)
            total_tokens -= self._estimate_tokens(block.get("content", ""))

            actions.append(OptimizationAction(
                strategy=OptimizationStrategy.REMOVE_LOW_PRIORITY,
                target_id=block["id"],
                description=f"Removed low-priority block (priority={block.get('priority', 50)})",
                before_size=self._estimate_tokens(block.get("content", "")),
                after_size=0,
                metadata={"priority": block.get("priority", 50)},
            ))

        if not dry_run:
            for idx in sorted(to_remove, reverse=True):
                blocks.pop(idx)

        return actions

    def _normalize(
        self, blocks: List[Dict[str, Any]], dry_run: bool
    ) -> List[OptimizationAction]:
        """Normalize formatting: whitespace, line endings, etc."""
        actions = []
        for i, block in enumerate(blocks):
            content = block.get("content", "")
            old_tokens = self._estimate_tokens(content)

            # Normalize newlines
            normalized = content.replace("\r\n", "\n").replace("\r", "\n")
            # Collapse multiple blank lines
            normalized = re.sub(r"\n{3,}", "\n\n", normalized)
            # Strip trailing whitespace
            normalized = "\n".join(line.rstrip() for line in normalized.split("\n"))
            # Normalize leading/trailing whitespace
            normalized = normalized.strip()

            if normalized != content:
                blocks[i]["content"] = normalized
                actions.append(OptimizationAction(
                    strategy=OptimizationStrategy.NORMALIZE,
                    target_id=block["id"],
                    description=f"Normalized formatting (saved {old_tokens - self._estimate_tokens(normalized)} tokens)",
                    before_size=old_tokens,
                    after_size=self._estimate_tokens(normalized),
                ))

        return actions

    # ------------------------------------------------------------------
    # Utility Methods
    # ------------------------------------------------------------------

    def get_history(self, limit: int = 10) -> List[OptimizationResult]:
        """Get recent optimization history."""
        with self._lock:
            return self._history[-limit:]

    def get_stats(self) -> Dict[str, Any]:
        """Get aggregate optimization statistics."""
        with self._lock:
            if not self._history:
                return {"runs": 0}

            total_saved = sum(r.tokens_saved for r in self._history)
            avg_ratio = sum(r.compression_ratio for r in self._history) / len(self._history)

            strategy_counts = Counter()
            for r in self._history:
                for s in r.strategies_applied:
                    strategy_counts[s.value] += 1

            return {
                "runs": len(self._history),
                "total_tokens_saved": total_saved,
                "avg_compression_ratio": round(avg_ratio, 2),
                "most_used_strategies": strategy_counts.most_common(5),
                "last_run": self._history[-1].timestamp.isoformat(),
            }

    # ------------------------------------------------------------------
    # Internal Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _estimate_tokens(text: str) -> int:
        """Rough token estimate (4 chars ~= 1 token)."""
        return max(1, len(text) // 4)

    @staticmethod
    def _text_similarity(a: str, b: str) -> float:
        """Jaccard similarity based on word sets."""
        words_a = set(a.lower().split())
        words_b = set(b.lower().split())
        if not words_a or not words_b:
            return 0.0
        return len(words_a & words_b) / len(words_a | words_b)

    @staticmethod
    def _find_repeated_phrases(text: str, min_length: int = 50) -> Dict[str, int]:
        """Find phrases that repeat in the text."""
        words = text.split()
        phrases: Dict[str, int] = {}
        seen: Set[str] = set()

        for i in range(len(words)):
            for j in range(i + 5, min(i + 30, len(words) + 1)):
                phrase = " ".join(words[i:j])
                if len(phrase) < min_length:
                    continue
                if phrase in seen:
                    continue
                seen.add(phrase)
                count = text.count(phrase)
                if count >= 3:
                    phrases[phrase] = count

        return phrases

    @staticmethod
    def _extractive_summarize(text: str, target_ratio: float = 0.3) -> str:
        """
        Simple extractive summarization: keep first and last paragraphs
        plus key sentences from the middle.
        """
        paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
        if len(paragraphs) <= 3:
            return text

        # Keep first paragraph (usually intro)
        # Keep last paragraph (usually conclusion)
        # Select key sentences from middle with compression
        kept = [paragraphs[0]]

        middle_paras = paragraphs[1:-1]
        target_middle = max(1, int(len(text) * target_ratio / max(1, len(middle_paras))))

        for para in middle_paras:
            sentences = re.split(r"(?<=[.!?])\s+", para)
            if len(sentences) <= 2:
                kept.append(para)
            else:
                # Keep first and last sentence of each middle paragraph
                summary_sentences = [sentences[0]]
                if len(sentences) > 2:
                    summary_sentences.append(sentences[-1])
                kept.append(" ".join(summary_sentences))

        kept.append(paragraphs[-1])

        result = "\n\n".join(kept)
        return result if result else text

    def __repr__(self) -> str:
        stats = self.get_stats()
        return (
            f"ContextOptimizer(runs={stats.get('runs', 0)}, "
            f"saved={stats.get('total_tokens_saved', 0)} tokens)"
        )