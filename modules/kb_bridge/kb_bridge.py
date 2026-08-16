"""
KnowledgeBaseBridge — Enterprise-grade wrapper around Hermes KB Universal.

Provides typesafe, event-publishing, thread-safe access to every KB
operation: search, CRUD for patterns/skills/operations, vector search,
metrics, and health checks.

All public methods are thread-safe via internal RLock.  Events are
published to the Platform Kernel EventBus when configured.

Python: 3.10+
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import sys
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

# ---------------------------------------------------------------------------
# Resolve hermes_kb_universal import path.
# The core library lives in ENI_Swarm_NEW/lib/, sibling to the enterprise
# package.  We fall back gracefully if the path is not on sys.path.
# ---------------------------------------------------------------------------
_HERMES_LIB_PATH: Path = (
    Path(__file__).resolve().parent / "lib"
)
if str(_HERMES_LIB_PATH) not in sys.path:
    sys.path.insert(0, str(_HERMES_LIB_PATH))

try:
    import hermes_kb_universal as _kb
except ImportError:  # pragma: no cover – only triggers in non-standard layouts
    _kb = None  # type: ignore[assignment]
    _FALLBACK = True
else:
    _FALLBACK = False

# Platform kernel types (lightweight import to avoid circular deps)
try:
    from enterprise.platform_kernel import (  # type: ignore[import-untyped]
        Event,
        EventBus,
        EventPriority,
        HealthStatus,
    )
except ImportError:
    Event = None  # type: ignore[assignment,misc]
    EventBus = None  # type: ignore[assignment,misc]
    EventPriority = None  # type: ignore[assignment,misc]
    HealthStatus = None  # type: ignore[assignment,misc]

# ---------------------------------------------------------------------------
# Logger
# ---------------------------------------------------------------------------
_log: logging.Logger = logging.getLogger("enterprise.kb.bridge")


# ======================================================================
# Dataclasses
# ======================================================================


@dataclass
class PatternRecord:
    """Normalised representation of a KB pattern row."""

    id: int
    pattern_hash: str
    pattern_type: str
    title: str
    content: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    source_profile: Optional[str] = None
    source_session: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    access_count: int = 0
    last_accessed: Optional[datetime] = None

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "PatternRecord":
        """Build from a sqlite3 Row."""
        d = dict(row)
        # Parse JSON fields
        for field_name in ("metadata", "tags"):
            raw = d.get(field_name)
            if isinstance(raw, str):
                try:
                    d[field_name] = json.loads(raw)
                except (json.JSONDecodeError, TypeError):
                    d[field_name] = [] if field_name == "tags" else {}
        # Timestamps
        for ts_field in ("created_at", "updated_at", "last_accessed"):
            val = d.get(ts_field)
            if val is not None:
                try:
                    d[ts_field] = datetime.fromtimestamp(val, tz=timezone.utc)
                except (TypeError, OSError, ValueError):
                    d[ts_field] = None
        return cls(**{k: v for k, v in d.items() if k in cls.__annotations__})

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to a JSON-frriendly dict."""
        result: Dict[str, Any] = {
            "id": self.id,
            "pattern_hash": self.pattern_hash,
            "pattern_type": self.pattern_type,
            "title": self.title,
            "content": self.content,
            "metadata": self.metadata,
            "source_profile": self.source_profile,
            "source_session": self.source_session,
            "tags": self.tags,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "access_count": self.access_count,
            "last_accessed": (
                self.last_accessed.isoformat() if self.last_accessed else None
            ),
        }
        return result


@dataclass
class SearchResult:
    """Result from a knowledge-base search."""
    items: List[PatternRecord] = field(default_factory=list)
    total_count: int = 0
    query: Optional[str] = None
    pattern_type: Optional[str] = None
    execution_time_ms: float = 0.0


@dataclass
class MetricSnapshot:
    """KB metrics at a point in time."""
    patterns_total: int = 0
    patterns_by_type: Dict[str, int] = field(default_factory=dict)
    patterns_by_profile: Dict[str, int] = field(default_factory=dict)
    operations_total: int = 0
    operations_by_type: Dict[str, int] = field(default_factory=dict)
    operations_by_tool: Dict[str, int] = field(default_factory=dict)
    sessions_total: int = 0
    files_tracked: int = 0
    files_by_op: Dict[str, int] = field(default_factory=dict)
    config_changes: int = 0
    db_sizes_kb: Dict[str, int] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "patterns_total": self.patterns_total,
            "patterns_by_type": self.patterns_by_type,
            "patterns_by_profile": self.patterns_by_profile,
            "operations_total": self.operations_total,
            "operations_by_type": self.operations_by_type,
            "operations_by_tool": self.operations_by_tool,
            "sessions_total": self.sessions_total,
            "files_tracked": self.files_tracked,
            "files_by_op": self.files_by_op,
            "config_changes": self.config_changes,
            "db_sizes_kb": self.db_sizes_kb,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class HealthReport:
    """Result of a KB health check."""
    status: HealthStatus = HealthStatus.UNKNOWN
    databases_ok: int = 0
    databases_total: int = 0
    message: str = ""
    response_time_ms: float = 0.0
    details: Dict[str, Any] = field(default_factory=dict)


# ======================================================================
# Helpers
# ======================================================================

def _now_epoch() -> int:
    """Return current unix timestamp as int."""
    return int(time.time())


def _safe_json_load(raw: Any) -> Any:
    """Safely load a JSON-string field, returning the original if it fails."""
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return raw
    return raw


# ======================================================================
# KnowledgeBaseBridge
# ======================================================================


class KnowledgeBaseBridge:
    """Enterprise bridge over hermes_kb_universal.

    Provides thread-safe, event-publishing wrappers for all KB operations.
    """

    # Databases known to the KB manager
    _DB_NAMES: Tuple[str, ...] = (
        "patterns",
        "skills",
        "sessions",
        "operations",
        "vectors",
    )

    def __init__(
        self,
        event_bus: Optional[EventBus] = None,
        profile: str = "default",
        publish_events: bool = True,
    ) -> None:
        """Initialise the bridge.

        Args:
            event_bus: Platform EventBus for publishing KB events.
            profile: Hermes profile name (used for source tracking).
            publish_events: Whether to emit events on the bus.
        """
        if _FALLBACK or _kb is None:
            raise RuntimeError(
                "hermes_kb_universal not available; "
                f"expected at {_HERMES_LIB_PATH}"
            )

        self._event_bus: Optional[EventBus] = event_bus
        self._profile: str = profile
        self._publish_events: bool = publish_events
        self._lock: threading.RLock = threading.RLock()
        self._kb_manager = _kb.get_kb()

        _log.info(
            "KnowledgeBaseBridge initialised (profile=%s, events=%s)",
            profile,
            publish_events,
        )

    # ── Event Bus ─────────────────────────────────────────────────────────────

    def set_event_bus(self, bus: EventBus) -> None:
        """Replace the event bus reference."""
        with self._lock:
            self._event_bus = bus

    def _publish(self, topic: str, payload: Dict[str, Any], priority: EventPriority = EventPriority.NORMAL) -> None:
        """Publish an event if event bus is wired and publishing is enabled."""
        if not self._publish_events or self._event_bus is None:
            return
        if Event is None:
            return
        try:
            event = Event.create(
                topic=topic,
                source="kb_bridge",
                payload=payload,
                priority=priority,
            )
            self._event_bus.publish(event)
        except Exception as exc:
            _log.warning("Failed to publish event %s: %s", topic, exc)

    # ── Low-level DB access ────────────────────────────────────────────────

    def _execute(
        self, db_name: str, sql: str, params: tuple = ()
    ) -> List[sqlite3.Row]:
        """Execute a read-only query on the named database."""
        with self._lock:
            with self._kb_manager.transaction(db_name) as conn:
                return conn.execute(sql, params).fetchall()

    def _execute_write(
        self, db_name: str, sql: str, params: tuple = ()
    ) -> int:
        """Execute a write query; returns lastrowid."""
        with self._lock:
            with self._kb_manager.transaction(db_name) as conn:
                cursor = conn.execute(sql, params)
                return cursor.lastrowid

    # ── Patterns CRUD ──────────────────────────────────────────────────────

    def create_pattern(
        self,
        pattern_type: str,
        title: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
        tags: Optional[List[str]] = None,
        session_id: Optional[str] = None,
    ) -> PatternRecord:
        """Create (or touch) a knowledge-base pattern.

        Returns the full PatternRecord after insertion/update.
        """
        t_start = time.perf_counter()
        now = _now_epoch()

        with self._lock:
            try:
                pid = _kb.store_pattern(
                    pattern_type=pattern_type,
                    title=title,
                    content=content,
                    metadata=metadata,
                    profile=self._profile,
                    session=session_id or os.environ.get("HERMES_SESSION", "default"),
                    tags=tags,
                )
            except Exception:
                _log.exception("create_pattern failed")
                raise

        # Fetch back the full row
        rows = self._execute("patterns", "SELECT * FROM patterns WHERE id = ?", (pid,))
        if not rows:
            raise RuntimeError(f"Pattern {pid} created but not found")

        record = PatternRecord.from_row(rows[0])
        elapsed = (time.perf_counter() - t_start) * 1000.0

        self._publish(
            "kb.pattern.created",
            {
                "pattern_id": pid,
                "pattern_type": pattern_type,
                "title": title,
                "profile": self._profile,
                "execution_time_ms": round(elapsed, 2),
            },
        )
        _log.debug("Pattern created: id=%s type=%s", pid, pattern_type)
        return record

    def read_pattern(self, pattern_id: int) -> Optional[PatternRecord]:
        """Retrieve a single pattern by primary key."""
        rows = self._execute("patterns", "SELECT * FROM patterns WHERE id = ?", (pattern_id,))
        if rows:
            return PatternRecord.from_row(rows[0])
        return None

    def update_pattern(
        self,
        pattern_id: int,
        title: Optional[str] = None,
        content: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        tags: Optional[List[str]] = None,
    ) -> Optional[PatternRecord]:
        """Update one or more fields of an existing pattern."""
        with self._lock:
            existing = self._execute(
                "patterns", "SELECT * FROM patterns WHERE id = ?", (pattern_id,)
            )
            if not existing:
                return None

            new_title = title if title is not None else existing[0]["title"]
            new_content = content if content is not None else existing[0]["content"]
            new_meta = (
                json.dumps(metadata)
                if metadata is not None
                else existing[0]["metadata"]
            )
            new_tags = json.dumps(tags) if tags is not None else existing[0]["tags"]
            now = _now_epoch()

            with self._kb_manager.transaction("patterns") as conn:
                conn.execute(
                    """UPDATE patterns
                       SET title=?, content=?, metadata=?, tags=?,
                           updated_at=?
                       WHERE id=?""",
                    (new_title, new_content, new_meta, new_tags, now, pattern_id),
                )

        updated = self.read_pattern(pattern_id)
        if updated:
            self._publish(
                "kb.pattern.updated",
                {
                    "pattern_id": pattern_id,
                    "title": new_title,
                    "profile": self._profile,
                },
            )
        return updated

    def delete_pattern(self, pattern_id: int) -> bool:
        """Delete a pattern by primary key.  Returns True if a row was removed."""
        with self._lock:
            with self._kb_manager.transaction("patterns") as conn:
                cur = conn.execute("DELETE FROM patterns WHERE id = ?", (pattern_id,))
                deleted = cur.rowcount > 0

        if deleted:
            self._publish(
                "kb.pattern.deleted",
                {"pattern_id": pattern_id, "profile": self._profile},
            )
        return deleted

    def search_patterns(
        self,
        query: Optional[str] = None,
        pattern_type: Optional[str] = None,
        tags: Optional[List[str]] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> SearchResult:
        """Full-text / filtered search across patterns."""
        t_start = time.perf_counter()

        raw = _kb.search_patterns(
            query=query,
            pattern_type=pattern_type,
            profile=self._profile,
            tags=tags,
            limit=limit,
            offset=offset,
        )

        elapsed = (time.perf_counter() - t_start) * 1000.0
        items = [PatternRecord.from_row(r) for r in raw] if raw else []

        # Count total without limit/offset for caller awareness
        total_sql = "SELECT COUNT(*) FROM patterns WHERE 1=1"
        total_params: list = []
        if query:
            total_sql += " AND (title LIKE ? OR content LIKE ?)"
            total_params.extend([f"%{query}%", f"%{query}%"])
        if pattern_type:
            total_sql += " AND pattern_type = ?"
            total_params.append(pattern_type)
        count_rows = self._execute("patterns", total_sql, tuple(total_params))
        total = count_rows[0][0] if count_rows else 0

        result = SearchResult(
            items=items,
            total_count=total or len(items),
            query=query,
            pattern_type=pattern_type,
            execution_time_ms=round(elapsed, 2),
        )

        self._publish(
            "kb.search.performed",
            {
                "query": query,
                "pattern_type": pattern_type,
                "results_count": len(items),
                "execution_time_ms": result.execution_time_ms,
                "profile": self._profile,
            },
        )
        return result

    def list_patterns_by_type(self) -> Dict[str, int]:
        """Return count breakdown by pattern_type."""
        rows = self._execute(
            "patterns",
            "SELECT pattern_type, COUNT(*) as cnt FROM patterns GROUP BY pattern_type",
        )
        return {r["pattern_type"]: r["cnt"] for r in rows}

    # ── Skills CRUD ────────────────────────────────────────────────────────

    def sync_skills(self) -> Dict[str, Any]:
        """Sync Hermes skills from disk into the KB skills table.

        Returns the result dict from hermes_kb_universal.sync_skills().
        """
        t_start = time.perf_counter()
        try:
            result = _kb.sync_skills()
        except Exception:
            _log.exception("sync_skills failed")
            raise
        elapsed = (time.perf_counter() - t_start) * 1000.0

        self._publish(
            "kb.skill.synced",
            {
                "synced": result.get("synced", 0),
                "updated": result.get("updated", 0),
                "errors": len(result.get("errors", [])),
                "execution_time_ms": round(elapsed, 2),
            },
        )
        return result

    def list_skills(
        self,
        category: Optional[str] = None,
        enabled_only: bool = True,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """List skills with optional filters."""
        sql = "SELECT id, name, category, description, version, tags, enabled, use_count, last_used FROM skills WHERE 1=1"
        params: list = []

        if category:
            sql += " AND category = ?"
            params.append(category)
        if enabled_only:
            sql += " AND enabled = 1"
        sql += " ORDER BY use_count DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        rows = self._execute("skills", sql, tuple(params))
        results: List[Dict[str, Any]] = []
        for row in rows:
            d = dict(row)
            d["tags"] = _safe_json_load(d.get("tags"))
            d["enabled"] = bool(d.get("enabled"))
            results.append(d)
        return results

    def get_skill(self, skill_id: int) -> Optional[Dict[str, Any]]:
        """Retrieve a single skill with full content."""
        rows = self._execute("skills", "SELECT * FROM skills WHERE id = ?", (skill_id,))
        if not rows:
            return None
        d = dict(rows[0])
        d["tags"] = _safe_json_load(d.get("tags"))
        d["dependencies"] = _safe_json_load(d.get("dependencies"))
        d["enabled"] = bool(d.get("enabled"))
        return d

    def update_skill(
        self,
        skill_id: int,
        **fields: Any,
    ) -> Optional[Dict[str, Any]]:
        """Update editable fields on a skill row.

        Allowed keys: category, description, version, enabled, tags, content.
        """
        allowed = {"category", "description", "version", "enabled", "tags", "content"}
        updates = {k: v for k, v in fields.items() if k in allowed}
        if not updates:
            return self.get_skill(skill_id)

        set_clause_parts: List[str] = []
        set_params: list = []
        for key, val in updates.items():
            if key == "enabled":
                set_clause_parts.append("enabled = ?")
                set_params.append(1 if val else 0)
            elif key == "tags":
                set_clause_parts.append("tags = ?")
                set_params.append(json.dumps(val) if isinstance(val, list) else val)
            else:
                set_clause_parts.append(f"{key} = ?")
                set_params.append(val)
        set_params.append(skill_id)
        set_params.append(_now_epoch())

        with self._lock:
            with self._kb_manager.transaction("skills") as conn:
                conn.execute(
                    f"""UPDATE skills SET {', '.join(set_clause_parts)}, updated_at = ? WHERE id = ?""",
                    tuple(set_params),
                )

        updated = self.get_skill(skill_id)
        if updated:
            self._publish(
                "kb.skill.updated",
                {
                    "skill_id": skill_id,
                    "name": updated.get("name"),
                    "fields": list(updates.keys()),
                },
            )
        return updated

    def get_skill_count(self) -> int:
        """Return total number of skills in the KB."""
        rows = self._execute("skills", "SELECT COUNT(*) FROM skills")
        return rows[0][0] if rows else 0

    # ── Operations ────────────────────────────────────────────────────────

    def store_operation(
        self,
        op_type: str,
        input_data: Optional[Dict[str, Any]] = None,
        output_data: Optional[Dict[str, Any]] = None,
        result: str = "success",
        error_message: Optional[str] = None,
        duration_ms: Optional[int] = None,
        tool_name: Optional[str] = None,
        command_name: Optional[str] = None,
        session_id: Optional[str] = None,
        working_dir: Optional[str] = None,
        git_commit: Optional[str] = None,
        tags: Optional[List[str]] = None,
    ) -> str:
        """Store an operation log entry.  Returns the operation ID."""
        try:
            op_id = _kb.store_operation(
                op_type=op_type,
                input_data=input_data,
                output_data=output_data,
                result=result,
                error_message=error_message,
                duration_ms=duration_ms,
                tool_name=tool_name,
                command_name=command_name,
                session_id=session_id,
                profile=self._profile,
                working_dir=working_dir,
                git_commit=git_commit,
                tags=tags,
            )
            _log.debug("Operation stored: %s", op_id)
            return op_id
        except Exception:
            _log.exception("store_operation failed")
            raise

    def list_operations(
        self,
        session_id: Optional[str] = None,
        op_type: Optional[str] = None,
        tool_name: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """Query operations with filters."""
        sql = "SELECT * FROM operations WHERE 1=1"
        params: list = []

        if session_id:
            sql += " AND session_id = ?"
            params.append(session_id)
        if op_type:
            sql += " AND op_type = ?"
            params.append(op_type)
        if tool_name:
            sql += " AND tool_name = ?"
            params.append(tool_name)
        sql += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        rows = self._execute("operations", sql, tuple(params))
        results: List[Dict[str, Any]] = []
        for row in rows:
            d = dict(row)
            d["input_data"] = _safe_json_load(d.get("input_data"))
            d["output_data"] = _safe_json_load(d.get("output_data"))
            d["tags"] = _safe_json_load(d.get("tags"))
            results.append(d)
        return results

    def get_operation_count(self) -> int:
        """Return total number of logged operations."""
        rows = self._execute("operations", "SELECT COUNT(*) FROM operations")
        return rows[0][0] if rows else 0

    # ── Vector / Semantic Search ──────────────────────────────────────────

    def semantic_search(
        self,
        query: str,
        limit: int = 10,
        min_similarity: float = 0.3,
        model_name: str = "all-MiniLM-L6-v2",
    ) -> List[Dict[str, Any]]:
        """Run semantic vector search against the KB.

        Returns patterns ranked by cosine similarity.
        """
        t_start = time.perf_counter()
        try:
            results = _kb.semantic_search(
                query=query,
                limit=limit,
                min_similarity=min_similarity,
                model_name=model_name,
            )
        except RuntimeError:
            # sentence-transformers not installed – return empty gracefully
            _log.warning("semantic_search unavailable: sentence-transformers missing")
            results = []
        except Exception:
            _log.exception("semantic_search failed")
            raise

        elapsed = (time.perf_counter() - t_start) * 1000.0

        self._publish(
            "kb.search.performed",
            {
                "query": query,
                "search_type": "semantic",
                "model": model_name,
                "results_count": len(results),
                "execution_time_ms": round(elapsed, 2),
                "profile": self._profile,
            },
        )
        return results

    # ── Metrics ──────────────────────────────────────────────────────────────

    def get_metrics(self) -> MetricSnapshot:
        """Collect comprehensive KB metrics."""
        t_start = time.perf_counter()

        with self._lock:
            stats = _kb.get_stats()

        snapshot = MetricSnapshot(
            patterns_total=stats.get("patterns_total", 0),
            patterns_by_type=stats.get("patterns_by_type", {}),
            patterns_by_profile=stats.get("patterns_by_profile", {}),
            operations_total=stats.get("operations_total", 0),
            operations_by_type=stats.get("operations_by_type", {}),
            operations_by_tool=stats.get("operations_by_tool", {}),
            sessions_total=stats.get("sessions_total", 0),
            files_tracked=stats.get("files_tracked", 0),
            files_by_op=stats.get("files_by_op", {}),
            config_changes=stats.get("config_changes", 0),
            db_sizes_kb={
                k: v
                for k, v in stats.items()
                if k.endswith("_db_size_kb")
            },
        )

        elapsed = (time.perf_counter() - t_start) * 1000.0
        _log.debug("Metrics collected in %.2f ms", elapsed)
        return snapshot

    def get_db_sizes(self) -> Dict[str, int]:
        """Return file sizes (KB) for each KB database."""
        db_paths = {
            "patterns": _kb.PATTERNS_DB,
            "skills": _kb.SKILLS_DB,
            "sessions": _kb.SESSIONS_DB,
            "operations": _kb.OPERATIONS_DB,
            "vectors": _kb.VECTORS_DB,
        }
        sizes: Dict[str, int] = {}
        with self._lock:
            for name, path in db_paths.items():
                if path.exists():
                    sizes[name] = path.stat().st_size // 1024
                else:
                    sizes[name] = 0
        return sizes

    # ── Health ──────────────────────────────────────────────────────────────

    def health_check(self) -> HealthReport:
        """Check connectivity to all KB databases."""
        t_start = time.perf_counter()
        details: Dict[str, Any] = {}
        ok = 0
        db_paths = {
            "patterns": _kb.PATTERNS_DB,
            "skills": _kb.SKILLS_DB,
            "sessions": _kb.SESSIONS_DB,
            "operations": _kb.OPERATIONS_DB,
            "vectors": _kb.VECTORS_DB,
        }

        with self._lock:
            for name, path in db_paths.items():
                try:
                    conn = sqlite3.connect(
                        str(path), timeout=5, check_same_thread=False
                    )
                    conn.execute("SELECT 1")
                    conn.close()
                    ok += 1
                    details[name] = "ok"
                except Exception as exc:
                    details[name] = str(exc)
                    _log.warning("Health check failed for %s: %s", name, exc)

        elapsed = (time.perf_counter() - t_start) * 1000.0
        total = len(db_paths)

        if ok == total:
            status = HealthStatus.HEALTHY
            msg = "All databases reachable"
        elif ok == 0:
            status = HealthStatus.UNHEALTHY
            msg = "No databases reachable"
        else:
            status = HealthStatus.DEGRADED
            msg = f"{ok}/{total} databases reachable"

        return HealthReport(
            status=status,
            databases_ok=ok,
            databases_total=total,
            message=msg,
            response_time_ms=round(elapsed, 2),
            details=details,
        )

    # ── Cleanup ──────────────────────────────────────────────────────

    def close(self) -> None:
        """Close all KB database connections."""
        with self._lock:
            self._kb_manager.close_all()
            _log.info("KnowledgeBaseBridge connections closed")


# ======================================================================
# KBHealthCheck – thin standalone for health integration
# ======================================================================

class KBHealthCheck:
    """Lightweight health check helper, usable by the ENIKBModule."""

    def __init__(self, bridge: KnowledgeBaseBridge) -> None:
        self._bridge = bridge

    def run(self) -> HealthReport:
        """Run the full health check."""
        return self._bridge.health_check()