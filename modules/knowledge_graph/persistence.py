"""
Knowledge Graph Persistence (SQLite + in-memory)

Durable, provenance-aware persistence layer for the Knowledge Graph OS module.

Backends
--------
- SQLite (default): a single ``public.db``-style file holds entities,
  relationships, and provenance records in relational tables.
- In-memory (``db_path=None``): same API backed by plain Python containers,
  useful for testing and ephemeral graphs.

Design
------
* Entities are deduplicated by ``(entity_type, id)`` — the natural key of a
  fact. Re-``upsert``ing the same (type, id) updates the stored attributes
  instead of inserting a duplicate row.
* Relationships are stored as directed, typed edges ``(from_id, to_id, type)``
  with an attribute JSON blob.
* Provenance is stored per-entity so that every fact (and each side of a
  contradiction) can cite its sources, evidence, and confidence.
* ``delete_entity`` cascades: the entity's outgoing/incoming relationships and
  its provenance records are removed atomically.
* ``sync(graph)`` snapshots an in-memory graph (an object exposing
  ``entity_registry`` and ``relationship_registry``) into the store, and
  ``load()`` rebuilds an in-memory graph from the store as real
  Entity/Relationship objects.
* Contradiction detection is preserved and provenance-enriched: when a
  contradiction is reported its two sides can be annotated with the
  provenance of the involved entities.
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .entities import Entity, EntityType, EntityRegistry
from .relationships import Relationship, RelationshipType, RelationshipRegistry
from .provenance import Provenance
from .contradiction import ContradictionManager, ContradictionRecord

__all__ = [
    "KGPersistence",
    "create_persistence",
]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _jdefault(o: Any) -> Any:
    """JSON fallback for non-serializable values."""
    if isinstance(o, set):
        return sorted(o)
    if hasattr(o, "value"):
        return o.value
    if isinstance(o, datetime):
        return o.isoformat()
    return str(o)


def _entity_type_str(data: Dict[str, Any]) -> str:
    """Extract the entity type string from a dict/Entity payload."""
    if isinstance(data, Entity):
        return data.entity_type.value
    t = data.get("entity_type") if isinstance(data, dict) else None
    if t is None:
        t = data.get("type")
    return str(t)


def _entity_id_str(data: Dict[str, Any]) -> str:
    if isinstance(data, Entity):
        return data.id
    if isinstance(data, dict):
        return data.get("id") or str(uuid.uuid4())
    return str(data)


_SCHEMA = """
CREATE TABLE IF NOT EXISTS entities (
    id          TEXT NOT NULL,
    type        TEXT NOT NULL,
    attrs_json  TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    PRIMARY KEY (type, id)
);

CREATE TABLE IF NOT EXISTS relationships (
    id          TEXT PRIMARY KEY,
    from_id     TEXT NOT NULL,
    to_id       TEXT NOT NULL,
    type        TEXT NOT NULL,
    attrs_json  TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_relationships_from ON relationships(from_id);
CREATE INDEX IF NOT EXISTS idx_relationships_to   ON relationships(to_id);

CREATE TABLE IF NOT EXISTS provenance (
    id          TEXT PRIMARY KEY,
    entity_id   TEXT NOT NULL,
    source      TEXT NOT NULL,
    evidence    TEXT NOT NULL,
    confidence  REAL NOT NULL,
    created_at  TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_provenance_entity ON provenance(entity_id);
"""


class _MemoryStore:
    """In-memory backend with an identical shape to the SQLite tables."""

    def __init__(self) -> None:
        self.entities: Dict[tuple, Dict[str, Any]] = {}
        self.relationships: Dict[str, Dict[str, Any]] = {}
        self.provenance: Dict[str, List[Dict[str, Any]]] = {}

    def execute_script(self, _sql: str) -> None:
        return None


class KGPersistence:
    """Entity / relationship / provenance persistence backed by SQLite or memory.

    Args:
        db_path: Path to the SQLite database file. If ``None``, an
            in-memory backend is used (no durable store). If a directory
            path is given, a ``knowledge_graph.db`` file is created inside it.
    """

    def __init__(self, db_path: Optional[str] = None) -> None:
        self.db_path = None
        self._memory: Optional[_MemoryStore] = None
        self._conn: Optional[sqlite3.Connection] = None
        self._lock = threading.RLock()

        if db_path is None:
            self._memory = _MemoryStore()
        else:
            # Resolve directory -> file inside it. A path is treated as a
            # directory unless it explicitly names a DB file (or is an
            # existing file).
            p = os.fspath(db_path)
            looks_like_file = os.path.splitext(p)[1].lower() in (
                ".db", ".sqlite", ".sqlite3", ".db3"
            ) or os.path.isfile(p)
            if not looks_like_file:
                p = os.path.join(p, "knowledge_graph.db")
            parent = os.path.dirname(os.path.abspath(p))
            if parent:
                os.makedirs(parent, exist_ok=True)
            self.db_path = p
            self._conn = sqlite3.connect(p, check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
            with self._lock:
                with self._conn:
                    self._conn.execute("PRAGMA foreign_keys=ON")
                    self._conn.executescript(_SCHEMA)

    # ------------------------------------------------------------------ #
    # connection lifecycle
    # ------------------------------------------------------------------ #

    def close(self) -> None:
        """Close the underlying database connection, if any."""
        with self._lock:
            if self._conn is not None:
                self._conn.close()
                self._conn = None

    def __enter__(self) -> "KGPersistence":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    # ------------------------------------------------------------------ #
    # low-level helpers
    # ------------------------------------------------------------------ #

    @property
    def _is_memory(self) -> bool:
        return self._memory is not None

    def _row_to_entity(self, row: Dict[str, Any]) -> Dict[str, Any]:
        data = json.loads(row["attrs_json"])
        data.setdefault("id", row["id"])
        data.setdefault("entity_type", row["type"])
        return data

    def _row_to_relationship(self, row: Dict[str, Any]) -> Dict[str, Any]:
        data = json.loads(row["attrs_json"])
        data.setdefault("id", row["id"])
        data.setdefault("source_id", row["from_id"])
        data.setdefault("target_id", row["to_id"])
        data.setdefault("relationship_type", row["type"])
        return data

    # ------------------------------------------------------------------ #
    # entities
    # ------------------------------------------------------------------ #

    def upsert_entity(self, entity: Any, attrs: Optional[Dict[str, Any]] = None) -> str:
        """Insert or update an entity, deduplicating by (type, id).

        Accepts a dict (from ``Entity.to_dict``), an ``Entity`` instance, or
        an explicit ``(dict, overrides)`` pair. Returns the entity id.
        """
        if isinstance(entity, Entity):
            data = entity.to_dict()
        elif isinstance(entity, dict):
            data = dict(entity)
        else:
            raise TypeError(f"Unsupported entity payload: {type(entity)!r}")

        if attrs:
            data.update(attrs)

        etype = _entity_type_str(data)
        eid = _entity_id_str(data)
        created = data.get("created_at") or _now_iso()
        updated = data.get("updated_at") or _now_iso()

        record = {
            "id": eid,
            "type": etype,
            "attrs_json": json.dumps(data, default=_jdefault),
            "created_at": created,
            "updated_at": updated,
        }

        with self._lock:
            if self._is_memory:
                self._memory.entities[(etype, eid)] = record  # type: ignore[union-attr]
            else:
                with self._conn:  # type: ignore[union-attr]
                    self._conn.execute(  # type: ignore[union-attr]
                        """
                        INSERT INTO entities (id, type, attrs_json, created_at, updated_at)
                        VALUES (:id, :type, :attrs_json, :created_at, :updated_at)
                        ON CONFLICT(type, id) DO UPDATE SET
                            attrs_json = excluded.attrs_json,
                            updated_at = excluded.updated_at
                        """,
                        record,
                    )
        return eid

    def get_entity(self, entity_id: str, entity_type: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Retrieve an entity dict by id (and optional type)."""
        with self._lock:
            if self._is_memory:
                for (etype, eid), rec in self._memory.entities.items():  # type: ignore[union-attr]
                    if eid == entity_id and (entity_type is None or etype == entity_type):
                        return self._row_to_entity(rec)
                return None
            if entity_type is None:
                rows = self._conn.execute(  # type: ignore[union-attr]
                    "SELECT id, type, attrs_json FROM entities WHERE id = ?", (entity_id,)
                ).fetchall()
            else:
                rows = self._conn.execute(  # type: ignore[union-attr]
                    "SELECT id, type, attrs_json FROM entities WHERE id = ? AND type = ?",
                    (entity_id, entity_type),
                ).fetchall()
            if not rows:
                return None
            return self._row_to_entity(dict(rows[0]))

    def list_entities(self, entity_type: Optional[str] = None) -> List[Dict[str, Any]]:
        """List all entities (optionally filtered by type) as dicts."""
        results: List[Dict[str, Any]] = []
        with self._lock:
            if self._is_memory:
                for (etype, _eid), rec in self._memory.entities.items():  # type: ignore[union-attr]
                    if entity_type is None or etype == entity_type:
                        results.append(self._row_to_entity(rec))
            else:
                if entity_type is None:
                    rows = self._conn.execute(  # type: ignore[union-attr]
                        "SELECT id, type, attrs_json FROM entities"
                    ).fetchall()
                else:
                    rows = self._conn.execute(  # type: ignore[union-attr]
                        "SELECT id, type, attrs_json FROM entities WHERE type = ?",
                        (entity_type,),
                    ).fetchall()
                results = [self._row_to_entity(dict(r)) for r in rows]
        return results

    # ------------------------------------------------------------------ #
    # relationships
    # ------------------------------------------------------------------ #

    def upsert_relationship(
        self,
        relationship: Any,
        from_id: Optional[str] = None,
        to_id: Optional[str] = None,
        rel_type: Optional[str] = None,
        attrs: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Insert or update a relationship by id. Returns the relationship id."""
        if isinstance(relationship, Relationship):
            data = relationship.to_dict()
        elif isinstance(relationship, dict):
            data = dict(relationship)
        else:
            raise TypeError(f"Unsupported relationship payload: {type(relationship)!r}")

        if attrs:
            data.update(attrs)
        if from_id is not None:
            data["source_id"] = from_id
        if to_id is not None:
            data["target_id"] = to_id
        if rel_type is not None:
            data["relationship_type"] = rel_type

        rid = data.get("id") or str(uuid.uuid4())
        src = data.get("source_id") or ""
        tgt = data.get("target_id") or ""
        rtype = data.get("relationship_type")
        if hasattr(rtype, "value"):
            rtype = rtype.value
        rtype = str(rtype)

        record = {
            "id": rid,
            "from_id": src,
            "to_id": tgt,
            "type": rtype,
            "attrs_json": json.dumps(data, default=_jdefault),
        }

        with self._lock:
            if self._is_memory:
                self._memory.relationships[rid] = record  # type: ignore[union-attr]
            else:
                with self._conn:  # type: ignore[union-attr]
                    self._conn.execute(  # type: ignore[union-attr]
                        """
                        INSERT INTO relationships (id, from_id, to_id, type, attrs_json)
                        VALUES (:id, :from_id, :to_id, :type, :attrs_json)
                        ON CONFLICT(id) DO UPDATE SET
                            from_id = excluded.from_id,
                            to_id = excluded.to_id,
                            type = excluded.type,
                            attrs_json = excluded.attrs_json
                        """,
                        record,
                    )
        return rid

    def get_relationships(self, from_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """List relationships as dicts, optionally filtered by source id."""
        results: List[Dict[str, Any]] = []
        with self._lock:
            if self._is_memory:
                for rec in self._memory.relationships.values():  # type: ignore[union-attr]
                    if from_id is None or rec["from_id"] == from_id:
                        results.append(self._row_to_relationship(rec))
            else:
                if from_id is None:
                    rows = self._conn.execute(  # type: ignore[union-attr]
                        "SELECT id, from_id, to_id, type, attrs_json FROM relationships"
                    ).fetchall()
                else:
                    rows = self._conn.execute(  # type: ignore[union-attr]
                        "SELECT id, from_id, to_id, type, attrs_json FROM relationships WHERE from_id = ?",
                        (from_id,),
                    ).fetchall()
                results = [self._row_to_relationship(dict(r)) for r in rows]
        return results

    # ------------------------------------------------------------------ #
    # provenance
    # ------------------------------------------------------------------ #

    def add_provenance(
        self,
        entity_id: str,
        source: str,
        evidence: Optional[str] = None,
        confidence: float = 0.5,
    ) -> str:
        """Record provenance for an entity. Returns the provenance record id."""
        pid = str(uuid.uuid4())
        record = {
            "id": pid,
            "entity_id": entity_id,
            "source": str(source),
            "evidence": str(evidence or ""),
            "confidence": float(max(0.0, min(1.0, confidence))),
            "created_at": _now_iso(),
        }
        with self._lock:
            if self._is_memory:
                self._memory.provenance.setdefault(entity_id, []).append(record)  # type: ignore[union-attr]
            else:
                with self._conn:  # type: ignore[union-attr]
                    self._conn.execute(  # type: ignore[union-attr]
                        """
                        INSERT INTO provenance (id, entity_id, source, evidence, confidence, created_at)
                        VALUES (:id, :entity_id, :source, :evidence, :confidence, :created_at)
                        """,
                        record,
                    )
        return pid

    def get_provenance(self, entity_id: str) -> List[Dict[str, Any]]:
        """Return provenance records for an entity (chronological)."""
        if self._is_memory:
            recs = self._memory.provenance.get(entity_id, [])  # type: ignore[union-attr]
            return [dict(r) for r in recs]
        rows = self._conn.execute(  # type: ignore[union-attr]
            "SELECT id, entity_id, source, evidence, confidence, created_at "
            "FROM provenance WHERE entity_id = ? ORDER BY created_at",
            (entity_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------ #
    # deletion (cascade)
    # ------------------------------------------------------------------ #

    def delete_entity(self, entity_id: str) -> bool:
        """Delete an entity. Cascades to its relationships and provenance.

        Only deletes if the entity exists (in-memory or in DB).
        """
        with self._lock:
            if self._is_memory:
                # find matching key
                key = None
                for (etype, eid) in list(self._memory.entities.keys()):  # type: ignore[union-attr]
                    if eid == entity_id:
                        key = (etype, eid)
                        break
                if key is None:
                    return False
                del self._memory.entities[key]  # type: ignore[union-attr]
                # cascade relationships
                rel_ids = [
                    rid for rid, rec in self._memory.relationships.items()  # type: ignore[union-attr]
                    if rec["from_id"] == entity_id or rec["to_id"] == entity_id
                ]
                for rid in rel_ids:
                    del self._memory.relationships[rid]  # type: ignore[union-attr]
                self._memory.provenance.pop(entity_id, None)  # type: ignore[union-attr]
                return True

            cur = self._conn.execute(  # type: ignore[union-attr]
                "SELECT type, id FROM entities WHERE id = ?", (entity_id,)
            )
            if cur.fetchone() is None:
                return False
            with self._conn:  # type: ignore[union-attr]
                self._conn.execute("DELETE FROM entities WHERE id = ?", (entity_id,))  # type: ignore[union-attr]
                self._conn.execute(  # type: ignore[union-attr]
                    "DELETE FROM relationships WHERE from_id = ? OR to_id = ?",
                    (entity_id, entity_id),
                )
                self._conn.execute(  # type: ignore[union-attr]
                    "DELETE FROM provenance WHERE entity_id = ?", (entity_id,)
                )
            return True

    # ------------------------------------------------------------------ #
    # stats
    # ------------------------------------------------------------------ #

    def stats(self) -> Dict[str, int]:
        """Return counts of persisted entities, relationships, and provenance."""
        if self._is_memory:
            rel_count = sum(len(v) for v in self._memory.relationships.values())  # type: ignore[union-attr]
            prov_count = sum(len(v) for v in self._memory.provenance.values())  # type: ignore[union-attr]
            return {
                "entities": len(self._memory.entities),  # type: ignore[union-attr]
                "relationships": rel_count,
                "provenance": prov_count,
            }
        entities = self._conn.execute("SELECT COUNT(*) AS c FROM entities").fetchone()["c"]  # type: ignore[union-attr,index]
        relationships = self._conn.execute(  # type: ignore[union-attr]
            "SELECT COUNT(*) AS c FROM relationships"
        ).fetchone()["c"]
        provenance = self._conn.execute(  # type: ignore[union-attr]
            "SELECT COUNT(*) AS c FROM provenance"
        ).fetchone()["c"]
        return {
            "entities": entities,
            "relationships": relationships,
            "provenance": provenance,
        }

    # ------------------------------------------------------------------ #
    # graph sync / load
    # ------------------------------------------------------------------ #

    def sync(self, graph: Any) -> Dict[str, int]:
        """Snapshot an in-memory graph into the store.

        ``graph`` must expose ``entity_registry`` and ``relationship_registry``
        (as built by the ingestion pipeline / module). Existing provenance
        attached to entities via ``metadata['provenance']`` is also persisted.
        """
        er = getattr(graph, "entity_registry", None)
        rr = getattr(graph, "relationship_registry", None)
        entity_dicts = list(er) if er is not None else []
        rel_dicts = list(rr) if rr is not None else []

        for entity in entity_dicts:
            data = entity.to_dict() if hasattr(entity, "to_dict") else dict(entity)
            self.upsert_entity(data)
            prov = data.get("metadata", {}).get("provenance")
            if prov:
                if isinstance(prov, Provenance):
                    self.add_provenance(
                        data["id"], prov.source, prov.evidence_url or prov.evidence_hash, prov.confidence
                    )
                elif isinstance(prov, dict):
                    self.add_provenance(
                        data["id"],
                        prov.get("source", ""),
                        prov.get("evidence", "") or prov.get("evidence_url", ""),
                        prov.get("confidence", 0.5),
                    )
                elif isinstance(prov, (list, tuple)):
                    for p in prov:
                        if isinstance(p, Provenance):
                            self.add_provenance(data["id"], p.source, p.evidence_url, p.confidence)
                        elif isinstance(p, dict):
                            self.add_provenance(data["id"], p.get("source", ""), p.get("evidence", ""), p.get("confidence", 0.5))

        for rel in rel_dicts:
            self.upsert_relationship(rel)

        return self.stats()

    def load(self, graph: Optional[Any] = None) -> Any:
        """Rebuild an in-memory graph from the store.

        If ``graph`` is provided it is populated (entities + relationships
        registered) and returned. Otherwise a fresh container object exposing
        ``entity_registry`` and ``relationship_registry`` plus ``provenance``
        is returned.
        """
        er = EntityRegistry()
        rr = RelationshipRegistry()

        for data in self.list_entities():
            try:
                entity = Entity.from_dict(data)
            except Exception:
                continue
            er.register(entity)

        for rel_data in self.get_relationships():
            try:
                rel = Relationship.from_dict(rel_data)
            except Exception:
                continue
            rr.add(rel)

        if graph is not None:
            graph_er = getattr(graph, "entity_registry", None)
            graph_rr = getattr(graph, "relationship_registry", None)
            if graph_er is not None:
                for e in er:
                    graph_er.register(e)
            if graph_rr is not None:
                for r in rr:
                    graph_rr.add(r)
            provenance = {eid: self.get_provenance(eid) for eid in {d["id"] for d in self.list_entities()}}
            graph.provenance = provenance  # type: ignore[attr-defined]
            return graph

        provenance = {
            eid: self.get_provenance(eid)
            for eid in {d["id"] for d in self.list_entities()}
        }
        return _GraphContainer(er, rr, provenance)

    # ------------------------------------------------------------------ #
    # contradiction detection with provenance
    # ------------------------------------------------------------------ #

    def scan_contradictions(
        self,
        manager: Optional[ContradictionManager] = None,
        entities: Optional[List[Entity]] = None,
        relationships: Optional[List[Relationship]] = None,
        annotate_sources: bool = True,
    ) -> List[ContradictionRecord]:
        """Run contradiction detection over the persisted graph.

        When ``annotate_sources`` is True each side of every detected
        contradiction is annotated with the provenance sources of the
        involved entities, so a contradiction can cite its sources.
        """
        manager = manager or ContradictionManager()

        if entities is None or relationships is None:
            loaded = self.load()
            entities = list(loaded.entity_registry)
            relationships = list(loaded.relationship_registry)

        contradictions = manager.scan(entities, relationships)

        if annotate_sources:
            for cr in contradictions:
                involved_ids: set = set()
                md = cr.metadata or {}
                for key in ("entity_id", "entity_ids", "entity_pair", "cycle", "relationship_ids"):
                    val = md.get(key)
                    if isinstance(val, str):
                        involved_ids.add(val)
                    elif isinstance(val, (list, tuple)):
                        involved_ids.update(str(v) for v in val)
                source_refs = []
                for eid in sorted(involved_ids):
                    prov = self.get_provenance(eid)
                    for p in prov:
                        source_refs.append(f"{p['source']} ({eid[:8]})")
                if source_refs:
                    if not cr.claim_a_source:
                        cr.claim_a_source = "; ".join(source_refs)
                    cr.metadata["provenance_sources"] = source_refs
        return contradictions


class _GraphContainer:
    """Lightweight in-memory graph container populated by ``load()``."""

    def __init__(
        self,
        entity_registry: EntityRegistry,
        relationship_registry: RelationshipRegistry,
        provenance: Dict[str, List[Dict[str, Any]]],
    ) -> None:
        self.entity_registry = entity_registry
        self.relationship_registry = relationship_registry
        self.provenance = provenance


def create_persistence(db_path: Optional[str] = None) -> KGPersistence:
    """Factory: create a KGPersistence instance (None => in-memory)."""
    return KGPersistence(db_path)
