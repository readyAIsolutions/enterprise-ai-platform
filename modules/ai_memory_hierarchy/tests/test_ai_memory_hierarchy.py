"""Tests for the AI Memory Hierarchy module (JEVanClief transcript-grounded)."""
from __future__ import annotations

import asyncio

import pytest

from enterprise.modules.ai_memory_hierarchy import (
    AiMemoryHierarchyModule,
    MemoryHierarchy,
    Tier,
    TierLockedError,
    create_ai_memory_hierarchy_module,
    overlap_score,
    tokenize,
)
from enterprise.platform_kernel import HealthStatus


# ---------------------------------------------------------------------------
# Pure core helpers: tokenization / overlap scoring
# ---------------------------------------------------------------------------

def test_tokenize_lowercases_and_splits_words():
    assert tokenize("The Quick-Brown fox, 'jumps'!") == [
        "the", "quick", "brown", "fox", "jumps",
    ]


def test_overlap_score_counts_distinct_query_tokens():
    q = ["cat", "dog", "bird"]
    c = ["cat", "cat", "dog"]
    assert overlap_score(q, c) == 2
    assert overlap_score([], c) == 0


# ---------------------------------------------------------------------------
# Core: insertion and auto-placement
# ---------------------------------------------------------------------------

def test_insert_with_explicit_tier_and_retrieval_by_key():
    h = MemoryHierarchy()
    e = h.insert("k1", "cat dog fish", tier=Tier.PERSISTENT)
    assert h.get("k1") is e
    assert h.get("k1").tier is Tier.PERSISTENT
    assert h.tier_summary()[Tier.PERSISTENT.value]["count"] == 1


def test_auto_placement_uses_hottest_available_memory_tier():
    h = MemoryHierarchy()
    e = h.insert("k1", "alpha beta")  # no tier -> WORKING
    assert e.tier is Tier.WORKING


def test_auto_placement_cascades_when_working_is_full():
    h = MemoryHierarchy(capacities={Tier.WORKING: 1, Tier.RETRIEVED: 2})
    h.insert("a", "one")
    e = h.insert("b", "two")  # WORKING full -> RETRIEVED
    assert e.tier is Tier.RETRIEVED


def test_set_prompt_writes_firmware_tier():
    h = MemoryHierarchy()
    e = h.set_prompt("sys", "You are a helpful assistant.")
    assert e.tier is Tier.PROMPT


# ---------------------------------------------------------------------------
# Model weights ~ ROM (read-only after training / lock)
# ---------------------------------------------------------------------------

def test_weights_writable_before_lock_and_rom_after():
    h = MemoryHierarchy()
    h.set_weights("w1", "training pattern")
    h.lock_weights()
    assert h.weights_locked is True
    with pytest.raises(TierLockedError):
        h.set_weights("w2", "cannot change during inference")
    with pytest.raises(TierLockedError):
        h.insert("w3", "nope", tier=Tier.WEIGHTS)


# ---------------------------------------------------------------------------
# Promotion policy (locality / access-count based, hot vs cold)
# ---------------------------------------------------------------------------

def test_access_promotes_cold_persistent_entry_to_retrieved():
    h = MemoryHierarchy(promote_threshold=2)
    h.insert("cold", "rarely-loaded summary", tier=Tier.PERSISTENT)
    h.access("cold")
    assert h.get("cold").tier is Tier.PERSISTENT  # not yet
    h.access("cold")
    assert h.get("cold").tier is Tier.RETRIEVED  # promoted one hotter


def test_access_promotes_all_the_way_to_working_memory():
    h = MemoryHierarchy(promote_threshold=1)
    h.insert("m", "hot data", tier=Tier.PERSISTENT)
    h.access("m")  # PERSISTENT -> RETRIEVED
    assert h.get("m").tier is Tier.RETRIEVED
    h.access("m")  # RETRIEVED -> WORKING
    assert h.get("m").tier is Tier.WORKING
    h.access("m")  # WORKING is the hottest memory tier — stays
    assert h.get("m").tier is Tier.WORKING


def test_promote_threshold_must_be_positive():
    with pytest.raises(ValueError):
        MemoryHierarchy(promote_threshold=0)


def test_manual_promote_and_demote():
    h = MemoryHierarchy()
    h.insert("x", "content", tier=Tier.PERSISTENT)
    h.promote("x")
    assert h.get("x").tier is Tier.RETRIEVED
    h.demote("x")
    assert h.get("x").tier is Tier.PERSISTENT


# ---------------------------------------------------------------------------
# Capacity eviction (coldest is demoted to a colder tier)
# ---------------------------------------------------------------------------

def test_capacity_eviction_demotes_coldest_to_next_tier():
    h = MemoryHierarchy(capacities={Tier.WORKING: 2, Tier.RETRIEVED: 4})
    h.insert("a", "first", tier=Tier.WORKING)
    h.insert("b", "second", tier=Tier.WORKING)
    h.insert("c", "third", tier=Tier.WORKING)  # evict coldest (a)
    assert h.get("a").tier is Tier.RETRIEVED
    assert h.tier_summary()[Tier.WORKING.value]["count"] == 2


def test_overflow_eventually_drops_from_persistent_cold_storage():
    h = MemoryHierarchy(capacities={Tier.PERSISTENT: 2})
    h.insert("p1", "one", tier=Tier.PERSISTENT)
    h.insert("p2", "two", tier=Tier.PERSISTENT)
    h.insert("p3", "three", tier=Tier.PERSISTENT)  # p1 demoted -> dropped
    assert h.get("p1") is None
    assert h.tier_summary()[Tier.PERSISTENT.value]["count"] == 2


# ---------------------------------------------------------------------------
# Retrieval ordering (query-driven, overlap-scored)
# ---------------------------------------------------------------------------

def test_retrieve_ranks_by_overlap_relevance():
    h = MemoryHierarchy()
    h.insert("cat_doc", "the cat sat on the mat", tier=Tier.WORKING)
    h.insert("dog_doc", "the dog barked loudly", tier=Tier.WORKING)
    hits = h.retrieve("cat mat", limit=5)
    assert [e.key for e in hits] == ["cat_doc"]


def test_retrieve_excludes_non_matching_and_respects_limit():
    h = MemoryHierarchy()
    h.insert("a", "red apple", tier=Tier.WORKING)
    h.insert("b", "blue berry", tier=Tier.WORKING)
    hits = h.retrieve("apple", limit=1)
    assert [e.key for e in hits] == ["a"]
    assert len(hits) == 1


def test_retrieve_returns_empty_for_no_match():
    h = MemoryHierarchy()
    h.insert("a", "unrelated content", tier=Tier.WORKING)
    assert h.retrieve("zzz-nonexistent") == []


def test_retrieve_ties_break_toward_hotter_tier_first():
    h = MemoryHierarchy()
    h.insert("hot", "query shared token here", tier=Tier.WORKING)
    h.insert("cold", "query shared token here", tier=Tier.PERSISTENT)
    hits = h.retrieve("query token", limit=5)
    assert [e.key for e in hits] == ["hot", "cold"]


def test_query_retrieval_counts_as_locality_access_for_promotion():
    h = MemoryHierarchy(promote_threshold=1)
    h.insert("m", "cat theme", tier=Tier.PERSISTENT)
    # retrieving it once should promote it (query-driven loading)
    h.retrieve("cat", limit=5)
    assert h.get("m").tier is Tier.RETRIEVED


# ---------------------------------------------------------------------------
# Tier summary
# ---------------------------------------------------------------------------

def test_tier_summary_reports_counts_and_capacities():
    h = MemoryHierarchy(capacities={Tier.WORKING: 5})
    h.insert("w1", "a", tier=Tier.WORKING)
    h.insert("w2", "b", tier=Tier.WORKING)
    h.set_prompt("sys", "op-param")
    s = h.tier_summary()
    assert s[Tier.WORKING.value]["count"] == 2
    assert s[Tier.WORKING.value]["capacity"] == 5
    assert s[Tier.PROMPT.value]["count"] == 1
    assert s[Tier.WEIGHTS.value]["count"] == 0


def test_stats_reflects_state():
    h = MemoryHierarchy()
    h.insert("a", "text", tier=Tier.WORKING)
    h.access("a")
    st = h.stats()
    assert st["total_items"] == 1
    assert st["total_accesses"] == 1
    assert st["tiers"] == len(Tier)


# ---------------------------------------------------------------------------
# Module facade / factory / lifecycle / events
# ---------------------------------------------------------------------------

def test_factory_returns_module_with_correct_name():
    m = create_ai_memory_hierarchy_module()
    assert m.name == "ai_memory_hierarchy"
    assert m.version == "1.0.0"
    assert m.status is HealthStatus.UNKNOWN


def test_facade_delegates_and_publishes_event():
    events = []

    class FakeBus:
        def publish(self, event):
            events.append(event)

    m = None  # noqa: F841  (placeholder removed)
    mod = AiMemoryHierarchyModule()
    mod.set_event_bus(FakeBus())
    mod.insert("k", "alpha beta gamma")
    assert len(events) == 1
    assert events[0].topic == "ai_memory_hierarchy.inserted"
    mod.retrieve("alpha")
    assert any(e.topic == "ai_memory_hierarchy.retrieved" for e in events)


def test_facade_no_event_bus_does_not_crash():
    mod = create_ai_memory_hierarchy_module()
    mod.insert("safe", "no bus here")
    assert mod.hierarchy.get("safe") is not None


async def test_module_initialize_sets_healthy():
    mod = create_ai_memory_hierarchy_module()
    await mod.initialize()
    assert mod.status is HealthStatus.HEALTHY
    assert await mod.health_check() is HealthStatus.HEALTHY


async def test_module_initialize_marks_unhealthy_and_reraises_on_failure():
    mod = create_ai_memory_hierarchy_module(
        config={"promote_threshold": 0}  # invalid -> ValueError
    )
    with pytest.raises(ValueError):
        await mod.initialize()
    assert mod.status is HealthStatus.UNHEALTHY
    assert await mod.health_check() is HealthStatus.UNHEALTHY


async def test_module_shutdown_clears_hierarchy():
    mod = create_ai_memory_hierarchy_module()
    await mod.initialize()
    mod.insert("k", "data")
    await mod.shutdown()
    assert mod.status is HealthStatus.UNKNOWN
    assert mod.hierarchy is None or mod.hierarchy.get("k") is None
