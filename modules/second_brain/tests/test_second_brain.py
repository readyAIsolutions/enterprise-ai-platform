"""Unit tests for the second_brain module (network-free)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from enterprise.modules.second_brain import (
    Entry, SecondBrain, make_second_brain, create_second_brain_module,
)


NOW = datetime(2026, 8, 16, 12, 0, tzinfo=timezone.utc)


def _brain_with_entries():
    b = make_second_brain()
    a = b.capture("A second brain must connect ideas, not just store them",
                  tags=["second-brain", "linking"], source="tea")
    c = b.capture("Plain storage becomes a graveyard of forgotten notes",
                  tags=["second-brain", "storage"], source="tea")
    d = b.capture("Label a long archive so it stays searchable for decades",
                  tags=["archive", "labeling"], source="vansquared")
    return b, a, c, d


# ------------------------------------------------------------------ capture
def test_capture_stores_metadata():
    b = make_second_brain()
    e = b.capture("ideas outlive any single model", tags=["First Principles"],
                  source="ai-since-2011")
    assert e.text == "ideas outlive any single model"
    assert e.tags == ["first principles"]  # normalized lowercase, kept whole
    assert e.source == "ai-since-2011"
    assert e.created_at is not None
    assert b.get(e.id) is e


def test_capture_normalizes_and_dedups_tags():
    b = make_second_brain()
    got = b.capture("note", tags=["Tag", "tag", "  ", "other"])
    assert got.tags == ["tag", "other"]  # lowercase, deduped, first-seen order


# -------------------------------------------------------------------- link
def test_link_ideas_creates_bidirectional_edge():
    b, a, c, _ = _brain_with_entries()
    assert b.link_ideas(a.id, c.id) is True
    assert c.id in b.neighbors(a.id)
    assert a.id in b.neighbors(c.id)


def test_link_ideas_rejects_unknown_and_self():
    b, a, c, _ = _brain_with_entries()
    assert b.link_ideas(a.id, "nope") is False
    assert b.link_ideas(a.id, a.id) is False
    assert b.link_ideas("nope", c.id) is False


def test_connected_component_bridges_ideas():
    b, a, c, d = _brain_with_entries()
    b.link_ideas(a.id, c.id)
    b.link_ideas(c.id, d.id)
    cluster = b.connected_component(a.id)
    assert set(cluster) == {a.id, c.id, d.id}


# --------------------------------------------------------------- resurface
def test_resurface_returns_due_entries_and_schedules_next():
    b = make_second_brain()
    e1 = b.capture("alpha", tags=["t1"])
    e2 = b.capture("beta", tags=["t2"])
    # force e1 due far in past so it's the clear pick
    e1.next_review = NOW - timedelta(days=5)
    e2.next_review = NOW + timedelta(days=30)
    due = b.resurface(due=NOW)
    assert [e.id for e in due] == [e1.id]

    # reviewing schedules the *next* prompt (1-day bump)
    assert b.review(e1.id) is True
    assert e1.next_review > NOW


def test_review_doubles_interval_until_cap():
    b = make_second_brain()
    e = b.capture("repeat me", tags=["rep"])
    b.review(e.id)   # -> 1 day
    b.review(e.id)   # -> 2 days
    b.review(e.id)   # -> 4 days
    d1 = e.next_review
    b.review(e.id)   # -> 8 days (cap at 32 eventually)
    assert e.next_review > d1


def test_forget_resets_schedule():
    b = make_second_brain()
    e = b.capture("Session 10", tags=["icm"])
    b.review(e.id)
    b.review(e.id)
    before = e.next_review
    assert b.review(e.id, forgotten=True) is True
    assert e.next_review < before      # pulled back much sooner


def test_review_unknown_id_returns_false():
    b = make_second_brain()
    assert b.review("missing") is False


# ---------------------------------------------------------- concept query
def test_query_concept_matches_tags_and_text():
    b, a, c, d = _brain_with_entries()
    b.link_ideas(a.id, c.id)  # both carry the 'second-brain' concept
    by_tag = b.query_concept("second-brain")
    ids = {e.id for e in by_tag}
    assert {a.id, c.id} <= ids

    by_text = b.query_concept("graveyard")
    assert {e.id for e in by_text} == {c.id}


def test_query_concept_returns_empty_for_unknown():
    b = make_second_brain()
    b.capture("a thing", tags=["x"])
    assert b.query_concept("zzzabsent") == []


# ------------------------------------------------------ compounding report
def test_compounding_report_reflects_linking():
    b, a, c, d = _brain_with_entries()
    b.link_ideas(a.id, c.id)
    b.link_ideas(c.id, d.id)
    rep = b.build_compounding_report(now=NOW)
    assert rep["total_entries"] == 3
    assert rep["total_links"] == 2
    assert rep["linked_entries"] == 3
    assert rep["verdict"] == "compounding"


def test_storage_only_is_graveyard():
    b = make_second_brain()
    b.capture("lonely note one", tags=["x"])
    b.capture("lonely note two", tags=["y"])
    rep = b.build_compounding_report(now=NOW)
    assert rep["total_entries"] == 2
    assert rep["total_links"] == 0
    assert rep["verdict"] == "storage only"


# ------------------------------------------------------------ platform svc
def test_module_initializes_and_facade_works():
    import asyncio
    m = create_second_brain_module({})
    asyncio.run(m.initialize())
    assert m.brain is not None
    assert asyncio.run(m.health_check()).value in ("healthy", "HEALTHY") \
        or "HEALTHY" in str(asyncio.run(m.health_check()))

    e = m.capture("capture via facade", tags=["facade"])
    assert e["source"] == "eni"  # global_source default
    assert len(m.query_concept("facade")) == 1
    asyncio.run(m.shutdown())
