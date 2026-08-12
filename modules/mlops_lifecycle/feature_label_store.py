"""
Feature/Label Store — versioned, SQLite-backed storage for training/validation
feature vectors, feature sets and label sets used across the MLOps/LLMOps
lifecycle.

Pure-stdlib implementation (sqlite3 + dataclasses). Every mutation is
transactional and every dataset upload is tagged with a monotonically
increasing ``DataVersion`` so downstream stages (canary, eval gates, drift
detection) can reason about the exact data snapshot they are operating on.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("enterprise.mlops_lifecycle.feature_label_store")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class FeatureVector:
    """A single labelled (or unlabelled) feature observation."""

    features: Dict[str, float]
    label: Optional[Any] = None
    vector_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: str = field(default_factory=_now)
    meta: Dict[str, Any] = field(default_factory=dict)


@dataclass
class FeatureSet:
    """Schema describing the ordered feature names for a dataset."""

    name: str
    feature_names: List[str] = field(default_factory=list)
    feature_set_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    description: str = ""
    created_at: str = field(default_factory=_now)


@dataclass
class LabelSet:
    """Schema describing the label semantics for a supervised dataset."""

    name: str
    label_names: List[str] = field(default_factory=list)
    label_set_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    description: str = ""
    created_at: str = field(default_factory=_now)


@dataclass
class DataVersion:
    """A versioned snapshot of data bound to a feature set + label set."""

    version: str
    feature_set_id: str
    label_set_id: Optional[str] = None
    version_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    description: str = ""
    row_count: int = 0
    created_at: str = field(default_factory=_now)


class FeatureLabelStore:
    """SQLite-backed feature/label store with versioned datasets.

    Args:
        db_path: Optional path to a SQLite database file. Defaults to an
            in-memory database (``:memory:``). Pass an explicit path for
            durable persistence.
    """

    def __init__(self, db_path: Optional[str] = None) -> None:
        self._db_path = db_path or ":memory:"
        self._lock = threading.RLock()
        self._conn: Optional[sqlite3.Connection] = None
        self._version_counter = 0
        self.initialize()

    # -- Low-level connection helpers ---------------------------------------

    def initialize(self) -> None:
        """Open the database connection and create the schema."""
        with self._lock:
            if self._conn is not None:
                return
            self._conn = sqlite3.connect(self._db_path)
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._create_schema()
            self._version_counter = self._max_version()

    def _create_schema(self) -> None:
        conn = self._require_conn()
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS feature_sets (
                feature_set_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT DEFAULT '',
                feature_names TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS label_sets (
                label_set_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT DEFAULT '',
                label_names TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS data_versions (
                version_id TEXT PRIMARY KEY,
                version TEXT NOT NULL UNIQUE,
                feature_set_id TEXT NOT NULL,
                label_set_id TEXT,
                description TEXT DEFAULT '',
                row_count INTEGER DEFAULT 0,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS feature_vectors (
                vector_id TEXT PRIMARY KEY,
                version TEXT NOT NULL,
                features TEXT NOT NULL,
                label TEXT,
                timestamp TEXT NOT NULL,
                meta TEXT NOT NULL

            );
            CREATE INDEX IF NOT EXISTS idx_vectors_version
                ON feature_vectors(version);
            """
        )
        conn.commit()

    def _require_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self.initialize()
        assert self._conn is not None
        return self._conn

    def _max_version(self) -> int:
        conn = self._require_conn()
        row = conn.execute("SELECT MAX(CAST(version AS INTEGER)) AS m FROM data_versions").fetchone()
        return int(row["m"] or 0)

    # -- Feature / label set schema -----------------------------------------

    def register_feature_set(
        self,
        name: str,
        feature_names: List[str],
        description: str = "",
    ) -> FeatureSet:
        """Register (or fetch an existing) feature set schema by name."""
        with self._lock:
            conn = self._require_conn()
            existing = conn.execute(
                "SELECT * FROM feature_sets WHERE name = ?", (name,)
            ).fetchone()
            if existing is not None:
                return FeatureSet(
                    feature_set_id=existing["feature_set_id"],
                    name=existing["name"],
                    feature_names=json.loads(existing["feature_names"]),
                    description=existing["description"],
                    created_at=existing["created_at"],
                )
            fs = FeatureSet(
                name=name,
                feature_names=list(feature_names),
                description=description,
            )
            conn.execute(
                "INSERT INTO feature_sets (feature_set_id, name, description, feature_names, created_at)"
                " VALUES (?, ?, ?, ?, ?)",
                (fs.feature_set_id, fs.name, fs.description, json.dumps(fs.feature_names), fs.created_at),
            )
            conn.commit()
            return fs

    def register_label_set(
        self,
        name: str,
        label_names: List[str],
        description: str = "",
    ) -> LabelSet:
        """Register (or fetch an existing) label set schema by name."""
        with self._lock:
            conn = self._require_conn()
            existing = conn.execute(
                "SELECT * FROM label_sets WHERE name = ?", (name,)
            ).fetchone()
            if existing is not None:
                return LabelSet(
                    label_set_id=existing["label_set_id"],
                    name=existing["name"],
                    label_names=json.loads(existing["label_names"]),
                    description=existing["description"],
                    created_at=existing["created_at"],
                )
            ls = LabelSet(name=name, label_names=list(label_names), description=description)
            conn.execute(
                "INSERT INTO label_sets (label_set_id, name, description, label_names, created_at)"
                " VALUES (?, ?, ?, ?, ?)",
                (ls.label_set_id, ls.name, ls.description, json.dumps(ls.label_names), ls.created_at),
            )
            conn.commit()
            return ls

    def get_feature_set(self, feature_set_id: str) -> Optional[FeatureSet]:
        conn = self._require_conn()
        row = conn.execute(
            "SELECT * FROM feature_sets WHERE feature_set_id = ?", (feature_set_id,)
        ).fetchone()
        if row is None:
            return None
        return FeatureSet(
            feature_set_id=row["feature_set_id"],
            name=row["name"],
            feature_names=json.loads(row["feature_names"]),
            description=row["description"],
            created_at=row["created_at"],
        )

    def get_label_set(self, label_set_id: str) -> Optional[LabelSet]:
        conn = self._require_conn()
        row = conn.execute(
            "SELECT * FROM label_sets WHERE label_set_id = ?", (label_set_id,)
        ).fetchone()
        if row is None:
            return None
        return LabelSet(
            label_set_id=row["label_set_id"],
            name=row["name"],
            label_names=json.loads(row["label_names"]),
            description=row["description"],
            created_at=row["created_at"],
        )

    # -- Dataset versions ---------------------------------------------------

    def create_version(
        self,
        feature_set: FeatureSet,
        vectors: List[FeatureVector],
        label_set: Optional[LabelSet] = None,
        description: str = "",
        version: Optional[str] = None,
    ) -> DataVersion:
        """Store a collection of feature vectors as a new immutable snapshot.

        Returns a :class:`DataVersion` that downstream stages can reference.
        """
        with self._lock:
            conn = self._require_conn()
            if version is None:
                self._version_counter += 1
                version = str(self._version_counter)
            # Coerce any existing version to numeric for reliable monotonicity.
            try:
                numeric = int(version)
                if numeric > self._version_counter:
                    self._version_counter = numeric
            except (TypeError, ValueError):
                pass

            dv = DataVersion(
                version=version,
                feature_set_id=feature_set.feature_set_id,
                label_set_id=label_set.label_set_id if label_set else None,
                description=description,
                row_count=len(vectors),
            )
            existing = conn.execute(
                "SELECT version_id FROM data_versions WHERE version = ?", (version,)
            ).fetchone()
            if existing is not None:
                raise ValueError(f"data version already exists: {version!r}")

            conn.execute(
                "INSERT INTO data_versions (version_id, version, feature_set_id, label_set_id,"
                " description, row_count, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    dv.version_id,
                    dv.version,
                    dv.feature_set_id,
                    dv.label_set_id,
                    dv.description,
                    dv.row_count,
                    dv.created_at,
                ),
            )
            for vec in vectors:
                conn.execute(
                    "INSERT INTO feature_vectors (vector_id, version, features, label, timestamp, meta)"
                    " VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        vec.vector_id,
                        version,
                        json.dumps(vec.features),
                        json.dumps(vec.label) if vec.label is not None else None,
                        vec.timestamp,
                        json.dumps(vec.meta),
                    ),
                )
            conn.commit()
            return dv

    def get_version(self, version: str) -> Optional[DataVersion]:
        conn = self._require_conn()
        row = conn.execute(
            "SELECT * FROM data_versions WHERE version = ?", (version,)
        ).fetchone()
        if row is None:
            return None
        return DataVersion(
            version_id=row["version_id"],
            version=row["version"],
            feature_set_id=row["feature_set_id"],
            label_set_id=row["label_set_id"],
            description=row["description"],
            row_count=row["row_count"],
            created_at=row["created_at"],
        )

    def get_vectors(self, version: str) -> List[FeatureVector]:
        """Return all feature vectors belonging to a data version."""
        conn = self._require_conn()
        rows = conn.execute(
            "SELECT * FROM feature_vectors WHERE version = ? ORDER BY timestamp",
            (version,),
        ).fetchall()
        vectors: List[FeatureVector] = []
        for row in rows:
            vec = FeatureVector(
                vector_id=row["vector_id"],
                features=json.loads(row["features"]),
                label=json.loads(row["label"]) if row["label"] is not None else None,
                timestamp=row["timestamp"],
                meta=json.loads(row["meta"]) if row["meta"] else {},
            )
            vectors.append(vec)
        return vectors

    def list_versions(self) -> List[DataVersion]:
        conn = self._require_conn()
        rows = conn.execute("SELECT * FROM data_versions ORDER BY CAST(version AS INTEGER)").fetchall()
        return [
            DataVersion(
                version_id=r["version_id"],
                version=r["version"],
                feature_set_id=r["feature_set_id"],
                label_set_id=r["label_set_id"],
                description=r["description"],
                row_count=r["row_count"],
                created_at=r["created_at"],
            )
            for r in rows
        ]

    def close(self) -> None:
        with self._lock:
            if self._conn is not None:
                try:
                    self._conn.close()
                except sqlite3.Error:  # pragma: no cover - defensive
                    pass
                self._conn = None

    @property
    def is_open(self) -> bool:
        return self._conn is not None

    def __enter__(self) -> "FeatureLabelStore":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()


def create_feature_label_store(config: Optional[Dict[str, Any]] = None) -> FeatureLabelStore:
    """Create :class:`FeatureLabelStore` from config.

    Args:
        config: Optional dict. Supported keys:
            - ``db_path`` (str): SQLite database path (default in-memory).
    """
    config = config or {}
    return FeatureLabelStore(db_path=config.get("db_path"))
