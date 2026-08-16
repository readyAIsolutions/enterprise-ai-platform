"""Pure AI Memory Hierarchy core — grounded in the JEVanClief transcript.

Transcript: "How a 1953 Word Game Explains AI Memory"
(https://www.youtube.com/watch?v=S3fXSc5z2n4, 14.4 min).

The transcript parallels the *hardware* memory hierarchy (registers -> cache ->
RAM -> disk -> archival tape, a speed-vs-capacity tradeoff with
locality-based staging) against an *AI* memory hierarchy:

  - model weights  ~ ROM            (read-only, fixed at training time)
  - context window ~ working memory / RAM (temporary, per-conversation)
  - system prompt  ~ firmware       (sets the operating parameters)
  - retrieved ctx  ~ disk -> RAM on demand (query-driven loading)
  - persistent mem ~ selectively loaded summaries kept between conversations

And crucially: *in AI, code and data are the same thing* — the system prompt,
skill files, and conversation history are all just text, all processed
identically, all tokens in a sequence. There is "no separate layer that
validates code versus data," so reading is the execution.

This module is stdlib-only and network-free. It models the five tiers above,
with a locality/access-count based promotion/demotion policy (hot vs cold),
capacity limits per tier, insertion, keyword/overlap query retrieval, and a
tier summary.

Tier ranks (0 = hottest, 4 = coldest):

  WEIGHTS(4) PROMPT(3) PERSISTENT(2) RETRIEVED(1) WORKING(0)

Promotion moves an entry to a hotter (lower-rank) tier; demotion moves it to a
colder (higher-rank) tier. The dynamic promotion chain runs over the
memory tiers WORKING / RETRIEVED / PERSISTENT. WEIGHTS is ROM: read-only after
it is "trained" (locked). PROMPT is firmware: it holds the operating
parameters and is treated as a fixed configuration store.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Iterable, Optional

__all__ = [
    "TIERS",
    "DEFAULT_CAPACITIES",
    "DEFAULT_PROMOTE_THRESHOLD",
    "Tier",
    "MemoryEntry",
    "MemoryHierarchy",
    "TierLockedError",
    "tokenize",
    "overlap_score",
]


class Tier(Enum):
    """The five tiers of the AI memory hierarchy (transcript-grounded)."""

    WEIGHTS = "weights"  # model weights ~ ROM (read-only, fixed at training)
    PROMPT = "prompt"  # system prompt ~ firmware (operating parameters)
    PERSISTENT = "persistent"  # selectively-loaded summaries between convos
    RETRIEVED = "retrieved"  # disk -> RAM on demand (query-driven)
    WORKING = "working"  # context window ~ working memory / RAM (hot)


#: Tier -> rank. Lower rank = hotter / closer to the processor (context).
TIER_RANK: dict[Tier, int] = {
    Tier.WORKING: 0,
    Tier.RETRIEVED: 1,
    Tier.PERSISTENT: 2,
    Tier.PROMPT: 3,
    Tier.WEIGHTS: 4,
}

#: Tiers that participate in the dynamic promotion/demotion chain.
MEMORY_TIERS: tuple[Tier, ...] = (Tier.WORKING, Tier.RETRIEVED, Tier.PERSISTENT)

TIERS: tuple[str, ...] = tuple(t.value for t in Tier)

#: Default item capacity per tier.
DEFAULT_CAPACITIES: dict[Tier, int] = {
    Tier.WORKING: 8,  # context window is hot but small (working memory)
    Tier.RETRIEVED: 12,  # pulled on demand
    Tier.PERSISTENT: 16,  # selectively loaded summaries
    Tier.PROMPT: 4,  # firmware / operating parameters
    Tier.WEIGHTS: 32,  # ROM — large, fixed knowledge
}

#: Number of accesses that triggers a promotion to a hotter tier.
DEFAULT_PROMOTE_THRESHOLD: int = 2


class TierLockedError(RuntimeError):
    """Raised when writing to a read-only tier (WEIGHTS ~ ROM)."""


def tokenize(text: str) -> list[str]:
    """Split text into lowercased word tokens (stdlib ``re`` only)."""
    return re.findall(r"[a-zA-Z0-9]+", (text or "").lower())


def overlap_score(query_tokens: Iterable[str], content_tokens: Iterable[str]) -> int:
    """Count how many distinct query tokens appear in the content tokens."""
    q = set(query_tokens)
    c = set(content_tokens)
    if not q:
        return 0
    return len(q & c)


@dataclass
class MemoryEntry:
    """A single stored memory item with locality bookkeeping."""

    key: str
    content: str
    tier: Tier
    access_count: int = 0
    #: monotonic recency counters (higher = more recent)
    last_access: int = 0
    created: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def hotness(self) -> tuple[int, int, int]:
        """Coldness key — lower access_count / older = colder. Used for eviction."""
        return (self.access_count, self.last_access, self.created)


class MemoryHierarchy:
    """A network-free model of the AI memory hierarchy.

    Args:
        capacities: Optional mapping of Tier -> max items. Defaults to
            :data:`DEFAULT_CAPACITIES`.
        promote_threshold: Accesses after which a memory-tier entry promotes.
            Defaults to :data:`DEFAULT_PROMOTE_THRESHOLD`.
    """

    def __init__(
        self,
        capacities: Optional[dict[Tier, int]] = None,
        promote_threshold: int = DEFAULT_PROMOTE_THRESHOLD,
    ) -> None:
        self.capacities: dict[Tier, int] = dict(DEFAULT_CAPACITIES)
        if capacities:
            for tier, cap in capacities.items():
                self.capacities[tier] = max(0, int(cap))
        if promote_threshold < 1:
            raise ValueError("promote_threshold must be >= 1")
        self.promote_threshold = promote_threshold

        self._items: dict[str, MemoryEntry] = {}
        self._tiers: dict[Tier, dict[str, MemoryEntry]] = {
            t: {} for t in Tier
        }
        #: model weights are ROM — locked once "trained".
        self._weights_locked: bool = False
        self._clock: int = 0

    # ------------------------------------------------------------------ util
    def _tick(self) -> int:
        self._clock += 1
        return self._clock

    def _count(self, tier: Tier) -> int:
        return len(self._tiers[tier])

    def capacity(self, tier: Tier) -> int:
        return self.capacities[tier]

    # ------------------------------------------------------------- insertion
    def _place(self, entry: MemoryEntry) -> None:
        """Insert an entry, evicting the coldest overflow to a colder tier."""
        tier = entry.tier
        if tier is Tier.WEIGHTS and self._weights_locked:
            raise TierLockedError("model weights are ROM — read-only once trained")
        bucket = self._tiers[tier]
        if entry.key in bucket:
            # replace in place
            bucket[entry.key] = entry
            self._items[entry.key] = entry
            return
        while self._count(tier) >= self.capacity(tier):
            victim = self._coldest(tier)
            if victim is None:
                break
            self._evict(victim)
        bucket[entry.key] = entry
        self._items[entry.key] = entry

    def _coldest(self, tier: Tier) -> Optional[MemoryEntry]:
        """The coldest (least-accessed / oldest) entry in a tier."""
        bucket = self._tiers[tier]
        if not bucket:
            return None
        return min(bucket.values(), key=lambda e: e.hotness)

    def _evict(self, entry: MemoryEntry) -> None:
        """Remove an entry and (for memory tiers) demote it one tier colder."""
        src = entry.tier
        bucket = self._tiers[src]
        bucket.pop(entry.key, None)
        self._items.pop(entry.key, None)
        # Demote within the dynamic memory chain; dropping from PERSISTENT =
        # falling out of cold storage entirely.
        if src in MEMORY_TIERS:
            nxt = self._next_colder(src)
            if nxt is not None:
                entry.tier = nxt
                self._place(entry)

    def _next_colder(self, tier: Tier) -> Optional[Tier]:
        order = (Tier.WORKING, Tier.RETRIEVED, Tier.PERSISTENT)
        if tier not in order:
            return None
        idx = order.index(tier)
        if idx + 1 < len(order):
            return order[idx + 1]
        return None  # PERSISTENT is the coldest memory tier — drop

    def insert(
        self,
        key: str,
        content: str,
        tier: Tier | None = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> MemoryEntry:
        """Store ``content`` under ``key``.

        If ``tier`` is None the item is placed in the hottest memory tier
        (WORKING) if space allows, otherwise it cascades to a colder memory
        tier. Inserting or replacing into a locked WEIGHTS tier raises
        :class:`TierLockedError`.
        """
        if tier is None:
            tier = self._first_available_memory_tier()
        entry = MemoryEntry(
            key=key,
            content=str(content),
            tier=tier,
            created=self._tick(),
            last_access=self._clock,
            metadata=dict(metadata or {}),
        )
        self._place(entry)
        return entry

    def _first_available_memory_tier(self) -> Tier:
        for t in MEMORY_TIERS:  # hottest -> coldest
            if self._count(t) < self.capacity(t):
                return t
        return Tier.PERSISTENT

    # ------------------------------------------------------------- weights
    def set_weights(self, key: str, content: str) -> MemoryEntry:
        """"Train" a model weight (ROM) before it is locked.

        Raises :class:`TierLockedError` once weights have been locked /
        read-only (i.e. after :meth:`lock_weights`).
        """
        if self._weights_locked:
            raise TierLockedError("model weights are ROM — read-only once trained")
        return self.insert(key, content, tier=Tier.WEIGHTS)

    def lock_weights(self) -> None:
        """Lock model weights (ROM) so no further writing is allowed."""
        self._weights_locked = True

    @property
    def weights_locked(self) -> bool:
        return self._weights_locked

    # ------------------------------------------------------------- firmware
    def set_prompt(self, key: str, content: str) -> MemoryEntry:
        """Write a system-prompt (firmware) operating-parameter entry."""
        return self.insert(key, content, tier=Tier.PROMPT)

    # ------------------------------------------------------------- access
    def access(self, key: str) -> Optional[MemoryEntry]:
        """Record a locality access on ``key`` (promotes hot entries)."""
        entry = self._items.get(key)
        if entry is None:
            return None
        entry.access_count += 1
        entry.last_access = self._tick()
        if entry.tier in MEMORY_TIERS:
            self._maybe_promote(entry)
        return entry

    def _maybe_promote(self, entry: MemoryEntry) -> None:
        if entry.access_count % self.promote_threshold != 0:
            return
        hotter = self._next_hotter(entry.tier)
        if hotter is None:
            return
        src = entry.tier
        self._tiers[src].pop(entry.key, None)
        entry.tier = hotter
        self._place(entry)

    def _next_hotter(self, tier: Tier) -> Optional[Tier]:
        order = (Tier.WORKING, Tier.RETRIEVED, Tier.PERSISTENT)
        if tier not in order:
            return None
        idx = order.index(tier)
        if idx > 0:
            return order[idx - 1]
        return None  # WORKING is the hottest memory tier

    # ------------------------------------------------------------- promote/demote
    def promote(self, key: str) -> Optional[MemoryEntry]:
        """Manually promote ``key`` one tier hotter (hot <= persisted data)."""
        entry = self._items.get(key)
        if entry is None:
            return None
        hotter = self._next_hotter(entry.tier)
        if hotter is None or entry.tier not in MEMORY_TIERS:
            return entry
        self._tiers[entry.tier].pop(key, None)
        entry.tier = hotter
        self._place(entry)
        return entry

    def demote(self, key: str) -> Optional[MemoryEntry]:
        """Manually demote ``key`` one tier colder (cold <= frequently used)."""
        entry = self._items.get(key)
        if entry is None:
            return None
        colder = self._next_colder(entry.tier)
        if colder is None or entry.tier not in MEMORY_TIERS:
            return entry
        self._tiers[entry.tier].pop(key, None)
        entry.tier = colder
        self._place(entry)
        return entry

    # ------------------------------------------------------------- retrieval
    def retrieve(
        self,
        query: str,
        limit: int = 5,
        include_tiers: Optional[Iterable[Tier]] = None,
    ) -> list[MemoryEntry]:
        """Return entries ranked by keyword/overlap relevance.

        Ranking (transcript: retrieved context is pulled dynamically based on a
        query, like loading disk -> RAM on demand): primary = overlap score
        (count of distinct query tokens present), secondary = tier hotness
        (hotter tier first), tertiary = access frequency.

        Retrieval counts as a locality access, so hot items promote.
        """
        q = tokenize(query)
        tiers = list(include_tiers) if include_tiers is not None else list(Tier)
        scored: list[tuple[int, int, int, MemoryEntry]] = []
        for tier in tiers:
            for entry in self._tiers[tier].values():
                sc = overlap_score(q, tokenize(entry.content))
                if sc == 0:
                    continue
                rank = TIER_RANK[entry.tier]
                scored.append((sc, -rank, entry.access_count, entry))
        # highest overlap, hottest tier, most-accessed first
        scored.sort(key=lambda x: (-x[0], -x[1], -x[2]))
        hits = [e for (_, _, _, e) in scored[: max(0, limit)]]
        for e in hits:
            self.access(e.key)  # query-driven loading counts as locality access
        return hits

    # ------------------------------------------------------------- summary
    def tier_summary(self) -> dict[str, dict[str, Any]]:
        """Return per-tier item counts and details."""
        summary: dict[str, dict[str, Any]] = {}
        for tier in Tier:
            bucket = self._tiers[tier]
            items = sorted(
                (e.key, e.access_count) for e in bucket.values()
            )
            summary[tier.value] = {
                "capacity": self.capacities[tier],
                "count": len(bucket),
                "items": items,
            }
        return summary

    def stats(self) -> dict[str, Any]:
        """Global statistics for health checks."""
        total = sum(len(b) for b in self._tiers.values())
        access = sum(e.access_count for e in self._items.values())
        return {
            "total_items": total,
            "total_accesses": access,
            "weights_locked": self._weights_locked,
            "tiers": len(Tier),
        }

    def get(self, key: str) -> Optional[MemoryEntry]:
        return self._items.get(key)

    def clear(self) -> None:
        """Remove all entries and relock-free state (keeps configured caps)."""
        self._items.clear()
        for t in Tier:
            self._tiers[t].clear()
        self._weights_locked = False
        self._clock = 0
