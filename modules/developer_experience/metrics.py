"""
Developer Productivity Metrics
==============================
Enterprise developer productivity and DORA metrics tracking.
Measures and reports on key indicators of developer experience
and delivery performance.

DORA Metrics:
    - Deployment Frequency
    - Lead Time for Changes
    - Change Failure Rate
    - Mean Time to Recovery (MTTR)

Productivity Metrics:
    - Setup Time
    - Build Duration
    - Test Duration
    - PR Cycle Time
    - Documentation Success Rate
    - Developer Satisfaction (eNPS)
    - Rework Rate
    - Defect Escape Rate
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple
import json
import logging
import statistics
import threading
import time
from collections import defaultdict
from contextlib import contextmanager

logger = logging.getLogger(__name__)


class MetricCategory(Enum):
    """Categories of developer productivity metrics."""
    DORA = "dora"
    SPEED = "speed"
    QUALITY = "quality"
    SATISFACTION = "satisfaction"
    EFFICIENCY = "efficiency"


@dataclass
class DXMetric:
    """A single developer experience metric data point."""
    name: str
    category: MetricCategory
    value: float
    unit: str
    timestamp: datetime = field(default_factory=datetime.utcnow)
    team: str = ""
    project: str = ""
    developer_id: str = ""
    tags: Dict[str, str] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "category": self.category.value,
            "value": self.value,
            "unit": self.unit,
            "timestamp": self.timestamp.isoformat(),
            "team": self.team,
            "project": self.project,
            "developer_id": self.developer_id,
            "tags": self.tags,
        }


@dataclass
class DORAMetrics:
    """DORA (DevOps Research and Assessment) metrics for a team/service."""
    team: str
    service: str = ""

    # Deployment Frequency (deploys per day/week)
    deployment_frequency_daily: float = 0.0
    deployment_frequency_weekly: float = 0.0

    # Lead Time for Changes (hours from commit to production)
    lead_time_for_changes_hours: float = 0.0
    lead_time_p50_hours: float = 0.0
    lead_time_p95_hours: float = 0.0

    # Change Failure Rate (percentage of deploys causing failure)
    change_failure_rate_percent: float = 0.0

    # Mean Time to Recovery (minutes)
    mttr_minutes: float = 0.0

    # Time period
    period_start: datetime = field(default_factory=datetime.utcnow)
    period_end: datetime = field(default_factory=datetime.utcnow)

    # Supporting data
    total_deployments: int = 0
    failed_deployments: int = 0
    total_incidents: int = 0
    incident_recovery_times_minutes: List[float] = field(default_factory=list)

    def performance_level(self) -> str:
        """Determine DORA performance level (Elite/High/Medium/Low)."""
        scores = 0

        # Deployment Frequency
        if self.deployment_frequency_daily >= 1:
            scores += 4  # Elite: on-demand (multiple per day)
        elif self.deployment_frequency_weekly >= 1:
            scores += 3  # High: between daily and weekly
        elif self.deployment_frequency_weekly >= 0.25:
            scores += 2  # Medium: between weekly and monthly
        else:
            scores += 1  # Low: monthly or less

        # Lead Time
        if self.lead_time_for_changes_hours < 1:
            scores += 4  # Elite: < 1 hour
        elif self.lead_time_for_changes_hours < 24:
            scores += 3  # High: < 1 day
        elif self.lead_time_for_changes_hours < 168:
            scores += 2  # Medium: < 1 week
        else:
            scores += 1  # Low

        # Change Failure Rate
        if self.change_failure_rate_percent < 5:
            scores += 4  # Elite: 0-5%
        elif self.change_failure_rate_percent < 10:
            scores += 3  # High: 5-10%
        elif self.change_failure_rate_percent < 15:
            scores += 2  # Medium: 10-15%
        else:
            scores += 1  # Low

        # MTTR
        if self.mttr_minutes < 60:       # Elite: < 1 hour
            scores += 4
        elif self.mttr_minutes < 1440:   # High: < 1 day
            scores += 3
        elif self.mttr_minutes < 4320:   # Medium: < 3 days
            scores += 2
        else:
            scores += 1  # Low

        # Classification
        avg = scores / 4.0
        if avg >= 3.5:
            return "Elite"
        elif avg >= 2.5:
            return "High"
        elif avg >= 1.5:
            return "Medium"
        else:
            return "Low"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "team": self.team,
            "service": self.service,
            "performance_level": self.performance_level(),
            "deployment_frequency": {
                "daily": round(self.deployment_frequency_daily, 2),
                "weekly": round(self.deployment_frequency_weekly, 2),
            },
            "lead_time_for_changes": {
                "mean_hours": round(self.lead_time_for_changes_hours, 1),
                "p50_hours": round(self.lead_time_p50_hours, 1),
                "p95_hours": round(self.lead_time_p95_hours, 1),
            },
            "change_failure_rate_percent": round(self.change_failure_rate_percent, 1),
            "mttr_minutes": round(self.mttr_minutes, 1),
            "total_deployments": self.total_deployments,
            "failed_deployments": self.failed_deployments,
            "total_incidents": self.total_incidents,
            "period": {
                "start": self.period_start.isoformat(),
                "end": self.period_end.isoformat(),
            },
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)


# --- Metric Store ---

_metric_store: List[DXMetric] = []
_store_lock = threading.Lock()

# --- Metric Timers (for duration tracking) ---

_timers: Dict[str, float] = {}
_timers_lock = threading.Lock()


def collect_metric(
    name: str,
    value: float,
    unit: str,
    category: MetricCategory,
    team: str = "",
    project: str = "",
    developer_id: str = "",
    tags: Optional[Dict[str, str]] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> DXMetric:
    """Collect a developer experience metric.

    This is the primary metric collection entry point.
    """
    metric = DXMetric(
        name=name,
        category=category,
        value=value,
        unit=unit,
        team=team,
        project=project,
        developer_id=developer_id,
        tags=tags or {},
        metadata=metadata or {},
    )

    with _store_lock:
        _metric_store.append(metric)

    logger.debug(f"Metric collected: {name}={value}{unit} [{category.value}]")
    return metric


def start_timer(name: str) -> str:
    """Start a named timer for duration tracking.

    Returns the timer name for use with stop_timer.
    """
    with _timers_lock:
        timer_id = f"{name}_{time.monotonic()}"
        _timers[timer_id] = time.monotonic()
        return timer_id


def stop_timer(
    timer_id: str,
    metric_name: str,
    category: MetricCategory,
    unit: str = "seconds",
    team: str = "",
    project: str = "",
) -> Optional[DXMetric]:
    """Stop a timer and record the duration as a metric.

    Returns None if the timer ID is not found.
    """
    with _timers_lock:
        start = _timers.pop(timer_id, None)

    if start is None:
        logger.warning(f"Timer not found: {timer_id}")
        return None

    duration = time.monotonic() - start
    return collect_metric(
        name=metric_name,
        value=round(duration, 3),
        unit=unit,
        category=category,
        team=team,
        project=project,
    )


@contextmanager
def timed_metric(
    name: str,
    category: MetricCategory,
    unit: str = "seconds",
    team: str = "",
    project: str = "",
):
    """Context manager for timing a block of code as a metric."""
    timer_id = start_timer(f"{category.value}.{name}")
    try:
        yield
    finally:
        stop_timer(timer_id, name, category, unit, team, project)


# --- Convenience Metric Functions ---

def track_setup_time(
    duration_seconds: float,
    developer_id: str,
    team: str,
    project: str = "",
) -> DXMetric:
    """Track environment setup time for a developer."""
    return collect_metric(
        name="setup_time",
        value=duration_seconds,
        unit="seconds",
        category=MetricCategory.SPEED,
        developer_id=developer_id,
        team=team,
        project=project,
    )


def track_build_duration(
    duration_seconds: float,
    project: str,
    team: str = "",
    commit_sha: str = "",
) -> DXMetric:
    """Track build duration for a project."""
    return collect_metric(
        name="build_duration",
        value=duration_seconds,
        unit="seconds",
        category=MetricCategory.SPEED,
        project=project,
        team=team,
        tags={"commit_sha": commit_sha} if commit_sha else {},
    )


def track_test_duration(
    duration_seconds: float,
    project: str,
    test_type: str = "unit",  # unit, integration, e2e
    team: str = "",
) -> DXMetric:
    """Track test execution duration."""
    return collect_metric(
        name=f"{test_type}_test_duration",
        value=duration_seconds,
        unit="seconds",
        category=MetricCategory.SPEED,
        project=project,
        team=team,
        tags={"test_type": test_type},
    )


def track_deploy_frequency(
    count: int,
    period_hours: float,
    team: str,
    service: str = "",
) -> DXMetric:
    """Track deployment frequency."""
    frequency_daily = count / (period_hours / 24) if period_hours > 0 else 0
    return collect_metric(
        name="deploy_frequency",
        value=frequency_daily,
        unit="deploys_per_day",
        category=MetricCategory.DORA,
        team=team,
        project=service,
        metadata={
            "count": count,
            "period_hours": period_hours,
        },
    )


def track_deploy_success(
    success: bool,
    team: str,
    service: str = "",
    commit_sha: str = "",
) -> DXMetric:
    """Track deployment success/failure."""
    return collect_metric(
        name="deploy_success",
        value=1.0 if success else 0.0,
        unit="boolean",
        category=MetricCategory.DORA,
        team=team,
        project=service,
        tags={"commit_sha": commit_sha, "success": str(success)},
    )


def track_pr_cycle_time(
    duration_hours: float,
    team: str,
    project: str = "",
    pr_id: str = "",
    author_id: str = "",
) -> DXMetric:
    """Track pull request cycle time (open to merge)."""
    return collect_metric(
        name="pr_cycle_time",
        value=duration_hours,
        unit="hours",
        category=MetricCategory.SPEED,
        team=team,
        project=project,
        developer_id=author_id,
        tags={"pr_id": pr_id},
    )


def track_incident_recovery(
    recovery_minutes: float,
    team: str,
    service: str = "",
    incident_id: str = "",
) -> DXMetric:
    """Track incident recovery time (MTTR)."""
    return collect_metric(
        name="mttr",
        value=recovery_minutes,
        unit="minutes",
        category=MetricCategory.DORA,
        team=team,
        project=service,
        tags={"incident_id": incident_id},
    )


def track_developer_satisfaction(
    score: float,  # 0-10 (eNPS scale)
    developer_id: str,
    team: str,
    survey_id: str = "",
) -> DXMetric:
    """Track developer satisfaction (eNPS survey)."""
    return collect_metric(
        name="developer_satisfaction",
        value=score,
        unit="score_0_10",
        category=MetricCategory.SATISFACTION,
        developer_id=developer_id,
        team=team,
        tags={"survey_id": survey_id},
    )


def track_rework_rate(
    rework_count: int,
    total_prs: int,
    team: str,
    project: str = "",
) -> DXMetric:
    """Track code rework rate (PRs requiring significant revision)."""
    rate = (rework_count / total_prs * 100) if total_prs > 0 else 0
    return collect_metric(
        name="rework_rate",
        value=rate,
        unit="percent",
        category=MetricCategory.QUALITY,
        team=team,
        project=project,
        metadata={"rework_count": rework_count, "total_prs": total_prs},
    )


def track_defect_escape_rate(
    escaped_defects: int,
    total_defects: int,
    team: str,
    project: str = "",
) -> DXMetric:
    """Track defect escape rate (bugs found in production vs. total)."""
    rate = (escaped_defects / total_defects * 100) if total_defects > 0 else 0
    return collect_metric(
        name="defect_escape_rate",
        value=rate,
        unit="percent",
        category=MetricCategory.QUALITY,
        team=team,
        project=project,
        metadata={"escaped_defects": escaped_defects, "total_defects": total_defects},
    )


def track_documentation_success_rate(
    successful_docs: int,
    total_docs: int,
    team: str,
    project: str = "",
) -> DXMetric:
    """Track documentation quality success rate."""
    rate = (successful_docs / total_docs * 100) if total_docs > 0 else 0
    return collect_metric(
        name="documentation_success_rate",
        value=rate,
        unit="percent",
        category=MetricCategory.QUALITY,
        team=team,
        project=project,
    )


# --- Query and Reporting ---

def get_metrics_by_name(
    name: str,
    since: Optional[datetime] = None,
    team: Optional[str] = None,
) -> List[DXMetric]:
    """Query metrics by name with optional filters."""
    with _store_lock:
        metrics = _metric_store

    if name:
        metrics = [m for m in metrics if m.name == name]
    if since:
        metrics = [m for m in metrics if m.timestamp >= since]
    if team:
        metrics = [m for m in metrics if m.team == team]

    return sorted(metrics, key=lambda m: m.timestamp)


def get_metrics_by_category(
    category: MetricCategory,
    since: Optional[datetime] = None,
) -> List[DXMetric]:
    """Query metrics by category."""
    with _store_lock:
        metrics = _metric_store

    metrics = [m for m in metrics if m.category == category]
    if since:
        metrics = [m for m in metrics if m.timestamp >= since]

    return sorted(metrics, key=lambda m: m.timestamp)


def calculate_dora_metrics(
    team: str,
    service: str = "",
    since: Optional[datetime] = None,
    until: Optional[datetime] = None,
) -> DORAMetrics:
    """Calculate DORA metrics for a team/service from collected data."""
    metrics = get_metrics_by_name("deploy_success", since=since, team=team)
    if service:
        metrics = [m for m in metrics if m.project == service]

    if until:
        metrics = [m for m in metrics if m.timestamp <= until]

    dora = DORAMetrics(
        team=team,
        service=service,
        period_start=since or datetime.utcnow(),
        period_end=until or datetime.utcnow(),
    )

    if not metrics:
        return dora

    total_deploys = len(metrics)
    failed_deploys = sum(1 for m in metrics if m.value == 0)

    dora.total_deployments = total_deploys
    dora.failed_deployments = failed_deploys

    if total_deploys > 0:
        # Deployment frequency
        if metrics:
            time_span_hours = (
                (metrics[-1].timestamp - metrics[0].timestamp).total_seconds() / 3600
            )
            if time_span_hours > 0:
                dora.deployment_frequency_daily = total_deploys / (time_span_hours / 24)
                dora.deployment_frequency_weekly = dora.deployment_frequency_daily * 7

        # Change failure rate
        dora.change_failure_rate_percent = (failed_deploys / total_deploys) * 100

    # MTTR from incident recovery metrics
    mttr_metrics = get_metrics_by_name("mttr", since=since, team=team)
    if service:
        mttr_metrics = [m for m in mttr_metrics if m.project == service]

    recovery_times = [m.value for m in mttr_metrics]
    if recovery_times:
        dora.total_incidents = len(recovery_times)
        dora.incident_recovery_times_minutes = recovery_times
        dora.mttr_minutes = statistics.mean(recovery_times)

    return dora


def get_metrics_dashboard(team: str = "") -> Dict[str, Any]:
    """Generate a metrics dashboard snapshot."""
    now = datetime.utcnow()
    last_30_days = now - timedelta(days=30)

    with _store_lock:
        all_metrics = list(_metric_store)

    if team:
        all_metrics = [m for m in all_metrics if m.team == team]

    recent = [m for m in all_metrics if m.timestamp >= last_30_days]

    # Aggregate by name
    by_name: Dict[str, List[float]] = defaultdict(list)
    for m in recent:
        by_name[m.name].append(m.value)

    aggregates = {}
    for name, values in by_name.items():
        if values:
            aggregates[name] = {
                "count": len(values),
                "mean": round(statistics.mean(values), 2),
                "median": round(statistics.median(values), 2),
                "min": round(min(values), 2),
                "max": round(max(values), 2),
            }
            if len(values) > 1:
                aggregates[name]["stdev"] = round(statistics.stdev(values), 2)

    # Developer satisfaction
    satisfaction = [m.value for m in recent if m.name == "developer_satisfaction"]
    enps = None
    if satisfaction:
        avg = statistics.mean(satisfaction)
        promoters = sum(1 for s in satisfaction if s >= 9)
        detractors = sum(1 for s in satisfaction if s <= 6)
        total = len(satisfaction)
        if total > 0:
            enps = round(((promoters - detractors) / total) * 100, 1)

    return {
        "team": team or "all",
        "period": "last_30_days",
        "generated_at": now.isoformat(),
        "total_metrics_collected": len(all_metrics),
        "recent_metrics": len(recent),
        "aggregates": aggregates,
        "developer_enps": enps,
    }


def generate_metrics_report(
    team: str = "",
    output_format: str = "json",
) -> str:
    """Generate a comprehensive metrics report.

    Args:
        team: Optional team filter.
        output_format: 'json', 'summary', or 'dora'.

    Returns:
        Formatted report string.
    """
    if output_format == "dora":
        dora = calculate_dora_metrics(team=team)
        return dora.to_json()

    dashboard = get_metrics_dashboard(team=team)

    if output_format == "summary":
        lines = [
            f"Developer Productivity Metrics: {team or 'All Teams'}",
            f"  Period: {dashboard['period']}",
            f"  Total Metrics: {dashboard['total_metrics_collected']}",
            f"  Recent (30d): {dashboard['recent_metrics']}",
        ]
        if dashboard.get("developer_enps") is not None:
            lines.append(f"  Developer eNPS: {dashboard['developer_enps']}")
        lines.append("  Key Metrics:")
        for name, agg in dashboard.get("aggregates", {}).items():
            lines.append(
                f"    {name}: mean={agg['mean']}, median={agg['median']}, "
                f"n={agg['count']}"
            )
        return "\n".join(lines)

    # JSON format (default)
    dora = calculate_dora_metrics(team=team)
    dashboard["dora"] = dora.to_dict()
    return json.dumps(dashboard, indent=2)


def clear_metrics() -> int:
    """Clear all stored metrics. Returns count of cleared metrics."""
    with _store_lock:
        count = len(_metric_store)
        _metric_store.clear()
    return count


def get_metric_count() -> int:
    """Get total number of stored metrics."""
    with _store_lock:
        return len(_metric_store)