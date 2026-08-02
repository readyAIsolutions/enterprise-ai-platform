"""
Customer Experience Metrics Engine.

Tracks, calculates, and analyzes key CX metrics including CSAT,
time-to-value, churn prediction, and accessibility scores.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, ClassVar, Dict, List, Optional, Set, Tuple

logger = logging.getLogger("enterprise.customer_experience")


class CXMetric(Enum):
    """Standard CX metrics tracked by the engine."""

    TIME_TO_FIRST_VALUE = "time_to_first_value"
    TASK_COMPLETION_RATE = "task_completion_rate"
    CSAT = "csat"
    RESPONSE_TIME = "response_time"
    RESOLUTION_TIME = "resolution_time"
    REPEAT_CONTACT_RATE = "repeat_contact_rate"
    ADOPTION_RATE = "adoption_rate"
    RETENTION_RATE = "retention_rate"
    CHURN_RATE = "churn_rate"
    COMPLAINT_RATE = "complaint_rate"
    ACCESSIBILITY_SCORE = "accessibility_score"
    TRUST_INDICATOR = "trust_indicator"


class TrendDirection(Enum):
    """Direction of metric trend over a period."""
    IMPROVING = "improving"
    STABLE = "stable"
    DECLINING = "declining"
    UNKNOWN = "unknown"


@dataclass
class MetricSnapshot:
    """A single data point for a CX metric at a point in time."""

    metric_type: CXMetric
    value: float
    target: float
    trend_direction: TrendDirection = TrendDirection.UNKNOWN
    period_start: datetime = field(default_factory=lambda: datetime.now(timezone.utc) - timedelta(days=30))
    period_end: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    segment: str = "all"

    # Metrics where lower values are better
    _LOWER_IS_BETTER: ClassVar[Set[CXMetric]] = {
        CXMetric.TIME_TO_FIRST_VALUE,
        CXMetric.RESPONSE_TIME,
        CXMetric.RESOLUTION_TIME,
        CXMetric.REPEAT_CONTACT_RATE,
        CXMetric.CHURN_RATE,
        CXMetric.COMPLAINT_RATE,
    }

    def on_target(self) -> bool:
        if self.metric_type in self._LOWER_IS_BETTER:
            return self.value <= self.target
        return self.value >= self.target

    def gap_to_target(self) -> float:
        if self.metric_type in self._LOWER_IS_BETTER:
            return self.value - self.target
        return self.target - self.value


class CXMetricsEngine:
    """Primary engine for CX metric collection, calculation, and reporting."""

    DEFAULT_TARGETS: Dict[CXMetric, float] = {
        CXMetric.TIME_TO_FIRST_VALUE: 30.0,      # days
        CXMetric.TASK_COMPLETION_RATE: 90.0,       # percent
        CXMetric.CSAT: 4.0,                        # out of 5
        CXMetric.RESPONSE_TIME: 60.0,              # minutes
        CXMetric.RESOLUTION_TIME: 480.0,           # minutes (8 hrs)
        CXMetric.REPEAT_CONTACT_RATE: 5.0,         # percent
        CXMetric.ADOPTION_RATE: 80.0,              # percent
        CXMetric.RETENTION_RATE: 95.0,             # percent
        CXMetric.CHURN_RATE: 3.0,                  # percent
        CXMetric.COMPLAINT_RATE: 2.0,              # percent
        CXMetric.ACCESSIBILITY_SCORE: 95.0,        # percent
        CXMetric.TRUST_INDICATOR: 80.0,            # percent
    }

    def __init__(self, custom_targets: Optional[Dict[CXMetric, float]] = None) -> None:
        self._snapshots: Dict[CXMetric, List[MetricSnapshot]] = {m: [] for m in CXMetric}
        self._targets = {**self.DEFAULT_TARGETS, **(custom_targets or {})}
        self._raw_events: List[Dict[str, Any]] = []
        logger.info("CXMetricsEngine initialized")

    # ------------------------------------------------------------------
    # Raw data ingestion
    # ------------------------------------------------------------------

    def collect_metrics(self, events: List[Dict[str, Any]]) -> None:
        """Ingest a batch of raw events for metric calculation."""
        self._raw_events.extend(events)
        logger.info("Collected %d raw CX events", len(events))

    # ------------------------------------------------------------------
    # Individual metric calculators
    # ------------------------------------------------------------------

    def calculate_time_to_value(
        self,
        activation_events: List[Dict[str, Any]],
        segment: str = "all",
    ) -> MetricSnapshot:
        """Calculate average time from signup to first meaningful value."""
        if not activation_events:
            return MetricSnapshot(
                metric_type=CXMetric.TIME_TO_FIRST_VALUE,
                value=self._targets[CXMetric.TIME_TO_FIRST_VALUE],
                target=self._targets[CXMetric.TIME_TO_FIRST_VALUE],
                trend_direction=TrendDirection.UNKNOWN,
                segment=segment,
            )

        total_days = 0.0
        for event in activation_events:
            signup = event.get("signup_date")
            activation = event.get("activation_date")
            if signup and activation:
                delta = (activation - signup).days if isinstance(signup, datetime) else 0
                total_days += max(0, delta)

        avg_days = total_days / len(activation_events)
        target = self._targets[CXMetric.TIME_TO_FIRST_VALUE]
        snapshot = self._build_snapshot(CXMetric.TIME_TO_FIRST_VALUE, avg_days, target, segment)
        self._snapshots[CXMetric.TIME_TO_FIRST_VALUE].append(snapshot)
        return snapshot

    def measure_task_completion(
        self,
        completed: int,
        attempted: int,
        segment: str = "all",
    ) -> MetricSnapshot:
        """Measure task completion rate."""
        rate = (completed / attempted * 100.0) if attempted > 0 else 0.0
        target = self._targets[CXMetric.TASK_COMPLETION_RATE]
        snapshot = self._build_snapshot(CXMetric.TASK_COMPLETION_RATE, rate, target, segment)
        self._snapshots[CXMetric.TASK_COMPLETION_RATE].append(snapshot)
        return snapshot

    def compute_csat(
        self,
        scores: List[float],
        segment: str = "all",
    ) -> MetricSnapshot:
        """Compute Customer Satisfaction (CSAT) average."""
        avg = sum(scores) / len(scores) if scores else 0.0
        target = self._targets[CXMetric.CSAT]
        snapshot = self._build_snapshot(CXMetric.CSAT, round(avg, 2), target, segment)
        self._snapshots[CXMetric.CSAT].append(snapshot)
        return snapshot

    def track_response_time(
        self,
        response_times_minutes: List[float],
        segment: str = "all",
    ) -> MetricSnapshot:
        """Track average support response time."""
        avg = sum(response_times_minutes) / len(response_times_minutes) if response_times_minutes else 0.0
        target = self._targets[CXMetric.RESPONSE_TIME]
        # Lower is better, so invert the comparison
        snapshot = self._build_snapshot(
            CXMetric.RESPONSE_TIME, avg, target, segment, lower_is_better=True,
        )
        self._snapshots[CXMetric.RESPONSE_TIME].append(snapshot)
        return snapshot

    def track_resolution_time(
        self,
        resolution_times_minutes: List[float],
        segment: str = "all",
    ) -> MetricSnapshot:
        """Track average resolution time."""
        avg = sum(resolution_times_minutes) / len(resolution_times_minutes) if resolution_times_minutes else 0.0
        target = self._targets[CXMetric.RESOLUTION_TIME]
        snapshot = self._build_snapshot(
            CXMetric.RESOLUTION_TIME, avg, target, segment, lower_is_better=True,
        )
        self._snapshots[CXMetric.RESOLUTION_TIME].append(snapshot)
        return snapshot

    def analyze_repeat_contacts(
        self,
        total_contacts: int,
        repeat_contacts: int,
        segment: str = "all",
    ) -> MetricSnapshot:
        """Calculate repeat contact rate (contacts about the same issue)."""
        rate = (repeat_contacts / total_contacts * 100.0) if total_contacts > 0 else 0.0
        target = self._targets[CXMetric.REPEAT_CONTACT_RATE]
        snapshot = self._build_snapshot(
            CXMetric.REPEAT_CONTACT_RATE, rate, target, segment, lower_is_better=True,
        )
        self._snapshots[CXMetric.REPEAT_CONTACT_RATE].append(snapshot)
        return snapshot

    def calculate_adoption(
        self,
        active_users: int,
        total_seats: int,
        segment: str = "all",
    ) -> MetricSnapshot:
        """Calculate feature/product adoption rate."""
        rate = (active_users / total_seats * 100.0) if total_seats > 0 else 0.0
        target = self._targets[CXMetric.ADOPTION_RATE]
        snapshot = self._build_snapshot(CXMetric.ADOPTION_RATE, rate, target, segment)
        self._snapshots[CXMetric.ADOPTION_RATE].append(snapshot)
        return snapshot

    def calculate_retention(
        self,
        retained: int,
        total: int,
        segment: str = "all",
    ) -> MetricSnapshot:
        """Calculate customer retention rate over a period."""
        rate = (retained / total * 100.0) if total > 0 else 0.0
        target = self._targets[CXMetric.RETENTION_RATE]
        snapshot = self._build_snapshot(CXMetric.RETENTION_RATE, rate, target, segment)
        self._snapshots[CXMetric.RETENTION_RATE].append(snapshot)
        return snapshot

    def calculate_churn(
        self,
        churned: int,
        total_at_start: int,
        segment: str = "all",
    ) -> MetricSnapshot:
        """Calculate churn rate over a period."""
        rate = (churned / total_at_start * 100.0) if total_at_start > 0 else 0.0
        target = self._targets[CXMetric.CHURN_RATE]
        snapshot = self._build_snapshot(
            CXMetric.CHURN_RATE, rate, target, segment, lower_is_better=True,
        )
        self._snapshots[CXMetric.CHURN_RATE].append(snapshot)
        return snapshot

    def monitor_complaints(
        self,
        complaints: int,
        total_interactions: int,
        segment: str = "all",
    ) -> MetricSnapshot:
        """Monitor complaint rate as a percentage of interactions."""
        rate = (complaints / total_interactions * 100.0) if total_interactions > 0 else 0.0
        target = self._targets[CXMetric.COMPLAINT_RATE]
        snapshot = self._build_snapshot(
            CXMetric.COMPLAINT_RATE, rate, target, segment, lower_is_better=True,
        )
        self._snapshots[CXMetric.COMPLAINT_RATE].append(snapshot)
        return snapshot

    def assess_accessibility(
        self,
        accessible_features: int,
        total_features: int,
        segment: str = "all",
    ) -> MetricSnapshot:
        """Calculate accessibility compliance score."""
        rate = (accessible_features / total_features * 100.0) if total_features > 0 else 0.0
        target = self._targets[CXMetric.ACCESSIBILITY_SCORE]
        snapshot = self._build_snapshot(CXMetric.ACCESSIBILITY_SCORE, rate, target, segment)
        self._snapshots[CXMetric.ACCESSIBILITY_SCORE].append(snapshot)
        return snapshot

    def evaluate_trust(
        self,
        positive_signals: int,
        total_signals: int,
        segment: str = "all",
    ) -> MetricSnapshot:
        """Evaluate trust indicator based on positive signal ratio."""
        rate = (positive_signals / total_signals * 100.0) if total_signals > 0 else 0.0
        target = self._targets[CXMetric.TRUST_INDICATOR]
        snapshot = self._build_snapshot(CXMetric.TRUST_INDICATOR, rate, target, segment)
        self._snapshots[CXMetric.TRUST_INDICATOR].append(snapshot)
        return snapshot

    # ------------------------------------------------------------------
    # Dashboard and reporting
    # ------------------------------------------------------------------

    def generate_dashboard(
        self,
        segment: str = "all",
    ) -> Dict[str, Any]:
        """Generate a comprehensive CX metrics dashboard.

        Returns an aggregated view of all metrics with trend analysis,
        target gaps, and health assessment.
        """
        dashboard: Dict[str, Any] = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "segment": segment,
            "metrics": {},
            "total_metrics": 0,
            "overall_health": {},
        }

        total_on_target = 0
        total_metrics = 0
        gaps: List[Dict[str, Any]] = []

        for metric in CXMetric:
            snapshots = [
                s for s in self._snapshots.get(metric, []) if s.segment == segment
            ]
            latest = snapshots[-1] if snapshots else None

            if latest:
                trend = self._compute_trend(metric, segment)
                latest.trend_direction = trend

                dashboard["metrics"][metric.value] = {
                    "value": latest.value,
                    "target": latest.target,
                    "trend": trend.value,
                    "on_target": latest.on_target(),
                    "gap": round(latest.gap_to_target(), 2),
                    "snapshot_count": len(snapshots),
                }

                if latest.on_target():
                    total_on_target += 1
                else:
                    gaps.append({
                        "metric": metric.value,
                        "gap": round(latest.gap_to_target(), 2),
                        "trend": trend.value,
                    })
                total_metrics += 1

        health_pct = (total_on_target / total_metrics * 100.0) if total_metrics > 0 else 0.0

        dashboard["total_metrics"] = total_metrics
        dashboard["overall_health"] = {
            "metrics_on_target": total_on_target,
            "total_metrics": total_metrics,
            "health_percentage": round(health_pct, 1),
            "status": (
                "excellent" if health_pct >= 90 else
                "good" if health_pct >= 70 else
                "needs_attention" if health_pct >= 50 else
                "critical"
            ),
            "top_gaps": sorted(gaps, key=lambda g: abs(g["gap"]), reverse=True)[:5],
        }

        logger.info("Dashboard generated for segment '%s': health=%s", segment, dashboard["overall_health"]["status"])
        return dashboard

    # ------------------------------------------------------------------
    # Trend analysis
    # ------------------------------------------------------------------

    def _compute_trend(self, metric: CXMetric, segment: str) -> TrendDirection:
        """Compute trend direction from historical snapshots."""
        snapshots = [
            s for s in self._snapshots.get(metric, []) if s.segment == segment
        ]
        if len(snapshots) < 2:
            return TrendDirection.UNKNOWN

        # Compare last 2 snapshots
        recent = snapshots[-1].value
        previous = snapshots[-2].value
        lower_is_better = metric in {
            CXMetric.TIME_TO_FIRST_VALUE,
            CXMetric.RESPONSE_TIME,
            CXMetric.RESOLUTION_TIME,
            CXMetric.REPEAT_CONTACT_RATE,
            CXMetric.CHURN_RATE,
            CXMetric.COMPLAINT_RATE,
        }

        if abs(recent - previous) < 0.01:
            return TrendDirection.STABLE

        if lower_is_better:
            return TrendDirection.IMPROVING if recent < previous else TrendDirection.DECLINING
        else:
            return TrendDirection.IMPROVING if recent > previous else TrendDirection.DECLINING

    def _build_snapshot(
        self,
        metric: CXMetric,
        value: float,
        target: float,
        segment: str,
        lower_is_better: bool = False,
    ) -> MetricSnapshot:
        """Build a MetricSnapshot with trend computed."""
        return MetricSnapshot(
            metric_type=metric,
            value=round(value, 2),
            target=target,
            trend_direction=TrendDirection.UNKNOWN,
            segment=segment,
        )

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------

    def get_latest(self, metric: CXMetric, segment: str = "all") -> Optional[MetricSnapshot]:
        snapshots = [s for s in self._snapshots.get(metric, []) if s.segment == segment]
        return snapshots[-1] if snapshots else None

    def get_history(
        self,
        metric: CXMetric,
        segment: str = "all",
        limit: int = 30,
    ) -> List[MetricSnapshot]:
        snapshots = [s for s in self._snapshots.get(metric, []) if s.segment == segment]
        return snapshots[-limit:] if limit > 0 else snapshots

    def clear_history(self, metric: Optional[CXMetric] = None) -> None:
        if metric:
            self._snapshots[metric] = []
        else:
            for m in CXMetric:
                self._snapshots[m] = []
        logger.info("Metric history cleared")