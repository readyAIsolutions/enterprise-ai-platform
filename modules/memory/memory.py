"""Agent Memory Core — dependency-free mem0-style long-term memory engine.

A lightweight, stdlib-only long-term memory engine inspired by mem0:

  * Four memory types: ``semantic`` / ``episodic`` / ``declarative`` /
    ``procedural``.
  * Per-user memory profiles — every entry is scoped by ``user_id``.
  * ``HashEmbedder`` — deterministic feature-hash bag-of-tokens embedding
    (re-implemented here so the module is standalone / CI-safe) with an
    L2-normalised dense vector and a pure-Python ``cosine_similarity``.
  * Relevance / importance / recency combined ranking.
  * Consolidation & de-duplication — merge near-duplicate entries and
    enforce a per-type limit.
  * Persistent SQLite storage (via the stdlib ``sqlite3`` module) with the
    database path supplied by the module configuration.

``AgentMemory`` is the high-level facade; ``MemoryStore`` owns persistence
and ranking; ``MemoryEntry`` is the stored record dataclass.

No external packages are required. Python 3.11+.

Version: 1.0.0
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import sqlite3
import statistics
import threading
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Sequence

__all__ = [
    "MEMORY_TYPES",
    "DEFAULT_MEMORY_TYPE",
    "HashEmbedder",
    "MemoryEntry",
    "ScoredMemory",
    "MemoryContext",
    "MemoryStore",
    "AgentMemory",
    "cosine_similarity",
    "dot",
    "normalize",
]

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MEMORY_TYPES: tuple[str, ...] = (
    "semantic",
    "episodic",
    "declarative",
    "procedural",
)
"""Valid long-term memory types."""

DEFAULT_MEMORY_TYPE: str = "semantic"
"""Fallback memory type when none is supplied."""

# A token is a run of alphanumeric characters (letters/digits/underscore).
_TOKEN_RE = re.compile(r"[a-z0-9_]+")

_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)


# ---------------------------------------------------------------------------
# Vector math helpers
# ---------------------------------------------------------------------------


def dot(a: Sequence[float], b: Sequence[float]) -> float:
    """Return the dot product of two equal-length vectors."""
    if len(a) != len(b):
        msg = "Vector dimension mismatch in dot product"
        raise ValueError(msg)
    return float(sum(x * y for x, y in zip(a, b, strict=True)))


def normalize(vec: Sequence[float]) -> list[float]:
    """Return a copy of ``vec`` scaled to unit L2 norm (all-zero unchanged)."""
    norm = math.sqrt(sum(x * x for x in vec))
    if norm == 0.0:
        return list(vec)
    return [x / norm for x in vec]


def cosine_similarity(a: Sequence[float], b: Sequence[float]) -> float:
    """Cosine similarity of two vectors in ``[-1.0, 1.0]`` (0.0 if either is zero)."""
    if len(a) != len(b):
        msg = "Vector dimension mismatch in cosine similarity"
        raise ValueError(msg)
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return sum(x * y for x, y in zip(a, b, strict=True)) / (norm_a * norm_b)


# ---------------------------------------------------------------------------
# Embedder
# ---------------------------------------------------------------------------


class HashEmbedder:
    """Deterministic feature-hash bag-of-tokens embedder.

    Maps each lowercase alphanumeric token to a fixed bucket using SHA-1,
    applies a sign trick (hash parity decides the sign) to reduce collision
    interference, then L2-normalises the resulting dense vector.

    Deterministic: the same input text always produces the identical vector.
    """

    __slots__ = ("_dim", "_salt")

    def __init__(self, dim: int = 128) -> None:
        if not isinstance(dim, int) or dim <= 0:
            msg = "dim must be a positive integer"
            raise ValueError(msg)
        self._dim = dim
        self._salt = b"eni-agent-memory-v1"

    @property
    def dim(self) -> int:
        """Embedding dimensionality."""
        return self._dim

    def _token_bucket(self, token: str) -> int:
        digest = hashlib.sha1(self._salt + token.encode("utf-8", "ignore")).digest()
        return int.from_bytes(digest[:8], "big") % self._dim

    def _token_sign(self, token: str) -> float:
        digest = hashlib.sha1(token.encode("utf-8", "ignore")).digest()
        return 1.0 if digest[0] % 2 == 0 else -1.0

    def embed(self, text: str) -> list[float]:
        """Embed text into a unit-length vector of size ``dim``.

        Empty text yields the zero vector. Repeated tokens within a document
        are counted once (bag-of-words semantics).
        """
        vec = [0.0] * self._dim
        seen_buckets: set[int] = set()
        for token in _TOKEN_RE.findall(str(text).lower()):
            bucket = self._token_bucket(token)
            if bucket in seen_buckets:
                continue
            seen_buckets.add(bucket)
            vec[bucket] += self._token_sign(token)
        return normalize(vec)


# ---------------------------------------------------------------------------
# Records
# ---------------------------------------------------------------------------


def _now_iso() -> str:
    """Current UTC time as an ISO-8601 string."""
    return datetime.now(UTC).isoformat()


def _parse_iso(value: str) -> float:
    """Return an epoch-seconds float for an ISO timestamp (0.0 if unparseable)."""
    try:
        dt = datetime.fromisoformat(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return (dt - _EPOCH).total_seconds()
    except (TypeError, ValueError):
        return 0.0


@dataclass
class MemoryEntry:
    """A single stored long-term memory record.

    Attributes:
        id: Unique memory identifier.
        user_id: Owner of this memory profile.
        memory_type: One of :data:`MEMORY_TYPES`.
        content: The stored memory text.
        metadata: Arbitrary key-value metadata.
        importance: Float in ``[0.0, 1.0]`` indicating salience.
        created_at: ISO-8601 UTC creation timestamp.
        updated_at: ISO-8601 UTC last modification timestamp.
        last_access_at: ISO-8601 UTC last retrieval timestamp.
        access_count: Number of times this memory was retrieved.
    """

    id: str
    user_id: str
    memory_type: str
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)
    importance: float = 0.5
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)
    last_access_at: str = field(default_factory=_now_iso)
    access_count: int = 0

    # -- serialization -------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        """Return a plain JSON-serialisable dict for this entry."""
        return {
            "id": self.id,
            "user_id": self.user_id,
            "memory_type": self.memory_type,
            "content": self.content,
            "metadata": dict(self.metadata),
            "importance": self.importance,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "last_access_at": self.last_access_at,
            "access_count": self.access_count,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MemoryEntry:
        """Build a :class:`MemoryEntry` from a dict (as produced by ``to_dict``)."""
        raw_meta = data.get("metadata")
        if isinstance(raw_meta, str):
            try:
                parsed_meta: Any = json.loads(raw_meta)
            except (TypeError, ValueError):
                parsed_meta = {}
        else:
            parsed_meta = raw_meta or {}
        return cls(
            id=str(data.get("id") or ""),
            user_id=str(data.get("user_id") or ""),
            memory_type=str(data.get("memory_type") or DEFAULT_MEMORY_TYPE),
            content=str(data.get("content") or ""),
            metadata=dict(parsed_meta or {}),
            importance=float(data.get("importance", 0.5) or 0.5),
            created_at=str(data.get("created_at") or _now_iso()),
            updated_at=str(data.get("updated_at") or _now_iso()),
            last_access_at=str(data.get("last_access_at") or _now_iso()),
            access_count=int(data.get("access_count", 0) or 0),
        )


@dataclass
class ScoredMemory:
    """A search hit: a memory paired with its composite relevance score."""

    memory: MemoryEntry
    score: float

    @property
    def id(self) -> str:
        return self.memory.id

    def to_dict(self) -> dict[str, Any]:
        """Return a plain dict with the memory and its score."""
        return {"memory": self.memory.to_dict(), "score": self.score}


@dataclass
class MemoryContext:
    """A grouped memory context blob for prompt injection.

    Attributes:
        context: Human-readable concatenated memory context string.
        memories: The ranked :class:`ScoredMemory` results.
        query: The query that produced this context.
    """

    query: str
    context: str
    memories: list[ScoredMemory] = field(default_factory=list)

    def to_text(self) -> str:
        """Return the raw ``context`` string."""
        return self.context


# ---------------------------------------------------------------------------
# Store
# ---------------------------------------------------------------------------


def _matches_filter(metadata: dict[str, Any], metadata_filter: dict[str, Any]) -> bool:
    """Return True if every filter key/value appears in ``metadata``."""
    metadata_filter = metadata_filter or {}
    if not metadata_filter:
        return True
    if not metadata:
        return False
    return all(metadata.get(key) == value for key, value in metadata_filter.items())


class MemoryStore:
    """Persistent store for agent memory with deterministic retrieval ranking.

    Backed by both an in-memory dict (for fast ranking) and a SQLite database
    (for durability across reopens). Thread-safe via an internal ``RLock``.

    Args:
        database_path: Path to the SQLite database file (or ``:memory:``).
        embedder: Embedder used for retrieval vectors. Defaults to a
            :class:`HashEmbedder`.
    """

    def __init__(
        self,
        database_path: str = ":memory:",
        embedder: HashEmbedder | None = None,
    ) -> None:
        self._database_path: str = database_path
        self._embedder: HashEmbedder = (
            embedder if embedder is not None else HashEmbedder()
        )
        self._entries: dict[str, MemoryEntry] = {}
        self._vectors: dict[str, list[float]] = {}
        self._lock = threading.RLock()
        # Reuse a single connection guarded by the lock; safe enough for a
        # per-instance store used by one module.
        self._conn = sqlite3.connect(database_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()
        self._load()

    # -- internals ----------------------------------------------------------

    def _init_schema(self) -> None:
        with self._lock:
            cur = self._conn.cursor()
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS memories (
                    id            TEXT PRIMARY KEY,
                    user_id       TEXT NOT NULL,
                    memory_type   TEXT NOT NULL,
                    content       TEXT NOT NULL,
                    metadata      TEXT NOT NULL,
                    importance    REAL NOT NULL,
                    created_at    TEXT NOT NULL,
                    updated_at    TEXT NOT NULL,
                    last_access_at TEXT NOT NULL,
                    access_count  INTEGER NOT NULL
                )
                """
            )
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_memories_user ON memories(user_id)"
            )
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_memories_type ON memories(memory_type)"
            )
            self._conn.commit()

    def _load(self) -> None:
        """Hydrate the in-memory index from the SQLite database."""
        with self._lock:
            cur = self._conn.cursor()
            cur.execute("SELECT * FROM memories")
            for row in cur.fetchall():
                columns = row.keys()
                row_dict = {columns[i]: row[i] for i in range(len(columns))}
                entry = MemoryEntry.from_dict(row_dict)
                self._entries[entry.id] = entry
                self._vectors[entry.id] = self._embedder.embed(entry.content)

    def _persist(self, entry: MemoryEntry) -> None:
        with self._lock:
            self._conn.execute(
                """
                INSERT OR REPLACE INTO memories
                    (id, user_id, memory_type, content, metadata, importance,
                     created_at, updated_at, last_access_at, access_count)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    entry.id,
                    entry.user_id,
                    entry.memory_type,
                    entry.content,
                    json.dumps(entry.metadata),
                    entry.importance,
                    entry.created_at,
                    entry.updated_at,
                    entry.last_access_at,
                    entry.access_count,
                ),
            )
            self._conn.commit()

    def _delete_row(self, memory_id: str) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM memories WHERE id = ?", (memory_id,))
            self._conn.commit()

    def _validate_type(self, memory_type: str) -> str:
        memory_type = memory_type or DEFAULT_MEMORY_TYPE
        if memory_type not in MEMORY_TYPES:
            msg = (
                f"Invalid memory_type '{memory_type}'; "
                f"expected one of {MEMORY_TYPES}"
            )
            raise ValueError(msg)
        return memory_type

    @property
    def embedder(self) -> HashEmbedder:
        """The embedder in use by this store."""
        return self._embedder

    @property
    def database_path(self) -> str:
        """The SQLite database path backing this store."""
        return self._database_path

    # -- CRUD ---------------------------------------------------------------

    def add(
        self,
        user_id: str,
        content: str,
        memory_type: str = DEFAULT_MEMORY_TYPE,
        metadata: dict[str, Any] | None = None,
        importance: float = 0.5,
        memory_id: str | None = None,
    ) -> MemoryEntry:
        """Add (or replace) a memory entry and return it.

        If ``memory_id`` matches an existing entry, that entry is replaced
        (its timestamps reset). Otherwise a fresh id is generated.
        """
        user_id = str(user_id or "default")
        memory_type = self._validate_type(memory_type)
        content = str(content or "")
        now = _now_iso()
        if memory_id and memory_id in self._entries:
            entry = self._entries[memory_id]
            entry.content = content
            entry.memory_type = memory_type
            entry.metadata = dict(metadata or {})
            entry.importance = float(importance)
            entry.updated_at = now
            entry.last_access_at = now
        else:
            entry = MemoryEntry(
                id=memory_id or uuid.uuid4().hex,
                user_id=user_id,
                memory_type=memory_type,
                content=content,
                metadata=dict(metadata or {}),
                importance=float(importance),
                created_at=now,
                updated_at=now,
                last_access_at=now,
                access_count=0,
            )
        with self._lock:
            self._entries[entry.id] = entry
            self._vectors[entry.id] = self._embedder.embed(entry.content)
        self._persist(entry)
        return entry

    def get(self, memory_id: str) -> MemoryEntry | None:
        """Return the entry with ``memory_id``, or ``None`` if absent."""
        with self._lock:
            return self._entries.get(memory_id)

    def update(
        self,
        memory_id: str,
        content: str | None = None,
        metadata: dict[str, Any] | None = None,
        importance: float | None = None,
        memory_type: str | None = None,
    ) -> MemoryEntry | None:
        """Update fields of an existing memory entry.

        Returns the updated entry, or ``None`` if ``memory_id`` is unknown.
        """
        with self._lock:
            entry = self._entries.get(memory_id)
            if entry is None:
                return None
            if content is not None:
                entry.content = str(content)
            if metadata is not None:
                entry.metadata = dict(metadata)
            if importance is not None:
                entry.importance = float(importance)
            if memory_type is not None:
                entry.memory_type = self._validate_type(memory_type)
            entry.updated_at = _now_iso()
            self._vectors[memory_id] = self._embedder.embed(entry.content)
            self._persist(entry)
            return entry

    def delete(self, memory_id: str) -> bool:
        """Delete the entry with ``memory_id``; return True if removed."""
        with self._lock:
            removed = self._entries.pop(memory_id, None) is not None
            self._vectors.pop(memory_id, None)
            if removed:
                self._delete_row(memory_id)
            return removed

    def forget(
        self,
        user_id: str | None = None,
        memory_type: str | None = None,
        older_than_iso: str | None = None,
    ) -> int:
        """Delete a batch of memories matching the given filters.

        Returns the number of deleted entries.
        """
        if memory_type is not None:
            memory_type = self._validate_type(memory_type)
        cutoff = _parse_iso(older_than_iso) if older_than_iso else None
        with self._lock:
            doomed = [
                eid
                for eid, e in self._entries.items()
                if (user_id is None or e.user_id == user_id)
                and (memory_type is None or e.memory_type == memory_type)
                and (cutoff is None or _parse_iso(e.created_at) <= cutoff)
            ]
            for eid in doomed:
                self._entries.pop(eid, None)
                self._vectors.pop(eid, None)
                self._delete_row(eid)
            return len(doomed)

    def list_memories(
        self,
        user_id: str | None = None,
        memory_type: str | None = None,
    ) -> list[MemoryEntry]:
        """List memories, optionally scoped by user and/or type."""
        if memory_type is not None:
            memory_type = self._validate_type(memory_type)
        with self._lock:
            entries = [
                e
                for e in self._entries.values()
                if (user_id is None or e.user_id == user_id)
                and (memory_type is None or e.memory_type == memory_type)
            ]
        entries.sort(key=lambda e: e.created_at)
        return entries

    def count(self, user_id: str | None = None) -> int:
        """Return the number of stored memories (optionally per user)."""
        with self._lock:
            if user_id is None:
                return len(self._entries)
            return sum(1 for e in self._entries.values() if e.user_id == user_id)

    # -- Ranking -------------------------------------------------------------

    def _recency_score(self, entry: MemoryEntry, now_ts: float | None = None) -> float:
        """A deterministic recency score in ``[0.0, 1.0]`` derived from the
        last-access time and access count (more/older access => lower score)."""
        now_ts = now_ts if now_ts is not None else _parse_iso(_now_iso())
        last_ts = _parse_iso(entry.last_access_at)
        if last_ts <= 0 or now_ts <= 0:
            return 0.0
        # Decay over ~30 days; saturate at 1.0 for very fresh memories.
        age_days = max(0.0, (now_ts - last_ts) / 86400.0)
        recency = math.exp(-age_days / 30.0)
        # Slight boost for frequently accessed memories (capped).
        boost = min(0.15, 0.05 * entry.access_count)
        return max(0.0, min(1.0, recency + boost))

    def search(
        self,
        query: str,
        k: int = 5,
        user_id: str | None = None,
        memory_type: str | None = None,
        metadata_filter: dict[str, Any] | None = None,
    ) -> list[ScoredMemory]:
        """Search scoped memories, returning the top ``k`` by composite score.

        Ranking combines semantic cosine similarity, importance, and recency
        (weighted ``0.65 / 0.25 / 0.10``). Only entries matching the optional
        ``user_id``, ``memory_type`` and ``metadata_filter`` constraints
        participate in ranking.
        """
        if memory_type is not None:
            memory_type = self._validate_type(memory_type)
        query_vec = self._embedder.embed(str(query or ""))
        now_ts = _parse_iso(_now_iso())
        f = metadata_filter or {}

        with self._lock:
            candidates = [
                e
                for e in self._entries.values()
                if (user_id is None or e.user_id == user_id)
                and (memory_type is None or e.memory_type == memory_type)
                and _matches_filter(e.metadata, f)
            ]

        scored: list[ScoredMemory] = []
        for entry in candidates:
            sim = cosine_similarity(query_vec, self._vectors.get(entry.id, []))
            sim = max(0.0, min(1.0, sim))
            recency = self._recency_score(entry, now_ts)
            composite = 0.65 * sim + 0.25 * entry.importance + 0.10 * recency
            scored.append(ScoredMemory(memory=entry, score=composite))

        scored.sort(key=lambda s: s.score, reverse=True)
        top = scored[: max(0, k)]

        # Bump the access metadata on the returned memories (durability + score).
        if top:
            self._touch([s.memory.id for s in top])
        return top

    def _touch(self, memory_ids: Sequence[str]) -> None:
        """Increment access metadata for the given memory ids."""
        now = _now_iso()
        with self._lock:
            for mid in memory_ids:
                entry = self._entries.get(mid)
                if entry is None:
                    continue
                entry.access_count += 1
                entry.last_access_at = now
                self._persist(entry)

    def search_all(
        self,
        query: str,
        k: int = 5,
        user_id: str | None = None,
        memory_types: Sequence[str] | None = None,
    ) -> MemoryContext:
        """Return a ranked memory context blob for prompt injection.

        Gathers the top contextual memories across (optionally) several memory
        types and formats them as a plain-text context string prefixed with a
        marker, e.g.::

            <memory_context> ... </memory_context>
        """
        types: Sequence[str] = memory_types or MEMORY_TYPES
        picked: list[ScoredMemory] = []
        for mtype in types:
            if mtype not in MEMORY_TYPES:
                continue
            results = self.search(
                query, k=k, user_id=user_id, memory_type=mtype
            )
            picked.extend(results)
        picked.sort(key=lambda s: s.score, reverse=True)
        picked = picked[: max(0, k)]

        lines = [
            f"- [{s.memory.memory_type}] {s.memory.content}" for s in picked
        ]
        context = (
            "<memory_context>\n" + "\n".join(lines) + "\n</memory_context>"
            if lines
            else "<memory_context></memory_context>"
        )
        return MemoryContext(query=query, context=context, memories=picked)

    # -- Consolidation --------------------------------------------------------

    def consolidate(
        self,
        max_per_type: int = 1000,
        similarity_threshold: float = 0.92,
        user_id: str | None = None,
    ) -> dict[str, int]:
        """De-duplicate near-identical memories and enforce the per-type cap.

        For each user/type group, entries whose vectors are more similar than
        ``similarity_threshold`` are merged (the higher-importance / more
        recently updated entry survives; importance is averaged). After
        merging, each user/type group is trimmed to at most ``max_per_type``
        entries (oldest dropped first).

        Returns a summary dict, e.g. ``{"merged": 3, "trimmed": 1}``.
        """
        summary = {"merged": 0, "trimmed": 0}

        with self._lock:
            # Group by (user_id, memory_type).
            groups: dict[tuple[str, str], list[str]] = {}
            for eid, e in self._entries.items():
                if user_id is not None and e.user_id != user_id:
                    continue
                groups.setdefault((e.user_id, e.memory_type), []).append(eid)

            for _key, ids in groups.items():
                # (a) merge near-duplicates
                ids.sort(
                    key=lambda iid: (
                        _parse_iso(self._entries[iid].updated_at),
                        self._entries[iid].importance,
                    ),
                    reverse=True,
                )
                kept: list[str] = []
                for iid in ids:
                    candidate = self._entries[iid]
                    merged = False
                    for existing_id in kept:
                        existing = self._entries[existing_id]
                        sim = cosine_similarity(
                            self._vectors.get(iid, []),
                            self._vectors.get(existing_id, []),
                        )
                        if sim >= similarity_threshold:
                            # Merge metadata + average importance into survivor.
                            existing.metadata.update(candidate.metadata)
                            existing.importance = round(
                                statistics.mean(
                                    [existing.importance, candidate.importance]
                                ),
                                4,
                            )
                            if existing.access_count < candidate.access_count:
                                existing.access_count = candidate.access_count
                            existing.updated_at = _now_iso()
                            self._vectors[existing_id] = self._embedder.embed(
                                existing.content
                            )
                            self._persist(existing)
                            self._entries.pop(iid, None)
                            self._vectors.pop(iid, None)
                            self._delete_row(iid)
                            summary["merged"] += 1
                            merged = True
                            break
                    if not merged:
                        kept.append(iid)

                # (b) enforce the per-type cap
                kept.sort(
                    key=lambda iid: _parse_iso(self._entries[iid].created_at)
                )
                excess = len(kept) - max(0, max_per_type)
                if excess > 0:
                    for iid in kept[:excess]:
                        self._entries.pop(iid, None)
                        self._vectors.pop(iid, None)
                        self._delete_row(iid)
                        summary["trimmed"] += 1

        return summary


# ---------------------------------------------------------------------------
# Facade
# ---------------------------------------------------------------------------


class AgentMemory:
    """High-level facade combining a :class:`MemoryStore` and an embedder.

    Provides the mem0-style API used by the ``memory`` module and by
    application code: ``remember`` / ``add``, ``search``, ``update``,
    ``delete``, ``forget``, ``get_memories`` and ``search_all``.
    """

    def __init__(
        self,
        database_path: str = ":memory:",
        embedder: HashEmbedder | None = None,
    ) -> None:
        self._embedder: HashEmbedder = (
            embedder if embedder is not None else HashEmbedder()
        )
        self._store = MemoryStore(
            database_path=database_path, embedder=self._embedder
        )

    @property
    def embedder(self) -> HashEmbedder:
        """The embedder in use."""
        return self._embedder

    @property
    def store(self) -> MemoryStore:
        """The backing persistent store."""
        return self._store

    def remember(
        self,
        user_id: str,
        content: str,
        memory_type: str = DEFAULT_MEMORY_TYPE,
        metadata: dict[str, Any] | None = None,
        importance: float = 0.5,
    ) -> MemoryEntry:
        """Store a memory and return the created entry."""
        return self._store.add(
            user_id=user_id,
            content=content,
            memory_type=memory_type,
            metadata=metadata,
            importance=importance,
        )

    def add(
        self,
        user_id: str,
        content: str,
        memory_type: str = DEFAULT_MEMORY_TYPE,
        metadata: dict[str, Any] | None = None,
        importance: float = 0.5,
    ) -> MemoryEntry:
        """Alias for :meth:`remember`."""
        return self.remember(
            user_id=user_id,
            content=content,
            memory_type=memory_type,
            metadata=metadata,
            importance=importance,
        )

    def search(
        self,
        query: str,
        k: int = 5,
        user_id: str | None = None,
        memory_type: str | None = None,
        metadata_filter: dict[str, Any] | None = None,
    ) -> list[ScoredMemory]:
        """Search ranked memories scoped by the optional filters."""
        return self._store.search(
            query=query,
            k=k,
            user_id=user_id,
            memory_type=memory_type,
            metadata_filter=metadata_filter,
        )

    def get(self, memory_id: str) -> MemoryEntry | None:
        """Return a single memory by id."""
        return self._store.get(memory_id)

    def update(
        self,
        memory_id: str,
        content: str | None = None,
        metadata: dict[str, Any] | None = None,
        importance: float | None = None,
        memory_type: str | None = None,
    ) -> MemoryEntry | None:
        """Update an existing memory by id."""
        return self._store.update(
            memory_id=memory_id,
            content=content,
            metadata=metadata,
            importance=importance,
            memory_type=memory_type,
        )

    def delete(self, memory_id: str) -> bool:
        """Delete a single memory by id."""
        return self._store.delete(memory_id)

    def forget(
        self,
        user_id: str | None = None,
        memory_type: str | None = None,
        older_than_iso: str | None = None,
    ) -> int:
        """Batch-delete memories matching the given filters."""
        return self._store.forget(
            user_id=user_id,
            memory_type=memory_type,
            older_than_iso=older_than_iso,
        )

    def get_memories(
        self,
        user_id: str | None = None,
        memory_type: str | None = None,
    ) -> list[MemoryEntry]:
        """List memories, optionally scoped by user and/or type."""
        return self._store.list_memories(
            user_id=user_id, memory_type=memory_type
        )

    def count(self, user_id: str | None = None) -> int:
        """Return the number of stored memories."""
        return self._store.count(user_id=user_id)

    def search_all(
        self,
        query: str,
        k: int = 5,
        user_id: str | None = None,
        memory_types: Sequence[str] | None = None,
    ) -> MemoryContext:
        """Return a ranked memory context blob for prompt injection."""
        return self._store.search_all(
            query=query, k=k, user_id=user_id, memory_types=memory_types
        )

    def consolidate(
        self,
        max_per_type: int = 1000,
        similarity_threshold: float = 0.92,
        user_id: str | None = None,
    ) -> dict[str, int]:
        """De-duplicate and trim memories; return a summary dict."""
        return self._store.consolidate(
            max_per_type=max_per_type,
            similarity_threshold=similarity_threshold,
            user_id=user_id,
        )
