"""
Pluggable knowledge-source adapters + cross-source query merging for the
ENI Knowledge Base bridge.

This module adds a real, pluggable knowledge-source abstraction on top of the
:class:`~enterprise.modules.kb_bridge.kb_bridge.KnowledgeBaseBridge`.  Instead
of a single monolithic store, callers can attach one or more *source adapters*
— filesystem documents (``.md``/``.txt``), a SQLite ``docs`` table, or a JSON
document array — and run one query across all of them, merging and re-ranking
the results.

Architecture
------------
* :class:`KbDoc`            — a normalized result document.
* :class:`SourceAdapter`    — abstract base for a pluggable source.
* :class:`FileSourceAdapter`  — reads ``.md`` / ``.txt`` files under a directory.
* :class:`SqliteSourceAdapter` — queries a ``docs`` table in a SQLite database.
* :class:`JsonSourceAdapter`   — loads a JSON array of document dicts.
* :class:`SourceRegistry`   — registers / resolves / lists adapters by id.
* :class:`KbMerger`         — fans a query across adapters, dedupes by id,
  re-ranks by score and applies a result limit.
* :class:`KbQueryBridge`    — the user-facing facade.

Design notes
------------
* Standard-library only (``abc``, ``json``, ``sqlite3``, ``pathlib``,
  ``dataclasses``, ``typing``) — no third-party dependencies.
* Matching is term-overlap based: a query is tokenized and each document is
  scored by how many terms (case-insensitive) appear in its text.  Higher
  scores win; ties break deterministically by source + id.
* Every adapter closes its underlying resources; the registry and bridge
  propagate ``close()`` so the whole graph can be torn down in one call.

Python: 3.10+
"""

from __future__ import annotations

import abc
import contextlib
import json
import re
import sqlite3
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import builtins
    from collections.abc import Iterable, Sequence

__all__ = [
    "KbDoc",
    "SourceAdapter",
    "FileSourceAdapter",
    "SqliteSourceAdapter",
    "JsonSourceAdapter",
    "SourceRegistry",
    "KbMerger",
    "KbQueryBridge",
    "tokenize",
    "score_text",
]

# Regex used to split a query into lower-cased keyword terms.
_WORD_RE = re.compile(r"[A-Za-z0-9_]+", re.UNICODE)


def _now_iso() -> str:
    """Current UTC time as an ISO-8601 string (for ``retrieved_at``)."""
    return datetime.now(UTC).isoformat()


def tokenize(text: str) -> list[str]:
    """Split ``text`` into lower-cased keyword terms.

    Non-alphanumeric characters act as separators.  Returns a list of terms
    preserving duplicates (so frequency matters to scoring).
    """
    return _WORD_RE.findall(text.lower())


def score_text(text: str, query: str) -> float:
    """Score ``text`` against ``query`` using term-overlap frequency.

    A higher score means the document is more relevant to the query.  The
    score is the total number of query-term occurrences found in the text;
    missing terms contribute nothing.  Deterministic and dependency-free.
    """
    if not query:
        return 0.0
    text_terms = tokenize(text)
    if not text_terms:
        return 0.0
    query_terms = tokenize(query)
    return float(sum(1 for term in text_terms if term in query_terms))


@dataclass
class KbDoc:
    """A normalized document returned from any knowledge source.

    Attributes:
        id: Unique identifier for the document within its source.
        text: The full textual content of the document.
        source: Identifier of the source adapter that produced this doc.
        metadata: Arbitrary source-specific extra fields.
        score: Relevance score from the latest query (higher is better).
        retrieved_at: UTC ISO-8601 timestamp of retrieval.
    """

    id: str
    text: str
    source: str
    metadata: dict[str, Any] = field(default_factory=dict)
    score: float = 0.0
    retrieved_at: str = field(default_factory=_now_iso)


class SourceAdapter(abc.ABC):
    """Abstract base class for a pluggable knowledge source.

    Subclasses implement :meth:`query`, :meth:`list_docs` and :meth:`close`,
    and expose immutable ``id`` / ``type`` attributes.
    """

    id: str
    type: str

    @abc.abstractmethod
    def query(
        self,
        query: str,
        filters: dict[str, Any] | None = None,
    ) -> list[KbDoc]:
        """Search this source for documents relevant to ``query``.

        Args:
            query: The free-text search query.
            filters: Optional source-specific filter dict (e.g. ``path``,
                ``content_type``, ``min_score``).  Interpretation is
                source-dependent.

        Returns:
            A list of matching :class:`KbDoc` records, best first.
        """

    @abc.abstractmethod
    def list_docs(self, limit: int | None = None) -> list[KbDoc]:
        """List every document available from this source.

        Args:
            limit: If given, cap the number of returned documents.

        Returns:
            A list of :class:`KbDoc` records (order is source-defined).
        """

    @abc.abstractmethod
    def close(self) -> None:
        """Release any underlying resources (files, connections, ...)."""

    def __repr__(self) -> str:  # pragma: no cover - cosmetic
        return f"<{type(self).__name__} id={self.id!r} type={self.type!r}>"


class FileSourceAdapter(SourceAdapter):
    """Adapter that treats every ``.md`` / ``.txt`` file under a directory as
    a knowledge document.

    The document ``id`` is the file's name relative to the root directory;
    ``metadata`` carries the absolute path, size and modification time.
    """

    _SUPPORTED = {".md", ".markdown", ".txt"}

    def __init__(self, directory: str, source_id: str | None = None) -> None:
        self.root = Path(directory).expanduser().resolve()
        self.id = source_id or f"file:{self.root.name}"
        self.type = "file"
        self._extensions: set = set(self._SUPPORTED)
        if not self.root.is_dir():
            msg = f"FileSourceAdapter root does not exist or is not a dir: {self.root}"
            raise FileNotFoundError(msg)

    def _iter_files(self) -> Iterable[Path]:
        for path in sorted(self.root.rglob("*")):
            if path.is_file() and path.suffix.lower() in self._extensions:
                yield path

    def _to_doc(self, path: Path) -> KbDoc:
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            text = ""
        stat = path.stat()
        rel = path.relative_to(self.root).as_posix()
        return KbDoc(
            id=rel,
            text=text,
            source=self.id,
            metadata={
                "path": str(path),
                "size": stat.st_size,
                "mtime": stat.st_mtime,
                "suffix": path.suffix,
            },
        )

    def query(
        self,
        query: str,
        filters: dict[str, Any] | None = None,
    ) -> list[KbDoc]:
        filters = filters or {}
        results: list[KbDoc] = []
        for path in self._iter_files():
            doc = self._to_doc(path)
            if filters.get("path") is not None and str(path) != str(filters["path"]):
                continue
            if filters.get("suffix") is not None:
                if path.suffix.lower() != filters["suffix"].lower():
                    continue
            if not query:
                doc.score = 0.0
            else:
                doc.score = score_text(doc.text, query)
            if doc.score > 0 or not query:
                results.append(doc)
        results.sort(key=lambda d: (-d.score, d.id))
        return results

    def list_docs(self, limit: int | None = None) -> list[KbDoc]:
        docs = [self._to_doc(p) for p in self._iter_files()]
        docs.sort(key=lambda d: d.id)
        return docs[:limit] if limit is not None else docs

    def close(self) -> None:
        # Files are read on demand; nothing to hold open.
        return None


class SqliteSourceAdapter(SourceAdapter):
    """Adapter that reads knowledge documents from a ``docs`` table in a
    SQLite database.

    Expected table schema (created on demand if missing)::

        CREATE TABLE docs (
            id       TEXT PRIMARY KEY,
            text     TEXT NOT NULL,
            source   TEXT DEFAULT '',
            metadata TEXT DEFAULT '{}',   -- JSON object
            score    REAL DEFAULT 0.0
        )

    ``query`` performs a case-insensitive ``LIKE`` match over the ``text``
    column (plus the ``source`` column when a ``source`` filter is given) and
    re-scores the matching rows with :func:`score_text` for consistent
    cross-source ranking.
    """

    def __init__(
        self,
        database: str,
        table: str = "docs",
        source_id: str | None = None,
        auto_create: bool = True,
    ) -> None:
        self.database = str(database)
        self.table = table
        self.id = source_id or f"sqlite:{Path(self.database).name}:{table}"
        self.type = "sqlite"
        self._conn = sqlite3.connect(self.database)
        self._conn.row_factory = sqlite3.Row
        if auto_create:
            self._ensure_table()

    def _ensure_table(self) -> None:
        self._conn.execute(
            f"""CREATE TABLE IF NOT EXISTS {self.table} (
                id       TEXT PRIMARY KEY,
                text     TEXT NOT NULL,
                source   TEXT DEFAULT '',
                metadata TEXT DEFAULT '{{}}',
                score    REAL DEFAULT 0.0
            )"""
        )
        self._conn.commit()

    @staticmethod
    def _parse_meta(raw: Any) -> dict[str, Any]:
        if isinstance(raw, dict):
            return dict(raw)
        if raw is None:
            return {}
        try:
            parsed = json.loads(raw)
            return dict(parsed) if isinstance(parsed, dict) else {}
        except (json.JSONDecodeError, TypeError):
            return {}

    def _row_to_doc(self, row: sqlite3.Row) -> KbDoc:
        return KbDoc(
            id=str(row["id"]),
            text=str(row["text"]),
            source=str(row["source"] or self.id),
            metadata=self._parse_meta(row["metadata"]),
            score=float(row["score"] or 0.0),
        )

    def query(
        self,
        query: str,
        filters: dict[str, Any] | None = None,
    ) -> list[KbDoc]:
        filters = filters or {}
        clauses: list[str] = []
        params: list[Any] = []
        if query:
            clauses.append(f"{self.table}.text LIKE ?")
            params.append(f"%{query}%")
        if filters.get("source"):
            clauses.append(f"{self.table}.source LIKE ?")
            params.append(f"%{filters['source']}%")
        if filters.get("min_score") is not None:
            clauses.append(f"{self.table}.score >= ?")
            params.append(float(filters["min_score"]))
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        sql = f"SELECT * FROM {self.table} {where} ORDER BY {self.table}.score DESC"
        rows = self._conn.execute(sql, params).fetchall()
        results = [self._row_to_doc(r) for r in rows]
        if query:
            for doc in results:
                doc.score = score_text(doc.text, query) + doc.score
        results.sort(key=lambda d: (-d.score, d.id))
        return results

    def list_docs(self, limit: int | None = None) -> list[KbDoc]:
        sql = f"SELECT * FROM {self.table} ORDER BY {self.table}.id"
        rows = self._conn.execute(sql).fetchall()
        docs = [self._row_to_doc(r) for r in rows]
        docs.sort(key=lambda d: d.id)
        return docs[:limit] if limit is not None else docs

    def close(self) -> None:
        with contextlib.suppress(sqlite3.Error):
            self._conn.close()


class JsonSourceAdapter(SourceAdapter):
    """Adapter that loads knowledge documents from a JSON file.

    The file must contain a JSON array of document objects, each with at least
    an ``id`` and ``text`` (``source``, ``metadata`` and ``score`` are
    optional).  The file is parsed lazily on first access.
    """

    def __init__(
        self,
        path: str,
        source_id: str | None = None,
    ) -> None:
        self.path = Path(path).expanduser().resolve()
        self.id = source_id or f"json:{self.path.name}"
        self.type = "json"
        self._docs: list[KbDoc] | None = None
        if not self.path.is_file():
            msg = f"JsonSourceAdapter file not found: {self.path}"
            raise FileNotFoundError(msg)

    def _load(self) -> list[KbDoc]:
        if self._docs is None:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(raw, list):
                msg = f"JsonSourceAdapter expects a JSON array, got {type(raw).__name__}"
                raise ValueError(msg)
            docs: list[KbDoc] = []
            for i, item in enumerate(raw):
                if not isinstance(item, dict):
                    msg = f"JsonSourceAdapter item {i} is not an object: {item!r}"
                    raise ValueError(msg)
                if "id" not in item or "text" not in item:
                    msg = f"JsonSourceAdapter item {i} missing 'id' or 'text': {item!r}"
                    raise ValueError(msg)
                meta = item.get("metadata", {})
                meta = dict(meta) if isinstance(meta, dict) else {}
                if item.get("source"):
                    meta = {**meta, "source": item["source"]}
                docs.append(
                    KbDoc(
                        id=str(item["id"]),
                        text=str(item["text"]),
                        source=self.id,
                        metadata=meta,
                        score=float(item.get("score", 0.0)),
                    )
                )
            self._docs = docs
        return self._docs

    def query(
        self,
        query: str,
        filters: dict[str, Any] | None = None,
    ) -> list[KbDoc]:
        filters = filters or {}
        results: list[KbDoc] = []
        for doc in self._load():
            if filters.get("source") is not None and doc.source != filters["source"]:
                continue
            if not query:
                doc.score = 0.0
                results.append(doc)
                continue
            relevance = score_text(doc.text, query)
            # Pre-stored base score is a boost; inclusion requires a real
            # text match so irrelevant docs never leak in.
            doc.score = relevance + doc.score
            if relevance > 0:
                results.append(doc)
        results.sort(key=lambda d: (-d.score, d.id))
        return results

    def list_docs(self, limit: int | None = None) -> list[KbDoc]:
        docs = sorted(self._load(), key=lambda d: d.id)
        return docs[:limit] if limit is not None else docs

    def close(self) -> None:
        # JSON is parsed into memory; nothing to release.
        self._docs = None


class SourceRegistry:
    """Registry that stores and resolves :class:`SourceAdapter` instances by
    their ``id``.

    This is the discovery point used by :class:`KbMerger` and
    :class:`KbQueryBridge` to decide which sources participate in a query.
    """

    def __init__(self) -> None:
        self._adapters: dict[str, SourceAdapter] = {}

    def register(self, adapter: SourceAdapter) -> SourceAdapter:
        """Register ``adapter`` under ``adapter.id`` and return it.

        Raises:
            ValueError: If an adapter with the same ``id`` is already
                registered.
        """
        if adapter.id in self._adapters:
            msg = f"Source adapter already registered: {adapter.id!r}"
            raise ValueError(msg)
        self._adapters[adapter.id] = adapter
        return adapter

    def get(self, source_id: str) -> SourceAdapter:
        """Return the registered adapter with ``source_id``.

        Raises:
            KeyError: If no adapter with that id is registered.
        """
        return self._adapters[source_id]

    def get_or_create(self, source_id: str) -> SourceAdapter | None:
        """Return the adapter for ``source_id`` or ``None`` if absent."""
        return self._adapters.get(source_id)

    def list(self) -> builtins.list[str]:
        """Return the ids of all registered adapters (sorted)."""
        return sorted(self._adapters.keys())

    def adapters(self) -> builtins.list[SourceAdapter]:
        """Return all registered adapters in registration order."""
        return list(self._adapters.values())

    def remove(self, source_id: str) -> SourceAdapter | None:
        """Unregister and return the adapter with ``source_id`` (if any)."""
        return self._adapters.pop(source_id, None)

    def close(self) -> None:
        """Close every registered adapter and clear the registry."""
        for adapter in self._adapters.values():
            adapter.close()
        self._adapters.clear()


class KbMerger:
    """Runs a query across multiple adapters and merges the results.

    Merging semantics
    -----------------
    1. Fan-out: the query is sent to each selected adapter (or all registered
       adapters when none are selected).
    2. De-duplicate: results sharing the same ``id`` keep only the copy with
       the higher ``score``.
    3. Re-rank: the merged list is sorted by ``score`` descending, then by
       ``source`` then ``id`` for deterministic tie-breaking.
    4. Limit: if ``limit`` is provided, only the top ``limit`` documents are
       returned.
    """

    def __init__(self, registry: SourceRegistry | None = None) -> None:
        self.registry = registry or SourceRegistry()

    @staticmethod
    def _dedupe(docs: Iterable[KbDoc]) -> list[KbDoc]:
        best: dict[str, KbDoc] = {}
        for doc in docs:
            current = best.get(doc.id)
            if current is None or doc.score > current.score:
                best[doc.id] = doc
        return list(best.values())

    def query(
        self,
        query: str,
        filters: dict[str, Any] | None = None,
        source_ids: Sequence[str] | None = None,
        limit: int | None = None,
    ) -> list[KbDoc]:
        """Query one or more sources and return merged, ranked results.

        Args:
            query: The free-text query.
            filters: Optional filters passed through to each adapter.
            source_ids: Optional subset of adapter ids to query.  If ``None``
                or empty, every registered adapter is queried.
            limit: Optional cap on the number of returned documents.

        Returns:
            Merged, de-duplicated, re-ranked :class:`KbDoc` list.
        """
        if source_ids:
            adapters = [self.registry.get(sid) for sid in source_ids]
        else:
            adapters = self.registry.adapters()

        collected: list[KbDoc] = []
        for adapter in adapters:
            collected.extend(adapter.query(query, filters=filters))

        merged = self._dedupe(collected)
        merged.sort(key=lambda d: (-d.score, d.source, d.id))
        if limit is not None and limit > 0:
            merged = merged[:limit]
        return merged

    def close(self) -> None:
        """Close the underlying registry and all its adapters."""
        self.registry.close()


class KbQueryBridge:
    """User-facing facade for querying across multiple knowledge sources.

    Example::

        bridge = KbQueryBridge()
        bridge.register(FileSourceAdapter("docs/"))
        bridge.register(JsonSourceAdapter("manual.json"))
        for doc in bridge.query("deploy", limit=5):
            print(doc.id, doc.score)
        bridge.close()
    """

    def __init__(self, registry: SourceRegistry | None = None) -> None:
        self.registry = registry or SourceRegistry()
        self.merger = KbMerger(self.registry)

    def register(self, adapter: SourceAdapter) -> SourceAdapter:
        """Register a source adapter so it participates in future queries."""
        return self.registry.register(adapter)

    def unregister(self, source_id: str) -> SourceAdapter | None:
        """Remove a source adapter by id; returns it (or ``None``)."""
        return self.registry.remove(source_id)

    def list_sources(self) -> list[str]:
        """Return the ids of all registered sources."""
        return self.registry.list()

    def query(
        self,
        query: str,
        limit: int | None = None,
        source_ids: Sequence[str] | None = None,
        filters: dict[str, Any] | None = None,
    ) -> list[KbDoc]:
        """Query the given sources and return merged, ranked results.

        Args:
            query: The free-text query.
            limit: Optional cap on returned documents.
            source_ids: Optional subset of source ids to query.  ``None`` means
                query every registered source.
            filters: Optional filters forwarded to each adapter.

        Returns:
            Merged, de-duplicated, re-ranked :class:`KbDoc` list.
        """
        return self.merger.query(
            query,
            filters=filters,
            source_ids=source_ids,
            limit=limit,
        )

    def close(self) -> None:
        """Close every registered source and its registry."""
        self.merger.close()
