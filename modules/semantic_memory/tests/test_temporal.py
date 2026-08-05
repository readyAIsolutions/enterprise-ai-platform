"""Tests for temporal memory + consolidation (Zep temporal recall, mem0 ranking).

Covers:
  * ``search(..., since=, until=, time_bucket=)`` timestamp-window filtering
  * ``recall_since()`` and ``group_by_time_bucket()`` temporal recall
  * ``consolidate()`` pruning stale + low-importance, keeping recent/important
  * ``ranking()`` ordering by recency + importance
  * keyword-exact-token rerank bonus in the hybrid merge
  * persistence of timestamps across a SQLite reload
  * backward compatibility (existing public API untouched)

Run with:
    python3 -m pytest modules/semantic_memory -q
"""

from __future__ import annotations

import datetime

import pytest

from enterprise.modules.semantic_memory.hybrid import (
    EXACT_TOKEN_BONUS,
    HybridRetriever,
    HybridSemanticMemory,
    _exact_tokens,
    _bucket_key,
)

DAY = 86400.0


@pytest.fixture
def memory(tmp_path):
    db = str(tmp_path / "temporal.db")
    m = HybridSemanticMemory(db_path=db)
    yield m
    m.close()


def _in_memory() -> HybridSemanticMemory:
    return HybridSemanticMemory()


def _backdate(m: HybridSemanticMemory, rid: str, days_ago: float) -> None:
    """Move a memory's created/updated timestamps into the past (in-memory)."""
    ts = datetime.datetime.now().timestamp() - days_ago * DAY
    m._created_at[rid] = ts
    m._updated_at[rid] = ts


# ---------------------------------------------------------------------------
# Temporal window filtering on search
# ---------------------------------------------------------------------------


class TestTemporalFiltering:
    def test_since_restricts_results(self) -> None:
        m = _in_memory()
        old = m.add("ancient memory about stone tools", {"source": "arch"})
        recent = m.add("fresh memory about rocket engines", {"source": "space"})
        _backdate(m, old.id, 10)
        now = datetime.datetime.now().timestamp()
        hits = m.search("about memory", limit=10, since=now - 2 * DAY)
        ids = {h.id for h in hits}
        assert recent.id in ids
        assert old.id not in ids

    def test_until_restricts_results(self) -> None:
        m = _in_memory()
        old = m.add("older decision recorded earlier", {"d": 1})
        newish = m.add("newer decision recorded now", {"d": 2})
        _backdate(m, old.id, 10)
        now = datetime.datetime.now().timestamp()
        # only memories updated at/after this cutoff -> only 'newish' passes `until` window
        until_ts = now - 5 * DAY
        hits = m.search("decision recorded", limit=10, until=until_ts)
        ids = {h.id for h in hits}
        assert old.id in ids
        assert newish.id not in ids

    def test_since_and_until_window(self) -> None:
        m = _in_memory()
        a = m.add("alpha note content here")
        b = m.add("beta note content here")
        c = m.add("gamma note content here")
        _backdate(m, a.id, 30)
        _backdate(m, b.id, 10)
        # c stays now
        now = datetime.datetime.now().timestamp()
        hits = m.search("note content", limit=10, since=now - 20 * DAY, until=now - 5 * DAY)
        ids = {h.id for h in hits}
        assert b.id in ids
        assert a.id not in ids
        assert c.id not in ids

    def test_accepts_datetime_objects(self) -> None:
        m = _in_memory()
        old = m.add("dated entry alpha", {"k": 1})
        recent = m.add("dated entry beta", {"k": 2})
        _backdate(m, old.id, 7)
        cutoff = datetime.datetime.now() - datetime.timedelta(days=2)
        hits = m.search("dated entry", limit=10, since=cutoff)
        ids = {h.id for h in hits}
        assert recent.id in ids
        assert old.id not in ids

    def test_time_bucket_searches_current_day(self) -> None:
        m = _in_memory()
        today = m.add("today planning note", {"d": 1})
        old = m.add("long_ago planning note", {"d": 2})
        _backdate(m, old.id, 30)
        hits = m.search("planning note", limit=10, time_bucket="day")
        ids = {h.id for h in hits}
        assert today.id in ids
        assert old.id not in ids


# ---------------------------------------------------------------------------
# Temporal recall: recall_since + group_by_time_bucket
# ---------------------------------------------------------------------------


class TestTemporalRecall:
    def test_recall_since_created(self) -> None:
        m = _in_memory()
        r = m.add("recently created memory")
        _backdate(m, r.id, 1)
        old = m.add("ancient created memory")
        _backdate(m, old.id, 40)
        cutoff = datetime.datetime.now() - datetime.timedelta(days=5)
        recent = m.recall_since(cutoff)
        ids = {it["id"] for it in recent}
        assert r.id in ids
        assert old.id not in ids

    def test_group_by_day_counts(self) -> None:
        m = _in_memory()
        a = m.add("day a memory one")
        b = m.add("day b memory one")
        c = m.add("day b memory two")
        _backdate(m, a.id, 30)
        _backdate(m, b.id, 30)
        groups = m.group_by_time_bucket("day")
        assert sum(g["count"] for g in groups.values()) == 3
        # a and b share a day bucket (backdated together); c is on 'today'
        today_bucket = _bucket_key("day", datetime.datetime.now().timestamp())
        assert groups[today_bucket]["count"] == 1

    def test_group_by_month(self) -> None:
        m = _in_memory()
        m.add("current month memory a")
        m.add("current month memory b")
        groups = m.group_by_time_bucket("month")
        labels = set()
        for g in groups.values():
            labels.update(it["id"] for it in g["memories"])
        assert len(groups) == 1  # all land in the same (current) month bucket
        assert all(g["count"] >= 1 for g in groups.values())

    def test_group_by_created_key(self) -> None:
        m = _in_memory()
        m.add("created-key memory")
        groups = m.group_by_time_bucket("week", key="created_at")
        assert sum(g["count"] for g in groups.values()) == m.stats()["total"]


# ---------------------------------------------------------------------------
# Consolidation + ranking (mem0-style)
# ---------------------------------------------------------------------------


class TestConsolidation:
    def test_prunes_stale_low_importance_keeps_recent(self) -> None:
        m = _in_memory()
        stale_low = m.add("stale trivial fact nobody needs", {"priority": 0})
        recent_low = m.add("recent but also low importance", {"priority": 0})
        recent_high = m.add("recent important decision we must keep", {"priority": 10})
        _backdate(m, stale_low.id, 30)
        res = m.consolidate(max_age=2 * DAY, min_importance=0.5)
        assert stale_low.id in res["pruned_ids"]
        assert recent_low.id not in res["pruned_ids"]  # recent -> not stale
        assert recent_high.id not in res["pruned_ids"]  # important -> kept
        ids = {it["id"] for it in m.list()}
        assert stale_low.id not in ids
        assert recent_low.id in ids
        assert recent_high.id in ids

    def test_default_consolidate_is_safe_noop_for_none(self) -> None:
        m = _in_memory()
        for i in range(5):
            m.add(f"plain memory number {i}")
        before = m.stats()["total"]
        res = m.consolidate()  # no thresholds -> nothing is both stale & low
        assert res["pruned"] == 0
        assert res["merged"] == 0
        assert m.stats()["total"] == before

    def test_stale_high_importance_is_kept(self) -> None:
        m = _in_memory()
        stale_high = m.add("old but crucial requirement", {"priority": 50})
        _backdate(m, stale_high.id, 60)
        res = m.consolidate(max_age=2 * DAY, min_importance=0.5)
        assert stale_high.id not in res["pruned_ids"]
        assert stale_high.id in {it["id"] for it in m.list()}

    def test_merge_reports_redundant_duplicate(self) -> None:
        m = _in_memory()
        dup = m.add("redundant copied reminder text", {"priority": 0})
        _backdate(m, dup.id, 30)
        m.add("redundant copied reminder text", {"priority": 0})
        # both low importance; one backdated/stale gets merged (near-duplicate)
        res = m.consolidate(max_age=2 * DAY, min_importance=0.5)
        assert res["merged"] + res["pruned"] >= 1


class TestRanking:
    def test_recent_ranks_above_old(self) -> None:
        m = _in_memory()
        now = m.add("current active memory")
        old = m.add("long ago dormant memory")
        _backdate(m, old.id, 50)
        ranked = m.ranking()
        ids = [it["id"] for it in ranked]
        assert ids.index(now.id) < ids.index(old.id)

    def test_importance_orders_within_recency(self) -> None:
        m = _in_memory()
        low = m.add("low priority recent decision", {"priority": 0})
        high = m.add("high priority recent decision", {"priority": 20})
        ranked = m.ranking(importance_weight=1.0, recency_weight=0.0)
        ids = [it["id"] for it in ranked]
        # pure importance sort -> high first
        assert ids.index(high.id) < ids.index(low.id)

    def test_ranking_reports_scores_and_ranks(self) -> None:
        m = _in_memory()
        m.add("ranking subject one")
        m.add("ranking subject two")
        ranked = m.ranking()
        assert ranked and all("rank" in it and "score" in it for it in ranked)
        scores = [it["score"] for it in ranked]
        assert scores == sorted(scores, reverse=True)


# ---------------------------------------------------------------------------
# Keyword-exact rerank bonus in the hybrid merge
# ---------------------------------------------------------------------------


class TestExactTokenRerankBonus:
    def test_exact_tokens_helper(self) -> None:
        assert _exact_tokens(["a", "b"], ["a", "b", "c"]) is True
        assert _exact_tokens(["a", "z"], ["a", "b", "c"]) is False
        assert _exact_tokens([], ["x"]) is False

    def test_bonus_lifts_exact_token_hit(self) -> None:
        m = _in_memory()
        m.add("python programming language tutorial", {"source": "dev"})
        m.add("snake animal in the zoo", {"source": "bio"})
        hits = m.search("python language tutorial", limit=5)
        # the exact-token doc must outrank the ambiguous one
        assert hits[0].score >= hits[1].score
        assert "python" in hits[0].text
        # bonus constant is a small positive magnitude
        assert 0.0 < EXACT_TOKEN_BONUS <= 0.1

    def test_keyword_exact_bonus_applied_over_vector_only(self) -> None:
        m = _in_memory()
        m.add("quantum computing qubit entanglement", {"source": "phys"})
        m.add("computing hardware chips memory", {"source": "cs"})
        # query shares exact tokens strongly with the first doc
        hits = m.search("quantum qubit computing", limit=5)
        assert hits[0].text.startswith("quantum")


# ---------------------------------------------------------------------------
# Temporal persistence across SQLite reload
# ---------------------------------------------------------------------------


class TestTemporalPersistence:
    def test_timestamps_persist_and_recall_since_after_reload(self, tmp_path) -> None:
        db = str(tmp_path / "mem.db")
        m1 = HybridSemanticMemory(db_path=db)
        r = m1.add("persistent decision from the past", {"source": "kb"})
        cutoff = datetime.datetime.now() - datetime.timedelta(hours=1)
        m1.close()

        m2 = HybridSemanticMemory(db_path=db)
        try:
            item = m2.list()[0]
            assert item["id"] == r.id
            assert item["created_at"] is not None
            assert item["updated_at"] is not None
            # created 'now' is after cutoff an hour ago -> recall_since finds it
            hits = m2.recall_since(cutoff)
            assert any(it["id"] == r.id for it in hits)
            # time-bucket search still surfaces it today
            day_hits = m2.search("persistent decision", limit=5, time_bucket="day")
            assert any(h.id == r.id for h in day_hits)
        finally:
            m2.close()

    def test_migration_adds_missing_time_columns(self, tmp_path) -> None:
        """A pre-temporal DB (no created_at/updated_at) opens and migrates cleanly."""
        db = str(tmp_path / "legacy.db")
        import sqlite3

        conn = sqlite3.connect(db)
        conn.execute(
            "CREATE TABLE memories (id TEXT PRIMARY KEY, text TEXT NOT NULL,"
            " metadata TEXT NOT NULL DEFAULT '{}', user_id TEXT)"
        )
        conn.execute(
            "INSERT INTO memories (id, text, metadata, user_id)"
            " VALUES ('legacy1', 'old legacy memory', '{}', NULL)"
        )
        conn.commit()
        conn.close()

        m = HybridSemanticMemory(db_path=db)
        try:
            # columns added
            conn = sqlite3.connect(db)
            cols = {row[1] for row in conn.execute("PRAGMA table_info(memories)")}
            conn.close()
            assert "created_at" in cols and "updated_at" in cols
            # legacy row loads and gets non-null timestamps (treated recent)
            item = m.list()[0]
            assert item["id"] == "legacy1"
            assert item["created_at"] is not None
            assert item["updated_at"] is not None
            # temporal search works over the migrated store
            assert any(h.id == "legacy1" for h in m.search("legacy memory", time_bucket="day"))
        finally:
            m.close()


# ---------------------------------------------------------------------------
# HybridRetriever standalone temporal + ranking
# ---------------------------------------------------------------------------


class TestHybridRetrieverTemporal:
    def test_retriever_ranking_and_recall_since(self) -> None:
        hr = HybridRetriever()
        hr.add("d1", "quantum computing qubit state")
        hr.add("d2", "making pizza dough from scratch")
        assert hr.count() == 2
        ranked = hr.ranking()
        assert len(ranked) == 2
        assert ranked[0]["rank"] == 1
        since_ts = datetime.datetime.now() - datetime.timedelta(seconds=1)
        recent = hr.recall_since(since_ts)
        assert len(recent) == 2  # both added 'now'

    def test_retriever_consolidate_prunes_stale(self) -> None:
        hr = HybridRetriever()
        hr.add("s1", "stale short-term scratch note", {"priority": 0})
        hr.add("s2", "important anchored decision", {"priority": 20})
        hr._times["s1"] = datetime.datetime.now().timestamp() - 30 * DAY
        res = hr.consolidate(max_age=2 * DAY, min_importance=0.5)
        assert "s1" in res["pruned_ids"]
        ids = {d.id for d in hr._index._documents.values()}
        assert "s1" not in ids
        assert "s2" in ids

    def test_retriever_search_until_filter(self) -> None:
        hr = HybridRetriever()
        hr.add("old", "obsolete config item content")
        now = datetime.datetime.now().timestamp()
        hr._times["old"] = now - 30 * DAY
        hr.add("fresh", "current config item content")
        hits = hr.search("config item content", limit=10, since=now - 1 * DAY)
        assert {h.id for h in hits} == {"fresh"}


# ---------------------------------------------------------------------------
# Module facade passthroughs
# ---------------------------------------------------------------------------


class TestModulePassthrough:
    async def test_module_temporal_and_consolidation(self) -> None:
        from enterprise.modules.semantic_memory import SemanticMemoryModule

        mod = SemanticMemoryModule(config={"dim": 64})
        await mod.initialize()
        try:
            r = mod.memory.add("module temporal memory", {"priority": 5})
            assert any(it["id"] == r.id for it in mod.recall_since(0))
            assert mod.ranking() and mod.ranking()[0]["rank"] == 1
            groups = mod.group_by_time_bucket("day")
            assert sum(g["count"] for g in groups.values()) == mod.memory.stats()["total"]
            res = mod.consolidate()  # safe no-op with no thresholds
            assert res["pruned"] == 0
        finally:
            await mod.shutdown()
