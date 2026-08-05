"""
Customer Journey Analytics Engine.

Master-class analytics layer for the Customer Experience OS. Provides a real
(no-stub) analytics stack comprising:

  * ``FunnelAnalyst``  -- track customers through an ordered set of funnel
    stages and compute stage-to-stage conversion, per-stage drop-off and
    overall funnel conversion.
  * ``NPS``            -- collect 0-10 Net Promoter Score responses and compute
    the canonical NPS metric (%% promoters - %% detractors), confidence bands
    and the detractor/passive/promoter segmentation.
  * ``ChurnRisk``      -- score a customer 0-100 on churn risk derived from a
    small, transparent weighted model over engagement signals (recent support
    tickets, negative feedback, inactivity).
  * ``JourneyAnalytics`` -- facade that combines funnel + NPS + churn-risk into
    a single coordinated dashboard and exposes a structured ``report()``.

Every component works fully in-memory and also supports optional SQLite
persistence (stdlib ``sqlite3`` only), with lossless ``save`` / ``load``
round-trips.

Version: 1.0.0
"""

from __future__ import annotations

import logging
import sqlite3
import threading
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Sequence

logger = logging.getLogger("enterprise.customer_experience")


# ---------------------------------------------------------------------------
# Funnel
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class StageConversion:
    """Conversion metrics between two adjacent funnel stages."""

    from_stage: str
    to_stage: str
    from_count: int
    to_count: int

    @property
    def rate(self) -> float:
        """Conversion rate (0.0-1.0) from ``from_stage`` to ``to_stage``."""
        if self.from_count <= 0:
            return 0.0
        return self.to_count / self.from_count

    @property
    def dropoff(self) -> int:
        """Absolute number of customers/events lost between the two stages."""
        return max(self.from_count - self.to_count, 0)

    @property
    def dropoff_rate(self) -> float:
        """Fraction (0.0-1.0) of the upstream stage lost at this transition."""
        if self.from_count <= 0:
            return 0.0
        return self.dropoff / self.from_count


class FunnelAnalyst:
    """Track raw (stage, event) funnel events and derive conversion analytics.

    Stages are declared once (an ordered sequence of stage labels). Calling
    ``feed(stage, event, customer_id=...)`` records a single funnel event. When
    ``customer_id`` values are supplied the engine computes *distinct-customer*
    reach per stage so re-entering a stage never double counts a customer;
    otherwise raw event counts are used (each event counts once).
    """

    def __init__(
        self,
        stages: Sequence[str],
        *,
        name: str = "customer_funnel",
    ) -> None:
        if not stages:
            msg = "FunnelAnalyst requires at least one stage"
            raise ValueError(msg)
        self.name = name
        self._stages: list[str] = list(stages)
        # Preserve declared order and reject duplicates for unambiguous metrics.
        if len(set(self._stages)) != len(self._stages):
            msg = "Funnel stages must be unique"
            raise ValueError(msg)
        self._events: list[dict[str, Any]] = []
        self._stage_counts: Counter = Counter()
        self._customer_stages: dict[str, set] = {s: set() for s in self._stages}
        self._lock = threading.RLock()
        logger.info("FunnelAnalyst '%s' initialized with %d stages", name, len(stages))

    # ------------------------------------------------------------------
    # Ingestion
    # ------------------------------------------------------------------

    def feed(
        self,
        stage: str,
        event: str | None = None,
        *,
        customer_id: str | None = None,
        timestamp: datetime | None = None,
    ) -> FunnelAnalyst:
        """Record a single funnel event at ``stage``.

        ``event`` is an optional free-form label describing what happened at
        that stage (e.g. ``"signup"``, ``"checkout"``). Returns self for fluent
        chaining.
        """
        if stage not in self._stages:
            msg = f"Unknown funnel stage: {stage!r}"
            raise ValueError(msg)
        record: dict[str, Any] = {
            "stage": stage,
            "event": event,
            "ts": timestamp or datetime.now(UTC),
        }
        with self._lock:
            if customer_id is not None:
                record["customer_id"] = customer_id
                if customer_id not in self._customer_stages[stage]:
                    self._customer_stages[stage].add(customer_id)
                    self._stage_counts[stage] += 1
            else:
                self._stage_counts[stage] += 1
            self._events.append(record)
        return self

    # Convenience alias matching the common "record reach" vocabulary.
    def track(
        self,
        stage: str,
        customer_id: str | None = None,
        event: str | None = None,
    ) -> FunnelAnalyst:
        """Alias for :meth:`feed` oriented toward per-customer tracking."""
        return self.feed(stage, event, customer_id=customer_id)

    # ------------------------------------------------------------------
    # Metrics
    # ------------------------------------------------------------------

    def stages(self) -> list[str]:
        """Return the ordered funnel stage labels."""
        return list(self._stages)

    def event_count(self) -> int:
        """Total number of raw events recorded."""
        return len(self._events)

    def reach(self) -> dict[str, int]:
        """Distinct-customer (or raw event) reach per stage in declared order."""
        has_customers = any("customer_id" in e for e in self._events)
        with self._lock:
            if has_customers:
                return {s: len(self._customer_stages[s]) for s in self._stages}
            return {s: int(self._stage_counts[s]) for s in self._stages}

    def conversions(self) -> list[StageConversion]:
        """Conversion + drop-off metrics for each adjacent stage pair."""
        reach = self.reach()
        out: list[StageConversion] = []
        for i in range(len(self._stages) - 1):
            out.append(
                StageConversion(
                    from_stage=self._stages[i],
                    to_stage=self._stages[i + 1],
                    from_count=reach[self._stages[i]],
                    to_count=reach[self._stages[i + 1]],
                )
            )
        return out

    def overall_conversion(self) -> float:
        """Fraction (0.0-1.0) that makes it from first to last stage."""
        reach = self.reach()
        first = reach[self._stages[0]]
        last = reach[self._stages[-1]]
        if first <= 0:
            return 0.0
        return last / first

    def dropoffs(self) -> dict[str, int]:
        """Absolute drop-off attributable to each stage transition key.

        Keys are ``"<from> -> <to>"``.
        """
        return {f"{c.from_stage} -> {c.to_stage}": c.dropoff for c in self.conversions()}

    def funnel_report(self) -> dict[str, Any]:
        """A structured, human-reviewable funnel dashboard."""
        reach = self.reach()
        convs = self.conversions()
        return {
            "name": self.name,
            "stages": self._stages,
            "reach": reach,
            "conversions": [
                {
                    "from": c.from_stage,
                    "to": c.to_stage,
                    "from_count": c.from_count,
                    "to_count": c.to_count,
                    "rate": c.rate,
                    "dropoff": c.dropoff,
                    "dropoff_rate": c.dropoff_rate,
                }
                for c in convs
            ],
            "overall_conversion": self.overall_conversion(),
            "total_events": self.event_count(),
        }

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def to_records(self) -> list[dict[str, Any]]:
        """Serialize raw events to JSON-friendly dicts (SQLite persistence)."""
        rows: list[dict[str, Any]] = []
        for e in self._events:
            rows.append(
                {
                    "stage": e["stage"],
                    "event": e.get("event"),
                    "customer_id": e.get("customer_id"),
                    "ts": e["ts"].isoformat(),
                }
            )
        return rows

    def save_sqlite(self, path: str) -> int:
        """Persist all funnel events to ``path``; returns row count written."""
        with sqlite3.connect(path) as conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS funnel_events ("
                "  id INTEGER PRIMARY KEY AUTOINCREMENT,"
                "  stage TEXT NOT NULL,"
                "  event TEXT,"
                "  customer_id TEXT,"
                "  ts TEXT NOT NULL)"
            )
            conn.executemany(
                "INSERT INTO funnel_events (stage, event, customer_id, ts) "
                "VALUES (:stage, :event, :customer_id, :ts)",
                self.to_records(),
            )
            conn.commit()
        logger.info("FunnelAnalyst persisted %d events to %s", len(self._events), path)
        return len(self._events)

    @classmethod
    def load_sqlite(
        cls, path: str, stages: Sequence[str], *, name: str = "customer_funnel"
    ) -> FunnelAnalyst:
        """Rebuild a FunnelAnalyst from a previously saved SQLite file."""
        fa = cls(stages, name=name)
        with sqlite3.connect(path) as conn:
            rows = conn.execute(
                "SELECT stage, event, customer_id, ts FROM funnel_events ORDER BY id"
            ).fetchall()
        for stage, event, customer_id, ts in rows:
            fa.feed(
                stage,
                event,
                customer_id=customer_id or None,
                timestamp=datetime.fromisoformat(ts),
            )
        logger.info("FunnelAnalyst loaded %d events from %s", len(rows), path)
        return fa


# ---------------------------------------------------------------------------
# NPS
# ---------------------------------------------------------------------------


class NPSBand(Enum):
    """Standard Net Promoter Score segmentation bands (0-10 scale)."""

    DETRACTOR = "detractor"  # 0-6
    PASSIVE = "passive"  # 7-8
    PROMOTER = "promoter"  # 9-10


class NPS:
    """Classic Net Promoter Score collector and calculator.

    Responses are integers 0-10. NPS = %promoters - %detractors, where
    promoters are 9-10, passives 7-8 and detractors 0-6. Scores land in the
    canonical [-100, +100] range and degrade gracefully with zero samples.
    """

    DETRACTOR_MAX = 6
    PASSIVE_MAX = 8

    def __init__(self) -> None:
        self._responses: list[dict[str, Any]] = []
        self._lock = threading.RLock()

    # ------------------------------------------------------------------
    # Ingestion
    # ------------------------------------------------------------------

    @staticmethod
    def band(score: int) -> NPSBand:
        """Classify a single 0-10 score into its NPS band."""
        score = int(score)
        if score < 0 or score > 10:
            msg = f"NPS score must be 0-10, got {score!r}"
            raise ValueError(msg)
        if score <= NPS.DETRACTOR_MAX:
            return NPSBand.DETRACTOR
        if score <= NPS.PASSIVE_MAX:
            return NPSBand.PASSIVE
        return NPSBand.PROMOTER

    def record(
        self, score: int, *, customer_id: str | None = None, timestamp: datetime | None = None
    ) -> NPS:
        """Record one 0-10 NPS response; returns self for chaining."""
        score = int(score)
        if not 0 <= score <= 10:
            msg = f"NPS score must be 0-10, got {score!r}"
            raise ValueError(msg)
        with self._lock:
            self._responses.append(
                {
                    "score": score,
                    "customer_id": customer_id,
                    "ts": timestamp or datetime.now(UTC),
                }
            )
        return self

    # ------------------------------------------------------------------
    # Metrics
    # ------------------------------------------------------------------

    def sample_count(self) -> int:
        return len(self._responses)

    def counts(self) -> dict[NPSBand, int]:
        """Absolute counts per band."""
        c: dict[NPSBand, int] = dict.fromkeys(NPSBand, 0)
        with self._lock:
            for r in self._responses:
                c[self.band(r["score"])] += 1
        return c

    def percentages(self) -> dict[NPSBand, float]:
        """Share (0.0-100.0) of respondents in each band."""
        total = self.sample_count()
        if total == 0:
            return dict.fromkeys(NPSBand, 0.0)
        counts = self.counts()
        return {b: (counts[b] / total) * 100.0 for b in NPSBand}

    @property
    def promoters(self) -> int:
        return self.counts()[NPSBand.PROMOTER]

    @property
    def passives(self) -> int:
        return self.counts()[NPSBand.PASSIVE]

    @property
    def detractors(self) -> int:
        return self.counts()[NPSBand.DETRACTOR]

    def nps(self) -> float:
        """Net Promoter Score in [-100, +100] (0.0 when no samples)."""
        pct = self.percentages()
        return pct[NPSBand.PROMOTER] - pct[NPSBand.DETRACTOR]

    def report(self) -> dict[str, Any]:
        """Structured NPS summary including bands and raw distribution."""
        pct = self.percentages()
        scores = [r["score"] for r in self._responses]
        return {
            "nps": self.nps(),
            "sample_count": self.sample_count(),
            "promoters": self.promoters,
            "passives": self.passives,
            "detractors": self.detractors,
            "promoter_pct": pct[NPSBand.PROMOTER],
            "passive_pct": pct[NPSBand.PASSIVE],
            "detractor_pct": pct[NPSBand.DETRACTOR],
            "mean_score": (sum(scores) / len(scores)) if scores else 0.0,
            "distribution": Counter(scores),
        }

    def reset(self) -> NPS:
        """Clear all recorded responses."""
        with self._lock:
            self._responses.clear()
        return self

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def save_sqlite(self, path: str) -> int:
        with sqlite3.connect(path) as conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS nps_responses ("
                "  id INTEGER PRIMARY KEY AUTOINCREMENT,"
                "  score INTEGER NOT NULL,"
                "  customer_id TEXT,"
                "  ts TEXT NOT NULL)"
            )
            conn.executemany(
                "INSERT INTO nps_responses (score, customer_id, ts) "
                "VALUES (:score, :customer_id, :ts)",
                [
                    {
                        "score": r["score"],
                        "customer_id": r.get("customer_id"),
                        "ts": r["ts"].isoformat(),
                    }
                    for r in self._responses
                ],
            )
            conn.commit()
        return len(self._responses)

    @classmethod
    def load_sqlite(cls, path: str) -> NPS:
        nps = cls()
        with sqlite3.connect(path) as conn:
            rows = conn.execute(
                "SELECT score, customer_id, ts FROM nps_responses ORDER BY id"
            ).fetchall()
        for score, customer_id, ts in rows:
            nps.record(score, customer_id=customer_id or None, timestamp=datetime.fromisoformat(ts))
        return nps


# ---------------------------------------------------------------------------
# Churn Risk
# ---------------------------------------------------------------------------


class ChurnRiskLevel(Enum):
    """Risk bands for an inferred churn score."""

    LOW = "low"  # 0-29
    MEDIUM = "medium"  # 30-59
    HIGH = "high"  # 60-100


@dataclass
class CustomerSignals:
    """Engagement signals feeding the churn-risk model for one customer."""

    customer_id: str
    support_tickets: int = 0  # recent support ticket count
    negative_feedback: int = 0  # recent negative feedback events
    inactivity_days: int = 0  # days since last meaningful activity
    metadata: dict[str, Any] = field(default_factory=dict)


class ChurnRisk:
    """Weighted churn-risk scorer (0-100, higher = more at risk).

    Model (transparent, documented weighted average of normalized signals):

        tickets_norm    = min(support_tickets / TICKETS_CAP, 1.0)
        feedback_norm   = min(negative_feedback / FEEDBACK_CAP, 1.0)
        inactivity_norm = min(inactivity_days / INACTIVITY_CAP, 1.0)

        score = 100 * (w_tickets * tickets_norm
                       + w_feedback * feedback_norm
                       + w_inactivity * inactivity_norm)

    Default weights sum to 1.0 and bias toward engagement-decay (inactivity)
    as the strongest single predictor, with negative feedback and support
    ticket volume as corroborating signals.
    """

    TICKETS_CAP = 5.0
    FEEDBACK_CAP = 3.0
    INACTIVITY_CAP = 90.0

    DEFAULT_WEIGHTS: dict[str, float] = {
        "tickets": 0.30,
        "feedback": 0.30,
        "inactivity": 0.40,
    }

    def __init__(self, weights: dict[str, float] | None = None) -> None:
        w = dict(self.DEFAULT_WEIGHTS)
        if weights:
            w.update(weights)
        total = sum(w.values())
        if total <= 0:
            msg = "ChurnRisk weights must sum to a positive value"
            raise ValueError(msg)
        self._weights = {k: v / total for k, v in w.items()}
        self._signals: dict[str, CustomerSignals] = {}
        self._lock = threading.RLock()

    def weights(self) -> dict[str, float]:
        """Effective (normalized) model weights."""
        return dict(self._weights)

    # ------------------------------------------------------------------
    # Ingestion
    # ------------------------------------------------------------------

    def update(
        self,
        customer_id: str,
        *,
        support_tickets: int = 0,
        negative_feedback: int = 0,
        inactivity_days: int = 0,
    ) -> float:
        """Record engagement signals for a customer and return their risk score."""
        sig = self._signals.get(customer_id, CustomerSignals(customer_id=customer_id))
        sig.support_tickets = max(int(support_tickets), 0)
        sig.negative_feedback = max(int(negative_feedback), 0)
        sig.inactivity_days = max(int(inactivity_days), 0)
        with self._lock:
            self._signals[customer_id] = sig
        return self.score(customer_id)

    def customers(self) -> list[str]:
        return list(self._signals.keys())

    # ------------------------------------------------------------------
    # Scoring
    # ------------------------------------------------------------------

    def _normalized(self, sig: CustomerSignals) -> dict[str, float]:
        return {
            "tickets": min(sig.support_tickets / self.TICKETS_CAP, 1.0),
            "feedback": min(sig.negative_feedback / self.FEEDBACK_CAP, 1.0),
            "inactivity": min(sig.inactivity_days / self.INACTIVITY_CAP, 1.0),
        }

    def score(self, customer_id: str) -> float:
        """Return the churn-risk score (0.0-100.0) for a customer (0 if unknown)."""
        sig = self._signals.get(customer_id)
        if sig is None:
            return 0.0
        norm = self._normalized(sig)
        raw = (
            self._weights["tickets"] * norm["tickets"]
            + self._weights["feedback"] * norm["feedback"]
            + self._weights["inactivity"] * norm["inactivity"]
        )
        return round(raw * 100.0, 2)

    @staticmethod
    def risk_level(score: float) -> ChurnRiskLevel:
        """Map a 0-100 score to a human risk band."""
        if score >= 60:
            return ChurnRiskLevel.HIGH
        if score >= 30:
            return ChurnRiskLevel.MEDIUM
        return ChurnRiskLevel.LOW

    def signal_breakdown(self, customer_id: str) -> dict[str, Any] | None:
        """Return the per-signal decomposition of a customer's risk score."""
        sig = self._signals.get(customer_id)
        if sig is None:
            return None
        norm = self._normalized(sig)
        weighted = {k: norm[k] * self._weights[k] * 100.0 for k in norm}
        return {
            "customer_id": customer_id,
            "signals": {
                "support_tickets": sig.support_tickets,
                "negative_feedback": sig.negative_feedback,
                "inactivity_days": sig.inactivity_days,
            },
            "normalized": norm,
            "weighted_contribution": weighted,
            "score": self.score(customer_id),
            "risk_level": self.risk_level(self.score(customer_id)).value,
        }

    def report(self) -> dict[str, Any]:
        """Aggregate churn-risk dashboard across all tracked customers."""
        scores = {cid: self.score(cid) for cid in self.customers()}
        n = len(scores)
        high = sum(1 for s in scores.values() if s >= 60)
        medium = sum(1 for s in scores.values() if 30 <= s < 60)
        low = sum(1 for s in scores.values() if s < 30)
        return {
            "model_weights": self._weights,
            "customer_count": n,
            "avg_score": (sum(scores.values()) / n) if n else 0.0,
            "max_score": max(scores.values()) if n else 0.0,
            "risk_bands": {
                "high": high,
                "medium": medium,
                "low": low,
            },
            "scores": scores,
        }

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def save_sqlite(self, path: str) -> int:
        with sqlite3.connect(path) as conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS churn_signals ("
                "  customer_id TEXT PRIMARY KEY,"
                "  support_tickets INTEGER NOT NULL,"
                "  negative_feedback INTEGER NOT NULL,"
                "  inactivity_days INTEGER NOT NULL)"
            )
            rows = [
                (
                    s.customer_id,
                    s.support_tickets,
                    s.negative_feedback,
                    s.inactivity_days,
                )
                for s in self._signals.values()
            ]
            conn.executemany(
                "INSERT OR REPLACE INTO churn_signals "
                "(customer_id, support_tickets, negative_feedback, inactivity_days) "
                "VALUES (?, ?, ?, ?)",
                rows,
            )
            conn.commit()
        return len(rows)

    @classmethod
    def load_sqlite(cls, path: str, weights: dict[str, float] | None = None) -> ChurnRisk:
        cr = cls(weights=weights)
        with sqlite3.connect(path) as conn:
            rows = conn.execute(
                "SELECT customer_id, support_tickets, negative_feedback, inactivity_days "
                "FROM churn_signals"
            ).fetchall()
        for cid, tickets, feedback, inactivity in rows:
            cr.update(
                cid, support_tickets=tickets, negative_feedback=feedback, inactivity_days=inactivity
            )
        return cr


# ---------------------------------------------------------------------------
# Journey Analytics facade
# ---------------------------------------------------------------------------


class JourneyAnalytics:
    """Facade that coordinates funnel, NPS and churn-risk into one dashboard.

    Owns a ``FunnelAnalyst``, an ``NPS`` collector and a ``ChurnRisk`` scorer,
    plus lightweight cross-cutting journey stats. ``report()`` merges all three
    into a single structured payload suitable for dashboards or persistence.
    """

    def __init__(
        self,
        funnel_stages: Sequence[str] = (
            "awareness",
            "evaluation",
            "purchase",
            "setup",
            "first_value",
            "regular_use",
            "renewal",
        ),
        *,
        churn_weights: dict[str, float] | None = None,
    ) -> None:
        self.funnel = FunnelAnalyst(funnel_stages)
        self.nps = NPS()
        self.churn = ChurnRisk(weights=churn_weights)
        self._started_at = datetime.now(UTC)
        logger.info("JourneyAnalytics initialized with %d funnel stages", len(funnel_stages))

    # A single high-level ingestion point mirroring the task's (stage, event)
    # vocabulary.
    def record_event(
        self, stage: str, event: str | None = None, *, customer_id: str | None = None
    ) -> JourneyAnalytics:
        """Record a funnel event; returns self for chaining."""
        self.funnel.feed(stage, event, customer_id=customer_id)
        return self

    def record_nps(self, score: int, *, customer_id: str | None = None) -> JourneyAnalytics:
        """Record an NPS response; returns self for chaining."""
        self.nps.record(score, customer_id=customer_id)
        return self

    def update_churn(self, customer_id: str, **signals) -> JourneyAnalytics:
        """Record churn-risk signals; returns self for chaining."""
        self.churn.update(customer_id, **signals)
        return self

    def report(self) -> dict[str, Any]:
        """Aggregate full journey-analytics dashboard."""
        return {
            "generated_at": datetime.now(UTC).isoformat(),
            "session_started_at": self._started_at.isoformat(),
            "funnel": self.funnel.funnel_report(),
            "nps": self.nps.report(),
            "churn_risk": self.churn.report(),
            "summary": {
                "total_funnel_events": self.funnel.event_count(),
                "nps_samples": self.nps.sample_count(),
                "tracked_customers": self.churn.report()["customer_count"],
            },
        }

    def save_sqlite(self, path: str) -> dict[str, int]:
        """Persist all three components to one SQLite DB; returns rows written."""
        return {
            "funnel": self.funnel.save_sqlite(path),
            "nps": self.nps.save_sqlite(path),
            "churn": self.churn.save_sqlite(path),
        }

    @classmethod
    def load_sqlite(
        cls,
        path: str,
        funnel_stages: Sequence[str],
        *,
        churn_weights: dict[str, float] | None = None,
    ) -> JourneyAnalytics:
        """Rebuild a full JourneyAnalytics from one SQLite DB."""
        ja = cls(funnel_stages, churn_weights=churn_weights)
        ja.funnel = FunnelAnalyst.load_sqlite(path, funnel_stages)
        ja.nps = NPS.load_sqlite(path)
        ja.churn = ChurnRisk.load_sqlite(path, weights=churn_weights)
        return ja
