"""
Experiment Tracker — Full lifecycle management for agent experiments.

Provides CRUD operations, lineage tracking, reproducibility verification,
and integration with the innovation_rd experiment registry.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

logger = logging.getLogger("enterprise.mlops_lifecycle.experiment_tracker")


class ExperimentStatus(Enum):
    """Status of an experiment through its lifecycle."""

    DRAFT = "draft"
    CONFIGURING = "configuring"
    RUNNING = "running"
    EVALUATING = "evaluating"
    CANARY = "canary"
    COMPLETED = "completed"
    FAILED = "failed"
    ARCHIVED = "archived"


@dataclass
class ExperimentConfig:
    """Configuration for an experiment."""

    name: str
    description: str
    hypothesis: str
    agent_type: str
    model_config: Dict[str, Any]
    prompt_config: Dict[str, Any]
    tool_config: Dict[str, Any]
    eval_config: Dict[str, Any]
    rollout_config: Dict[str, Any]
    tags: Dict[str, str] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> str:
        return json.dumps(asdict(self), default=str)

    @classmethod
    def from_json(cls, json_str: str) -> ExperimentConfig:
        data = json.loads(json_str)
        return cls(**data)


@dataclass
class ExperimentRecord:
    """Complete record of an experiment."""

    experiment_id: str
    config: ExperimentConfig
    status: ExperimentStatus
    created_at: datetime
    updated_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    parent_experiment_id: Optional[str] = None
    lineage: Optional["ExperimentLineage"] = None
    results: Dict[str, Any] = field(default_factory=dict)
    metrics: Dict[str, float] = field(default_factory=dict)
    artifacts: Dict[str, str] = field(default_factory=dict)  # name -> path
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "experiment_id": self.experiment_id,
            "config": json.loads(self.config.to_json()),
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "parent_experiment_id": self.parent_experiment_id,
            "lineage": self.lineage.to_dict() if self.lineage else None,
            "results": self.results,
            "metrics": self.metrics,
            "artifacts": self.artifacts,
            "error": self.error,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ExperimentRecord:
        config = ExperimentConfig.from_json(json.dumps(data["config"]))
        lineage = (
            ExperimentLineage.from_dict(data["lineage"]) if data.get("lineage") else None
        )
        return cls(
            experiment_id=data["experiment_id"],
            config=config,
            status=ExperimentStatus(data["status"]),
            created_at=datetime.fromisoformat(data["created_at"]),
            updated_at=datetime.fromisoformat(data["updated_at"]),
            started_at=(
                datetime.fromisoformat(data["started_at"]) if data.get("started_at") else None
            ),
            completed_at=(
                datetime.fromisoformat(data["completed_at"])
                if data.get("completed_at")
                else None
            ),
            parent_experiment_id=data.get("parent_experiment_id"),
            lineage=lineage,
            results=data.get("results", {}),
            metrics=data.get("metrics", {}),
            artifacts=data.get("artifacts", {}),
            error=data.get("error"),
        )


@dataclass
class ExperimentLineage:
    """Lineage tracking for experiment reproducibility."""

    root_experiment_id: str
    ancestors: List[str] = field(default_factory=list)  # Ordered from root to parent
    fork_point: Optional[str] = None  # Experiment ID where this forked
    fork_reason: Optional[str] = None
    git_commit: Optional[str] = None
    environment_hash: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ExperimentLineage:
        return cls(**data)


class ExperimentTracker:
    """
    Persistent experiment tracker with SQLite backend.

    Provides:
    - Full CRUD for experiments
    - Lineage tracking for reproducibility
    - Query/filter by status, tags, time range
    - Integration with innovation_rd experiment registry
    """

    def __init__(self, db_path: str = "mlops_experiments.db"):
        self.db_path = Path(db_path)
        self._lock = threading.RLock()
        self._init_db()

    def _init_db(self) -> None:
        """Initialize the database schema."""
        with self._get_conn() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS experiments (
                    experiment_id TEXT PRIMARY KEY,
                    config_json TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    started_at TEXT,
                    completed_at TEXT,
                    parent_experiment_id TEXT,
                    lineage_json TEXT,
                    results_json TEXT,
                    metrics_json TEXT,
                    artifacts_json TEXT,
                    error TEXT,
                    FOREIGN KEY (parent_experiment_id) REFERENCES experiments(experiment_id)
                )
            """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_experiments_status
                ON experiments(status)
            """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_experiments_created
                ON experiments(created_at)
            """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_experiments_parent
                ON experiments(parent_experiment_id)
            """
            )
            conn.commit()

    @contextmanager
    def _get_conn(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def create_experiment(
        self,
        config: ExperimentConfig,
        parent_experiment_id: Optional[str] = None,
        fork_reason: Optional[str] = None,
    ) -> ExperimentRecord:
        """Create a new experiment in DRAFT status."""
        experiment_id = f"exp-{uuid.uuid4().hex[:12]}"
        now = datetime.now(timezone.utc)

        lineage = None
        if parent_experiment_id:
            parent = self.get_experiment(parent_experiment_id)
            if parent:
                ancestors = parent.lineage.ancestors + [parent_experiment_id] if parent.lineage else [parent_experiment_id]
                lineage = ExperimentLineage(
                    root_experiment_id=parent.lineage.root_experiment_id if parent.lineage else parent_experiment_id,
                    ancestors=ancestors,
                    fork_point=parent_experiment_id,
                    fork_reason=fork_reason,
                )
            else:
                lineage = ExperimentLineage(root_experiment_id=experiment_id)
        else:
            lineage = ExperimentLineage(root_experiment_id=experiment_id)

        record = ExperimentRecord(
            experiment_id=experiment_id,
            config=config,
            status=ExperimentStatus.DRAFT,
            created_at=now,
            updated_at=now,
            parent_experiment_id=parent_experiment_id,
            lineage=lineage,
        )

        with self._get_conn() as conn:
            conn.execute(
                """
                INSERT INTO experiments
                (experiment_id, config_json, status, created_at, updated_at,
                 parent_experiment_id, lineage_json, results_json, metrics_json, artifacts_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    experiment_id,
                    config.to_json(),
                    ExperimentStatus.DRAFT.value,
                    now.isoformat(),
                    now.isoformat(),
                    parent_experiment_id,
                    json.dumps(lineage.to_dict()),
                    "{}",
                    "{}",
                    "{}",
                ),
            )
            conn.commit()

        logger.info(f"Created experiment {experiment_id}: {config.name}")
        return record

    def get_experiment(self, experiment_id: str) -> Optional[ExperimentRecord]:
        """Retrieve an experiment by ID."""
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM experiments WHERE experiment_id = ?", (experiment_id,)
            ).fetchone()
            if not row:
                return None
            return self._row_to_record(row)

    def update_experiment(self, record: ExperimentRecord) -> ExperimentRecord:
        """Update an existing experiment record."""
        record.updated_at = datetime.now(timezone.utc)
        with self._get_conn() as conn:
            conn.execute(
                """
                UPDATE experiments SET
                    config_json = ?, status = ?, updated_at = ?,
                    started_at = ?, completed_at = ?,
                    lineage_json = ?, results_json = ?, metrics_json = ?,
                    artifacts_json = ?, error = ?
                WHERE experiment_id = ?
            """,
                (
                    record.config.to_json(),
                    record.status.value,
                    record.updated_at.isoformat(),
                    record.started_at.isoformat() if record.started_at else None,
                    record.completed_at.isoformat() if record.completed_at else None,
                    json.dumps(record.lineage.to_dict()) if record.lineage else None,
                    json.dumps(record.results),
                    json.dumps(record.metrics),
                    json.dumps(record.artifacts),
                    record.error,
                    record.experiment_id,
                ),
            )
            conn.commit()
        return record

    def set_status(self, experiment_id: str, status: ExperimentStatus) -> Optional[ExperimentRecord]:
        """Update experiment status with appropriate timestamps."""
        record = self.get_experiment(experiment_id)
        if not record:
            return None
        record.status = status
        now = datetime.now(timezone.utc)
        if status == ExperimentStatus.RUNNING and not record.started_at:
            record.started_at = now
        if status in (ExperimentStatus.COMPLETED, ExperimentStatus.FAILED):
            record.completed_at = now
        return self.update_experiment(record)

    def list_experiments(
        self,
        status: Optional[ExperimentStatus] = None,
        tags: Optional[Dict[str, str]] = None,
        since: Optional[datetime] = None,
        until: Optional[datetime] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[ExperimentRecord]:
        """List experiments with optional filters."""
        query = "SELECT * FROM experiments WHERE 1=1"
        params: List[Any] = []

        if status:
            query += " AND status = ?"
            params.append(status.value)

        if since:
            query += " AND created_at >= ?"
            params.append(since.isoformat())

        if until:
            query += " AND created_at <= ?"
            params.append(until.isoformat())

        query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        with self._get_conn() as conn:
            rows = conn.execute(query, params).fetchall()

        records = [self._row_to_record(row) for row in rows]

        # Filter by tags in Python (JSON extraction in SQLite is limited)
        if tags:
            filtered = []
            for r in records:
                config_tags = r.config.tags
                if all(config_tags.get(k) == v for k, v in tags.items()):
                    filtered.append(r)
            return filtered

        return records

    def get_lineage(self, experiment_id: str) -> List[ExperimentRecord]:
        """Get full lineage chain from root to this experiment."""
        record = self.get_experiment(experiment_id)
        if not record or not record.lineage:
            return [record] if record else []

        lineage_records = []
        for anc_id in record.lineage.ancestors:
            anc = self.get_experiment(anc_id)
            if anc:
                lineage_records.append(anc)
        lineage_records.append(record)
        return lineage_records

    def get_children(self, experiment_id: str) -> List[ExperimentRecord]:
        """Get direct children of an experiment."""
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM experiments WHERE parent_experiment_id = ?", (experiment_id,)
            ).fetchall()
        return [self._row_to_record(row) for row in rows]

    def delete_experiment(self, experiment_id: str, cascade: bool = False) -> bool:
        """Delete an experiment. If cascade, also delete children."""
        with self._get_conn() as conn:
            if cascade:
                children = self.get_children(experiment_id)
                for child in children:
                    self.delete_experiment(child.experiment_id, cascade=True)
            cursor = conn.execute("DELETE FROM experiments WHERE experiment_id = ?", (experiment_id,))
            conn.commit()
            return cursor.rowcount > 0

    def _row_to_record(self, row: sqlite3.Row) -> ExperimentRecord:
        config = ExperimentConfig.from_json(row["config_json"])
        lineage = (
            ExperimentLineage.from_dict(json.loads(row["lineage_json"]))
            if row["lineage_json"]
            else None
        )
        return ExperimentRecord(
            experiment_id=row["experiment_id"],
            config=config,
            status=ExperimentStatus(row["status"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
            started_at=(
                datetime.fromisoformat(row["started_at"]) if row["started_at"] else None
            ),
            completed_at=(
                datetime.fromisoformat(row["completed_at"]) if row["completed_at"] else None
            ),
            parent_experiment_id=row["parent_experiment_id"],
            lineage=lineage,
            results=json.loads(row["results_json"]) if row["results_json"] else {},
            metrics=json.loads(row["metrics_json"]) if row["metrics_json"] else {},
            artifacts=json.loads(row["artifacts_json"]) if row["artifacts_json"] else {},
            error=row["error"],
        )

    def export_experiment(self, experiment_id: str, export_path: Path) -> bool:
        """Export experiment to JSON file for portability."""
        record = self.get_experiment(experiment_id)
        if not record:
            return False
        export_path.write_text(json.dumps(record.to_dict(), indent=2, default=str))
        return True

    def import_experiment(self, import_path: Path) -> Optional[ExperimentRecord]:
        """Import experiment from JSON file."""
        data = json.loads(import_path.read_text())
        record = ExperimentRecord.from_dict(data)
        with self._get_conn() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO experiments
                (experiment_id, config_json, status, created_at, updated_at,
                 started_at, completed_at, parent_experiment_id, lineage_json,
                 results_json, metrics_json, artifacts_json, error)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    record.experiment_id,
                    record.config.to_json(),
                    record.status.value,
                    record.created_at.isoformat(),
                    record.updated_at.isoformat(),
                    record.started_at.isoformat() if record.started_at else None,
                    record.completed_at.isoformat() if record.completed_at else None,
                    record.parent_experiment_id,
                    json.dumps(record.lineage.to_dict()) if record.lineage else None,
                    json.dumps(record.results),
                    json.dumps(record.metrics),
                    json.dumps(record.artifacts),
                    record.error,
                ),
            )
            conn.commit()
        return record


def create_experiment_tracker(db_path: str = "mlops_experiments.db") -> ExperimentTracker:
    """Factory function to create an ExperimentTracker."""
    return ExperimentTracker(db_path)