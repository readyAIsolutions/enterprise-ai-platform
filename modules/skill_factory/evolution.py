"""Evolution engine for ENI Skill Factory — real usage/feedback-backed scoring.

MASTER-CLASS upgrade over the naive in-memory ``SkillEvolutionLoop``: instead
of deriving a skill's health from a single boolean ``moving_average`` stream,
this module persists every concrete outcome -- success/fail, latency,
iterations, a 0-10 human/agent feedback rating and a timestamp -- in a SQLite
``SkillFeedbackStore`` and derives an *evolution score* from that real usage
data.  No heuristic embedding is involved: the weight for a skill is computed
entirely from the outcomes that were actually recorded for it.

Components
----------
``SkillFeedbackStore``
    SQLite-backed durable store of per-skill outcome records.
``SkillScore``
    Deterministic scoring of a skill from its stored outcomes: success rate
    (Bayesian-shrunk), volume (confidence-weighted so a handful of samples is
    never overweighted), average feedback, efficiency (inverse
    latency/iterations) and recency, collapsed into a 0-100 weight.
``EvolutionEngine``
    Orchestrates recording, ranking, promotion and the refresh loop on top of
    a store (+optional skill registry / refiner).

Stdlib only (sqlite3 / math / datetime / pathlib).
"""

from __future__ import annotations

import contextlib
import math
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable

__all__ = [
    "SkillFeedbackStore",
    "SkillScore",
    "EvolutionEngine",
    "RESULT_SUCCESS",
    "RESULT_FAIL",
    "DEFAULT_PROMOTE_THRESHOLD",
    "compute_evolution_score",
]

# ---------------------------------------------------------------------------
# Scoring configuration (deterministic, documented)
# ---------------------------------------------------------------------------

RESULT_SUCCESS = "success"
RESULT_FAIL = "fail"

#: Bayesian shrinkage strength applied to the observed success rate.  The
#: smoothed rate is ``(successes + 0.5*PRIOR_STRENGTH) / (n + PRIOR_STRENGTH)``
#: which pulls a few samples toward the neutral 0.5 instead of treating 1 lucky
#: run as a perfect track record.
PRIOR_STRENGTH = 4.0

#: Confidence weighting: ``confidence = n / (n + CONFIDENCE_PRIOR)``.  A skill
#: backed by few samples is therefore never overweighted; more volume raises
#: confidence toward 1.0 at a diminishing rate.
CONFIDENCE_PRIOR = 5.0

#: Normalisation constants for the efficiency term (lower is better).
LATENCY_NORM = 5.0  # seconds at which latency_score = 0.5
ITER_NORM = 5.0  # iterations at which iter_score = 0.5

#: Recency half-life in seconds; freshness ``exp(-age / half_life)``.
RECENCY_HALF_LIFE = 7 * 86400.0

#: Relative weights of the four score components (must sum to 1.0).
W_SUCCESS = 0.40
W_FEEDBACK = 0.25
W_EFFICIENCY = 0.20
W_RECENCY = 0.15
_WEIGHT_SUM = W_SUCCESS + W_FEEDBACK + W_EFFICIENCY + W_RECENCY

#: Default score (0-100) below which a skill is promoted for refinement.
DEFAULT_PROMOTE_THRESHOLD = 35.0


# ---------------------------------------------------------------------------
# Time helpers (determinism friendly)
# ---------------------------------------------------------------------------


def _iso_now() -> str:
    return datetime.now(UTC).isoformat()


def _epoch(ts: str) -> float:
    """Parse an ISO8601 timestamp to epoch seconds (handles a trailing ``Z``)."""
    normalized = ts.replace("Z", "+00:00")
    return datetime.fromisoformat(normalized).timestamp()


# ---------------------------------------------------------------------------
# SkillFeedbackStore
# ---------------------------------------------------------------------------


class SkillFeedbackStore:
    """SQLite-backed durable store of per-skill usage/feedback outcomes.

    Each row captures one concrete usage: ``{result, score, latency,
    iterations, feedback (0-10), timestamp}`` for a given skill.
    """

    #: Outcome columns (id/skill excluded: identity + grouping keys).
    OUTCOME_FIELDS = ("result", "score", "latency", "iterations", "feedback", "timestamp")

    def __init__(self, db_path: str | Path) -> None:
        self._path: Path = Path(db_path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self._path))
        self._conn.row_factory = sqlite3.Row
        self._create_schema()
        #: In-memory cache of skills with at least one outcome (reflects live DB).
        self._skills: set[str] = set()
        self._refresh_skills()

    def _create_schema(self) -> None:
        with self._conn:
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS outcomes (
                    id         INTEGER PRIMARY KEY AUTOINCREMENT,
                    skill      TEXT    NOT NULL,
                    result     TEXT    NOT NULL,
                    score      REAL    NOT NULL DEFAULT 0.0,
                    latency    REAL    NOT NULL DEFAULT 0.0,
                    iterations INTEGER NOT NULL DEFAULT 1,
                    feedback   INTEGER,
                    timestamp  TEXT    NOT NULL
                )
                """
            )
            self._conn.execute("CREATE INDEX IF NOT EXISTS idx_outcomes_skill ON outcomes(skill)")

    def _refresh_skills(self) -> None:
        rows = self._conn.execute("SELECT DISTINCT skill FROM outcomes").fetchall()
        self._skills = {str(r["skill"]) for r in rows}

    # -- writes -------------------------------------------------------------

    def record_outcome(
        self,
        skill: str,
        result: str = RESULT_SUCCESS,
        score: float = 0.0,
        latency: float = 0.0,
        iterations: int = 1,
        feedback: int | None = None,
        timestamp: str | None = None,
    ) -> int:
        """Persist a single real outcome for a skill, returning its row id.

        ``result`` is normalised to ``RESULT_SUCCESS`` / ``RESULT_FAIL`` and
        ``feedback`` is clamped to ``[0, 10]`` (``None`` allowed for absent
        feedback).
        """
        if result.lower() in ("success", "true", "1", "pass", "succeeded"):
            norm_result = RESULT_SUCCESS
        else:
            norm_result = RESULT_FAIL

        if feedback is not None:
            feedback = int(max(0, min(10, round(float(feedback)))))

        ts = timestamp or _iso_now()
        with self._conn:
            cur = self._conn.execute(
                """
                INSERT INTO outcomes
                  (skill, result, score, latency, iterations, feedback, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (skill, norm_result, float(score), float(latency), int(iterations), feedback, ts),
            )
        self._skills.add(skill)
        return int(cur.lastrowid)

    def _record_from_dict(self, data: dict[str, Any]) -> int:
        """Record an outcome from a dict (used by tests / rebuilds)."""
        return self.record_outcome(
            skill=str(data["skill"]),
            result=str(data.get("result", RESULT_SUCCESS)),
            score=float(data.get("score", 0.0)),
            latency=float(data.get("latency", 0.0)),
            iterations=int(data.get("iterations", 1)),
            feedback=data.get("feedback"),
            timestamp=data.get("timestamp"),
        )

    # -- reads --------------------------------------------------------------

    def get_outcomes(self, skill: str) -> list[dict[str, Any]]:
        """Return all outcome records for a skill (insertion order)."""
        rows = self._conn.execute(
            "SELECT * FROM outcomes WHERE skill = ? ORDER BY id", (skill,)
        ).fetchall()
        return [dict(r) for r in rows]

    def all_skills(self) -> list[str]:
        """Return the distinct skills that have at least one recorded outcome."""
        return sorted(self._skills)

    def count(self, skill: str | None = None) -> int:
        """Count outcomes (for one skill, or the whole store when None)."""
        if skill is None:
            return int(self._conn.execute("SELECT COUNT(*) FROM outcomes").fetchone()[0])
        return int(
            self._conn.execute(
                "SELECT COUNT(*) FROM outcomes WHERE skill = ?", (skill,)
            ).fetchone()[0]
        )

    def clear(self) -> None:
        """Delete every outcome in the store (mainly for tests / resets)."""
        with self._conn:
            self._conn.execute("DELETE FROM outcomes")
        self._skills.clear()

    def close(self) -> None:
        """Close the underlying SQLite connection."""
        with contextlib.suppress(sqlite3.Error):
            self._conn.close()


# ---------------------------------------------------------------------------
# SkillScore
# ---------------------------------------------------------------------------


class SkillScore:
    """Deterministic evolution scoring of a skill from its real outcomes.

    The final ``weight`` is an integer-%-style float in ``[0.0, 100.0]`` that
    combines:

    * success rate  (Bayesian-shrunk toward 0.5 so few samples aren't optimistic)
    * average human/agent feedback (0-10)
    * efficiency    (inverse of mean latency & iterations)
    * recency       (exponential time-decay of the newest outcome)

    attenuated by a confidence factor that scales with recorded volume, so a
    single lucky run is never overweighted relative to a well-measured skill.
    """

    def __init__(
        self,
        w_success: float = W_SUCCESS,
        w_feedback: float = W_FEEDBACK,
        w_efficiency: float = W_EFFICIENCY,
        w_recency: float = W_RECENCY,
        prior_strength: float = PRIOR_STRENGTH,
        confidence_prior: float = CONFIDENCE_PRIOR,
    ) -> None:
        total = w_success + w_feedback + w_efficiency + w_recency
        if total <= 0:
            msg = "score weights must sum to a positive value"
            raise ValueError(msg)
        self.w_success = w_success / total
        self.w_feedback = w_feedback / total
        self.w_efficiency = w_efficiency / total
        self.w_recency = w_recency / total
        self.prior_strength = prior_strength
        self.confidence_prior = confidence_prior

    # -- component scoring --------------------------------------------------

    def _success_rate(self, outcomes: list[dict[str, Any]]) -> float:
        n = len(outcomes)
        successes = sum(
            1
            for o in outcomes
            if str(o.get("result", "")).lower() in ("success", "true", "1", "pass", "succeeded")
        )
        return (successes + 0.5 * self.prior_strength) / (n + self.prior_strength)

    def _confidence(self, n: int) -> float:
        return n / (n + self.confidence_prior)

    @staticmethod
    def _avg_feedback(outcomes: list[dict[str, Any]]) -> float:
        values = [float(o["feedback"]) for o in outcomes if o.get("feedback") is not None]
        # Neutral 5/10 when no explicit feedback was captured.
        return (sum(values) / len(values) / 10.0) if values else 0.5

    @staticmethod
    def _efficiency(outcomes: list[dict[str, Any]]) -> float:
        n = len(outcomes)
        avg_lat = sum(float(o.get("latency", 0.0) or 0.0) for o in outcomes) / n
        avg_iter = sum(int(o.get("iterations", 1) or 1) for o in outcomes) / n
        latency_score = 1.0 / (1.0 + avg_lat / LATENCY_NORM)
        iter_score = 1.0 / (1.0 + avg_iter / ITER_NORM)
        return 0.5 * latency_score + 0.5 * iter_score

    @staticmethod
    def _recency(outcomes: list[dict[str, Any]], now: float | None = None) -> float:
        try:
            newest = max(_epoch(str(o["timestamp"])) for o in outcomes)
        except (ValueError, KeyError, TypeError):
            newest = 0.0
        ref = float(now) if now is not None else newest
        age = max(0.0, ref - newest)
        return math.exp(-age / RECENCY_HALF_LIFE)

    # -- combined scoring ---------------------------------------------------

    def compute(
        self,
        skill: str,
        outcomes: list[dict[str, Any]],
        now: float | None = None,
    ) -> dict[str, Any]:
        """Compute the evolution score breakdown for a skill's real outcomes.

        Args:
            skill: Name of the skill.
            outcomes: Stored outcome records (see ``SkillFeedbackStore``).
            now: Optional reference epoch for recency (tests pass a fixed one).

        Returns:
            A dict with raw components plus the final ``weight`` in ``[0, 100]``.
        """
        n = len(outcomes)
        if n == 0:
            return {
                "skill": skill,
                "n": 0,
                "successes": 0,
                "success_rate": 0.0,
                "confidence": 0.0,
                "avg_feedback": None,
                "efficiency": 0.0,
                "recency": 0.0,
                "weight": 0.0,
            }

        successes = sum(
            1
            for o in outcomes
            if str(o.get("result", "")).lower() in ("success", "true", "1", "pass", "succeeded")
        )
        success_rate = self._success_rate(outcomes)
        confidence = self._confidence(n)
        avg_fb = self._avg_feedback(outcomes)
        efficiency = self._efficiency(outcomes)
        recency = self._recency(outcomes, now=now)

        blended = (
            self.w_success * success_rate
            + self.w_feedback * avg_fb
            + self.w_efficiency * efficiency
            + self.w_recency * recency
        )
        weight = round(blended * confidence * 100.0, 2)

        return {
            "skill": skill,
            "n": n,
            "successes": successes,
            "success_rate": round(success_rate, 4),
            "confidence": round(confidence, 4),
            "avg_feedback": round(avg_fb * 10.0, 2),
            "efficiency": round(efficiency, 4),
            "recency": round(recency, 4),
            "weight": weight,
        }


def compute_evolution_score(
    skill: str,
    store: SkillFeedbackStore,
    now: float | None = None,
    scorer: SkillScore | None = None,
) -> dict[str, Any]:
    """Module-level convenience: score one skill from a real store."""
    scorer = scorer or SkillScore()
    return scorer.compute(skill, store.get_outcomes(skill), now=now)


# ---------------------------------------------------------------------------
# EvolutionEngine
# ---------------------------------------------------------------------------


class EvolutionEngine:
    """Outcome-driven evolution orchestration.

    Records real outcomes (delegating persistence to a ``SkillFeedbackStore``),
    updates per-skill evolution scores from that stored data, ranks skills by
    their real weight, identifies top/bottom performers, and runs a refresh
    loop that promotes (optionally refines via a user-supplied ``refiner``)
    any skill scoring below the promotion threshold.

    ``refiner`` is an optional ``callable(skill_name) -> Any`` (e.g. a bound
    ``SkillEvolutionLoop.evolve``) invoked once per promoted skill in a
    refresh; when absent, promotion simply marks the skill as needing
    refinement.
    """

    def __init__(
        self,
        store: SkillFeedbackStore,
        refiner: Callable[[str], object] | None = None,
        threshold: float = DEFAULT_PROMOTE_THRESHOLD,
        scorer: SkillScore | None = None,
    ) -> None:
        self.store: SkillFeedbackStore = store
        self.refiner = refiner
        self.threshold = float(threshold)
        self.scorer: SkillScore = scorer or SkillScore()
        #: skills marked as needing refinement: {skill: {"weight": w, "reason": str}}
        self.promotions: dict[str, dict[str, Any]] = {}

    # -- recording ----------------------------------------------------------

    def record_outcome(
        self,
        skill: str,
        result: str = RESULT_SUCCESS,
        score: float = 0.0,
        latency: float = 0.0,
        iterations: int = 1,
        feedback: int | None = None,
        timestamp: str | None = None,
    ) -> dict[str, Any]:
        """Persist a real outcome and return the row as a dict."""
        row_id = self.store.record_outcome(
            skill=skill,
            result=result,
            score=score,
            latency=latency,
            iterations=iterations,
            feedback=feedback,
            timestamp=timestamp,
        )
        return {
            "id": row_id,
            "skill": skill,
            "result": RESULT_SUCCESS
            if str(result).lower() in ("success", "true", "1", "pass", "succeeded")
            else RESULT_FAIL,
            "score": float(score),
            "latency": float(latency),
            "iterations": int(iterations),
            "feedback": None if feedback is None else int(max(0, min(10, round(float(feedback))))),
            "timestamp": timestamp or _iso_now(),
        }

    # -- scoring / ranking --------------------------------------------------

    def update_score(self, skill: str, now: float | None = None) -> dict[str, Any]:
        """Recompute a skill's evolution score from its stored real outcomes."""
        return self.scorer.compute(skill, self.store.get_outcomes(skill), now=now)

    def rank_skills(
        self, limit: int | None = None, now: float | None = None
    ) -> list[tuple[str, float]]:
        """Rank all skills with stored outcomes by evolution weight, descending.

        Ties are broken deterministically by skill name ascending.
        """
        rows = [
            (skill, self.scorer.compute(skill, self.store.get_outcomes(skill), now=now)["weight"])
            for skill in self.store.all_skills()
        ]
        rows.sort(key=lambda item: (-item[1], item[0]))
        return rows if limit is None else rows[: max(0, int(limit))]

    def identify_top(self, n: int = 5, now: float | None = None) -> list[tuple[str, float]]:
        """Return the ``n`` highest-scoring skills."""
        return self.rank_skills(limit=n, now=now)

    def identify_bottom(self, n: int = 5, now: float | None = None) -> list[tuple[str, float]]:
        """Return the ``n`` lowest-scoring skills (weakest performers).

        Among the measured skills, the bottom are the most likely refinement
        candidates across refresh cycles.
        """
        rows = self.rank_skills(now=now)
        return rows[-max(0, int(n)) :] if rows else []

    # -- promotion ----------------------------------------------------------

    def promote(
        self,
        skill: str,
        threshold: float | None = None,
        now: float | None = None,
    ) -> dict[str, Any]:
        """Mark a skill for refinement when its real score is below the threshold.

        Returns ``{"skill", "weight", "promoted", "reason"}``.  When promoted
        and a ``refiner`` was provided, the refiner is invoked once for the
        skill.
        """
        threshold = self.threshold if threshold is None else float(threshold)
        breakdown = self.update_score(skill, now=now)
        weight = breakdown["weight"]
        promoted = weight < threshold

        result = {
            "skill": skill,
            "weight": weight,
            "promoted": promoted,
            "reason": (
                f"evolution score {weight:.2f} below threshold {threshold:.2f}"
                if promoted
                else f"evolution score {weight:.2f} meets threshold {threshold:.2f}"
            ),
        }

        if promoted:
            self.promotions[skill] = {"weight": weight, "reason": result["reason"]}
            if self.refiner is not None:
                with contextlib.suppress(Exception):  # pragma: no cover - defensive
                    self.refiner(skill)
        else:
            # No longer needing refinement once it scores well.
            self.promotions.pop(skill, None)

        return result

    # -- refresh loop -------------------------------------------------------

    def refresh(
        self,
        limit: int | None = None,
        threshold: float | None = None,
        now: float | None = None,
    ) -> list[dict[str, Any]]:
        """Run one full evolution pass over every measured skill.

        For each skill it: recomputes the real evolution score (``update_score``)
        and promotes it for refinement if below ``threshold``.  Returns a list
        of per-skill outcome dicts for observability.
        """
        skills = self.store.all_skills()
        if limit is not None:
            skills = skills[: max(0, int(limit))]

        results: list[dict[str, Any]] = []
        for skill in skills:
            update = self.update_score(skill, now=now)
            promo = self.promote(skill, threshold=threshold, now=now)
            results.append(
                {
                    "skill": skill,
                    "weight": update["weight"],
                    "n": update["n"],
                    "promoted": promo["promoted"],
                    "reason": promo["reason"],
                }
            )
        return results
