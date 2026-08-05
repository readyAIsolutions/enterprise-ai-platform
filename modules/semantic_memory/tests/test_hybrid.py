"""Tests for the mem0-style hybrid memory core (hybrid.py).

Covers hybrid vector+keyword retrieval, mem0-style change detection on add()
(created / updated / noop), metadata filtering, SQLite persistence across
re-inits, threshold semantics, and stats.

Run with:
    python3 -m pytest modules/semantic_memory -q
"""

from __future__ import annotations

import json
import sqlite3

import pytest

from enterprise.modules.semantic_memory.hybrid import (
    HybridRetriever,
    HybridSemanticMemory,
    keyword_score,
    tokenize,
)

# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------


@pytest.fixture
def memory(tmp_path):
    db = str(tmp_path / "mem.db")
    m = HybridSemanticMemory(db_path=db)
    yield m
    m.close()


def _in_memory() -> HybridSemanticMemory:
    return HybridSemanticMemory()  # db_path=None -> in-memory


# ---------------------------------------------------------------------------
# Keyword scoring + tokenization
# ---------------------------------------------------------------------------


class TestKeywordScoring:
    def test_tokenize_lowercases_and_splits(self) -> None:
        assert tokenize("Machine Learning Model") == ["machine", "learning", "model"]

    def test_full_overlap_scores_one(self) -> None:
        assert keyword_score(["bread", "flour"], ["bread", "flour", "water"]) == 1.0

    def test_empty_query_scores_zero(self) -> None:
        assert keyword_score([], ["anything"]) == 0.0

    def test_partial_overlap_partial_score(self) -> None:
        s = keyword_score(["a", "b", "c"], ["a", "z", "z"])
        assert 0 < s < 1.0


# ---------------------------------------------------------------------------
# Hybrid retrieval: vector + keyword
# ---------------------------------------------------------------------------


class TestHybridRetrieval:
    def test_search_returns_merged_ranked_results(self) -> None:
        m = _in_memory()
        r1 = m.add("neural network trains on gpu data", {"source": "ai"})
        r2 = m.add("baking sourdough bread with flour", {"source": "food"})
        r3 = m.add("supervised machine learning model training", {"source": "ai"})
        assert [r1.event, r2.event, r3.event] == ["created", "created", "created"]

        hits = m.search("model training neural", limit=5)
        # keyword + vector both surface the two ML-ish docs
        assert len(hits) >= 2
        ids = {h.id for h in hits}
        assert r1.id in ids
        assert r3.id in ids
        # hits are ordered descending by blended score
        scores = [h.score for h in hits]
        assert scores == sorted(scores, reverse=True)

    def test_keyword_exact_hit_outranks_pure_vector(self) -> None:
        m = _in_memory()
        m.add("python programming language tutorial", {"source": "dev"})
        m.add("snake animal in the zoo", {"source": "bio"})
        # A query that shares exact tokens with the python doc but the vector
        # alone could be ambiguous -> keyword term must pull it to the top.
        hits = m.search("python language tutorial", limit=5)
        assert hits[0].score >= hits[1].score
        assert "python" in hits[0].text

    def test_search_respects_limit(self) -> None:
        m = _in_memory()
        m.add("quantum computing qubit theory")
        m.add("neural network deep learning")
        m.add("astrophysics black hole galaxy")
        m.add("baking bread flour sourdough")
        m.add("robotics actuators mechanical joints")
        assert len(m.search("quantum neural astrophysics", limit=2)) == 2
        assert len(m.search("quantum neural astrophysics", limit=0)) == 0

    def test_hybrid_retriever_standalone(self) -> None:
        hr = HybridRetriever()
        hr.add("d1", "quantum computing qubit state")
        hr.add("d2", "making pizza dough from scratch")
        assert hr.count() == 2
        hits = hr.search("quantum qubit computing")
        assert hits and hits[0].id == "d1"


# ---------------------------------------------------------------------------
# mem0-style add(): created / updated / noop + threshold semantics
# ---------------------------------------------------------------------------


class TestChangeDetection:
    def test_add_created_then_noop_for_duplicate(self) -> None:
        m = _in_memory()
        first = m.add("the cat sat on the mat", {"source": "test"})
        assert first.event == "created"
        count_after_first = m.stats()["total"]
        assert count_after_first == 1
        # exact duplicate (threshold default 0.85) -> noop
        dup = m.add("the cat sat on the mat", {"source": "test"})
        assert dup.event == "noop"
        assert dup.id == first.id
        # no new memory created for a noop
        assert m.stats()["total"] == 1

    def test_add_updated_for_changed_near_duplicate(self) -> None:
        m = _in_memory()
        first = m.add("neural network training pipeline", {"source": "ai"})
        changed = m.add(
            "neural network training pipeline now", {"source": "ai"}
        )
        # Near-duplicate but text differs -> updated, same id kept
        assert changed.event == "updated"
        assert changed.id == first.id
        assert changed.previous == "neural network training pipeline"
        # still only one memory, text replaced
        assert m.stats()["total"] == 1
        assert m.recall("neural network training pipeline", k=5)[0].text.endswith("now")

    def test_add_created_when_distinct(self) -> None:
        m = _in_memory()
        a = m.add("quantum entanglement experiment", {"source": "phys"})
        b = m.add("cooking a creamy mushroom risotto", {"source": "food"})
        assert a.event == "created" and b.event == "created"
        assert a.id != b.id
        assert m.stats()["total"] == 2

    def test_add_result_helpers(self) -> None:
        m = _in_memory()
        c = m.add("alpha beta gamma")
        assert c.is_new and not c.is_updated and not c.noop
        d = m.add("alpha beta gamma")
        assert d.noop and not d.is_new
        assert set(d.as_dict()) == {"id", "event", "score", "text", "metadata", "previous"}

    def test_threshold_high_forces_created(self) -> None:
        m = _in_memory()
        m.add("unique phrase alpha beta gamma")
        # threshold 1.0 => even a near-duplicate must score exactly 1.0 to
        # qualify; a changed phrase scores below 1.0 -> created, not updated.
        b = m.add("unique phrase alpha beta gamma changed", threshold=1.0)
        assert b.event == "created"
        assert m.stats()["total"] == 2

    def test_threshold_low_forces_updated(self) -> None:
        m = _in_memory()
        m.add("same root phrase duplicated words here")
        # threshold 0.0 => any overlap qualifies -> near-duplicate updated.
        b = m.add("same root phrase duplicated words here plus more", threshold=0.0)
        assert b.event == "updated"
        assert m.stats()["total"] == 1

    def test_threshold_exact_noop(self) -> None:
        m = _in_memory()
        m.add("exact copy text corpus")
        # identical text scores 1.0 >= 0.85 -> noop
        b = m.add("exact copy text corpus")
        assert b.event == "noop"
        assert m.stats()["total"] == 1

    def test_add_memory_alias_matches_add(self) -> None:
        m = _in_memory()
        assert m.add_memory("hello world greeting").event == "created"
        assert m.add_memory("hello world greeting").event == "noop"


# ---------------------------------------------------------------------------
# Metadata filtering
# ---------------------------------------------------------------------------


class TestMetadataFiltering:
    def test_filter_by_scalar_key(self) -> None:
        m = _in_memory()
        m.add("machine learning model", {"source": "kb", "kind": "note"})
        m.add("baking bread recipe", {"source": "kb", "kind": "recipe"})
        m.add("restaurant review about food", {"source": "web", "kind": "note"})
        kb_hits = m.search("food bread recipe model", filters={"source": "kb"})
        assert kb_hits and all(h.metadata["source"] == "kb" for h in kb_hits)
        assert len(kb_hits) == 2

    def test_filter_by_list_membership(self) -> None:
        m = _in_memory()
        m.add("machine learning model", {"tags": ["ai", "nn"]})
        m.add("baking bread recipe", {"tags": ["food", "cooking"]})
        hits = m.search("model bread recipe", filters={"tags": ["ai"]})
        assert hits and all("ai" in h.metadata["tags"] for h in hits)

    def test_metadata_persisted_in_db(self, memory) -> None:
        memory.add("some stored text with meaning", {"source": "emo", "tags": ["x"]})
        conn = sqlite3.connect(memory.db_path)
        row = conn.execute("SELECT text, metadata FROM memories").fetchone()
        conn.close()
        assert row[0] == "some stored text with meaning"
        assert json.loads(row[1]) == {"source": "emo", "tags": ["x"]}


# ---------------------------------------------------------------------------
# Persistence round-trip across re-inits
# ---------------------------------------------------------------------------


class TestPersistence:
    def test_round_trip_reload(self, tmp_path) -> None:
        db = str(tmp_path / "mem.db")
        m1 = HybridSemanticMemory(db_path=db)
        r = m1.add("persistent memory about orbital mechanics", {"source": "phys"})
        m1.add("mixed fruit smoothie recipe", {"source": "food"})
        m1.close()

        m2 = HybridSemanticMemory(db_path=db)  # reload from same DB
        try:
            assert m2.stats()["total"] == 2
            hits = m2.search("orbital mechanics", limit=5)
            assert hits[0].id == r.id
            assert hits[0].metadata["source"] == "phys"
        finally:
            m2.close()

    def test_created_vs_updated_reflected_after_reload(self, tmp_path) -> None:
        db = str(tmp_path / "mem.db")
        m1 = HybridSemanticMemory(db_path=db)
        m1.add("update detection persists text change")
        m1.add("update detection persists text change now different", threshold=0.0)
        m1.close()
        m2 = HybridSemanticMemory(db_path=db)
        try:
            assert m2.stats()["total"] == 1
            assert m2.list()[0]["text"].endswith("now different")
        finally:
            m2.close()

    def test_delete_persists(self, tmp_path) -> None:
        db = str(tmp_path / "mem.db")
        m1 = HybridSemanticMemory(db_path=db)
        r = m1.add("temporary memory to delete later")
        m1.delete(r.id)
        m1.close()
        m2 = HybridSemanticMemory(db_path=db)
        try:
            assert m2.stats()["total"] == 0
        finally:
            m2.close()


# ---------------------------------------------------------------------------
# Update / delete / list / stats
# ---------------------------------------------------------------------------


class TestMutationAndStats:
    def test_update_changes_text_and_metadata(self) -> None:
        m = _in_memory()
        r = m.add("original text content", {"source": "a"})
        assert m.update(r.id, text="new text content", metadata={"source": "b"}) is True
        doc = m.recall("new text content", k=5)[0]
        assert doc.text == "new text content"
        assert doc.metadata["source"] == "b"
        # update returns False for unknown id
        assert m.update("does-not-exist", text="x") is False

    def test_delete_removes(self) -> None:
        m = _in_memory()
        r = m.add("delete me please")
        assert m.stats()["total"] == 1
        assert m.delete(r.id) is True
        assert m.stats()["total"] == 0
        assert m.delete(r.id) is False

    def test_list_returns_dicts_sorted(self) -> None:
        m = _in_memory()
        m.add("first memory", {"source": "a"})
        m.add("second memory", {"source": "b"}, user_id="u1")
        items = m.list()
        assert len(items) == 2
        assert {"id", "text", "metadata", "user_id", "created_at", "updated_at"} <= set(
            items[0]
        )

    def test_list_filter_by_user(self) -> None:
        m = _in_memory()
        m.add("alice memory one", user_id="alice")
        m.add("bob memory one", user_id="bob")
        alice_items = m.list(user_id="alice")
        assert len(alice_items) == 1
        assert alice_items[0]["user_id"] == "alice"

    def test_stats_counts(self) -> None:
        m = _in_memory()
        assert m.stats()["total"] == 0
        m.add("one")
        m.add("two")
        m.add("three")
        s = m.stats()
        assert s["total"] == 3
        assert s["memories"] == 3
        assert s["persisted"] is False
        assert s["db_path"] is None
        assert s["threshold"] == 0.85

    def test_stats_by_user(self) -> None:
        m = _in_memory()
        m.add("a", user_id="u1")
        m.add("b", user_id="u1")
        m.add("c", user_id="u2")
        by_user = m.stats()["by_user"]
        assert by_user["u1"] == 2
        assert by_user["u2"] == 1

    def test_remember_preserves_original_api(self) -> None:
        m = _in_memory()
        m.remember("explicit-id", "explicitly stored text", {"k": "v"})
        hits = m.recall("explicitly stored text", k=5)
        assert hits[0].id == "explicit-id"
        assert "explicit-id" in {i["id"] for i in m.list()}


# ---------------------------------------------------------------------------
# Module-level wiring
# ---------------------------------------------------------------------------


class TestModuleIntegration:
    async def test_module_runs_in_memory_by_default(self) -> None:
        from enterprise.modules.semantic_memory import SemanticMemoryModule

        mod = SemanticMemoryModule(config={"dim": 64})
        await mod.initialize()
        try:
            assert mod.memory is not None
            assert mod.memory.db_path is None
            mod.remember("h1", "hybrid index text", {"source": "mod"})
            assert mod.memory.stats()["total"] == 1
            assert mod.recall("hybrid index text", k=1)[0].id == "h1"
        finally:
            await mod.shutdown()

    async def test_module_db_path_config(self, tmp_path) -> None:
        from enterprise.modules.semantic_memory import SemanticMemoryModule

        db = str(tmp_path / "mod.db")
        mod = SemanticMemoryModule(config={"dim": 64, "db_path": db})
        await mod.initialize()
        try:
            assert mod.db_path == db
            mod.remember("p1", "persisted module memory", {"source": "mod"})
        finally:
            await mod.shutdown()

        # New module instance reloads the same DB.
        mod2 = SemanticMemoryModule(config={"dim": 64, "db_path": db})
        await mod2.initialize()
        try:
            assert mod2.memory.stats()["total"] == 1
        finally:
            await mod2.shutdown()
