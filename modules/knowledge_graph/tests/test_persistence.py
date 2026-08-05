"""
Tests for the Knowledge Graph persistence layer (KGPersistence).

Covers SQLite durability, in-memory mode, entity/relationship/provenance
CRUD, dedup by (type, id), delete cascade, stats, sync/load round-trips,
and provenance-cited contradiction detection.

Usage:
    python -m pytest modules/knowledge_graph/tests/test_persistence.py -v
"""

import os
import sys
from datetime import datetime, timezone

import pytest

sys.path.insert(0, "/home/hunter/Desktop/Enterprise Builder")

from enterprise.modules.knowledge_graph.persistence import (
    KGPersistence,
    create_persistence,
)
from enterprise.modules.knowledge_graph.entities import (
    Entity,
    EntityType,
    EntityRegistry,
)
from enterprise.modules.knowledge_graph.relationships import (
    Relationship,
    RelationshipType,
    RelationshipRegistry,
)
from enterprise.modules.knowledge_graph.provenance import Provenance
from enterprise.modules.knowledge_graph.contradiction import ContradictionManager


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #

def _dir_path(tmp_path):
    return str(tmp_path / "kg")


def _entity(entity_type=EntityType.PROJECT, name="Alpha", **kw):
    e = Entity(entity_type=entity_type, name=name, **kw)
    return e


def _make_graph(entities=None, relationships=None):
    """Build a minimal graph container exposing entity/relationship registries."""
    class _Graph:
        pass
    g = _Graph()
    er = EntityRegistry()
    rr = RelationshipRegistry()
    for e in entities or []:
        er.register(e)
    for r in relationships or []:
        rr.add(r)
    g.entity_registry = er
    g.relationship_registry = rr
    return g


# --------------------------------------------------------------------------- #
# construction / backends
# --------------------------------------------------------------------------- #

def test_memory_backend_when_none():
    p = KGPersistence(None)
    assert p._is_memory is True
    assert p.db_path is None
    p.close()


def test_sqlite_backend_with_file(tmp_path):
    db = str(tmp_path / "kg" / "kb.db")
    p = KGPersistence(db)
    assert p._is_memory is False
    assert p.db_path == db
    assert os.path.exists(db)
    p.close()


def test_sqlite_backend_with_directory(tmp_path):
    d = str(tmp_path / "some_dir")
    p = KGPersistence(d)
    assert p._is_memory is False
    assert p.db_path == os.path.join(d, "knowledge_graph.db")
    assert os.path.exists(p.db_path)
    p.close()


def test_create_persistence_factory(tmp_path):
    p = create_persistence()
    assert p._is_memory is True
    p.close()
    p2 = create_persistence(str(tmp_path / "factory"))
    assert p2._is_memory is False
    p2.close()


# --------------------------------------------------------------------------- #
# entity CRUD
# --------------------------------------------------------------------------- #

def test_upsert_and_get_entity(tmp_path):
    with KGPersistence(_dir_path(tmp_path)) as p:
        e = _entity()
        pid = p.upsert_entity(e.to_dict())
        assert pid == e.id
        got = p.get_entity(e.id)
        assert got is not None
        assert got["name"] == "Alpha"
        assert got["entity_type"] == e.entity_type.value


def test_get_missing_entity_returns_none(tmp_path):
    with KGPersistence(_dir_path(tmp_path)) as p:
        assert p.get_entity("nope") is None


def test_get_entity_by_type(tmp_path):
    with KGPersistence(_dir_path(tmp_path)) as p:
        e = _entity()
        p.upsert_entity(e.to_dict())
        assert p.get_entity(e.id, entity_type=EntityType.PROJECT.value) is not None
        assert p.get_entity(e.id, entity_type=EntityType.USER.value) is None


def test_list_entities_and_type_filter(tmp_path):
    with KGPersistence(_dir_path(tmp_path)) as p:
        p.upsert_entity(_entity(EntityType.PROJECT, "P1").to_dict())
        p.upsert_entity(_entity(EntityType.PROJECT, "P2").to_dict())
        p.upsert_entity(_entity(EntityType.USER, "U1").to_dict())
        assert len(p.list_entities()) == 3
        projs = p.list_entities(entity_type=EntityType.PROJECT.value)
        assert len(projs) == 2
        names = {e["name"] for e in projs}
        assert names == {"P1", "P2"}


def test_accepts_entity_object_directly(tmp_path):
    with KGPersistence(_dir_path(tmp_path)) as p:
        e = _entity()
        p.upsert_entity(e)
        assert p.get_entity(e.id)["name"] == "Alpha"


def test_upsert_with_extra_attrs(tmp_path):
    with KGPersistence(_dir_path(tmp_path)) as p:
        e = _entity()
        p.upsert_entity(e.to_dict(), attrs={"metadata": {"owner": "team"}})
        got = p.get_entity(e.id)
        assert got["metadata"]["owner"] == "team"


# --------------------------------------------------------------------------- #
# dedup by (type, id)
# --------------------------------------------------------------------------- #

def test_dedup_entities_by_type_and_id(tmp_path):
    with KGPersistence(_dir_path(tmp_path)) as p:
        e = _entity(EntityType.PROJECT, "Alpha")
        p.upsert_entity(e.to_dict())
        p.upsert_entity(e.to_dict())  # same (type, id)
        assert len(p.list_entities()) == 1
        assert p.stats()["entities"] == 1


def test_dedup_same_id_different_type_still_deduped_if_added_again():
    # Same id + same type -> one row. Verify upsert updates in place.
    with KGPersistence(None) as p:
        e = _entity(EntityType.PROJECT, "Alpha")
        p.upsert_entity(e.to_dict())
        p.upsert_entity({**e.to_dict(), "name": "Alpha v2"})
        rows = p.list_entities()
        assert len(rows) == 1
        assert rows[0]["name"] == "Alpha v2"


def test_dedup_distinct_ids_are_separate(tmp_path):
    with KGPersistence(_dir_path(tmp_path)) as p:
        p.upsert_entity(_entity(EntityType.PROJECT, "A").to_dict())
        p.upsert_entity(_entity(EntityType.PROJECT, "B").to_dict())
        assert p.stats()["entities"] == 2


# --------------------------------------------------------------------------- #
# relationships
# --------------------------------------------------------------------------- #

def test_upsert_and_get_relationships(tmp_path):
    with KGPersistence(_dir_path(tmp_path)) as p:
        e1 = _entity(EntityType.SERVICE, "svc")
        e2 = _entity(EntityType.DATABASE, "db")
        p.upsert_entity(e1.to_dict())
        p.upsert_entity(e2.to_dict())
        r = Relationship(
            source_id=e1.id,
            target_id=e2.id,
            relationship_type=RelationshipType.USES,
        )
        rid = p.upsert_relationship(r.to_dict())
        rels = p.get_relationships()
        assert len(rels) == 1
        assert rels[0]["id"] == rid
        assert rels[0]["relationship_type"] == "Uses"


def test_get_relationships_filtered_by_from_id(tmp_path):
    with KGPersistence(_dir_path(tmp_path)) as p:
        a = _entity(EntityType.SERVICE, "a")
        b = _entity(EntityType.SERVICE, "b")
        c = _entity(EntityType.SERVICE, "c")
        for e in (a, b, c):
            p.upsert_entity(e.to_dict())
        p.upsert_relationship(Relationship(source_id=a.id, target_id=b.id, relationship_type=RelationshipType.USES).to_dict())
        p.upsert_relationship(Relationship(source_id=a.id, target_id=c.id, relationship_type=RelationshipType.USES).to_dict())
        p.upsert_relationship(Relationship(source_id=b.id, target_id=c.id, relationship_type=RelationshipType.DEPENDS_ON).to_dict())
        out_a = p.get_relationships(from_id=a.id)
        assert len(out_a) == 2
        assert all(r["source_id"] == a.id for r in out_a)
        assert len(p.get_relationships()) == 3


def test_upsert_relationship_deduplicates_by_id(tmp_path):
    with KGPersistence(_dir_path(tmp_path)) as p:
        a = _entity(EntityType.SERVICE, "a")
        b = _entity(EntityType.SERVICE, "b")
        p.upsert_entity(a.to_dict())
        p.upsert_entity(b.to_dict())
        r = Relationship(source_id=a.id, target_id=b.id, relationship_type=RelationshipType.USES)
        p.upsert_relationship(r.to_dict())
        p.upsert_relationship(r.to_dict())
        assert len(p.get_relationships()) == 1


# --------------------------------------------------------------------------- #
# provenance
# --------------------------------------------------------------------------- #

def test_add_and_get_provenance(tmp_path):
    with KGPersistence(_dir_path(tmp_path)) as p:
        e = _entity()
        p.upsert_entity(e.to_dict())
        pid = p.add_provenance(e.id, "scanner-v1", "evidence-xyz", 0.9)
        prov = p.get_provenance(e.id)
        assert len(prov) == 1
        assert prov[0]["id"] == pid
        assert prov[0]["source"] == "scanner-v1"
        assert prov[0]["evidence"] == "evidence-xyz"
        assert prov[0]["confidence"] == 0.9


def test_multiple_provenance_records_ordered(tmp_path):
    with KGPersistence(_dir_path(tmp_path)) as p:
        e = _entity()
        p.upsert_entity(e.to_dict())
        p.add_provenance(e.id, "src-1", "e1", 0.5)
        p.add_provenance(e.id, "src-2", "e2", 0.8)
        prov = p.get_provenance(e.id)
        assert len(prov) == 2
        assert [r["source"] for r in prov] == ["src-1", "src-2"]


def test_provenance_filters_by_entity(tmp_path):
    with KGPersistence(_dir_path(tmp_path)) as p:
        e1 = _entity(EntityType.PROJECT, "A")
        e2 = _entity(EntityType.PROJECT, "B")
        p.upsert_entity(e1.to_dict())
        p.upsert_entity(e2.to_dict())
        p.add_provenance(e1.id, "s1", "e", 0.8)
        assert len(p.get_provenance(e1.id)) == 1
        assert len(p.get_provenance(e2.id)) == 0


def test_provenance_from_provenance_object(tmp_path):
    with KGPersistence(_dir_path(tmp_path)) as p:
        e = _entity()
        p.upsert_entity(e.to_dict())
        prov = Provenance(source="audit", confidence=0.95, evidence_url="http://ev")
        p.add_provenance(e.id, prov.source, prov.evidence_url, prov.confidence)
        got = p.get_provenance(e.id)
        assert got[0]["source"] == "audit"
        assert got[0]["confidence"] == 0.95


# --------------------------------------------------------------------------- #
# delete cascade
# --------------------------------------------------------------------------- #

def test_delete_entity_cascades(tmp_path):
    with KGPersistence(_dir_path(tmp_path)) as p:
        a = _entity(EntityType.SERVICE, "a")
        b = _entity(EntityType.DATABASE, "b")
        p.upsert_entity(a.to_dict())
        p.upsert_entity(b.to_dict())
        p.upsert_relationship(Relationship(source_id=a.id, target_id=b.id, relationship_type=RelationshipType.USES).to_dict())
        p.upsert_relationship(Relationship(source_id=b.id, target_id=a.id, relationship_type=RelationshipType.USES).to_dict())
        p.add_provenance(a.id, "s1", "e", 0.8)

        assert p.delete_entity(a.id) is True
        stats = p.stats()
        assert stats["entities"] == 1  # b remains
        assert stats["relationships"] == 0  # both a-b edges removed
        assert stats["provenance"] == 0  # a's provenance removed
        assert p.get_entity(a.id) is None


def test_delete_missing_entity_returns_false(tmp_path):
    with KGPersistence(_dir_path(tmp_path)) as p:
        assert p.delete_entity("missing") is False


# --------------------------------------------------------------------------- #
# stats
# --------------------------------------------------------------------------- #

def test_stats_counts(tmp_path):
    with KGPersistence(_dir_path(tmp_path)) as p:
        e = _entity()
        p.upsert_entity(e.to_dict())
        p.add_provenance(e.id, "s", "e", 0.5)
        stats = p.stats()
        assert stats["entities"] == 1
        assert stats["provenance"] == 1
        assert sorted(stats.keys()) == ["entities", "provenance", "relationships"]


# --------------------------------------------------------------------------- #
# persistence round-trip across reopen
# --------------------------------------------------------------------------- #

def test_round_trip_across_reopen(tmp_path):
    db = str(tmp_path / "kg.db")
    e = _entity(EntityType.REQUIREMENT, "REQ-1", description="initial")
    e2 = _entity(EntityType.USER, "u1")
    r = Relationship(source_id=e.id, target_id=e2.id, relationship_type=RelationshipType.CREATED_BY)

    with KGPersistence(db) as p:
        p.upsert_entity(e.to_dict())
        p.upsert_entity(e2.to_dict())
        p.upsert_relationship(r.to_dict())
        p.add_provenance(e.id, "src", "ev", 0.7)

    # Reopen a fresh connection and confirm everything survived.
    with KGPersistence(db) as p2:
        assert len(p2.list_entities()) == 2
        assert len(p2.get_relationships()) == 1
        got = p2.get_entity(e.id)
        assert got["description"] == "initial"
        assert len(p2.get_provenance(e.id)) == 1
        assert p2.stats()["entities"] == 2


def test_data_survives_module_default_path(tmp_path):
    # Directory-based persistence across reopen via the same path.
    d = str(tmp_path / "store")
    with KGPersistence(d) as p:
        e = _entity()
        p.upsert_entity(e.to_dict())
        assert os.path.exists(p.db_path)
    with KGPersistence(d) as p2:
        assert len(p2.list_entities()) == 1


# --------------------------------------------------------------------------- #
# sync / load
# --------------------------------------------------------------------------- #

def test_sync_persists_graph(tmp_path):
    with KGPersistence(_dir_path(tmp_path)) as p:
        a = _entity(EntityType.SERVICE, "svc")
        b = _entity(EntityType.DATABASE, "db")
        r = Relationship(source_id=a.id, target_id=b.id, relationship_type=RelationshipType.USES)
        g = _make_graph([a, b], [r])
        stats = p.sync(g)
        assert stats["entities"] == 2
        assert stats["relationships"] == 1


def test_load_rebuilds_graph(tmp_path):
    with KGPersistence(_dir_path(tmp_path)) as p:
        a = _entity(EntityType.SERVICE, "svc")
        b = _entity(EntityType.DATABASE, "db")
        r = Relationship(source_id=a.id, target_id=b.id, relationship_type=RelationshipType.DEPENDS_ON)
        p.upsert_entity(a.to_dict())
        p.upsert_entity(b.to_dict())
        p.upsert_relationship(r.to_dict())

        g = p.load()
        assert len(g.entity_registry) == 2
        assert len(g.relationship_registry) == 1
        ids = {e.id for e in g.entity_registry}
        assert ids == {a.id, b.id}
        rel = list(g.relationship_registry)[0]
        assert (rel.source_id, rel.target_id) == (a.id, b.id)
        assert rel.relationship_type == RelationshipType.DEPENDS_ON


def test_sync_then_reopen_then_load(tmp_path):
    db = str(tmp_path / "kg.db")
    a = _entity(EntityType.SERVICE, "svc")
    b = _entity(EntityType.DATABASE, "db")
    r = Relationship(source_id=a.id, target_id=b.id, relationship_type=RelationshipType.USES)
    g = _make_graph([a, b], [r])

    with KGPersistence(db) as p:
        p.sync(g)

    with KGPersistence(db) as p2:
        rebuilt = p2.load()
        assert len(rebuilt.entity_registry) == 2
        assert len(rebuilt.relationship_registry) == 1


def test_load_populates_existing_graph(tmp_path):
    with KGPersistence(_dir_path(tmp_path)) as p:
        a = _entity(EntityType.SERVICE, "svc")
        p.upsert_entity(a.to_dict())
        er = EntityRegistry()
        rr = RelationshipRegistry()
        class G:
            pass
        g = G()
        g.entity_registry = er
        g.relationship_registry = rr
        out = p.load(g)
        assert out is g
        assert len(er) == 1


def test_sync_persists_embedded_provenance(tmp_path):
    with KGPersistence(_dir_path(tmp_path)) as p:
        a = _entity(EntityType.SERVICE, "svc")
        prov = Provenance(source="extractor", confidence=0.9, evidence_url="http://e")
        a.metadata["provenance"] = prov
        b = _entity(EntityType.DATABASE, "db")
        g = _make_graph([a, b], [])
        p.sync(g)
        # Reload provenance from the store.
        provs = p.get_provenance(a.id)
        assert len(provs) == 1
        assert provs[0]["source"] == "extractor"
        assert provs[0]["confidence"] == 0.9


# --------------------------------------------------------------------------- #
# contradiction detection with provenance
# --------------------------------------------------------------------------- #

def test_contradiction_still_reported_with_provenance(tmp_path):
    with KGPersistence(_dir_path(tmp_path)) as p:
        # Duplicate names -> DUPLICATE_CLAIM contradiction.
        e1 = _entity(EntityType.SERVICE, "dup")
        e2 = _entity(EntityType.SERVICE, "dup")
        p.upsert_entity(e1.to_dict())
        p.upsert_entity(e2.to_dict())
        p.add_provenance(e1.id, "src-A", "evA", 0.8)
        p.add_provenance(e2.id, "src-B", "evB", 0.6)

        mgr = ContradictionManager()
        conts = p.scan_contradictions(mgr)
        # duplicate name detected
        dup = [c for c in conts if c.contradiction_type.value == "duplicate_claim"]
        assert dup, "duplicate claim contradiction should be detected"
        cr = dup[0]
        # provenance must cite its sources
        sources = cr.metadata.get("provenance_sources", [])
        assert sources, "contradiction should cite sources via provenance"
        assert any("src-A" in s for s in sources)
        assert any("src-B" in s for s in sources)


def test_contradiction_cycle_detected_with_sources(tmp_path):
    with KGPersistence(_dir_path(tmp_path)) as p:
        a = _entity(EntityType.SERVICE, "a")
        b = _entity(EntityType.SERVICE, "b")
        p.upsert_entity(a.to_dict())
        p.upsert_entity(b.to_dict())
        p.add_provenance(a.id, "dep-scan-a", "ea", 0.7)
        p.add_provenance(b.id, "dep-scan-b", "eb", 0.7)
        rab = Relationship(source_id=a.id, target_id=b.id, relationship_type=RelationshipType.DEPENDS_ON)
        rba = Relationship(source_id=b.id, target_id=a.id, relationship_type=RelationshipType.DEPENDS_ON)
        p.upsert_relationship(rab.to_dict())
        p.upsert_relationship(rba.to_dict())

        conts = p.scan_contradictions()
        cyc = [c for c in conts if c.contradiction_type.value == "cyclic_dependency"]
        assert cyc, "cyclic dependency should be detected"
        sources = cyc[0].metadata.get("provenance_sources", [])
        assert sources
        assert any("dep-scan-a" in s for s in sources)


def test_contradiction_without_provenance_has_empty_sources(tmp_path):
    with KGPersistence(_dir_path(tmp_path)) as p:
        e1 = _entity(EntityType.SERVICE, "dup")
        e2 = _entity(EntityType.SERVICE, "dup")
        p.upsert_entity(e1.to_dict())
        p.upsert_entity(e2.to_dict())
        conts = p.scan_contradictions()
        dup = [c for c in conts if c.contradiction_type.value == "duplicate_claim"]
        assert dup
        # no provenance recorded -> sources empty but contradiction still present
        assert dup[0].metadata.get("provenance_sources", []) == []


def test_module_persistence_exposed(tmp_path):
    from enterprise.modules.knowledge_graph import (
        create_knowledge_graph_module,
        KGPersistence,
        create_persistence,
    )
    assert KGPersistence is not None
    assert callable(create_persistence)
    m = create_knowledge_graph_module({"db_path": None})
    assert m.persistence is not None
    assert m.persistence._is_memory is True
    m2 = create_knowledge_graph_module({"db_path": str(tmp_path / "mod")})
    assert m2.persistence._is_memory is False
