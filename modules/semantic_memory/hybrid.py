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

    def _iter_candidates(self, filters: dict[str, Any] | None) -> list[Any]:
        docs = list(self._index._documents.values())
        if not filters:
            return docs
        return [d for d in docs if _matches_meta(d.metadata, filters)]

    def add(self, id: str, text: str, metadata: dict[str, Any] | None = None) -> str:
        """Add a document to the hybrid retriever (vector + keyword source)."""
        self._index.add(id, text, metadata)
        return id

    def count(self) -> int:
        return self._index.count()

    def search(
        self,
        query: str,
        limit: int = 5,
        filters: dict[str, Any] | None = None,
    ) -> list[ScoredDoc]:
        """Hybrid search merging vector + keyword hits.

        Each candidate doc (optionally pre-filtered by ``filters``) receives a
        blended score ``w_vec * vec_score + w_kw * kw_score``; results are
        sorted descending and the top ``limit`` returned.
        """
        q_tokens = tokenize(query)
        q_vec = self._index.embedder.embed(query)
        ranked: list[ScoredDoc] = []
        for doc in self._iter_candidates(filters):
            vec = max(0.0, min(1.0, cosine_similarity(q_vec, doc.vector)))
            kw = keyword_score(q_tokens, tokenize(doc.text))
            blended = (self._kw_weight * kw) + ((1.0 - self._kw_weight) * vec)
            ranked.append(
                ScoredDoc(
                    id=doc.id,
                    score=round(blended, 6),
                    text=doc.text,
                    metadata=dict(doc.metadata),
                )
            )
        ranked.sort(key=lambda s: s.score, reverse=True)
        if limit <= 0:
            return []
        return ranked[:limit]


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
            self._created_at[row_id] = created_at
            self._updated_at[row_id] = updated_at

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
    ) -> list[ScoredDoc]:
        """Hybrid retrieval: vector + keyword, merged + ranked.

        Args:
            query: Query text.
            limit: Maximum number of results.
            filters: Optional metadata key/value filters
                (e.g. ``{'source': 'kb', 'tags': ['x']}``).

        Returns:
            Ranked :class:`~.semantic_memory.ScoredDoc` list (descending score).
        """
        q_tokens = tokenize(query)
        q_vec = self._index.embedder.embed(query)
        ranked: list[ScoredDoc] = []
        with self._lock:
            for doc in self._iter_candidates(filters):
                vec = max(0.0, min(1.0, cosine_similarity(q_vec, doc.vector)))
                kw = keyword_score(q_tokens, tokenize(doc.text))
                blended = (self._kw_weight * kw) + ((1.0 - self._kw_weight) * vec)
                ranked.append(
                    ScoredDoc(
                        id=doc.id,
                        score=round(blended, 6),
                        text=doc.text,
                        metadata=dict(doc.metadata),
                    )
                )
        ranked.sort(key=lambda s: s.score, reverse=True)
        if limit <= 0:
            return []
        return ranked[:limit]

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
        if keep_created:
            created_at = self._created_at.get(row_id, now)
        else:
            created_at = now
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
            existing = self._index.get(id)
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
        try:
            self.close()
        except Exception:
            pass
