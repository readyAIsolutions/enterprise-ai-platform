"""
Billing Tracker - Usage tracking, metering, and billing reports.

Provides BillingTracker for tracking tenant resource usage (API calls,
tokens, storage), metering consumption, generating billing reports,
and firing usage alerts when thresholds are exceeded.
"""

from __future__ import annotations

import csv
import io
import threading
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum, auto
from typing import Any, Callable, Dict, List, Optional, Tuple


class UsageAlert(Enum):
    """Types of usage alerts."""

    WARNING = auto()
    """Approaching threshold but not yet exceeded."""

    CRITICAL = auto()
    """Threshold exceeded."""

    QUOTA_EXCEEDED = auto()
    """Hard quota limit reached."""


@dataclass
class UsageRecord:
    """A single usage event record.

    Attributes:
        record_id: Unique record identifier.
        tenant_id: Tenant consuming the resource.
        timestamp: When the usage occurred.
        metric: What was consumed (api_call, token, storage_byte, etc.).
        quantity: Amount consumed.
        resource_details: Optional context about the consumption.
        cost: Calculated cost for this usage event.
    """

    record_id: str
    tenant_id: str
    timestamp: datetime
    metric: str
    quantity: float
    resource_details: Dict[str, Any] = field(default_factory=dict)
    cost: float = 0.0


@dataclass
class BillingReport:
    """Generated billing report for a tenant over a period.

    Attributes:
        report_id: Unique report identifier.
        tenant_id: Tenant this report covers.
        period_start: Start of the billing period.
        period_end: End of the billing period.
        generated_at: When the report was generated.
        metrics: Breakdown of usage by metric type.
        total_cost: Total cost across all metrics.
        line_items: Detailed line items.
    """

    report_id: str
    tenant_id: str
    period_start: datetime
    period_end: datetime
    generated_at: datetime = field(default_factory=datetime.utcnow)
    metrics: Dict[str, Dict[str, float]] = field(default_factory=dict)
    total_cost: float = 0.0
    line_items: List[str] = field(default_factory=list)


@dataclass
class UsageThreshold:
    """Threshold configuration for firing usage alerts.

    Attributes:
        threshold_id: Unique threshold identifier.
        tenant_id: Tenant this threshold applies to.
        metric: Metric to monitor.
        warning_percent: Percentage of limit to trigger WARNING.
        critical_percent: Percentage of limit to trigger CRITICAL.
        absolute_limit: Hard limit for the metric in the period.
        period_days: Number of days in the monitoring period.
    """

    threshold_id: str
    tenant_id: str
    metric: str
    warning_percent: float = 80.0
    critical_percent: float = 95.0
    absolute_limit: float = 0.0
    period_days: int = 30


class MeteringEngine:
    """Calculates costs from usage records based on configurable rates.

    Attributes:
        _rates: Pricing rates per metric (unit price).
    """

    def __init__(self) -> None:
        """Initialize with default pricing rates."""
        self._rates: Dict[str, float] = {
            "api_call": 0.0001,       # $0.0001 per API call
            "token_input": 0.000003,  # $3 per 1M input tokens
            "token_output": 0.000015, # $15 per 1M output tokens
            "storage_gb_hour": 0.00003,  # ~$0.022/GB/month
            "compute_hour": 0.05,     # $0.05 per compute hour
            "user_seat": 10.0,        # $10 per user per month
        }

    def set_rate(self, metric: str, rate: float) -> None:
        """Set the unit price for a metric.

        Args:
            metric: Metric name.
            rate: Cost per unit.
        """
        self._rates[metric] = rate

    def get_rate(self, metric: str) -> float:
        """Get the unit price for a metric.

        Args:
            metric: Metric name.

        Returns:
            Unit price; 0.0 if metric has no rate defined.
        """
        return self._rates.get(metric, 0.0)

    def calculate_cost(self, metric: str, quantity: float) -> float:
        """Calculate cost for a given quantity of a metric.

        Args:
            metric: Metric name.
            quantity: Amount consumed.

        Returns:
            Calculated cost.
        """
        return self._rates.get(metric, 0.0) * quantity

    def calculate_record_cost(self, record: UsageRecord) -> float:
        """Calculate the cost for a usage record.

        Args:
            record: Usage record to price.

        Returns:
            Calculated cost.
        """
        return self.calculate_cost(record.metric, record.quantity)


class BillingTracker:
    """Tracks tenant usage and generates billing reports.

    Provides:
    - Usage event recording with cost calculation
    - Usage aggregation by tenant, metric, and time period
    - Billing report generation (summary and detailed)
    - CSV export of billing data
    - Threshold-based usage alerts
    - Usage trend analysis

    Attributes:
        _records: All usage records.
        _tenant_records: Index of records by tenant.
        _thresholds: Per-tenant usage thresholds.
        _metering: Metering engine for cost calculation.
        _alert_callbacks: Registered alert handlers.
        _lock: Thread safety lock.
    """

    def __init__(self, metering: Optional[MeteringEngine] = None) -> None:
        """Initialize the billing tracker.

        Args:
            metering: Optional custom metering engine.
        """
        self._records: Dict[str, UsageRecord] = {}
        self._tenant_records: Dict[str, List[str]] = defaultdict(list)
        self._thresholds: Dict[str, UsageThreshold] = {}
        self._metering = metering or MeteringEngine()
        self._alert_callbacks: Dict[UsageAlert, List[Callable[..., Any]]] = defaultdict(list)
        self._lock = threading.RLock()
        self._record_counter = 0

    # ------------------------------------------------------------------
    # Usage Tracking
    # ------------------------------------------------------------------

    def record_usage(
        self,
        tenant_id: str,
        metric: str,
        quantity: float,
        resource_details: Optional[Dict[str, Any]] = None,
    ) -> UsageRecord:
        """Record a usage event for a tenant.

        Automatically calculates the cost using the metering engine
        and checks thresholds for alert conditions.

        Args:
            tenant_id: Tenant consuming the resource.
            metric: What was consumed.
            quantity: Amount consumed.
            resource_details: Optional context.

        Returns:
            The created UsageRecord.
        """
        with self._lock:
            self._record_counter += 1
            record_id = f"rec_{self._record_counter:010d}"

            record = UsageRecord(
                record_id=record_id,
                tenant_id=tenant_id,
                timestamp=datetime.utcnow(),
                metric=metric,
                quantity=quantity,
                resource_details=resource_details or {},
            )

            # Calculate cost
            record.cost = self._metering.calculate_record_cost(record)

            # Store
            self._records[record_id] = record
            self._tenant_records[tenant_id].append(record_id)

            # Check thresholds
            self._check_thresholds(tenant_id)

            return record

    def get_usage(
        self,
        tenant_id: str,
        metric: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> List[UsageRecord]:
        """Query usage records for a tenant with optional filters.

        Args:
            tenant_id: Tenant to query.
            metric: Filter by metric type.
            start_time: Filter records after this time.
            end_time: Filter records before this time.

        Returns:
            List of matching usage records.
        """
        with self._lock:
            record_ids = self._tenant_records.get(tenant_id, [])
            records = [self._records[rid] for rid in record_ids if rid in self._records]

            if metric:
                records = [r for r in records if r.metric == metric]
            if start_time:
                records = [r for r in records if r.timestamp >= start_time]
            if end_time:
                records = [r for r in records if r.timestamp <= end_time]

            return records

    def get_usage_summary(
        self,
        tenant_id: str,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> Dict[str, Dict[str, float]]:
        """Get aggregated usage summary for a tenant.

        Args:
            tenant_id: Tenant to query.
            start_time: Period start.
            end_time: Period end.

        Returns:
            Dictionary mapping metric -> {"quantity": float, "cost": float}.
        """
        records = self.get_usage(tenant_id, start_time=start_time, end_time=end_time)

        summary: Dict[str, Dict[str, float]] = defaultdict(
            lambda: {"quantity": 0.0, "cost": 0.0}
        )

        for record in records:
            summary[record.metric]["quantity"] += record.quantity
            summary[record.metric]["cost"] += record.cost

        return dict(summary)

    def get_total_cost(
        self,
        tenant_id: str,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> float:
        """Get total cost for a tenant over a period.

        Args:
            tenant_id: Tenant to query.
            start_time: Period start.
            end_time: Period end.

        Returns:
            Total cost in currency units.
        """
        records = self.get_usage(tenant_id, start_time=start_time, end_time=end_time)
        return sum(r.cost for r in records)

    # ------------------------------------------------------------------
    # Billing Reports
    # ------------------------------------------------------------------

    def generate_report(
        self,
        tenant_id: str,
        period_start: datetime,
        period_end: datetime,
    ) -> BillingReport:
        """Generate a detailed billing report for a tenant over a period.

        Args:
            tenant_id: Tenant to report on.
            period_start: Start of billing period.
            period_end: End of billing period.

        Returns:
            Complete BillingReport.
        """
        with self._lock:
            report_id = f"rpt_{tenant_id}_{period_start.strftime('%Y%m%d')}"

            records = self.get_usage(
                tenant_id, start_time=period_start, end_time=period_end
            )

            # Aggregate metrics
            metrics: Dict[str, Dict[str, float]] = defaultdict(
                lambda: {"quantity": 0.0, "cost": 0.0, "count": 0.0}
            )
            total_cost = 0.0
            line_items: List[str] = []

            for record in records:
                m = metrics[record.metric]
                m["quantity"] += record.quantity
                m["cost"] += record.cost
                m["count"] += 1
                total_cost += record.cost

                line_items.append(
                    f"{record.timestamp.isoformat()} | {record.metric} | "
                    f"qty={record.quantity} | cost=${record.cost:.6f}"
                )

            report = BillingReport(
                report_id=report_id,
                tenant_id=tenant_id,
                period_start=period_start,
                period_end=period_end,
                metrics=dict(metrics),
                total_cost=total_cost,
                line_items=line_items,
            )

            return report

    def generate_report_csv(
        self,
        tenant_id: str,
        period_start: datetime,
        period_end: datetime,
    ) -> str:
        """Generate a billing report in CSV format.

        Args:
            tenant_id: Tenant to report on.
            period_start: Start of billing period.
            period_end: End of billing period.

        Returns:
            CSV-formatted string with header row.
        """
        report = self.generate_report(tenant_id, period_start, period_end)

        output = io.StringIO()
        writer = csv.writer(output)

        # Header
        writer.writerow(
            [
                "Report ID",
                "Tenant ID",
                "Period Start",
                "Period End",
                "Total Cost",
            ]
        )
        writer.writerow(
            [
                report.report_id,
                report.tenant_id,
                report.period_start.isoformat(),
                report.period_end.isoformat(),
                f"${report.total_cost:.4f}",
            ]
        )
        writer.writerow([])  # blank row

        # Metrics summary
        writer.writerow(["Metric", "Quantity", "Event Count", "Cost"])
        for metric_name, data in report.metrics.items():
            writer.writerow(
                [
                    metric_name,
                    f"{data['quantity']:.2f}",
                    f"{data['count']:.0f}",
                    f"${data['cost']:.4f}",
                ]
            )
        writer.writerow([])

        # Line items
        writer.writerow(["Timestamp", "Metric", "Quantity", "Cost"])
        for item in report.line_items:
            parts = item.split(" | ")
            writer.writerow(parts)

        return output.getvalue()

    def get_all_tenant_costs(
        self,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> Dict[str, float]:
        """Get total costs for all tenants.

        Args:
            start_time: Period start.
            end_time: Period end.

        Returns:
            Dictionary mapping tenant_id -> total_cost.
        """
        with self._lock:
            costs: Dict[str, float] = defaultdict(float)
            for tenant_id in self._tenant_records:
                costs[tenant_id] = self.get_total_cost(
                    tenant_id, start_time, end_time
                )
            return dict(costs)

    # ------------------------------------------------------------------
    # Usage Alerts
    # ------------------------------------------------------------------

    def set_threshold(
        self,
        tenant_id: str,
        metric: str,
        absolute_limit: float,
        warning_percent: float = 80.0,
        critical_percent: float = 95.0,
        period_days: int = 30,
    ) -> UsageThreshold:
        """Configure a usage threshold for alerting.

        Args:
            tenant_id: Tenant to monitor.
            metric: Metric to track.
            absolute_limit: Hard limit for the period.
            warning_percent: Percentage for WARNING alert.
            critical_percent: Percentage for CRITICAL alert.
            period_days: Monitoring window in days.

        Returns:
            The created UsageThreshold.
        """
        threshold_id = f"thresh_{tenant_id}_{metric}"
        threshold = UsageThreshold(
            threshold_id=threshold_id,
            tenant_id=tenant_id,
            metric=metric,
            warning_percent=warning_percent,
            critical_percent=critical_percent,
            absolute_limit=absolute_limit,
            period_days=period_days,
        )

        with self._lock:
            self._thresholds[threshold_id] = threshold

        return threshold

    def remove_threshold(self, threshold_id: str) -> bool:
        """Remove a usage threshold.

        Args:
            threshold_id: Threshold to remove.

        Returns:
            True if removed, False if not found.
        """
        with self._lock:
            if threshold_id in self._thresholds:
                del self._thresholds[threshold_id]
                return True
            return False

    def get_thresholds(self, tenant_id: str) -> List[UsageThreshold]:
        """Get all thresholds for a tenant.

        Args:
            tenant_id: Tenant to query.

        Returns:
            List of thresholds.
        """
        with self._lock:
            return [
                t for t in self._thresholds.values() if t.tenant_id == tenant_id
            ]

    def check_thresholds(self, tenant_id: str) -> List[Tuple[UsageAlert, UsageThreshold, float]]:
        """Check all thresholds for a tenant and return triggered alerts.

        Args:
            tenant_id: Tenant to check.

        Returns:
            List of (alert_level, threshold, current_usage) tuples for
            triggered thresholds.
        """
        with self._lock:
            triggered: List[Tuple[UsageAlert, UsageThreshold, float]] = []
            now = datetime.utcnow()
            period_start = now - timedelta(days=30)  # default 30-day window

            for threshold in self._thresholds.values():
                if threshold.tenant_id != tenant_id:
                    continue

                # Get usage for this metric in the threshold period
                metric_start = now - timedelta(days=threshold.period_days)
                records = self.get_usage(
                    tenant_id,
                    metric=threshold.metric,
                    start_time=metric_start,
                    end_time=now,
                )
                current_usage = sum(r.quantity for r in records)

                if threshold.absolute_limit > 0:
                    pct = (current_usage / threshold.absolute_limit) * 100

                    if pct >= 100:
                        triggered.append(
                            (UsageAlert.QUOTA_EXCEEDED, threshold, current_usage)
                        )
                    elif pct >= threshold.critical_percent:
                        triggered.append(
                            (UsageAlert.CRITICAL, threshold, current_usage)
                        )
                    elif pct >= threshold.warning_percent:
                        triggered.append(
                            (UsageAlert.WARNING, threshold, current_usage)
                        )

            return triggered

    def on_alert(
        self, alert_type: UsageAlert, callback: Callable[..., Any]
    ) -> None:
        """Register a callback for usage alerts.

        Args:
            alert_type: Alert type to listen for.
            callback: Function to call when alert fires.
                      Receives (tenant_id, threshold, current_usage).
        """
        self._alert_callbacks[alert_type].append(callback)

    def off_alert(
        self, alert_type: UsageAlert, callback: Callable[..., Any]
    ) -> None:
        """Remove a previously registered alert callback.

        Args:
            alert_type: Alert type.
            callback: The callback to remove.
        """
        if alert_type in self._alert_callbacks:
            self._alert_callbacks[alert_type] = [
                cb
                for cb in self._alert_callbacks[alert_type]
                if cb is not callback
            ]

    # ------------------------------------------------------------------
    # Usage Analytics
    # ------------------------------------------------------------------

    def get_usage_trend(
        self,
        tenant_id: str,
        metric: str,
        days: int = 30,
        interval: str = "day",
    ) -> List[Dict[str, Any]]:
        """Get usage trend data over time.

        Args:
            tenant_id: Tenant to analyze.
            metric: Metric to track.
            days: Number of days to look back.
            interval: Aggregation interval ('day' or 'hour').

        Returns:
            List of {timestamp, quantity, cost} dictionaries.
        """
        now = datetime.utcnow()
        start = now - timedelta(days=days)

        records = self.get_usage(
            tenant_id, metric=metric, start_time=start, end_time=now
        )

        # Group by interval
        buckets: Dict[str, Dict[str, float]] = defaultdict(
            lambda: {"quantity": 0.0, "cost": 0.0}
        )

        for record in records:
            if interval == "hour":
                key = record.timestamp.strftime("%Y-%m-%dT%H:00")
            else:
                key = record.timestamp.strftime("%Y-%m-%d")

            buckets[key]["quantity"] += record.quantity
            buckets[key]["cost"] += record.cost

        # Sort chronologically
        sorted_keys = sorted(buckets.keys())
        return [
            {
                "timestamp": key,
                "quantity": buckets[key]["quantity"],
                "cost": buckets[key]["cost"],
            }
            for key in sorted_keys
        ]

    def get_top_tenants_by_cost(
        self, limit: int = 10, days: int = 30
    ) -> List[Tuple[str, float]]:
        """Get top spending tenants.

        Args:
            limit: Maximum number of tenants to return.
            days: Look-back period in days.

        Returns:
            Sorted list of (tenant_id, cost) tuples.
        """
        start = datetime.utcnow() - timedelta(days=days)
        costs = self.get_all_tenant_costs(start_time=start)
        sorted_costs = sorted(costs.items(), key=lambda x: x[1], reverse=True)
        return sorted_costs[:limit]

    # ------------------------------------------------------------------
    # Internal Helpers
    # ------------------------------------------------------------------

    def _check_thresholds(self, tenant_id: str) -> None:
        """Internal: check thresholds and fire alerts.

        Called automatically after each usage recording.

        Args:
            tenant_id: Tenant to check.
        """
        triggered = self.check_thresholds(tenant_id)
        for alert_type, threshold, current_usage in triggered:
            for callback in self._alert_callbacks.get(alert_type, []):
                try:
                    callback(tenant_id, threshold, current_usage)
                except Exception:
                    pass

    def cleanup(self) -> None:
        """Reset all billing state."""
        with self._lock:
            self._records.clear()
            self._tenant_records.clear()
            self._thresholds.clear()
            self._alert_callbacks.clear()
            self._record_counter = 0