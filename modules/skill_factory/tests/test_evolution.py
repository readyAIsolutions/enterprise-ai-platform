"""Tests for the master-class outcome-based evolution engine.

Covers: the SQLite ``SkillFeedbackStore``, deterministic ``SkillScore``
computation from real usage (success rate, volume-weighted stability,
feedback, efficiency, recency), and the ``EvolutionEngine`` ranking /
promotion / refresh loop, plus persistence round-trips and lifecycle.
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

# Match the sys.path bootstrap used by the sibling module tests so that the
# repo root (named ``enterprise``) resolves as an importable package.
_PROJECT_ROOT: Path = Path(__file__).resolve().parents[4]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import enterprise.modules.skill_factory as sf_module  # noqa: E402
from enterprise.modules.skill_factory.evolution import (  # noqa: E402
    DEFAULT_PROMOTE_THRESHOLD,
    RESULT_FAIL,
    RESULT_SUCCESS,
    EvolutionEngine,
    SkillFeedbackStore,
    compute_evolution_score,
)

# ---------------------------------------------------------------------------
# Deterministic time controls
# ---------------------------------------------------------------------------
_T = "2026-08-04T00:00:00+00:00"  # reference "now"
_NEWER = "2026-08-03T00:00:00+00:00"
_OLDER = "2026-07-01T00:00:00+00:00"
_NOW_EPOCH = datetime.fromisoformat(_T).timestamp()


def _ts(day: int) -> str:
    """Fixed ISO timestamp ``2026-08-{day:02d}T00:00:00+00:00``."""
    return f"2026-08-{day:02d}T00:00:00+00:00"


def _make(tmp_path: Path) -> SkillFeedbackStore:
    return SkillFeedbackStore(tmp_path / "evolution.db")


def _seed_good(store: SkillFeedbackStore, name: str = "alpha", n: int = 20, day: int = 1) -> None:
    for _ in range(n):
        store.record_outcome(
            skill=name,
            result=RESULT_SUCCESS,
            feedback=10,
            latency=0.0,
            iterations=1,
            timestamp=_ts(day),
        )


def _seed_bad(store: SkillFeedbackStore, name: str = "gamma", n: int = 12, day: int = 1) -> None:
    for _ in range(n):
        store.record_outcome(
            skill=name,
            result=RESULT_FAIL,
            feedback=0,
            latency=8.0,
            iterations=8,
            timestamp=_ts(day),
        )


# ===========================================================================
# SkillFeedbackStore
# ===========================================================================


class TestSkillFeedbackStore:
    def test_record_and_read_outcome(self, tmp_path: Path) -> None:
        store = _make(tmp_path)
        row_id = store.record_outcome(
            skill="alpha",
            result="success",
            score=0.9,
            latency=1.2,
            iterations=3,
            feedback=7,
            timestamp=_NEWER,
        )
        # A second, failure row with out-of-range feedback -> clamped to [0,10].
        store.record_outcome("alpha", "fail", feedback=11, timestamp=_NEWER)
        store.record_outcome("alpha", "TRUE", feedback=-4, timestamp=_NEWER)

        outcomes = store.get_outcomes("alpha")
        assert len(outcomes) == 3
        row = outcomes[0]
        assert row["id"] == row_id
        assert row["skill"] == "alpha"
        assert row["result"] == RESULT_SUCCESS
        assert row["score"] == 0.9
        assert row["latency"] == 1.2
        assert row["iterations"] == 3
        assert row["feedback"] == 7
        assert row["timestamp"] == _NEWER
        # Result is normalised; feedback is clamped into the 0-10 band.
        assert [r["result"] for r in outcomes] == [RESULT_SUCCESS, RESULT_FAIL, RESULT_SUCCESS]
        assert [r["feedback"] for r in outcomes] == [7, 10, 0]

    def test_count_and_all_skills(self, tmp_path: Path) -> None:
        store = _make(tmp_path)
        store.record_outcome("a", timestamp=_NEWER)
        store.record_outcome("a", "fail", timestamp=_NEWER)
        store.record_outcome("b", timestamp=_NEWER)
        assert store.count() == 3
        assert store.count("a") == 2
        assert store.count("missing") == 0
        assert store.get_outcomes("missing") == []
        assert store.all_skills() == ["a", "b"]

    def test_clear_removes_everything(self, tmp_path: Path) -> None:
        store = _make(tmp_path)
        _seed_good(store)
        assert store.count() == 20
        store.clear()
        assert store.count() == 0
        assert store.all_skills() == []

    def test_persistence_round_trip(self, tmp_path: Path) -> None:
        path = tmp_path / "evodb.sqlite"
        store = SkillFeedbackStore(path)
        _seed_good(store, name="persist")
        _seed_bad(store, name="persist2")
        store.close()

        reloaded = SkillFeedbackStore(path)
        assert reloaded.all_skills() == ["persist", "persist2"]
        assert len(reloaded.get_outcomes("persist")) == 20
        assert len(reloaded.get_outcomes("persist2")) == 12
        assert reloaded.count() == 32
        reloaded.close()


# ===========================================================================
# SkillScore
# ===========================================================================


class TestSkillScore:
    def test_empty_outcomes_zero_weight(self, tmp_path: Path) -> None:
        store = _make(tmp_path)
        score = compute_evolution_score("ghost", store, now=_NOW_EPOCH)
        assert score["n"] == 0
        assert score["weight"] == 0.0

    def test_all_success_high_score(self, tmp_path: Path) -> None:
        store = _make(tmp_path)
        _seed_good(store)
        score = compute_evolution_score("alpha", store, now=_NOW_EPOCH)
        assert score["successes"] == 20
        assert score["n"] == 20
        assert score["weight"] >= 70.0  # well-measured, consistent success

    def test_success_rate_orders_scores(self, tmp_path: Path) -> None:
        store = _make(tmp_path)
        _seed_good(store, name="good")
        _seed_bad(store, name="bad")
        good = compute_evolution_score("good", store, now=_NOW_EPOCH)
        bad = compute_evolution_score("bad", store, now=_NOW_EPOCH)
        assert good["success_rate"] > bad["success_rate"]
        assert good["weight"] > bad["weight"]

    def test_feedback_raises_score(self, tmp_path: Path) -> None:
        store = _make(tmp_path)
        for _ in range(20):
            store.record_outcome(
                "liked", RESULT_SUCCESS, feedback=10, latency=0, iterations=1, timestamp=_ts(1)
            )
            store.record_outcome(
                "flat", RESULT_SUCCESS, feedback=0, latency=0, iterations=1, timestamp=_ts(1)
            )
        liked = compute_evolution_score("liked", store, now=_NOW_EPOCH)
        flat = compute_evolution_score("flat", store, now=_NOW_EPOCH)
        assert liked["avg_feedback"] > flat["avg_feedback"]
        assert liked["weight"] > flat["weight"]

    def test_efficiency_raises_score(self, tmp_path: Path) -> None:
        store = _make(tmp_path)
        for _ in range(20):
            store.record_outcome(
                "fast", RESULT_SUCCESS, feedback=5, latency=0.1, iterations=1, timestamp=_ts(1)
            )
            store.record_outcome(
                "slow", RESULT_SUCCESS, feedback=5, latency=20.0, iterations=20, timestamp=_ts(1)
            )
        fast = compute_evolution_score("fast", store, now=_NOW_EPOCH)
        slow = compute_evolution_score("slow", store, now=_NOW_EPOCH)
        assert fast["efficiency"] > slow["efficiency"]
        assert fast["weight"] > slow["weight"]

    def test_recency_boosts_newer_skill(self, tmp_path: Path) -> None:
        store = _make(tmp_path)
        for _ in range(20):
            store.record_outcome(
                "fresh", RESULT_SUCCESS, feedback=5, latency=1, iterations=1, timestamp=_ts(3)
            )
            store.record_outcome(
                "stale", RESULT_SUCCESS, feedback=5, latency=1, iterations=1, timestamp=_ts(1)
            )
        fresh = compute_evolution_score("fresh", store, now=_NOW_EPOCH)
        stale = compute_evolution_score("stale", store, now=_NOW_EPOCH)
        assert fresh["recency"] > stale["recency"]
        assert fresh["weight"] > stale["weight"]

    def test_volume_weighted_stability_no_overweight(self, tmp_path: Path) -> None:
        """A single lucky 100% run must NOT rival a well-measured 100% skill."""
        store = _make(tmp_path)
        store.record_outcome(
            "lucky", RESULT_SUCCESS, feedback=10, latency=0, iterations=1, timestamp=_ts(1)
        )
        _seed_good(store, name="steady", n=20, day=1)
        lucky = compute_evolution_score("lucky", store, now=_NOW_EPOCH)
        steady = compute_evolution_score("steady", store, now=_NOW_EPOCH)
        # Both are 100% raw success (shrunk rates > neutral 0.5).
        assert lucky["success_rate"] > 0.5
        assert steady["success_rate"] > 0.5
        assert lucky["n"] < steady["n"]
        assert lucky["confidence"] < steady["confidence"]
        # Equal success but far less volume => far lower weight, not overweighted.
        assert steady["weight"] > lucky["weight"] * 3


# ===========================================================================
# EvolutionEngine
# ===========================================================================


class TestEvolutionEngine:
    def test_record_outcome_delegates_and_returns_row(self, tmp_path: Path) -> None:
        store = _make(tmp_path)
        engine = EvolutionEngine(store)
        row = engine.record_outcome("s", "success", feedback=8, timestamp=_NEWER)
        assert row["skill"] == "s"
        assert row["result"] == RESULT_SUCCESS
        assert row["feedback"] == 8
        assert store.count("s") == 1

    def test_update_score_computes_weight(self, tmp_path: Path) -> None:
        store = _make(tmp_path)
        _seed_good(store)
        engine = EvolutionEngine(store)
        bd = engine.update_score("alpha", now=_NOW_EPOCH)
        assert set(bd) >= {"skill", "n", "weight", "success_rate", "confidence"}
        assert bd["skill"] == "alpha"
        assert bd["n"] == 20
        assert bd["weight"] > 0

    def test_rank_skills_orders_descending(self, tmp_path: Path) -> None:
        store = _make(tmp_path)
        _seed_good(store, name="top")
        _seed_bad(store, name="bottom")
        # A moderate middle-performer: 10 success / 5 fail, mild feedback.
        for i in range(15):
            store.record_outcome(
                "mid",
                RESULT_SUCCESS if i < 10 else RESULT_FAIL,
                feedback=5,
                latency=1,
                iterations=1,
                timestamp=_ts(1),
            )
        engine = EvolutionEngine(store)
        ranked = engine.rank_skills(now=_NOW_EPOCH)
        weights = [w for _, w in ranked]
        assert weights == sorted(weights, reverse=True)
        assert ranked[0][0] == "top"
        assert ranked[-1][0] == "bottom"
        top, bottom = (
            engine.identify_top(1, now=_NOW_EPOCH)[0],
            engine.identify_bottom(1, now=_NOW_EPOCH)[0],
        )
        assert top == ranked[0]
        assert bottom == ranked[-1]

    def test_promote_below_threshold_marks(self, tmp_path: Path) -> None:
        store = _make(tmp_path)
        _seed_bad(store)  # low score
        engine = EvolutionEngine(store, threshold=DEFAULT_PROMOTE_THRESHOLD)
        result = engine.promote("gamma", now=_NOW_EPOCH)
        assert result["promoted"] is True
        assert "gamma" in engine.promotions
        assert engine.promotions["gamma"]["weight"] == result["weight"]

    def test_promote_above_threshold_not_marked(self, tmp_path: Path) -> None:
        store = _make(tmp_path)
        _seed_good(store)  # high score
        engine = EvolutionEngine(store)
        result = engine.promote("alpha", now=_NOW_EPOCH)
        assert result["promoted"] is False
        assert "alpha" not in engine.promotions

    def test_refresh_loop_scores_scores_and_promotes(self, tmp_path: Path) -> None:
        refiner_calls: list[str] = []
        store = _make(tmp_path)
        _seed_good(store, name="good")
        _seed_bad(store, name="bad")
        engine = EvolutionEngine(store, refiner=refiner_calls.append)
        results = engine.refresh(now=_NOW_EPOCH)
        by_skill = {r["skill"]: r for r in results}
        assert set(by_skill) == {"good", "bad"}
        assert by_skill["bad"]["promoted"] is True
        assert by_skill["good"]["promoted"] is False
        # refiner invoked exactly once, for the promoted (bad) skill.
        assert refiner_calls == ["bad"]
        assert "bad" in engine.promotions

    def test_module_exports_new_symbols(self) -> None:
        for name in ("EvolutionEngine", "SkillFeedbackStore", "SkillScore"):
            assert hasattr(sf_module, name), f"missing export {name}"
        assert sf_module.RESULT_SUCCESS == RESULT_SUCCESS
        assert sf_module.RESULT_FAIL == RESULT_FAIL
        assert callable(sf_module.compute_evolution_score)
