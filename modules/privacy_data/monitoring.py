"""
Privacy & Data Governance Monitoring
Monitors: Unauthorized access, Data leakage, Data drift,
  Schema changes, Compliance violations, Privacy violations,
  Missing backups, Storage utilization, AI knowledge freshness,
  Data quality degradation
"""
from __future__ import annotations

import hashlib
import json
import uuid
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set, Tuple, Union


# ─── Alert Severity ───────────────────────────────────────────────────────────

class AlertSeverity(str, Enum):
    """Alert severity levels."""
    INFO = "info"
    WARNING = "warning"
    HIGH = "high"
    CRITICAL = "critical"


class MonitorCategory(str, Enum):
    """Monitoring categories."""
    ACCESS_CONTROL = "access_control"
    DATA_LEAKAGE = "data_leakage"
    DATA_DRIFT = "data_drift"
    SCHEMA_CHANGE = "schema_change"
    COMPLIANCE = "compliance"
    PRIVACY = "privacy"
    BACKUP = "backup"
    STORAGE = "storage"
    AI_KNOWLEDGE = "ai_knowledge"
    DATA_QUALITY = "data_quality"
    ENCRYPTION = "encryption"
    RETENTION = "retention"
    CONSENT = "consent"


# ─── Alert Definition ─────────────────────────────────────────────────────────

@dataclass
class MonitorAlert:
    """A monitoring alert."""
    alert_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    category: MonitorCategory = MonitorCategory.DATA_QUALITY
    severity: AlertSeverity = AlertSeverity.INFO
    title: str = ""
    description: str = ""
    source: str = ""
    triggered_at: datetime = field(default_factory=datetime.utcnow)
    resolved_at: Optional[datetime] = None
    is_resolved: bool = False
    resolution_notes: str = ""
    affected_resources: List[str] = field(default_factory=list)
    metrics: Dict[str, Any] = field(default_factory=dict)
    suggested_actions: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    alert_hash: str = ""  # For deduplication

    def compute_hash(self) -> str:
        payload = f"{self.category.value}|{self.title}|{self.source}"
        return hashlib.md5(payload.encode()).hexdigest()

    def resolve(self, notes: str = "") -> None:
        self.is_resolved = True
        self.resolved_at = datetime.utcnow()
        self.resolution_notes = notes

    @property
    def age_minutes(self) -> float:
        return (datetime.utcnow() - self.triggered_at).total_seconds() / 60

    def to_dict(self) -> Dict[str, Any]:
        return {
            "alert_id": self.alert_id,
            "category": self.category.value,
            "severity": self.severity.value,
            "title": self.title,
            "description": self.description,
            "source": self.source,
            "triggered_at": self.triggered_at.isoformat(),
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
            "is_resolved": self.is_resolved,
            "age_minutes": round(self.age_minutes, 1),
            "suggested_actions": self.suggested_actions,
        }


# ─── Metric Snapshot ──────────────────────────────────────────────────────────

@dataclass
class MetricSnapshot:
    """A point-in-time snapshot of a monitored metric."""
    snapshot_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    category: MonitorCategory = MonitorCategory.DATA_QUALITY
    metric_name: str = ""
    value: float = 0.0
    unit: str = ""
    threshold_warning: Optional[float] = None
    threshold_critical: Optional[float] = None
    taken_at: datetime = field(default_factory=datetime.utcnow)
    source: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def status(self) -> str:
        if self.threshold_critical is not None and self._exceeds(self.threshold_critical):
            return "critical"
        if self.threshold_warning is not None and self._exceeds(self.threshold_warning):
            return "warning"
        return "ok"

    def _exceeds(self, threshold: float) -> bool:
        """Check if value exceeds threshold (higher is worse)."""
        return self.value > threshold

    def to_dict(self) -> Dict[str, Any]:
        return {
            "metric_name": self.metric_name,
            "value": self.value,
            "unit": self.unit,
            "status": self.status,
            "threshold_warning": self.threshold_warning,
            "threshold_critical": self.threshold_critical,
            "taken_at": self.taken_at.isoformat(),
        }


# ─── Access Event ─────────────────────────────────────────────────────────────

@dataclass
class AccessEvent:
    """Record of a data access event."""
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    actor: str = ""
    resource: str = ""
    action: str = ""  # read, write, delete, admin, export
    timestamp: datetime = field(default_factory=datetime.utcnow)
    ip_address: str = ""
    user_agent: str = ""
    is_authorized: bool = True
    is_suspicious: bool = False
    suspicion_reasons: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


# ─── Monitor Rule ─────────────────────────────────────────────────────────────

@dataclass
class MonitorRule:
    """A monitoring rule that triggers alerts based on conditions."""
    rule_id: str
    name: str
    category: MonitorCategory
    description: str = ""
    severity: AlertSeverity = AlertSeverity.WARNING
    condition: Optional[Callable[[Dict[str, Any]], Tuple[bool, str]]] = None
    cooldown_minutes: int = 15  # Minimum time between re-triggers
    enabled: bool = True


# ─── Main Monitor ─────────────────────────────────────────────────────────────

class PrivacyMonitor:
    """
    Privacy & Data Governance Monitor.

    Continuously monitors for:
      - Unauthorized access attempts
      - Data leakage indicators
      - Data drift and schema changes
      - Compliance violations
      - Privacy violations
      - Missing/failed backups
      - Storage utilization
      - AI knowledge freshness
      - Data quality degradation
    """

    def __init__(self):
        self._alerts: Dict[str, MonitorAlert] = {}
        self._resolved_alerts: List[MonitorAlert] = []
        self._snapshots: List[MetricSnapshot] = []
        self._access_events: List[AccessEvent] = []
        self._rules: Dict[str, MonitorRule] = {}
        self._last_triggered: Dict[str, datetime] = {}  # rule_id -> last triggered
        self._alert_dedup: Set[str] = set()  # alert hashes
        self._setup_default_rules()

    def _setup_default_rules(self) -> None:
        """Initialize default monitoring rules."""
        rules = [
            MonitorRule("M001", "Unauthorized Access Detected",
                       MonitorCategory.ACCESS_CONTROL, AlertSeverity.CRITICAL,
                       "Detect unauthorized access attempts", cooldown_minutes=5),
            MonitorRule("M002", "Data Leakage Detected",
                       MonitorCategory.DATA_LEAKAGE, AlertSeverity.CRITICAL,
                       "Detect potential data exfiltration", cooldown_minutes=5),
            MonitorRule("M003", "Data Drift Detected",
                       MonitorCategory.DATA_DRIFT, AlertSeverity.WARNING,
                       "Statistical distribution changes", cooldown_minutes=60),
            MonitorRule("M004", "Schema Change Detected",
                       MonitorCategory.SCHEMA_CHANGE, AlertSeverity.HIGH,
                       "Unauthorized or unexpected schema changes", cooldown_minutes=30),
            MonitorRule("M005", "Compliance Violation",
                       MonitorCategory.COMPLIANCE, AlertSeverity.CRITICAL,
                       "Regulatory compliance violations", cooldown_minutes=15),
            MonitorRule("M006", "Privacy Violation",
                       MonitorCategory.PRIVACY, AlertSeverity.CRITICAL,
                       "Privacy policy or consent violations", cooldown_minutes=15),
            MonitorRule("M007", "Backup Missing/Failed",
                       MonitorCategory.BACKUP, AlertSeverity.HIGH,
                       "Scheduled backups not completed", cooldown_minutes=120),
            MonitorRule("M008", "Storage Utilization High",
                       MonitorCategory.STORAGE, AlertSeverity.WARNING,
                       "Storage usage exceeding thresholds", cooldown_minutes=60),
            MonitorRule("M009", "AI Knowledge Stale",
                       MonitorCategory.AI_KNOWLEDGE, AlertSeverity.WARNING,
                       "AI knowledge/embeddings past freshness threshold", cooldown_minutes=120),
            MonitorRule("M010", "Data Quality Degradation",
                       MonitorCategory.DATA_QUALITY, AlertSeverity.HIGH,
                       "Overall data quality score dropping", cooldown_minutes=30),
            MonitorRule("M011", "Encryption Key Rotation Overdue",
                       MonitorCategory.ENCRYPTION, AlertSeverity.HIGH,
                       "Encryption keys past rotation schedule", cooldown_minutes=120),
            MonitorRule("M012", "Retention Policy Violation",
                       MonitorCategory.RETENTION, AlertSeverity.HIGH,
                       "Data past retention period not deleted", cooldown_minutes=240),
            MonitorRule("M013", "Consent Violation",
                       MonitorCategory.CONSENT, AlertSeverity.CRITICAL,
                       "Processing without valid consent", cooldown_minutes=15),
        ]
        for rule in rules:
            self._rules[rule.rule_id] = rule

    # ── Alert Management ──────────────────────────────────────────────────

    def raise_alert(
        self,
        category: MonitorCategory,
        severity: AlertSeverity,
        title: str,
        description: str,
        source: str = "",
        affected_resources: Optional[List[str]] = None,
        metrics: Optional[Dict[str, Any]] = None,
        suggested_actions: Optional[List[str]] = None,
        rule_id: Optional[str] = None,
    ) -> Optional[MonitorAlert]:
        """Raise a monitoring alert with deduplication."""
        alert = MonitorAlert(
            category=category,
            severity=severity,
            title=title,
            description=description,
            source=source,
            affected_resources=affected_resources or [],
            metrics=metrics or {},
            suggested_actions=suggested_actions or [],
        )
        alert.alert_hash = alert.compute_hash()

        # Deduplication check
        if alert.alert_hash in self._alert_dedup:
            # Check cooldown
            if rule_id and rule_id in self._last_triggered:
                rule = self._rules.get(rule_id)
                if rule:
                    elapsed = (datetime.utcnow() - self._last_triggered[rule_id]).total_seconds() / 60
                    if elapsed < rule.cooldown_minutes:
                        return None  # Still in cooldown

        self._alert_dedup.add(alert.alert_hash)
        self._alerts[alert.alert_id] = alert
        if rule_id:
            self._last_triggered[rule_id] = datetime.utcnow()
        return alert

    def resolve_alert(self, alert_id: str, notes: str = "") -> bool:
        """Resolve an alert."""
        alert = self._alerts.pop(alert_id, None)
        if alert:
            alert.resolve(notes)
            self._resolved_alerts.append(alert)
            return True
        return False

    def get_active_alerts(
        self,
        category: Optional[MonitorCategory] = None,
        severity: Optional[AlertSeverity] = None,
    ) -> List[MonitorAlert]:
        """Get active (unresolved) alerts with optional filters."""
        alerts = list(self._alerts.values())
        if category:
            alerts = [a for a in alerts if a.category == category]
        if severity:
            alerts = [a for a in alerts if a.severity == severity]
        return sorted(alerts, key=lambda a: a.triggered_at, reverse=True)

    def get_critical_alerts(self) -> List[MonitorAlert]:
        return self.get_active_alerts(severity=AlertSeverity.CRITICAL)

    def get_alert_history(self, limit: int = 100) -> List[MonitorAlert]:
        return sorted(
            self._resolved_alerts,
            key=lambda a: a.resolved_at or a.triggered_at,
            reverse=True,
        )[:limit]

    # ── Metrics Recording ─────────────────────────────────────────────────

    def record_metric(
        self,
        category: MonitorCategory,
        metric_name: str,
        value: float,
        unit: str = "",
        threshold_warning: Optional[float] = None,
        threshold_critical: Optional[float] = None,
        source: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> MetricSnapshot:
        """Record a metric snapshot and check thresholds."""
        snapshot = MetricSnapshot(
            category=category,
            metric_name=metric_name,
            value=value,
            unit=unit,
            threshold_warning=threshold_warning,
            threshold_critical=threshold_critical,
            source=source,
            metadata=metadata or {},
        )
        self._snapshots.append(snapshot)

        # Check thresholds and raise alerts
        if snapshot.status == "critical":
            self.raise_alert(
                category=category,
                severity=AlertSeverity.CRITICAL,
                title=f"Critical: {metric_name} at {value}{unit}",
                description=f"Metric {metric_name} exceeds critical threshold ({threshold_critical})",
                source=source,
                metrics={"value": value, "threshold": threshold_critical},
                suggested_actions=[f"Investigate {metric_name} immediately"],
            )
        elif snapshot.status == "warning":
            self.raise_alert(
                category=category,
                severity=AlertSeverity.WARNING,
                title=f"Warning: {metric_name} at {value}{unit}",
                description=f"Metric {metric_name} exceeds warning threshold ({threshold_warning})",
                source=source,
                metrics={"value": value, "threshold": threshold_warning},
            )

        return snapshot

    def get_metrics(
        self,
        category: Optional[MonitorCategory] = None,
        since: Optional[datetime] = None,
    ) -> List[MetricSnapshot]:
        """Get metric snapshots with filters."""
        snapshots = self._snapshots
        if category:
            snapshots = [s for s in snapshots if s.category == category]
        if since:
            snapshots = [s for s in snapshots if s.taken_at >= since]
        return snapshots

    def get_latest_metric(self, metric_name: str) -> Optional[MetricSnapshot]:
        """Get the latest snapshot for a metric."""
        for s in reversed(self._snapshots):
            if s.metric_name == metric_name:
                return s
        return None

    # ── Access Monitoring ─────────────────────────────────────────────────

    def record_access(
        self,
        actor: str,
        resource: str,
        action: str,
        ip_address: str = "",
        user_agent: str = "",
        is_authorized: bool = True,
    ) -> AccessEvent:
        """Record a data access event."""
        event = AccessEvent(
            actor=actor,
            resource=resource,
            action=action,
            ip_address=ip_address,
            user_agent=user_agent,
            is_authorized=is_authorized,
        )
        self._access_events.append(event)

        # Check for unauthorized access
        if not is_authorized:
            event.is_suspicious = True
            event.suspicion_reasons.append("Unauthorized access")
            self.raise_alert(
                category=MonitorCategory.ACCESS_CONTROL,
                severity=AlertSeverity.CRITICAL,
                title=f"Unauthorized access by {actor}",
                description=f"User {actor} attempted {action} on {resource} without authorization",
                source=ip_address,
                affected_resources=[resource],
                suggested_actions=[
                    "Investigate access logs",
                    "Review permissions",
                    "Consider account lockout",
                ],
                rule_id="M001",
            )

        return event

    def detect_anomalous_access(self, lookback_minutes: int = 60) -> List[AccessEvent]:
        """Detect anomalous access patterns."""
        cutoff = datetime.utcnow() - timedelta(minutes=lookback_minutes)
        recent = [e for e in self._access_events if e.timestamp >= cutoff]

        suspicious: List[AccessEvent] = []

        # Group by actor
        actor_events: Dict[str, List[AccessEvent]] = defaultdict(list)
        for e in recent:
            actor_events[e.actor].append(e)

        for actor, events in actor_events.items():
            # Detect rapid access bursts (>20 accesses/min)
            if len(events) > 20:
                for e in events:
                    e.is_suspicious = True
                    e.suspicion_reasons.append(
                        f"Burst: {len(events)} events in {lookback_minutes} min"
                    )
                suspicious.extend(events)

            # Detect access to unusual resources
            resources = set(e.resource for e in events)
            if len(resources) > 10 and len(events) > len(resources) * 3:
                for e in events:
                    e.is_suspicious = True
                    e.suspicion_reasons.append("Unusually broad resource access")
                suspicious.extend(events)

        if suspicious:
            self.raise_alert(
                category=MonitorCategory.ACCESS_CONTROL,
                severity=AlertSeverity.HIGH,
                title="Anomalous access pattern detected",
                description=f"{len(set(e.actor for e in suspicious))} actors show suspicious patterns",
                source="access_monitor",
                suggested_actions=["Review access patterns", "Check for compromised accounts"],
                rule_id="M001",
            )

        return suspicious

    # ─── Data Leakage Monitoring ──────────────────────────────────────────

    def check_data_leakage(
        self,
        data_exports: List[Dict[str, Any]],
        export_threshold: int = 1000,
        sensitive_types: Optional[List[str]] = None,
    ) -> List[MonitorAlert]:
        """Check for potential data leakage through exports."""
        alerts: List[MonitorAlert] = []
        sensitive_types = sensitive_types or ["pii", "financial", "medical", "ip"]

        for export in data_exports:
            record_count = export.get("record_count", 0)
            has_sensitive = any(
                dt in str(export.get("data_types", []))
                for dt in sensitive_types
            )

            if record_count > export_threshold and has_sensitive:
                alert = self.raise_alert(
                    category=MonitorCategory.DATA_LEAKAGE,
                    severity=AlertSeverity.CRITICAL,
                    title="Large sensitive data export detected",
                    description=(
                        f"Export of {record_count} records containing sensitive data types. "
                        f"Exporter: {export.get('actor', 'unknown')}"
                    ),
                    source=export.get("source", "unknown"),
                    metrics={"record_count": record_count},
                    suggested_actions=[
                        "Verify export authorization",
                        "Check data classification",
                        "Review export audit trail",
                        "Block if unauthorized",
                    ],
                    rule_id="M002",
                )
                if alert:
                    alerts.append(alert)

        return alerts

    def monitor_external_transfers(
        self,
        transfers: List[Dict[str, Any]],
    ) -> List[MonitorAlert]:
        """Monitor data transfers to external destinations."""
        alerts: List[MonitorAlert] = []
        for transfer in transfers:
            if transfer.get("destination_type") == "external":
                if transfer.get("contains_pii") or transfer.get("sensitivity") in (
                    "confidential", "restricted"
                ):
                    alert = self.raise_alert(
                        category=MonitorCategory.DATA_LEAKAGE,
                        severity=AlertSeverity.HIGH,
                        title="Sensitive data transferred externally",
                        description=f"Data sent to {transfer.get('destination')}",
                        source=transfer.get("source", ""),
                        suggested_actions=[
                            "Verify transfer authorization",
                            "Check data residency compliance",
                            "Ensure encryption in transit",
                        ],
                    )
                    if alert:
                        alerts.append(alert)
        return alerts

    # ─── Schema Change Monitoring ─────────────────────────────────────────

    def check_schema_changes(
        self,
        current_schema: Dict[str, Any],
        previous_schema: Dict[str, Any],
        authorized_changes: Optional[List[str]] = None,
    ) -> List[MonitorAlert]:
        """Detect unauthorized schema changes."""
        alerts: List[MonitorAlert] = []
        authorized = set(authorized_changes or [])

        # Find added fields
        added = set(current_schema.keys()) - set(previous_schema.keys())
        for field in added:
            if field not in authorized:
                alert = self.raise_alert(
                    category=MonitorCategory.SCHEMA_CHANGE,
                    severity=AlertSeverity.HIGH,
                    title=f"Schema change: new field '{field}'",
                    description=f"Unauthorized new field '{field}' added to schema",
                    source="schema_monitor",
                    suggested_actions=["Review schema change", "Update documentation"],
                    rule_id="M004",
                )
                if alert:
                    alerts.append(alert)

        # Find removed fields
        removed = set(previous_schema.keys()) - set(current_schema.keys())
        for field in removed:
            if field not in authorized:
                alert = self.raise_alert(
                    category=MonitorCategory.SCHEMA_CHANGE,
                    severity=AlertSeverity.CRITICAL,
                    title=f"Schema change: field '{field}' removed",
                    description=f"Unauthorized removal of field '{field}' - potential data loss",
                    source="schema_monitor",
                    suggested_actions=["Investigate immediately", "Check for data loss"],
                    rule_id="M004",
                )
                if alert:
                    alerts.append(alert)

        # Find type changes
        for field in set(current_schema.keys()) & set(previous_schema.keys()):
            if current_schema[field] != previous_schema[field] and field not in authorized:
                alert = self.raise_alert(
                    category=MonitorCategory.SCHEMA_CHANGE,
                    severity=AlertSeverity.WARNING,
                    title=f"Schema change: type change for '{field}'",
                    description=(
                        f"Type changed: {previous_schema[field]} -> {current_schema[field]}"
                    ),
                    source="schema_monitor",
                    rule_id="M004",
                )
                if alert:
                    alerts.append(alert)

        return alerts

    # ─── Compliance Monitoring ────────────────────────────────────────────

    def check_compliance(
        self,
        framework_results: Dict[str, Dict[str, Any]],
    ) -> List[MonitorAlert]:
        """Check compliance framework results for violations."""
        alerts: List[MonitorAlert] = []
        for fw_name, result in framework_results.items():
            compliance_pct = result.get("compliance_pct", 1.0)
            if compliance_pct < 0.60:
                alert = self.raise_alert(
                    category=MonitorCategory.COMPLIANCE,
                    severity=AlertSeverity.CRITICAL,
                    title=f"Critical compliance gap: {fw_name}",
                    description=(
                        f"Framework {fw_name} at {compliance_pct:.1%} compliance. "
                        f"Status: {result.get('status', 'Unknown')}"
                    ),
                    source=fw_name,
                    metrics={"compliance_pct": compliance_pct},
                    suggested_actions=[
                        f"Prioritize {fw_name} remediation",
                        "Schedule compliance review",
                        "Engage compliance team",
                    ],
                    rule_id="M005",
                )
                if alert:
                    alerts.append(alert)
            elif compliance_pct < 0.80:
                alert = self.raise_alert(
                    category=MonitorCategory.COMPLIANCE,
                    severity=AlertSeverity.HIGH,
                    title=f"Compliance gap: {fw_name}",
                    description=f"Framework {fw_name} at {compliance_pct:.1%} compliance",
                    source=fw_name,
                    metrics={"compliance_pct": compliance_pct},
                    rule_id="M005",
                )
                if alert:
                    alerts.append(alert)
        return alerts

    # ─── Privacy Violation Monitoring ─────────────────────────────────────

    def check_privacy_violations(
        self,
        consent_checks: List[Dict[str, Any]],
        overdue_requests: int = 0,
        dsar_violations: int = 0,
    ) -> List[MonitorAlert]:
        """Check for privacy and consent violations."""
        alerts: List[MonitorAlert] = []

        # Check consent violations
        for check in consent_checks:
            if not check.get("allowed", True):
                alert = self.raise_alert(
                    category=MonitorCategory.PRIVACY,
                    severity=AlertSeverity.CRITICAL,
                    title="Processing without valid consent",
                    description=(
                        f"Subject {check.get('subject_id')}: {check.get('reason')}"
                    ),
                    source="consent_monitor",
                    suggested_actions=[
                        "Stop processing immediately",
                        "Obtain proper consent",
                        "Review processing logic",
                    ],
                    rule_id="M013",
                )
                if alert:
                    alerts.append(alert)

        # Check overdue DSARs
        if overdue_requests > 0:
            self.raise_alert(
                category=MonitorCategory.PRIVACY,
                severity=AlertSeverity.HIGH,
                title=f"{overdue_requests} overdue privacy requests",
                description="Data subject access requests past legal deadline",
                source="dsar_monitor",
                metrics={"overdue_requests": overdue_requests},
                suggested_actions=["Process overdue requests immediately"],
                rule_id="M006",
            )

        return alerts

    # ─── Backup Monitoring ────────────────────────────────────────────────

    def check_backups(
        self,
        expected_backups: List[Dict[str, Any]],
        completed_backups: List[Dict[str, Any]],
        max_missed_hours: int = 24,
    ) -> List[MonitorAlert]:
        """Check for missing or failed backups."""
        alerts: List[MonitorAlert] = []

        expected_ids = {b["backup_id"] for b in expected_backups}
        completed_ids = {b["backup_id"] for b in completed_backups if b.get("status") == "completed"}
        failed_ids = {b["backup_id"] for b in completed_backups if b.get("status") == "failed"}

        missing = expected_ids - completed_ids - failed_ids

        if missing:
            alert = self.raise_alert(
                category=MonitorCategory.BACKUP,
                severity=AlertSeverity.HIGH,
                title=f"Missing backups: {len(missing)} not completed",
                description=f"Backup IDs: {list(missing)[:5]}",
                source="backup_monitor",
                metrics={"missing_count": len(missing)},
                suggested_actions=[
                    "Check backup scheduler",
                    "Verify storage availability",
                    "Trigger manual backup",
                ],
                rule_id="M007",
            )
            if alert:
                alerts.append(alert)

        if failed_ids:
            alert = self.raise_alert(
                category=MonitorCategory.BACKUP,
                severity=AlertSeverity.CRITICAL,
                title=f"Failed backups: {len(failed_ids)}",
                description=f"Backup IDs: {list(failed_ids)[:5]}",
                source="backup_monitor",
                metrics={"failed_count": len(failed_ids)},
                suggested_actions=[
                    "Investigate backup failures immediately",
                    "Check error logs",
                    "Verify data integrity",
                ],
                rule_id="M007",
            )
            if alert:
                alerts.append(alert)

        return alerts

    # ─── Storage Monitoring ───────────────────────────────────────────────

    def monitor_storage(
        self,
        total_bytes: int,
        used_bytes: int,
        warning_threshold_pct: float = 80.0,
        critical_threshold_pct: float = 95.0,
    ) -> Optional[MonitorAlert]:
        """Monitor storage utilization."""
        if total_bytes == 0:
            return None

        used_pct = (used_bytes / total_bytes) * 100

        if used_pct >= critical_threshold_pct:
            return self.raise_alert(
                category=MonitorCategory.STORAGE,
                severity=AlertSeverity.CRITICAL,
                title=f"Storage critically full: {used_pct:.1f}%",
                description=f"Used {used_bytes:,} / {total_bytes:,} bytes",
                source="storage_monitor",
                metrics={
                    "used_pct": used_pct,
                    "used_bytes": used_bytes,
                    "total_bytes": total_bytes,
                },
                suggested_actions=[
                    "Immediate storage expansion",
                    "Archive or delete old data",
                    "Check retention policies",
                ],
                rule_id="M008",
            )
        elif used_pct >= warning_threshold_pct:
            return self.raise_alert(
                category=MonitorCategory.STORAGE,
                severity=AlertSeverity.WARNING,
                title=f"Storage utilization high: {used_pct:.1f}%",
                description=f"Used {used_bytes:,} / {total_bytes:,} bytes",
                source="storage_monitor",
                metrics={"used_pct": used_pct},
                suggested_actions=["Plan storage expansion", "Review data lifecycle"],
                rule_id="M008",
            )
        return None

    # ─── AI Knowledge Freshness ───────────────────────────────────────────

    def check_ai_knowledge_freshness(
        self,
        knowledge_entries: List[Dict[str, Any]],
        max_age_days: int = 90,
    ) -> List[MonitorAlert]:
        """Check AI knowledge base freshness."""
        alerts: List[MonitorAlert] = []
        now = datetime.utcnow()
        stale_count = 0

        for entry in knowledge_entries:
            created_at = entry.get("created_at")
            if isinstance(created_at, str):
                created_at = datetime.fromisoformat(created_at)
            if created_at and (now - created_at).days > max_age_days:
                stale_count += 1

        if stale_count > 0:
            alert = self.raise_alert(
                category=MonitorCategory.AI_KNOWLEDGE,
                severity=AlertSeverity.WARNING,
                title=f"AI knowledge entries stale: {stale_count}/{len(knowledge_entries)}",
                description=f"{stale_count} entries older than {max_age_days} days",
                source="ai_knowledge_monitor",
                metrics={
                    "stale_count": stale_count,
                    "total_entries": len(knowledge_entries),
                    "max_age_days": max_age_days,
                },
                suggested_actions=[
                    "Refresh stale knowledge entries",
                    "Review RAG knowledge expiration policy",
                    "Regenerate embeddings",
                ],
                rule_id="M009",
            )
            if alert:
                alerts.append(alert)

        return alerts

    # ─── Data Quality Monitoring ──────────────────────────────────────────

    def monitor_data_quality(
        self,
        quality_report: Dict[str, Any],
        degradation_threshold: float = 0.10,
    ) -> List[MonitorAlert]:
        """Monitor data quality and detect degradation."""
        alerts: List[MonitorAlert] = []

        overall_score = quality_report.get("overall_score", 1.0)
        status = quality_report.get("overall_status", "excellent")

        if status in ("poor", "critical"):
            alert = self.raise_alert(
                category=MonitorCategory.DATA_QUALITY,
                severity=AlertSeverity.HIGH if status == "poor" else AlertSeverity.CRITICAL,
                title=f"Data quality {status}: score {overall_score:.2f}",
                description="Data quality has degraded below acceptable thresholds",
                source="quality_monitor",
                metrics={"overall_score": overall_score},
                suggested_actions=[
                    "Investigate quality degradation",
                    "Review anomaly reports",
                    "Check data pipeline health",
                ],
                rule_id="M010",
            )
            if alert:
                alerts.append(alert)

        # Check individual dimensions
        dimension_scores = quality_report.get("dimension_scores", {})
        for dim, score in dimension_scores.items():
            if score < 0.70:
                self.raise_alert(
                    category=MonitorCategory.DATA_QUALITY,
                    severity=AlertSeverity.WARNING,
                    title=f"Quality dimension '{dim}' degraded: {score:.2f}",
                    description=f"{dim} score below threshold",
                    source="quality_monitor",
                    metrics={"dimension": dim, "score": score},
                    rule_id="M010",
                )

        return alerts

    # ─── Encryption Monitoring ────────────────────────────────────────────

    def check_encryption_rotation(
        self,
        key_ages_days: Dict[str, int],
        max_age_days: int = 90,
    ) -> List[MonitorAlert]:
        """Check if encryption keys need rotation."""
        alerts: List[MonitorAlert] = []
        for key_id, age in key_ages_days.items():
            if age > max_age_days:
                alert = self.raise_alert(
                    category=MonitorCategory.ENCRYPTION,
                    severity=AlertSeverity.HIGH,
                    title=f"Encryption key rotation overdue: {key_id}",
                    description=f"Key {key_id} is {age} days old (max {max_age_days})",
                    source="encryption_monitor",
                    metrics={"key_id": key_id, "age_days": age},
                    suggested_actions=["Rotate encryption key", "Verify re-encryption"],
                    rule_id="M011",
                )
                if alert:
                    alerts.append(alert)
        return alerts

    # ─── Retention Monitoring ─────────────────────────────────────────────

    def check_retention(
        self,
        assets_past_retention: List[Dict[str, Any]],
    ) -> List[MonitorAlert]:
        """Check for data past retention policy."""
        alerts: List[MonitorAlert] = []
        if assets_past_retention:
            alert = self.raise_alert(
                category=MonitorCategory.RETENTION,
                severity=AlertSeverity.HIGH,
                title=f"Data past retention: {len(assets_past_retention)} assets",
                description="Data exists beyond defined retention period",
                source="retention_monitor",
                metrics={"overdue_count": len(assets_past_retention)},
                suggested_actions=[
                    "Trigger deletion workflow",
                    "Check legal holds",
                    "Review retention policies",
                ],
                rule_id="M012",
            )
            if alert:
                alerts.append(alert)
        return alerts

    # ─── Dashboard ────────────────────────────────────────────────────────

    def get_dashboard(self) -> Dict[str, Any]:
        """Generate a monitoring dashboard summary."""
        active_alerts = self.get_active_alerts()
        critical = self.get_critical_alerts()

        alert_by_category = Counter(a.category.value for a in active_alerts)
        alert_by_severity = Counter(a.severity.value for a in active_alerts)

        # Recent access stats
        recent_access = self._access_events[-1000:]
        suspicious_access = sum(1 for e in recent_access if e.is_suspicious)

        return {
            "timestamp": datetime.utcnow().isoformat(),
            "alert_summary": {
                "total_active": len(active_alerts),
                "critical": len(critical),
                "high": alert_by_severity.get("high", 0),
                "warning": alert_by_severity.get("warning", 0),
                "by_category": dict(alert_by_category),
            },
            "access_summary": {
                "recent_events": len(recent_access),
                "suspicious_events": suspicious_access,
                "suspicious_pct": (
                    round(suspicious_access / len(recent_access) * 100, 2)
                    if recent_access else 0
                ),
            },
            "metric_snapshots": len(self._snapshots),
            "resolved_alerts": len(self._resolved_alerts),
            "top_critical": [
                {"title": a.title, "age_minutes": a.age_minutes}
                for a in critical[:5]
            ],
        }

    @property
    def stats(self) -> Dict[str, Any]:
        return {
            "active_alerts": len(self._alerts),
            "resolved_alerts": len(self._resolved_alerts),
            "total_snapshots": len(self._snapshots),
            "total_access_events": len(self._access_events),
            "monitoring_rules": len(self._rules),
        }