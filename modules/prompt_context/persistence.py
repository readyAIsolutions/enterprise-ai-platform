"""
Prompt & Context Persistence — Master-class persistent state layer.
===================================================================

Adds durable persistence and real A/B variant optimization to the
prompt_context module:

- ``PromptStore``   : SQLite-backed store that persists prompt records
                      ``name -> (template, version, params, status, metadata)``
                      with ``get/put/delete/list/versions`` round-trips that
                      survive a reopen. Can also persist a full serialized
                      prompt record (``record_json``) so the host
                      :class:`PromptRegistry` can round-trip losslessly.
- registry hook     : :class:`PromptRegistry` may opt into SQLite persistence
                      via the ``db_path`` config (default ``data/``;
                      ``None`` = pure in-memory). Existing memory-only API is
                      fully preserved.
- ``ABOptimizer``   : Real epsilon-greedy A/B variant optimizer. Given a prompt
                      and its variants, tracks per-variant statistics
                      (``n, mean_score, best_score, last_used``) and selects a
                      variant deterministically (``seed``) — explores a fraction
                      of the time, otherwise exploits the best-performing variant
                      once it clears the min-sample throttle.

Stdlib only: ``sqlite3``, ``json``, ``random``, ``threading``.
"""

from __future__ import annotations

import json
import os
import random
import sqlite3
import threading
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import builtins

__all__ = [
    "PromptStore",
    "PromptStoreError",
    "PromptNotFoundError",
    "VariantStats",
    "ABOptimizer",
]

DEFAULT_DB_FILENAME = "prompt_context.db"


class PromptStoreError(Exception):
    """Base error for the persistent prompt store."""


class PromptNotFoundError(PromptStoreError):
    """Raised when a requested prompt name does not exist in the store."""


def _now() -> str:
    return datetime.now(UTC).isoformat()


class PromptStore:
    """
    SQLite-backed persistent prompt store.

    Persists prompt records keyed by name with ``get/put/delete/list/versions``.
    A full serialized prompt record can be carried in ``record_json`` so the
    host :class:`PromptRegistry` can round-trip losslessly across a reopen.

    Layout::

        data/
          prompt_context.db      <- SQLite file
    """

    def __init__(self, db_path: str | None = None) -> None:
        """
        Args:
            db_path: Directory (or ``.db`` file path) for the SQLite database.
                ``None`` uses an in-memory database (ephemeral, for tests).
                A directory path is made absolute and ``prompt_context.db``
                is created inside it. Default ``data/`` when not given.
        """
        self._lock = threading.RLock()
        self._db_path = db_path
        self._path = self._resolve_path(db_path)
        self._conn = sqlite3.connect(self._path)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._init_schema()

    # ------------------------------------------------------------------
    # Construction helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _resolve_path(db_path: str | None) -> str:
        if db_path is None:
            return ":memory:"
        path = db_path if db_path.endswith(".db") else os.path.join(db_path, DEFAULT_DB_FILENAME)
        # Make directory-relative paths relative to CWD as-is; ensure parent exists.
        parent = os.path.dirname(os.path.abspath(path))
        if parent and not os.path.isdir(parent):
            os.makedirs(parent, exist_ok=True)
        return path

    def _init_schema(self) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS prompts (
                    name            TEXT PRIMARY KEY,
                    template        TEXT NOT NULL DEFAULT '',
                    version         TEXT NOT NULL DEFAULT '',
                    params_json     TEXT NOT NULL DEFAULT '{}',
                    status          TEXT NOT NULL DEFAULT 'draft',
                    metadata_json   TEXT NOT NULL DEFAULT '{}',
                    record_json     TEXT NOT NULL DEFAULT '{}',
                    updated_at      TEXT NOT NULL
                )
                """
            )
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS prompt_versions (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    name        TEXT NOT NULL,
                    version     TEXT NOT NULL,
                    template    TEXT NOT NULL DEFAULT '',
                    params_json TEXT NOT NULL DEFAULT '{}',
                    status      TEXT NOT NULL DEFAULT 'draft',
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at  TEXT NOT NULL,
                    UNIQUE(name, version)
                )
                """
            )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def put(
        self,
        name: str,
        template: str = "",
        version: str = "",
        params: dict[str, Any] | None = None,
        status: str = "draft",
        metadata: dict[str, Any] | None = None,
        record_json: dict[str, Any] | None = None,
    ) -> None:
        """
        Insert or update a prompt record by name. Any existing ``version``
        history for this name is preserved (append-only on version change).
        """
        now = _now()
        params_json = json.dumps(params or {}, sort_keys=True)
        metadata_json = json.dumps(metadata or {}, sort_keys=True)
        record_payload = json.dumps(record_json or {}, sort_keys=True, default=str)

        with self._lock, self._conn:
            existing = self._conn.execute(
                "SELECT version, template FROM prompts WHERE name=?", (name,)
            ).fetchone()

            self._conn.execute(
                """
                INSERT INTO prompts
                    (name, template, version, params_json, status, metadata_json,
                     record_json, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(name) DO UPDATE SET
                    template=excluded.template,
                    version=excluded.version,
                    params_json=excluded.params_json,
                    status=excluded.status,
                    metadata_json=excluded.metadata_json,
                    record_json=excluded.record_json,
                    updated_at=excluded.updated_at
                """,
                (name, template, version, params_json, status, metadata_json, record_payload, now),
            )

            # Append version history only when the version actually changed
            if existing is None or existing["version"] != version:
                self._conn.execute(
                    """
                    INSERT OR IGNORE INTO prompt_versions
                        (name, version, template, params_json, status,
                         metadata_json, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (name, version, template, params_json, status, metadata_json, now),
                )

    def get(self, name: str) -> dict[str, Any]:
        """
        Fetch a prompt record by name.

        Returns a dict:
            {name, template, version, params, status, metadata,
             record, updated_at}
        """
        with self._lock:
            row = self._conn.execute("SELECT * FROM prompts WHERE name=?", (name,)).fetchone()
        if row is None:
            msg = f"Prompt not found in store: {name}"
            raise PromptNotFoundError(msg)
        return self._row_to_record(row)

    def get_or_none(self, name: str) -> dict[str, Any] | None:
        """Like :meth:`get` but returns ``None`` instead of raising."""
        try:
            return self.get(name)
        except PromptNotFoundError:
            return None

    def delete(self, name: str) -> bool:
        """
        Remove a prompt by name (and its version history). Returns True if the
        prompt existed and was removed.
        """
        with self._lock, self._conn:
            cur = self._conn.execute("DELETE FROM prompts WHERE name=?", (name,))
            self._conn.execute("DELETE FROM prompt_versions WHERE name=?", (name,))
            return cur.rowcount > 0

    def list(self) -> builtins.list[str]:
        """Return all prompt names currently stored."""
        with self._lock:
            rows = self._conn.execute("SELECT name FROM prompts ORDER BY name").fetchall()
        return [r["name"] for r in rows]

    def list_records(self) -> builtins.list[dict[str, Any]]:
        """Return all prompt records as dicts."""
        with self._lock:
            rows = self._conn.execute("SELECT * FROM prompts ORDER BY name").fetchall()
        return [self._row_to_record(r) for r in rows]

    def versions(self, name: str) -> builtins.list[dict[str, Any]]:
        """
        Return the ordered version history for a prompt name.

        Each entry: {name, version, template, params, status, metadata, created_at}
        """
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM prompt_versions WHERE name=? ORDER BY id",
                (name,),
            ).fetchall()
        return [self._row_to_version(r) for r in rows]

    def count(self) -> int:
        """Number of stored prompts."""
        with self._lock:
            row = self._conn.execute("SELECT COUNT(*) AS c FROM prompts").fetchone()
        return int(row["c"])

    def close(self) -> None:
        with self._lock:
            if self._conn is not None:
                self._conn.close()
                self._conn = None

    # ------------------------------------------------------------------
    # Serialization helpers
    # ------------------------------------------------------------------

    def _row_to_record(self, row: sqlite3.Row) -> dict[str, Any]:
        record = {
            "name": row["name"],
            "template": row["template"],
            "version": row["version"],
            "params": json.loads(row["params_json"] or "{}"),
            "status": row["status"],
            "metadata": json.loads(row["metadata_json"] or "{}"),
            "updated_at": row["updated_at"],
        }
        rj = row["record_json"]
        if rj and rj != "{}":
            record["record"] = json.loads(rj)
        return record

    def _row_to_version(self, row: sqlite3.Row) -> dict[str, Any]:
        return {
            "name": row["name"],
            "version": row["version"],
            "template": row["template"],
            "params": json.loads(row["params_json"] or "{}"),
            "status": row["status"],
            "metadata": json.loads(row["metadata_json"] or "{}"),
            "created_at": row["created_at"],
        }

    # ------------------------------------------------------------------
    # Context manager (auto-close)
    # ------------------------------------------------------------------

    def __enter__(self) -> PromptStore:
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()


class VariantStats:
    """Per-variant A/B statistics: sample count, mean/best score, last use."""

    __slots__ = ("n", "sum_score", "best_score", "last_used", "created_at")

    def __init__(
        self,
        n: int = 0,
        sum_score: float = 0.0,
        best_score: float | None = None,
        last_used: str | None = None,
        created_at: str | None = None,
    ) -> None:
        self.n = int(n)
        self.sum_score = float(sum_score)
        self.best_score = best_score
        self.last_used = last_used
        self.created_at = created_at or _now()

    @property
    def mean_score(self) -> float:
        return round(self.sum_score / self.n, 4) if self.n else 0.0

    def record(self, score: float, when: str | None = None) -> None:
        self.n += 1
        self.sum_score += float(score)
        if self.best_score is None or score > self.best_score:
            self.best_score = score
        self.last_used = when or _now()

    def to_dict(self) -> dict[str, Any]:
        return {
            "n": self.n,
            "mean_score": self.mean_score,
            "best_score": self.best_score,
            "last_used": self.last_used,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> VariantStats:
        return cls(
            n=data.get("n", 0),
            sum_score=data.get("n", 0) * data.get("mean_score", 0.0),
            best_score=data.get("best_score"),
            last_used=data.get("last_used"),
            created_at=data.get("created_at"),
        )


class ABOptimizer:
    """
    Real epsilon-greedy A/B variant optimizer.

    Given a prompt name and its variants, records evaluation scores per
    variant and selects which variant to serve using epsilon-greedy:

    - With probability ``epsilon`` (explore): pick uniformly at random.
    - Otherwise (exploit): pick the variant with the highest mean score,
      but only among variants that have cleared ``min_samples`` (throttle).
      If no variant has enough samples yet, fall back to uniform random
      exploration among all variants.

    Deterministic given a fixed ``seed`` (uses a private :class:`random.Random`).

    Statistic tracking: ``n``, ``mean_score``, ``best_score``, ``last_used``.
    Stats are persisted to SQLite so they survive an optimizer reopen when
    ``db_path`` is provided.
    """

    def __init__(
        self,
        prompt: str,
        variants: list[str] | None = None,
        epsilon: float = 0.1,
        min_samples: int = 10,
        seed: int | None = None,
        db_path: str | None = None,
    ) -> None:
        self.prompt = prompt
        self.epsilon = float(epsilon)
        self.min_samples = int(min_samples)
        self._rng = random.Random(seed)
        self._stats: dict[str, VariantStats] = {}
        self._lock = threading.RLock()

        variant_list = list(variants or [])
        for v in variant_list:
            if v not in self._stats:
                self._stats[v] = VariantStats()

        # Optional SQLite persistence of A/B stats
        self._store: PromptStore | None = None
        self._ab_db_path = db_path
        if db_path is not None:
            self._store = PromptStore(db_path)
            self._load_stats()

    # ------------------------------------------------------------------
    # Variants
    # ------------------------------------------------------------------

    def add_variant(self, name: str) -> None:
        """Register a new variant (idempotent)."""
        with self._lock:
            if name not in self._stats:
                self._stats[name] = VariantStats()
            if self._store is not None:
                self._persist_stats()

    @property
    def variants(self) -> list[str]:
        with self._lock:
            return list(self._stats.keys())

    def __len__(self) -> int:
        with self._lock:
            return len(self._stats)

    # ------------------------------------------------------------------
    # Recording
    # ------------------------------------------------------------------

    def record(self, name: str, score: float, when: str | None = None) -> None:
        """Record a single evaluation score for a variant."""
        with self._lock:
            if name not in self._stats:
                self.add_variant(name)
            self._stats[name].record(score, when)
            if self._store is not None:
                self._persist_stats()

    def record_scores(self, scores: dict[str, float]) -> None:
        """Record multiple variant scores at once: {variant: score}."""
        with self._lock:
            for name, score in scores.items():
                if name not in self._stats:
                    self._stats[name] = VariantStats()
                self._stats[name].record(score)
            if self._store is not None:
                self._persist_stats()

    # ------------------------------------------------------------------
    # Selection (epsilon-greedy)
    # ------------------------------------------------------------------

    def select_variant(self) -> str:
        """
        Select a variant to serve this round using epsilon-greedy.

        Returns the variant name.
        """
        with self._lock:
            variants = list(self._stats.keys())
            if not variants:
                msg = f"No variants registered for prompt '{self.prompt}'"
                raise PromptNotFoundError(msg)

            if len(variants) == 1:
                return variants[0]

            # Explore with probability epsilon.
            if self._rng.random() < self.epsilon:
                chosen = self._rng.choice(variants)
            else:
                # Exploit: best mean among variants that cleared min_samples.
                eligible = [v for v in variants if self._stats[v].n >= self.min_samples]
                if not eligible:
                    # Not enough data yet — explore (uniform) to bootstrap.
                    chosen = self._rng.choice(variants)
                else:
                    chosen = max(eligible, key=lambda v: self._stats[v].mean_score)

            self._stats[chosen].last_used = _now()
            if self._store is not None:
                self._persist_stats()
            return chosen

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def stats(self, name: str) -> VariantStats:
        with self._lock:
            if name not in self._stats:
                msg = f"Variant not registered: {name}"
                raise PromptNotFoundError(msg)
            return self._stats[name]

    def all_stats(self) -> dict[str, VariantStats]:
        with self._lock:
            return dict(self._stats)

    def best_variant(self, min_samples: int | None = None) -> str | None:
        """
        Best-performing variant (highest mean score) that has cleared the
        sample throttle. Returns None if none have enough samples.
        """
        threshold = self.min_samples if min_samples is None else min_samples
        with self._lock:
            eligible = [v for v in self._stats if self._stats[v].n >= threshold]
            if not eligible:
                return None
            return max(eligible, key=lambda v: self._stats[v].mean_score)

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _persist_stats(self) -> None:
        if self._store is None:
            return
        for name, st in self._stats.items():
            self._store.put(
                name,
                template="",
                version=str(st.n),
                params={
                    "prompt": self.prompt,
                    "stats": st.to_dict(),
                },
                status="ab_variant",
                metadata={"prompt": self.prompt},
                record_json={
                    "prompt": self.prompt,
                    "variant": name,
                    "stats": st.to_dict(),
                },
            )

    def _load_stats(self) -> None:
        if self._store is None:
            return
        for name in self._store.list():
            rec = self._store.get_or_none(name)
            if not rec or rec.get("status") != "ab_variant":
                continue
            stats_data = rec.get("params", {}).get("stats", {})
            if not stats_data:
                rj = rec.get("record", {})
                stats_data = rj.get("stats", {}) if rj else {}
            if stats_data:
                self._stats[name] = VariantStats.from_dict(stats_data)

    def close(self) -> None:
        if self._store is not None:
            self._store.close()
