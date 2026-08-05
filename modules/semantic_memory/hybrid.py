"""Hybrid Semantic Memory Core — mem0-style change detection + hybrid retrieval.

Extends the dependency-free semantic retrieval layer (:mod:`.semantic_memory`)
with a mem0-inspired hybrid retrieval + change-detection memory core, using
only the Python standard library (``sqlite3``, ``math``, ``json``, ...):

  * **Hybrid retrieval** — every ``search`` runs BOTH a vector retrieval
    (feature-hash cosine similarity, from :class:`~.semantic_memory.HashEmbedder`)
    AND a keyword retrieval (token overlap / TF scoring over stored text),
    then merges, de-duplicates, and re-ranks into a single result set.
  * **Change detection (mem0 ``add`` delta)** — ``add()`` returns a result with
    ``event in {'created','updated','noop'}``. A near-duplicate (hybrid score
    above a configurable threshold) is updated in place (``updated``) or left
    unchanged when already identical (``noop``); otherwise a new memory is
    inserted (``created``).
  * **Metadata filtering** — metadata JSON is stored per memory and search can
    filter by metadata key/value pairs (e.g. ``{'source':'kb','tags':['x']}``).
  * **SQLite persistence** — memories, embeddings and metadata are persisted to
    a SQLite database (path configurable, default under ``data/``), and reloaded
    transparently on ``__init__``.
  * **Facade** — :class:`HybridSemanticMemory` exposing ``add`` / ``search`` /
    ``update`` / ``delete`` / ``list`` / ``recall`` and ``.stats()`` (counts),
    while preserving the original :class:`~.semantic_memory.SemanticMemory`
    public API (``remember`` / ``recall`` / ``adapter`` / ``index``).

No external packages required. Python 3.10+.

Version: 2.0.0
"""

from __future__ import annotations

import contextlib
import datetime as _dt
import json
import math
import os
import re
import sqlite3
import threading
import time
import uuid
from collections import Counter
from pathlib import Path
from typing import Any

from .semantic_memory import (
    Embedder,
    HashEmbedder,
    ScoredDoc,
    SemanticIndex,
    SemanticMemory,
    cosine_similarity,
)

__all__ = [
    "HybridRetriever",
    "HybridSemanticMemory",
    "AddResult",
    "keyword_score",
    "tokenize",
]

_TOKEN_RE = re.compile(r"[A-Za-z0-9_]+")


def tokenize(text: str) -> list[str]:
    """Return the lowercase alphanumeric tokens of ``text`` (in order)."""
    return _TOKEN_RE.findall((text or "").lower())


def keyword_score(query_tokens: list[str], text_tokens: list[str]) -> float:
    """Simple TF-overlap keyword score in ``[0.0, 1.0]``.

    Computes Jaccard-ish overlap weighted by term frequency of the query terms
    present in the document text. Returns 0.0 when the query is empty.
    """
    if not query_tokens:
        return 0.0
    q = Counter(query_tokens)
    d = Counter(text_tokens)
    hit_weight = sum(count * min(count, d.get(tok, 0)) for tok, count in q.items())
    total_weight = sum(count for count in q.values())
    if total_weight == 0:
        return 0.0
    return max(0.0, min(1.0, hit_weight / total_weight))


def _matches_meta(metadata: dict[str, Any], filters: dict[str, Any] | None) -> bool:
    """Return True if ``metadata`` satisfies the filter spec.

    Supports exact scalar equality (``{'source': 'kb'}``) and list membership
    (``{'tags': ['x']}`` -> metadata['tags'] must contain 'x').
    """
    if not filters:
        return True
    for key, expected in filters.items():
        if key not in metadata:
            return False
        actual = metadata[key]
        if isinstance(expected, (list, tuple, set)):
            actual_set = set(actual) if isinstance(actual, (list, tuple, set)) else {actual}
            if not any(e in actual_set for e in expected):
                return False
        else:
            if actual != expected:
                return False
    return True


# ---------------------------------------------------------------------------
# Temporal memory + consolidation helpers (Zep temporal recall / mem0 ranking)
# ---------------------------------------------------------------------------

DEFAULT_RECENCY_WEIGHT = 0.5
DEFAULT_IMPORTANCE_WEIGHT = 0.5
EXACT_TOKEN_BONUS = 0.05  # small rerank boost for keyword-exact-token hits


def _coerce_ts(value: Any) -> float | None:
    """Normalize ``since``/``until`` to a unix-epoch float (or ``None``).

    Accepts floats, ints, and anything exposing ``.timestamp()`` (datetime/date).
    """
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    ts = getattr(value, "timestamp", None)
    if callable(ts):
        return float(ts())
    return float(value)


def _window_ok(since: float | None, until: float | None, ts: float) -> bool:
    """Return True if timestamp ``ts`` falls within the ``[since, until]`` window."""
    if since is not None and ts < since:
        return False
    return not (until is not None and ts > until)


def _exact_tokens(q_tokens: list[str], doc_tokens: list[str]) -> bool:
    """True when every query token appears as an exact token in the doc."""
    if not q_tokens:
        return False
    dset = set(doc_tokens)
    return all(t in dset for t in q_tokens)


def _bucket_range(bucket: str) -> tuple[float, float]:
    """Return ``(start, end)`` epoch bounds for the *current* time bucket.

    ``bucket`` is one of ``'day'``, ``'week'`` (Monday-start), ``'month'``.
    """
    now = time.time()
    lt = time.localtime(now)
    name = (bucket or "day").lower()
    dst = -1  # let time.mktime resolve DST
    if name == "week":
        start = time.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday - lt.tm_wday, 0, 0, 0, 0, 0, dst))
    elif name == "month":
        start = time.mktime((lt.tm_year, lt.tm_mon, 1, 0, 0, 0, 0, 0, dst))
    else:  # 'day' (default)
        start = time.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday, 0, 0, 0, 0, 0, dst))
    return start, now


def _bucket_key(bucket: str, ts: float) -> str:
    """Human-readable label for a timestamp within a bucket (e.g. ``2026-08-04``)."""
    name = (bucket or "day").lower()
    d = _dt.date.fromtimestamp(ts)
    if name == "week":
        iso = d.isocalendar()
        return f"{iso[0]:04d}-W{iso[1]:02d}"
    if name == "month":
        return f"{d.year:04d}-{d.month:02d}"
    return f"{d.year:04d}-{d.month:02d}-{d.day:02d}"


class HybridRetriever:
    """Merges vector + keyword retrieval into a single ranked result set.

    Args:
        embedder: Embedder used for vector retrieval. Defaults to a
            :class:`~.semantic_memory.HashEmbedder`.
        vector_weight: Relative weight of the vector (semantic) score.
            Keyword weight is ``1 - vector_weight``.
    """

    DEFAULT_VECTOR_WEIGHT = 0.6
    DEFAULT_KEYWORD_WEIGHT = 0.4

    def __init__(
        self,
        embedder: Embedder | None = None,
        vector_weight: float = DEFAULT_VECTOR_WEIGHT,
    ) -> None:
        self._kw_weight = 1.0 - vector_weight
        self._index = SemanticIndex(embedder=embedder or HashEmbedder())
        self._times: dict[str, float] = {}
        self._access_count: dict[str, int] = {}

    def _iter_candidates(self, filters: dict[str, Any] | None) -> list[Any]:
        docs = list(self._index._documents.values())
        if not filters:
            return docs
        return [d for d in docs if _matches_meta(d.metadata, filters)]

    def add(self, id: str, text: str, metadata: dict[str, Any] | None = None) -> str:
        """Add a document to the hybrid retriever (vector + keyword source)."""
        self._index.add(id, text, metadata)
        self._times[id] = time.time()
        return id

    def remove(self, id: str) -> bool:
        """Remove a document by id; returns True if it existed."""
        removed = self._index.remove(id)
        if removed:
            self._times.pop(id, None)
            self._access_count.pop(id, None)
        return removed

    def count(self) -> int:
        return self._index.count()

    def search(
        self,
        query: str,
        limit: int = 5,
        filters: dict[str, Any] | None = None,
        since: Any = None,
        until: Any = None,
        time_bucket: str | None = None,
    ) -> list[ScoredDoc]:
        """Hybrid search merging vector + keyword hits.

        Each candidate doc (optionally pre-filtered by ``filters`` and the
        temporal window ``[since, until]`` / ``time_bucket``) receives a
        blended score ``w_vec * vec_score + w_kw * kw_score`` plus a small
        rerank bonus when every query token appears as an exact doc token.
        Results are de-duplicated by id, sorted descending, and the top
        ``limit`` returned.
        """
        since, until = self._resolve_window(since, until, time_bucket)
        q_tokens = tokenize(query)
        q_vec = self._index.embedder.embed(query)
        merged: dict[str, ScoredDoc] = {}
        for doc in self._iter_candidates(filters):
            ts = self._times.get(doc.id, 0.0) or 0.0
            if not _window_ok(since, until, ts):
                continue
            vec = max(0.0, min(1.0, cosine_similarity(q_vec, doc.vector)))
            doc_tokens = tokenize(doc.text)
            kw = keyword_score(q_tokens, doc_tokens)
            blended = (self._kw_weight * kw) + ((1.0 - self._kw_weight) * vec)
            if kw > 0.0 and _exact_tokens(q_tokens, doc_tokens):
                blended += EXACT_TOKEN_BONUS
            self._access_count[doc.id] = self._access_count.get(doc.id, 0) + 1
            existing = merged.get(doc.id)
            if existing is not None:
                existing.score = max(existing.score, round(blended, 6))
            else:
                merged[doc.id] = ScoredDoc(
                    id=doc.id,
                    score=round(blended, 6),
                    text=doc.text,
                    metadata=dict(doc.metadata),
                )
        ranked = sorted(merged.values(), key=lambda s: s.score, reverse=True)
        if limit <= 0:
            return []
        return ranked[:limit]

    def _resolve_window(
        self, since: Any, until: Any, time_bucket: str | None
    ) -> tuple[float | None, float | None]:
        """Combine explicit ``since``/``until`` with an optional ``time_bucket``."""
        if time_bucket:
            start, end = _bucket_range(time_bucket)
            if since is None:
                since = start
            if until is None:
                until = end
        return _coerce_ts(since), _coerce_ts(until)

    def recall_since(self, since: Any) -> list[dict[str, Any]]:
        """Return memories whose created/updated timestamp is at/after ``since``."""
        ts = _coerce_ts(since) or 0.0
        out = []
        for doc in self._index._documents.values():
            t = self._times.get(doc.id, 0.0) or 0.0
            if t >= ts:
                out.append(
                    {
                        "id": doc.id,
                        "text": doc.text,
                        "metadata": dict(doc.metadata),
                        "timestamp": t,
                    }
                )
        out.sort(key=lambda d: d["timestamp"], reverse=True)
        return out

    def group_by_time_bucket(self, bucket: str = "day") -> dict[str, dict[str, Any]]:
        """Group memories into time buckets, returning counts + grouped memories."""
        groups: dict[str, dict[str, Any]] = {}
        for doc in self._index._documents.values():
            ts = self._times.get(doc.id, 0.0) or 0.0
            key = _bucket_key(bucket, ts)
            g = groups.setdefault(key, {"count": 0, "memories": []})
            g["count"] += 1
            g["memories"].append({"id": doc.id, "text": doc.text})
        return groups

    def _importance(self, row_id: str, doc: Any) -> float:
        meta = doc.metadata if doc is not None else {}
        score = 0.0
        pri = meta.get("priority")
        if isinstance(pri, (int, float)):
            score += float(pri)
        if meta.get("important") is True:
            score += 1.0
        score += math.log1p(max(0, self._access_count.get(row_id, 0)))
        return score

    def ranking(
        self,
        limit: int | None = None,
        recency_weight: float = DEFAULT_RECENCY_WEIGHT,
        importance_weight: float = DEFAULT_IMPORTANCE_WEIGHT,
    ) -> list[dict[str, Any]]:
        """Rank memories by (recency + importance) descending (mem0-style)."""
        now = time.time()
        raws = []
        for doc in self._index._documents.values():
            updated = self._times.get(doc.id, now)
            age = max(0.0, now - updated)
            recency = 1.0 / (1.0 + age)
            importance = self._importance(doc.id, doc)
            raws.append((doc, recency, importance))
        results = []
        for doc, recency, importance in raws:
            imp_norm = float(importance) / (1.0 + float(importance))  # saturating -> [0,1]
            score = recency_weight * recency + importance_weight * imp_norm
            results.append(
                {
                    "id": doc.id,
                    "text": doc.text,
                    "metadata": dict(doc.metadata),
                    "timestamp": self._times.get(doc.id),
                    "recency": round(recency, 6),
                    "importance": round(imp_norm, 6),
                    "score": round(score, 6),
                }
            )
        results.sort(key=lambda d: d["score"], reverse=True)
        for idx, d in enumerate(results, start=1):
            d["rank"] = idx
        if limit is not None and limit > 0:
            results = results[:limit]
        return results

    def consolidate(
        self,
        max_age: float | None = None,
        min_importance: float | None = None,
        merge_threshold: float | None = 0.7,
    ) -> dict[str, Any]:
        """Prune (or merge) stale + low-importance memories (mem0 ranking idea).

        A memory is pruned only when it is BOTH stale (``max_age`` exceeded,
        if given) and low-importance (``importance`` below ``min_importance``,
        if given). Redundant stale/low-importance memories that are near-duplicates
        of retained ones are counted as ``merged``.
        """
        now = time.time()
        ranked = self.ranking()
        pruned: list[str] = []
        merged: list[str] = []
        for item in ranked:
            rid = item["id"]
            updated = item.get("timestamp") or now
            age = max(0.0, now - updated)
            stale = max_age is not None and age >= float(max_age)
            low_imp = min_importance is not None and item["importance"] < float(min_importance)
            if not (stale and low_imp):
                continue
            if merge_threshold is not None and self._redundant_with(
                rid, ranked, float(merge_threshold)
            ):
                merged.append(rid)
            else:
                pruned.append(rid)
            self.remove(rid)
        return {
            "pruned": len(pruned),
            "pruned_ids": pruned,
            "merged": len(merged),
            "merged_ids": merged,
            "kept": self.count(),
        }

    def _redundant_with(self, row_id: str, ranked: list[dict[str, Any]], threshold: float) -> bool:
        """True if ``row_id`` is a near-duplicate (hybrid sim >= threshold) of any retained doc."""
        doc = self._index.get(row_id)
        if doc is None:
            return False
        q_tokens = tokenize(doc.text)
        q_vec = doc.vector
        for other in ranked:
            if other["id"] == row_id:
                continue
            odoc = self._index.get(other["id"])
            if odoc is None:
                continue
            vec = max(0.0, min(1.0, cosine_similarity(q_vec, odoc.vector)))
            kw = keyword_score(q_tokens, tokenize(odoc.text))
            blended = (self._kw_weight * kw) + ((1.0 - self._kw_weight) * vec)
            if blended >= threshold:
                return True
        return False


# Re-export SemanticIndex pieces we depend on for type hints only.


class AddResult:
    """Result of a mem0-style :meth:`HybridSemanticMemory.add` call.

    Attributes:
        id: The id of the affected (created / updated / noop) memory.
        event: One of ``'created'``, ``'updated'``, ``'noop'``.
        score: The hybrid similarity that triggered the decision in ``[0,1]``.
        text: The final stored text (after any merge).
        metadata: The final stored metadata.
        previous: For ``'updated'``, the prior stored text; else ``None``.
    """

    __slots__ = ("id", "event", "score", "text", "metadata", "previous")

    def __init__(
        self,
        id: str,
        event: str,
        score: float,
        text: str,
        metadata: dict[str, Any] | None = None,
        previous: str | None = None,
    ) -> None:
        self.id = id
        self.event = event
        self.score = score
        self.text = text
        self.metadata = dict(metadata or {})
        self.previous = previous

    @property
    def is_new(self) -> bool:
        return self.event == "created"

    @property
    def is_updated(self) -> bool:
        return self.event == "updated"

    @property
    def noop(self) -> bool:
        return self.event == "noop"

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "event": self.event,
            "score": self.score,
            "text": self.text,
            "metadata": dict(self.metadata),
            "previous": self.previous,
        }

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"AddResult(id={self.id!r}, event={self.event!r}, score={self.score:.3f})"


_SQL_SCHEMA = """
CREATE TABLE IF NOT EXISTS memories (
    id          TEXT PRIMARY KEY,
    text        TEXT NOT NULL,
    metadata    TEXT NOT NULL DEFAULT '{}',
    user_id     TEXT,
    created_at  REAL NOT NULL,
    updated_at  REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_memories_user ON memories(user_id);
"""


class HybridSemanticMemory(SemanticMemory):
    """Mem0-style hybrid memory facade with change detection + SQLite persistence.

    Extends :class:`~.semantic_memory.SemanticMemory` so all existing public API
    (``remember`` / ``recall`` / ``adapter`` / ``index`` / ``embedder``) is
    preserved, while adding mem0-style ``add`` (change detection), hybrid
    ``search`` with metadata filtering, ``update`` / ``delete`` / ``list`` /
    ``recall`` and ``.stats()``.

    SQLite persistence is used when ``db_path`` is provided; otherwise the store
    is purely in-memory. On construction, any existing rows in the DB are loaded
    back into the in-memory index.

    Args:
        embedder: Embedder for vector retrieval.
        db_path: Path to the SQLite database file. If ``None`` the store is
            in-memory only. A bare filename/relative path is resolved under
            ``data/``.
        threshold: Default similarity threshold in ``[0,1]`` for change
            detection in ``add()`` (overridable per-call).
        vector_weight: Weight for the vector score in hybrid retrieval.
    """

    DEFAULT_DATA_DIR = "data"

    def __init__(
        self,
        embedder: Embedder | None = None,
        db_path: str | os.PathLike | None = None,
        threshold: float = 0.85,
        vector_weight: float = HybridRetriever.DEFAULT_VECTOR_WEIGHT,
    ) -> None:
        super().__init__(embedder=embedder)
        self._db_path = self._resolve_db_path(db_path)
        self._lock = threading.RLock()
        self._threshold = float(threshold)
        self._kw_weight = 1.0 - vector_weight
        self._user_ids: dict[str, str | None] = {}
        self._created_at: dict[str, float] = {}
        self._updated_at: dict[str, float] = {}
        self._access_count: dict[str, int] = {}
        self._conn: sqlite3.Connection | None = None
        self._init_db()
        self._load_from_db()

    # -- Path / DB bootstrapping -------------------------------------------

    @classmethod
    def _resolve_db_path(cls, db_path: str | os.PathLike | None) -> str | None:
        if db_path is None:
            return None
        p = Path(db_path)
        # A bare relative file name (no directory component) -> data/<name>
        if not p.is_absolute() and not p.parent.parts and p.suffix:
            p = Path(cls.DEFAULT_DATA_DIR) / p.name
        return str(p)

    @property
    def db_path(self) -> str | None:
        return self._db_path

    def _init_db(self) -> None:
        if self._db_path is None:
            return
        parent = os.path.dirname(self._db_path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        self._conn = sqlite3.connect(self._db_path)
        self._conn.executescript(_SQL_SCHEMA)
        self._ensure_time_columns()
        self._conn.commit()

    def _ensure_time_columns(self) -> None:
        """Migration-safe: add timestamp columns to pre-existing DBs that lack them.

        Older stored DBs (created before temporal memory was introduced) may not
        have ``created_at`` / ``updated_at``. ``CREATE TABLE IF NOT EXISTS`` does
        not add columns to an existing table, so we ALTER TABLE ADD COLUMN when
        the PRAGMA column list is missing them.
        """
        if self._conn is None:
            return
        cols = {row[1] for row in self._conn.execute("PRAGMA table_info(memories)")}
        for name in ("created_at", "updated_at"):
            if name not in cols:
                self._conn.execute(f"ALTER TABLE memories ADD COLUMN {name} REAL")
                self._conn.commit()

    def _load_from_db(self) -> None:
        if self._conn is None:
            return
        rows = self._conn.execute(
            "SELECT id, text, metadata, user_id, created_at, updated_at FROM memories"
        ).fetchall()
        for row_id, text, meta_json, user_id, created_at, updated_at in rows:
            meta = json.loads(meta_json or "{}")
            self._index.add(row_id, text, meta)
            self._user_ids[row_id] = user_id
            ts = time.time()
            # NULL timestamps (legacy rows added before temporal columns existed)
            # default to the load time so they are treated as recent, not stale.
            self._created_at[row_id] = created_at if created_at is not None else ts
            self._updated_at[row_id] = updated_at if updated_at is not None else ts

    def _persist(
        self,
        row_id: str,
        text: str,
        metadata: dict[str, Any],
        user_id: str | None,
        created_at: float,
        updated_at: float,
    ) -> None:
        if self._conn is None:
            return
        self._conn.execute(
            "INSERT OR REPLACE INTO memories (id, text, metadata, user_id, created_at, updated_at)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (row_id, text, json.dumps(metadata), user_id, created_at, updated_at),
        )
        self._conn.commit()

    def _delete_row(self, row_id: str) -> None:
        if self._conn is None:
            return
        self._conn.execute("DELETE FROM memories WHERE id = ?", (row_id,))
        self._conn.commit()

    # -- Hybrid candidates: union over index + registered metadata ----------

    def _iter_candidates(self, filters: dict[str, Any] | None) -> list[Any]:
        """Return index documents (matching filters when provided)."""
        with self._lock:
            docs = list(self._index._documents.values())
        if not filters:
            return docs
        return [d for d in docs if _matches_meta(d.metadata, filters)]

    # -- mem0-style add with change detection -------------------------------

    def add(
        self,
        text: str,
        metadata: dict[str, Any] | None = None,
        user_id: str | None = None,
        threshold: float | None = None,
    ) -> AddResult:
        """Add a memory with change detection (mem0 ``add`` delta).

        Behaviour:
          * If no near-duplicate exists (hybrid similarity below ``threshold``),
            a new memory is inserted and ``event='created'``.
          * If a near-duplicate exists and the text differs, the existing memory
            is updated in place and ``event='updated'`` (stores the new text).
          * If a near-duplicate exists and the text is effectively identical,
            the memory is left unchanged and ``event='noop'``.

        Args:
            text: Memory text to store.
            metadata: Optional key-value metadata (persisted as JSON).
            user_id: Optional user scope.
            threshold: Similarity threshold overriding the store default.

        Returns:
            An :class:`AddResult` describing the delta.
        """
        thr = self._threshold if threshold is None else float(threshold)
        text = (text or "").strip()
        meta = dict(metadata or {})
        q_tokens = tokenize(text)
        q_vec = self._index.embedder.embed(text)

        with self._lock:
            best_id: str | None = None
            best_score = 0.0
            best_doc = None
            for doc in self._index._documents.values():
                vec = max(0.0, min(1.0, cosine_similarity(q_vec, doc.vector)))
                kw = keyword_score(q_tokens, tokenize(doc.text))
                blended = (self._kw_weight * kw) + ((1.0 - self._kw_weight) * vec)
                if blended > best_score:
                    best_score = blended
                    best_id = doc.id
                    best_doc = doc

            if best_id is not None and best_doc is not None and best_score >= thr:
                identical = best_doc.text.strip().lower() == text.lower()
                if identical:
                    return AddResult(
                        id=best_id,
                        event="noop",
                        score=round(best_score, 6),
                        text=best_doc.text,
                        metadata=dict(best_doc.metadata),
                        previous=best_doc.text,
                    )
                # update in place
                self._update_locked(best_id, text, meta, user_id, keep_created=True)
                return AddResult(
                    id=best_id,
                    event="updated",
                    score=round(best_score, 6),
                    text=text,
                    metadata=meta,
                    previous=best_doc.text,
                )

            # created
            row_id = f"mem_{uuid.uuid4().hex}"
            now = time.time()
            self._index.add(row_id, text, meta)
            self._user_ids[row_id] = user_id
            self._created_at[row_id] = now
            self._updated_at[row_id] = now
            self._persist(row_id, text, meta, user_id, now, now)
            return AddResult(
                id=row_id,
                event="created",
                score=round(best_score, 6),
                text=text,
                metadata=meta,
            )

    # Alias matching the task's preferred name.
    add_memory = add

    # -- Hybrid search ------------------------------------------------------

    def search(
        self,
        query: str,
        limit: int = 5,
        filters: dict[str, Any] | None = None,
        since: Any = None,
        until: Any = None,
        time_bucket: str | None = None,
    ) -> list[ScoredDoc]:
        """Hybrid retrieval: vector + keyword, merged + de-duplicated + re-ranked.

        Args:
            query: Query text.
            limit: Maximum number of results.
            filters: Optional metadata key/value filters
                (e.g. ``{'source': 'kb', 'tags': ['x']}``).
            since: Optional lower bound (unix float, or datetime) for the
                memory timestamp window.
            until: Optional upper bound (unix float, or datetime).
            time_bucket: Optional ``'day'`` / ``'week'`` / ``'month'`` bucket —
                restricts results to the current bucket when ``since``/``until``
                are not provided.

        Returns:
            Ranked :class:`~.semantic_memory.ScoredDoc` list (descending score).
        """
        since, until = self._resolve_window(since, until, time_bucket)
        q_tokens = tokenize(query)
        q_vec = self._index.embedder.embed(query)
        merged: dict[str, ScoredDoc] = {}
        with self._lock:
            for doc in self._iter_candidates(filters):
                ts = self._updated_at.get(doc.id, self._created_at.get(doc.id, 0.0)) or 0.0
                if not _window_ok(since, until, ts):
                    continue
                vec = max(0.0, min(1.0, cosine_similarity(q_vec, doc.vector)))
                doc_tokens = tokenize(doc.text)
                kw = keyword_score(q_tokens, doc_tokens)
                blended = (self._kw_weight * kw) + ((1.0 - self._kw_weight) * vec)
                if kw > 0.0 and _exact_tokens(q_tokens, doc_tokens):
                    blended += EXACT_TOKEN_BONUS
                self._access_count[doc.id] = self._access_count.get(doc.id, 0) + 1
                existing = merged.get(doc.id)
                if existing is not None:
                    existing.score = max(existing.score, round(blended, 6))
                else:
                    merged[doc.id] = ScoredDoc(
                        id=doc.id,
                        score=round(blended, 6),
                        text=doc.text,
                        metadata=dict(doc.metadata),
                    )
        ranked = sorted(merged.values(), key=lambda s: s.score, reverse=True)
        if limit <= 0:
            return []
        return ranked[:limit]

    def _resolve_window(
        self, since: Any, until: Any, time_bucket: str | None
    ) -> tuple[float | None, float | None]:
        """Combine explicit ``since``/``until`` with an optional ``time_bucket``."""
        if time_bucket:
            start, end = _bucket_range(time_bucket)
            if since is None:
                since = start
            if until is None:
                until = end
        return _coerce_ts(since), _coerce_ts(until)

    def recall_since(self, since: Any) -> list[dict[str, Any]]:
        """Return memories created at/after ``since`` (temporal recall).

        Args:
            since: A datetime, unix-epoch float, or similar timestamp.

        Returns:
            List of memory dicts (``id``, ``text``, ``metadata``, ``user_id``,
            ``created_at``, ``updated_at``) ordered newest-first.
        """
        ts = _coerce_ts(since) or 0.0
        out = [it for it in self.list() if (it.get("created_at") or 0.0) >= ts]
        out.sort(key=lambda d: d.get("updated_at") or 0.0, reverse=True)
        return out

    def group_by_time_bucket(
        self, bucket: str = "day", key: str = "updated_at"
    ) -> dict[str, dict[str, Any]]:
        """Group memories into time buckets (Zep temporal recall).

        Args:
            bucket: One of ``'day'``, ``'week'`` (Monday-start), ``'month'``.
            key: Which timestamp to bucket by (``'updated_at'`` or ``'created_at'``).

        Returns:
            ``{bucket_label: {"count": int, "memories": [dicts]}}``.
        """
        groups: dict[str, dict[str, Any]] = {}
        for it in self.list():
            ts = it.get(key) or it.get("created_at") or 0.0
            label = _bucket_key(bucket, ts)
            g = groups.setdefault(label, {"count": 0, "memories": []})
            g["count"] += 1
            g["memories"].append(it)
        return groups

    def _importance(self, row_id: str, doc: Any) -> float:
        """Importance score from metadata priority + hit-frequency (mem0-style)."""
        meta = doc.metadata if doc is not None else {}
        score = 0.0
        pri = meta.get("priority")
        if isinstance(pri, (int, float)):
            score += float(pri)
        if meta.get("important") is True:
            score += 1.0
        score += math.log1p(max(0, self._access_count.get(row_id, 0)))
        return score

    def ranking(
        self,
        limit: int | None = None,
        recency_weight: float = DEFAULT_RECENCY_WEIGHT,
        importance_weight: float = DEFAULT_IMPORTANCE_WEIGHT,
    ) -> list[dict[str, Any]]:
        """Rank all memories by recency + importance, descending (mem0 ranking).

        Importance is normalized to ``[0,1]`` across the current store; recency
        decays as ``1 / (1 + age_seconds)``. Returns dicts including ``rank``,
        ``score``, ``recency``, ``importance`` and the stored fields.
        """
        now = time.time()
        items = self.list()
        raws: list[tuple[dict[str, Any], float, float]] = []
        for it in items:
            rid = it["id"]
            doc = self._index.get(rid)
            importance = self._importance(rid, doc)
            updated = it.get("updated_at") or it.get("created_at") or now
            recency = 1.0 / (1.0 + max(0.0, now - updated))
            raws.append((it, recency, importance))
        results: list[dict[str, Any]] = []
        for it, recency, importance in raws:
            imp_norm = float(importance) / (1.0 + float(importance))  # saturating -> [0,1]
            score = recency_weight * recency + importance_weight * imp_norm
            results.append(
                {
                    "id": it["id"],
                    "text": it["text"],
                    "metadata": it["metadata"],
                    "user_id": it["user_id"],
                    "created_at": it["created_at"],
                    "updated_at": it["updated_at"],
                    "recency": round(recency, 6),
                    "importance": round(imp_norm, 6),
                    "score": round(score, 6),
                }
            )
        results.sort(key=lambda d: d["score"], reverse=True)
        for idx, d in enumerate(results, start=1):
            d["rank"] = idx
        if limit is not None and limit > 0:
            results = results[:limit]
        return results

    def consolidate(
        self,
        max_age: float | None = None,
        min_importance: float | None = None,
        merge_threshold: float | None = 0.7,
    ) -> dict[str, Any]:
        """Prune/merge stale + low-importance memories (mem0 ranking idea).

        A memory is removed only when it is BOTH stale (older than ``max_age``,
        if given) AND low-importance (normalized importance below
        ``min_importance``, if given). Redundant stale/low-importance memories
        that are near-duplicates of retained ones are counted as ``merged``
        rather than ``pruned``.

        Returns:
            ``{"pruned", "pruned_ids", "merged", "merged_ids", "kept"}``.
        """
        now = time.time()
        ranked = self.ranking()
        pruned: list[str] = []
        merged: list[str] = []
        for item in ranked:
            rid = item["id"]
            updated = item.get("updated_at") or item.get("created_at") or now
            age = max(0.0, now - updated)
            stale = max_age is not None and age >= float(max_age)
            low_imp = min_importance is not None and item["importance"] < float(min_importance)
            if not (stale and low_imp):
                continue
            if merge_threshold is not None and self._redundant_with(
                rid, ranked, float(merge_threshold)
            ):
                merged.append(rid)
            else:
                pruned.append(rid)
            self.delete(rid)
        return {
            "pruned": len(pruned),
            "pruned_ids": pruned,
            "merged": len(merged),
            "merged_ids": merged,
            "kept": self.stats()["total"],
        }

    def _redundant_with(self, row_id: str, ranked: list[dict[str, Any]], threshold: float) -> bool:
        """True if ``row_id`` is a near-duplicate (hybrid sim >= threshold) of any retained doc."""
        doc = self._index.get(row_id)
        if doc is None:
            return False
        q_tokens = tokenize(doc.text)
        q_vec = doc.vector
        for other in ranked:
            if other["id"] == row_id:
                continue
            odoc = self._index.get(other["id"])
            if odoc is None:
                continue
            vec = max(0.0, min(1.0, cosine_similarity(q_vec, odoc.vector)))
            kw = keyword_score(q_tokens, tokenize(odoc.text))
            blended = (self._kw_weight * kw) + ((1.0 - self._kw_weight) * vec)
            if blended >= threshold:
                return True
        return False

    def recall(
        self,
        query: str,
        k: int = 5,
        metadata_filter: dict[str, Any] | None = None,
    ) -> list[ScoredDoc]:
        """Preserved original API — delegates to hybrid :meth:`search`."""
        return self.search(query, limit=k, filters=metadata_filter)

    # -- Mutation helpers ---------------------------------------------------

    def _update_locked(
        self,
        row_id: str,
        text: str,
        metadata: dict[str, Any],
        user_id: str | None,
        keep_created: bool = False,
    ) -> None:
        now = time.time()
        self._index.add(row_id, text, metadata)
        prev_user = self._user_ids.get(row_id)
        self._user_ids[row_id] = user_id if user_id is not None else prev_user
        created_at = self._created_at.get(row_id, now) if keep_created else now
        self._created_at[row_id] = created_at
        self._updated_at[row_id] = now
        self._persist(row_id, text, metadata, self._user_ids[row_id], created_at, now)

    def update(
        self,
        row_id: str,
        text: str | None = None,
        metadata: dict[str, Any] | None = None,
        user_id: str | None = None,
    ) -> bool:
        """Update an existing memory by id. Returns True on success."""
        with self._lock:
            doc = self._index.get(row_id)
            if doc is None:
                return False
            new_text = text if text is not None else doc.text
            new_meta = dict(metadata) if metadata is not None else dict(doc.metadata)
            self._update_locked(row_id, new_text, new_meta, user_id)
            return True

    def delete(self, row_id: str) -> bool:
        """Delete a memory by id. Returns True if it existed."""
        with self._lock:
            removed = self._index.remove(row_id)
            if removed:
                self._user_ids.pop(row_id, None)
                self._created_at.pop(row_id, None)
                self._updated_at.pop(row_id, None)
                self._access_count.pop(row_id, None)
                self._delete_row(row_id)
            return removed

    def list(self, limit: int | None = None, user_id: str | None = None) -> list[dict[str, Any]]:
        """List stored memories as dicts (``id``, ``text``, ``metadata``,
        ``user_id``, ``created_at``, ``updated_at``)."""
        with self._lock:
            items: list[dict[str, Any]] = []
            for doc in self._index._documents.values():
                if user_id is not None and self._user_ids.get(doc.id) != user_id:
                    continue
                items.append(
                    {
                        "id": doc.id,
                        "text": doc.text,
                        "metadata": dict(doc.metadata),
                        "user_id": self._user_ids.get(doc.id),
                        "created_at": self._created_at.get(doc.id),
                        "updated_at": self._updated_at.get(doc.id),
                    }
                )
        items.sort(key=lambda d: d.get("updated_at") or 0.0, reverse=True)
        if limit is None:
            return items
        return items[:limit]

    def remember(
        self,
        id: str,
        text: str,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """Preserved original API — store/replace a doc by explicit id."""
        meta = dict(metadata or {})
        now = time.time()
        with self._lock:
            self._index.get(id)
            created_at = self._created_at.get(id, now)
            self._index.add(id, text, meta)
            self._created_at.setdefault(id, created_at)
            self._updated_at[id] = now
            self._persist(id, text, meta, self._user_ids.get(id), created_at, now)
        return id

    # -- Stats --------------------------------------------------------------

    def stats(self) -> dict[str, Any]:
        """Return store statistics (counts)."""
        with self._lock:
            total = self._index.count()
            by_user: dict[str, int] = Counter()
            for uid in self._user_ids.values():
                by_user[uid if uid is not None else "<none>"] += 1
            return {
                "total": total,
                "memories": total,
                "by_user": dict(by_user),
                "db_path": self._db_path,
                "persisted": self._db_path is not None,
                "threshold": self._threshold,
                "vector_weight": round(1.0 - self._kw_weight, 3),
            }

    def close(self) -> None:
        """Close the underlying SQLite connection (if any)."""
        if self._conn is not None:
            try:
                self._conn.close()
            finally:
                self._conn = None

    def __del__(self) -> None:  # pragma: no cover - best-effort cleanup
        with contextlib.suppress(Exception):
            self.close()
