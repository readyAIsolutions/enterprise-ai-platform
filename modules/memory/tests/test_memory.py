"""Comprehensive tests for the agent memory module.

Covers the pure logic (``memory.py``), persistence, consolidation, ranking,
and the Platform Kernel module lifecycle + event-bus wiring.

The root ``conftest.py`` already places the repo parent on ``sys.path`` so
``enterprise.*`` imports resolve.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import pytest
from enterprise.modules.memory import (
    DEFAULT_MEMORY_TYPE,
    MEMORY_TYPES,
    AgentMemory,
    HashEmbedder,
    MemoryModule,
)
from enterprise.modules.memory.memory import (
    MemoryEntry,
    cosine_similarity,
    dot,
    normalize,
)

if TYPE_CHECKING:
    from pathlib import Path


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_memory(path: Path) -> AgentMemory:
    return AgentMemory(database_path=str(path))


def iso_days_ago(days: int) -> str:
    return (datetime.now(UTC) - timedelta(days=days)).isoformat()


class FakeBus:
    """A fake event bus that records published events."""

    def __init__(self) -> None:
        self.events = []

    def publish(self, event: object) -> None:
        self.events.append(event)

    @property
    def topics(self) -> list[str]:
        return [e.topic for e in self.events]

    def payloads_for(self, topic: str) -> list[dict]:
        return [e.payload for e in self.events if e.topic == topic]


# ---------------------------------------------------------------------------
# Embedder / vector helpers
# ---------------------------------------------------------------------------


def test_embedder_is_deterministic() -> None:
    emb = HashEmbedder(dim=128)
    assert emb.embed("the quick brown fox") == emb.embed("the quick brown fox")


def test_embedder_has_configured_dim() -> None:
    emb = HashEmbedder(dim=64)
    assert emb.dim == 64
    assert len(emb.embed("anything")) == 64


def test_embedder_rejects_bad_dim() -> None:
    with pytest.raises(ValueError, match="positive integer"):
        HashEmbedder(dim=0)
    with pytest.raises(ValueError, match="positive integer"):
        HashEmbedder(dim=-3)


def test_cosine_similarity_identical_vectors() -> None:
    v = normalize([1.0, 0.5, 0.25])
    assert cosine_similarity(v, v) == pytest.approx(1.0)


def test_cosine_similarity_orthogonal_vectors() -> None:
    assert cosine_similarity([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)


def test_cosine_similarity_zero_vector() -> None:
    assert cosine_similarity([0.0, 0.0], [1.0, 0.0]) == 0.0


def test_dot_and_normalize() -> None:
    assert dot([1.0, 2.0], [3.0, 4.0]) == 11.0
    n = normalize([3.0, 4.0])
    assert sum(x * x for x in n) == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# AgentMemory CRUD
# ---------------------------------------------------------------------------


def test_add_returns_entry_with_defaults(tmp_path: Path) -> None:
    mem = make_memory(tmp_path / "m.sqlite")
    entry = mem.remember(user_id="u1", content="hello world")
    assert isinstance(entry, MemoryEntry)
    assert entry.id
    assert entry.user_id == "u1"
    assert entry.memory_type == DEFAULT_MEMORY_TYPE
    assert entry.metadata == {}
    assert entry.access_count == 0
    assert mem.count() == 1


def test_add_all_memory_types(tmp_path: Path) -> None:
    mem = make_memory(tmp_path / "m.sqlite")
    for mtype in MEMORY_TYPES:
        entry = mem.remember(
            user_id="u1", content=f"memory of type {mtype}", memory_type=mtype
        )
        assert entry.memory_type == mtype
    assert mem.count() == 4


def test_add_invalid_type_raises(tmp_path: Path) -> None:
    mem = make_memory(tmp_path / "m.sqlite")
    with pytest.raises(ValueError, match="Invalid memory_type"):
        mem.remember(user_id="u1", content="bad", memory_type="not_a_type")


def test_add_alias_matches_remember(tmp_path: Path) -> None:
    mem = make_memory(tmp_path / "m.sqlite")
    e1 = mem.remember(user_id="u1", content="aliased")
    e2 = mem.add(user_id="u1", content="aliased")
    assert e1.content == e2.content
    assert mem.count() == 2


def test_get_returns_entry(tmp_path: Path) -> None:
    mem = make_memory(tmp_path / "m.sqlite")
    entry = mem.remember(user_id="u1", content="gettable")
    assert mem.get(entry.id).content == "gettable"
    assert mem.get("missing") is None


def test_update_content_and_metadata(tmp_path: Path) -> None:
    mem = make_memory(tmp_path / "m.sqlite")
    entry = mem.remember(user_id="u1", content="old content")
    updated = mem.update(
        entry.id,
        content="new content",
        metadata={"source": "api"},
        importance=0.9,
    )
    assert updated.content == "new content"
    assert updated.metadata == {"source": "api"}
    assert updated.importance == 0.9
    assert mem.get(entry.id).content == "new content"


def test_update_missing_returns_none(tmp_path: Path) -> None:
    mem = make_memory(tmp_path / "m.sqlite")
    assert mem.update("missing") is None


def test_update_type_validation(tmp_path: Path) -> None:
    mem = make_memory(tmp_path / "m.sqlite")
    entry = mem.remember(user_id="u1", content="x")
    mem.update(entry.id, memory_type="episodic")
    assert mem.get(entry.id).memory_type == "episodic"
    with pytest.raises(ValueError, match="Invalid memory_type"):
        mem.update(entry.id, memory_type="bogus")


def test_delete_removes_entry(tmp_path: Path) -> None:
    mem = make_memory(tmp_path / "m.sqlite")
    entry = mem.remember(user_id="u1", content="delete me")
    assert mem.delete(entry.id) is True
    assert mem.count() == 0
    assert mem.get(entry.id) is None


def test_delete_missing_returns_false(tmp_path: Path) -> None:
    mem = make_memory(tmp_path / "m.sqlite")
    assert mem.delete("missing") is False


def test_list_memories_scoped(tmp_path: Path) -> None:
    mem = make_memory(tmp_path / "m.sqlite")
    mem.remember(user_id="u1", content="a", memory_type="semantic")
    mem.remember(user_id="u1", content="b", memory_type="episodic")
    mem.remember(user_id="u2", content="c", memory_type="semantic")
    assert len(mem.get_memories(user_id="u1")) == 2
    assert len(mem.get_memories(user_id="u2")) == 1
    assert len(mem.get_memories(memory_type="semantic")) == 2
    assert len(mem.get_memories(user_id="u1", memory_type="episodic")) == 1
    assert len(mem.get_memories()) == 3


def test_count_per_user(tmp_path: Path) -> None:
    mem = make_memory(tmp_path / "m.sqlite")
    mem.remember(user_id="u1", content="x")
    mem.remember(user_id="u1", content="y")
    mem.remember(user_id="u2", content="z")
    assert mem.count() == 3
    assert mem.count(user_id="u1") == 2
    assert mem.count(user_id="u2") == 1


# ---------------------------------------------------------------------------
# Search / ranking
# ---------------------------------------------------------------------------


def test_search_returns_expected_top_result(tmp_path: Path) -> None:
    mem = make_memory(tmp_path / "m.sqlite")
    mem.remember(user_id="u1", content="user prefers dark roast coffee every morning")
    mem.remember(user_id="u1", content="user is allergic to peanuts")
    mem.remember(
        user_id="u1", content="user works as a software engineer at a fintech company"
    )
    results = mem.search("dark roast coffee", k=3)
    assert len(results) == 3
    assert "coffee" in results[0].memory.content


def test_search_respects_k_limit(tmp_path: Path) -> None:
    mem = make_memory(tmp_path / "m.sqlite")
    for i in range(10):
        mem.remember(user_id="u1", content=f"topic alpha entry number {i}")
    assert len(mem.search("alpha", k=3)) == 3
    assert len(mem.search("alpha", k=0)) == 0


def test_search_type_filter(tmp_path: Path) -> None:
    mem = make_memory(tmp_path / "m.sqlite")
    mem.remember(user_id="u1", content="alpha semantic", memory_type="semantic")
    mem.remember(user_id="u1", content="alpha episodic", memory_type="episodic")
    semantic = mem.search("alpha", memory_type="semantic")
    assert len(semantic) == 1
    assert semantic[0].memory.memory_type == "semantic"


def test_search_metadata_filter(tmp_path: Path) -> None:
    mem = make_memory(tmp_path / "m.sqlite")
    mem.remember(
        user_id="u1", content="alpha with project", metadata={"project": "nebula"}
    )
    mem.remember(
        user_id="u1", content="alpha with team", metadata={"project": "orion"}
    )
    results = mem.search("alpha", metadata_filter={"project": "orion"})
    assert len(results) == 1
    assert results[0].memory.metadata["project"] == "orion"


def test_search_user_scoping(tmp_path: Path) -> None:
    mem = make_memory(tmp_path / "m.sqlite")
    mem.remember(user_id="alice", content="alice secret token")
    mem.remember(user_id="bob", content="bob secret token")
    results = mem.search("secret token", user_id="alice")
    assert len(results) == 1
    assert results[0].memory.user_id == "alice"


def test_search_does_not_leak_other_users(tmp_path: Path) -> None:
    mem = make_memory(tmp_path / "m.sqlite")
    mem.remember(user_id="alice", content="alice-only confidential data")
    results = mem.search("alice-only confidential", user_id="bob")
    assert results == []


def test_update_importance_affects_ranking(tmp_path: Path) -> None:
    mem = make_memory(tmp_path / "m.sqlite")
    high = mem.remember(
        user_id="u1",
        content="quarterly earnings report released",
        importance=0.9,
    )
    mem.remember(
        user_id="u1",
        content="quarterly earnings report released",
        importance=0.1,
    )
    results = mem.search("quarterly earnings report", k=2)
    assert len(results) == 2
    # Same content -> same cosine; higher importance must rank first.
    assert results[0].memory.id == high.id


def test_search_touches_access_metadata(tmp_path: Path) -> None:
    mem = make_memory(tmp_path / "m.sqlite")
    entry = mem.remember(user_id="u1", content="tracked topic content")
    assert entry.access_count == 0
    mem.search("tracked topic")
    mem.search("tracked topic")
    assert mem.get(entry.id).access_count == 2


def test_search_empty_query_is_safe(tmp_path: Path) -> None:
    mem = make_memory(tmp_path / "m.sqlite")
    mem.remember(user_id="u1", content="something")
    assert isinstance(mem.search(""), list)  # returns list, does not crash


def test_search_all_returns_context_blob(tmp_path: Path) -> None:
    mem = make_memory(tmp_path / "m.sqlite")
    mem.remember(user_id="u1", content="project deadline is next friday")
    mem.remember(
        user_id="u1", content="user likes hiking on weekends", memory_type="episodic"
    )
    ctx = mem.search_all("project deadline", k=5)
    assert ctx.query == "project deadline"
    assert "<memory_context>" in ctx.context
    assert "friday" in ctx.context
    assert len(ctx.memories) >= 1


def test_search_all_without_matches(tmp_path: Path) -> None:
    mem = make_memory(tmp_path / "m.sqlite")
    ctx = mem.search_all("nothing here")
    assert "<memory_context>" in ctx.context
    assert ctx.memories == []


def test_search_all_scoped_to_user(tmp_path: Path) -> None:
    mem = make_memory(tmp_path / "m.sqlite")
    mem.remember(user_id="alice", content="alice plan xyz")
    mem.remember(user_id="bob", content="bob plan xyz")
    ctx = mem.search_all("plan xyz", user_id="bob")
    assert all(s.memory.user_id == "bob" for s in ctx.memories)


# ---------------------------------------------------------------------------
# Forget
# ---------------------------------------------------------------------------


def test_forget_by_user(tmp_path: Path) -> None:
    mem = make_memory(tmp_path / "m.sqlite")
    mem.remember(user_id="u1", content="a")
    mem.remember(user_id="u2", content="b")
    assert mem.forget(user_id="u1") == 1
    assert mem.count(user_id="u1") == 0
    assert mem.count(user_id="u2") == 1


def test_forget_by_type(tmp_path: Path) -> None:
    mem = make_memory(tmp_path / "m.sqlite")
    mem.remember(user_id="u1", content="a", memory_type="semantic")
    mem.remember(user_id="u1", content="b", memory_type="episodic")
    assert mem.forget(memory_type="episodic") == 1
    assert mem.count() == 1


def test_forget_older_than(tmp_path: Path) -> None:
    mem = make_memory(tmp_path / "m.sqlite")
    old = mem.remember(user_id="u1", content="old memory")
    fresh = mem.remember(user_id="u1", content="fresh memory")
    # Backdate the old entry in the store.
    mem.store._entries[old.id].created_at = iso_days_ago(40)
    mem.store._persist(mem.store._entries[old.id])
    removed = mem.forget(user_id="u1", older_than_iso=iso_days_ago(10))
    assert removed == 1
    assert mem.get(old.id) is None
    assert mem.get(fresh.id) is not None


def test_forget_all_of_user(tmp_path: Path) -> None:
    mem = make_memory(tmp_path / "m.sqlite")
    mem.remember(user_id="u1", content="a")
    mem.remember(user_id="u1", content="b")
    assert mem.forget(user_id="u1") == 2
    assert mem.count() == 0


# ---------------------------------------------------------------------------
# Consolidation / de-duplication
# ---------------------------------------------------------------------------


def test_consolidation_merges_near_duplicates(tmp_path: Path) -> None:
    mem = make_memory(tmp_path / "m.sqlite")
    mem.remember(user_id="u1", content="The sky is blue today")
    mem.remember(user_id="u1", content="The sky is blue today")
    mem.remember(user_id="u1", content="Unrelated topic entirely")
    assert mem.count() == 3
    summary = mem.consolidate(similarity_threshold=0.9)
    assert summary["merged"] >= 1
    assert mem.count() == 2


def test_consolidation_does_not_merge_distinct(tmp_path: Path) -> None:
    mem = make_memory(tmp_path / "m.sqlite")
    mem.remember(user_id="u1", content="The sky is blue today")
    mem.remember(user_id="u1", content="The stock market rallied strongly")
    summary = mem.consolidate(similarity_threshold=0.9)
    assert summary["merged"] == 0
    assert mem.count() == 2


def test_consolidation_trims_per_type(tmp_path: Path) -> None:
    mem = make_memory(tmp_path / "m.sqlite")
    words = [
        "alpha bravo",
        "charlie delta",
        "echo foxtrot",
        "golf hotel",
        "india juliet",
        "kilo lima",
    ]
    for i, content in enumerate(words):
        mem.remember(user_id="u1", content=content, importance=0.1 + i / 10)
    summary = mem.consolidate(max_per_type=2, similarity_threshold=0.99)
    assert summary["trimmed"] == 4
    assert mem.count() == 2


def test_consolidation_scoped_to_user(tmp_path: Path) -> None:
    mem = make_memory(tmp_path / "m.sqlite")
    for _ in range(2):
        mem.remember(user_id="alice", content="Alice sky is blue today")
    mem.remember(user_id="bob", content="Bob unrelated content")
    summary = mem.consolidate(
        max_per_type=10, similarity_threshold=0.9, user_id="alice"
    )
    assert summary["merged"] >= 1
    assert mem.count(user_id="alice") == 1
    assert mem.count(user_id="bob") == 1


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------


def test_persistence_across_reopen(tmp_path: Path) -> None:
    db = tmp_path / "persist.sqlite"
    m1 = AgentMemory(database_path=str(db))
    m1.remember(user_id="u1", content="persisted semantic", memory_type="semantic")
    m1.remember(user_id="u1", content="persisted episodic", memory_type="episodic")
    m2 = AgentMemory(database_path=str(db))
    assert m2.count() == 2
    contents = sorted(e.content for e in m2.get_memories())
    assert contents == ["persisted episodic", "persisted semantic"]


def test_metadata_and_importance_survive_reopen(tmp_path: Path) -> None:
    db = tmp_path / "meta.sqlite"
    m1 = AgentMemory(database_path=str(db))
    e = m1.remember(
        user_id="u1",
        content="with meta",
        metadata={"k": "v"},
        importance=0.77,
    )
    m2 = AgentMemory(database_path=str(db))
    loaded = m2.get(e.id)
    assert loaded.metadata == {"k": "v"}
    assert loaded.importance == 0.77


def test_update_persists_across_reopen(tmp_path: Path) -> None:
    db = tmp_path / "upd.sqlite"
    m1 = AgentMemory(database_path=str(db))
    e = m1.remember(user_id="u1", content="before")
    m1.update(e.id, content="after")
    m2 = AgentMemory(database_path=str(db))
    assert m2.get(e.id).content == "after"


def test_delete_persists_across_reopen(tmp_path: Path) -> None:
    db = tmp_path / "del.sqlite"
    m1 = AgentMemory(database_path=str(db))
    e = m1.remember(user_id="u1", content="will be deleted")
    m1.delete(e.id)
    m2 = AgentMemory(database_path=str(db))
    assert m2.count() == 0


# ---------------------------------------------------------------------------
# Module lifecycle
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_module_initialize_health_shutdown(tmp_path: Path) -> None:
    mod = MemoryModule(config={"database_path": str(tmp_path / "m.sqlite")})
    assert (await mod.health_check()) == mod.status  # UNKNOWN before init
    await mod.initialize()
    assert (await mod.health_check()).is_operational()
    assert mod.memory is not None
    assert mod.status.is_operational()
    await mod.shutdown()
    assert mod.memory is None


@pytest.mark.asyncio
async def test_module_remember_and_search(tmp_path: Path) -> None:
    mod = MemoryModule(config={"database_path": str(tmp_path / "m.sqlite")})
    await mod.initialize()
    mod.remember(user_id="u1", content="module remembers coffee preferences")
    mod.remember(user_id="u1", content="module remembers python and asyncio")
    results = mod.search("coffee", k=5)
    assert len(results) >= 1
    assert "coffee" in results[0].memory.content


@pytest.mark.asyncio
async def test_module_facade_methods(tmp_path: Path) -> None:
    mod = MemoryModule(config={"database_path": str(tmp_path / "m.sqlite")})
    await mod.initialize()
    e = mod.remember(user_id="u1", content="facade content")
    assert mod.get_memories(user_id="u1")[0].content == "facade content"
    mod.update(e.id, content="facade updated")
    assert mod.get(e.id).content == "facade updated"
    ctx = mod.search_all("facade", k=5)
    assert "<memory_context>" in ctx.context
    assert mod.forget(user_id="u1") == 1
    assert mod.get_memories() == []


@pytest.mark.asyncio
async def test_module_not_initialized_raises(tmp_path: Path) -> None:
    mod = MemoryModule(config={"database_path": str(tmp_path / "m.sqlite")})
    with pytest.raises(RuntimeError, match="not initialized"):
        mod.remember(user_id="u1", content="x")


@pytest.mark.asyncio
async def test_module_initialize_creates_data_dir(tmp_path: Path) -> None:
    db = tmp_path / "nested" / "dir" / "m.sqlite"
    mod = MemoryModule(config={"database_path": str(db)})
    await mod.initialize()
    assert db.exists()


@pytest.mark.asyncio
async def test_module_default_db_resolves_absolute() -> None:
    mod = MemoryModule(config={})
    assert mod.database_path.endswith("agent_memory.sqlite")
    assert "/" in mod.database_path


# ---------------------------------------------------------------------------
# Module event-bus wiring
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_module_publishes_add_event(tmp_path: Path) -> None:
    bus = FakeBus()
    mod = MemoryModule(config={"database_path": str(tmp_path / "m.sqlite")})
    mod.set_event_bus(bus)
    await mod.initialize()
    mod.remember(user_id="u1", content="hello")
    assert "memory.added" in bus.topics


@pytest.mark.asyncio
async def test_module_publishes_search_event(tmp_path: Path) -> None:
    bus = FakeBus()
    mod = MemoryModule(config={"database_path": str(tmp_path / "m.sqlite")})
    mod.set_event_bus(bus)
    await mod.initialize()
    mod.remember(user_id="u1", content="searchable content")
    mod.search("searchable")
    assert "memory.searched" in bus.topics


@pytest.mark.asyncio
async def test_module_publishes_update_delete_forget_events(tmp_path: Path) -> None:
    bus = FakeBus()
    mod = MemoryModule(config={"database_path": str(tmp_path / "m.sqlite")})
    mod.set_event_bus(bus)
    await mod.initialize()
    e = mod.remember(user_id="u1", content="x")
    mod.update(e.id, content="y")
    assert "memory.updated" in bus.topics
    mod.delete(e.id)
    assert "memory.deleted" in bus.topics
    mod.remember(user_id="u1", content="z")
    mod.forget(user_id="u1")
    assert "memory.forgotten" in bus.topics


@pytest.mark.asyncio
async def test_module_publish_when_no_bus_is_noop(tmp_path: Path) -> None:
    mod = MemoryModule(config={"database_path": str(tmp_path / "m.sqlite")})
    await mod.initialize()
    mod.remember(user_id="u1", content="no bus no crash")
    assert mod.memory.count() == 1


@pytest.mark.asyncio
async def test_module_search_event_payload(tmp_path: Path) -> None:
    bus = FakeBus()
    mod = MemoryModule(config={"database_path": str(tmp_path / "m.sqlite")})
    mod.set_event_bus(bus)
    await mod.initialize()
    mod.remember(user_id="u1", content="payload target doc")
    mod.search("payload target")
    payloads = bus.payloads_for("memory.searched")
    assert len(payloads) >= 1
    assert payloads[0]["query"] == "payload target"


def test_module_registered_name_and_version() -> None:
    mod = MemoryModule()
    assert mod.name == "memory"
    assert mod.version == "1.0.0"
