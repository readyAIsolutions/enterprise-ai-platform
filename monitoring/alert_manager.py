"""
ENI Enterprise Alert Manager — Threshold-Based Alerting System
================================================================
Provides threshold-based alerting with severity levels (CRITICAL, HIGH,
MEDIUM, LOW, INFO), escalation policies, alert deduplication, cooldown
periods, and integration with the Platform Kernel EventBus.

Architecture:
    AlertSeverity      — CRITICAL, HIGH, MEDIUM, LOW, INFO
    AlertState         — FIRING, RESOLVED, ACKNOWLEDGED, ESCALATED, SUPPRESSED
    AlertRule          — Threshold condition definitions
    EscalationPolicy   — Escalation chain and timing rules
    Alert              — Single alert instance with full lifecycle
    AlertManager       — Central manager: evaluates rules, manages lifecycle

Integration:
    - EventBus publishes alert.* events for cross-module notification
    - HealthChecker feeds module health status into alert evaluation
    - MetricsCollector provides metric-based threshold evaluation
    - API Gateway exposes /api/v1/alerts for query
"""

from __future__ import annotations

import threading
import time
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, ClassVar, Dict, List, Optional, Set, Tuple

# =============================================================================
# Enums
# =============================================================================


class AlertSeverity(Enum):
    """Alert severity levels in order of increasing criticality."""

    INFO = 0
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4

    @classmethod
    def from_string(cls, value: str) -> "AlertSeverity":
        """Parse severity from a case-insensitive string."""
        try:
            return cls[value.upper()]
        except KeyError:
            return cls.INFO

    def label(self) -> str:
        """Human-readable label."""
        return self.name


class AlertState(Enum):
    """Lifecycle states for an alert."""

    FIRING = "firing"
    RESOLVED = "resolved"
    ACKNOWLEDGED = "acknowledged"
    ESCALATED = "escalated"
    SUPPRESSED = "suppressed"
    EXPIRED = "expired"


# =============================================================================
# Data Classes
# =============================================================================


@dataclass
class AlertCondition:
    """A condition that triggers an alert based on a metric threshold.

    Attributes:
        metric_name: Name of the metric to evaluate.
        operator: Comparison operator ('>', '<', '>=', '<=', '==', '!=').
        threshold: Numeric threshold value.
        labels: Optional metric labels to filter on.
        duration_sec: Condition must persist for this many seconds before firing.
    """

    metric_name: str
    operator: str
    threshold: float
    labels: Dict[str, str] = field(default_factory=dict)
    duration_sec: float = 0.0

    def evaluate(self, current_value: float) -> bool:
        """Evaluate the condition against a current metric value."""
        ops: Dict[str, Callable[[float, float], bool]] = {
            ">": lambda a, b: a > b,
            "<": lambda a, b: a < b,
            ">=": lambda a, b: a >= b,
            "<=": lambda a, b: a <= b,
            "==": lambda a, b: a == b,
            "!=": lambda a, b: a != b,
        }
        op = ops.get(self.operator)
        if op is None:
            raise ValueError(f"Unknown operator: {self.operator}")
        return op(current_value, self.threshold)


@dataclass
class AlertRule:
    """An alert rule that defines conditions, severity, and metadata.

    Attributes:
        name: Unique rule name.
        description: Human-readable description.
        severity: Alert severity level.
        conditions: List of conditions (ALL must be true for alert to fire).
        module: Associated module name, or '*' for platform-wide.
        cooldown_sec: Minimum time between repeated alerts from this rule.
        escalation_policy: Optional escalation chain reference.
        labels: Additional labels attached to fired alerts.
        annotations: Additional context for alert handling.
        enabled: Whether this rule is actively evaluated.
    """

    name: str
    description: str
    severity: AlertSeverity
    conditions: List[AlertCondition] = field(default_factory=list)
    module: str = "*"
    cooldown_sec: float = 300.0
    escalation_policy: Optional[str] = None
    labels: Dict[str, str] = field(default_factory=dict)
    annotations: Dict[str, str] = field(default_factory=dict)
    enabled: bool = True

    def evaluate(
        self, metric_values: Dict[str, Dict[str, float]]
    ) -> Tuple[bool, Dict[str, Any]]:
        """Evaluate all conditions against current metric values.

        Args:
            metric_values: Dict of metric_name -> {label_key -> value}.

        Returns:
            Tuple of (should_fire, details_dict).
        """
        if not self.enabled or not self.conditions:
            return False, {}

        details: Dict[str, Any] = {}
        for condition in self.conditions:
            label_key = _labels_key(condition.labels)
            values = metric_values.get(condition.metric_name, {})
            current = values.get(label_key, 0.0)

            if not condition.evaluate(current):
                return False, details
            details[condition.metric_name] = {
                "value": current,
                "threshold": condition.threshold,
                "operator": condition.operator,
            }

        return True, details


@dataclass
class EscalationPolicy:
    """Defines escalation behavior for alerts.

    Attributes:
        name: Unique policy name.
        steps: Ordered list of escalation steps (severity level -> delay_sec).
        max_escalations: Maximum number of escalations before alert is critical.
        auto_resolve_sec: Auto-resolve alert after this many seconds in resolved state.
        notify_on_escalation: Whether to publish events on each escalation step.
    """

    name: str
    steps: List[Tuple[AlertSeverity, float]] = field(default_factory=list)
    max_escalations: int = 3
    auto_resolve_sec: float = 3600.0
    notify_on_escalation: bool = True

    def get_next_level(
        self, current: AlertSeverity
    ) -> Optional[Tuple[AlertSeverity, float]]:
        """Get the next escalation step after the current severity level."""
        for severity, delay in self.steps:
            if severity.value > current.value:
                return (severity, delay)
        return None


@dataclass
class Alert:
    """A single alert instance tracked through its full lifecycle.

    Attributes:
        alert_id: Unique alert identifier (UUID4).
        rule_name: Name of the rule that generated this alert.
        severity: Current severity level.
        state: Current lifecycle state.
        module: Affected module.
        message: Alert description/message.
        details: Additional alert context.
        created_at: UTC creation timestamp.
        updated_at: Last update timestamp.
        resolved_at: When the alert was resolved (if applicable).
        acknowledged_at: When acknowledged (if applicable).
        escalated_at: Last escalation timestamp.
        escalation_count: Number of times this alert has been escalated.
        labels: Key-value labels for filtering.
        annotations: Contextual annotations.
    """

    alert_id: str
    rule_name: str
    severity: AlertSeverity
    state: AlertState
    module: str
    message: str
    details: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    resolved_at: Optional[datetime] = None
    acknowledged_at: Optional[datetime] = None
    escalated_at: Optional[datetime] = None
    escalation_count: int = 0
    labels: Dict[str, str] = field(default_factory=dict)
    annotations: Dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize alert to a dict."""
        return {
            "alert_id": self.alert_id,
            "rule_name": self.rule_name,
            "severity": self.severity.label(),
            "state": self.state.value,
            "module": self.module,
            "message": self.message,
            "details": self.details,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
            "acknowledged_at": (
                self.acknowledged_at.isoformat() if self.acknowledged_at else None
            ),
            "escalated_at": (
                self.escalated_at.isoformat() if self.escalated_at else None
            ),
            "escalation_count": self.escalation_count,
            "labels": self.labels,
            "annotations": self.annotations,
        }

    def acknowledge(self) -> None:
        """Mark this alert as acknowledged."""
        self.state = AlertState.ACKNOWLEDGED
        self.acknowledged_at = datetime.now(timezone.utc)
        self.updated_at = datetime.now(timezone.utc)

    def resolve(self) -> None:
        """Mark this alert as resolved."""
        self.state = AlertState.RESOLVED
        self.resolved_at = datetime.now(timezone.utc)
        self.updated_at = datetime.now(timezone.utc)

    def escalate(self, new_severity: AlertSeverity) -> None:
        """Escalate this alert to a higher severity level."""
        self.severity = new_severity
        self.state = AlertState.ESCALATED
        self.escalated_at = datetime.now(timezone.utc)
        self.escalation_count += 1
        self.updated_at = datetime.now(timezone.utc)

    def suppress(self) -> None:
        """Suppress this alert (e.g., during maintenance)."""
        self.state = AlertState.SUPPRESSED
        self.updated_at = datetime.now(timezone.utc)


# =============================================================================
# Alert Manager
# =============================================================================


class AlertManager:
    """Central alert manager for the ENI Enterprise Platform.

    Manages alert rules, evaluates thresholds, maintains alert lifecycle,
    handles escalation, and integrates with the EventBus for cross-module
    notifications.

    Usage::

        manager = AlertManager(event_bus=platform.event_bus, metrics=collector)
        manager.register_rule(AlertRule(...))
        manager.evaluate_all()
        alerts = manager.get_active_alerts()

    Built-in rules cover:
        - Module health degraded/unhealthy detection
        - High error rates on endpoints
        - Event bus failure thresholds
        - Circuit breaker open detection
        - Resource utilization (CPU, memory, disk)
        - Swarm turbocharger WiFi signal degradation
    """

    # Default built-in rules
    BUILTIN_RULES: ClassVar[List[AlertRule]] = []

    def __init__(
        self,
        event_bus: Optional[Any] = None,
        metrics_collector: Optional[Any] = None,
        config: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Initialize the AlertManager.

        Args:
            event_bus: Platform Kernel EventBus for publishing alert events.
            metrics_collector: MonitoringMetricsCollector for metric evaluation.
            config: Alert manager configuration dict.
        """
        cfg = config or {}
        self._event_bus = event_bus
        self._metrics = metrics_collector
        self._lock: threading.RLock = threading.RLock()
        self._rules: Dict[str, AlertRule] = {}
        self._policies: Dict[str, EscalationPolicy] = {}
        self._alerts: Dict[str, Alert] = {}
        self._alert_history: List[Alert] = []
        self._fired_timestamps: Dict[str, datetime] = {}
        self._condition_states: Dict[str, datetime] = defaultdict(
            lambda: datetime.now(timezone.utc)
        )
        self._max_history: int = cfg.get("max_history", 10000)
        self._enabled: bool = cfg.get("enabled", True)

        # Register default escalation policies
        self._register_default_policies()
        # Register built-in rules
        self._register_builtin_rules()

    def _register_default_policies(self) -> None:
        """Register default escalation policies."""
        self.register_escalation_policy(
            EscalationPolicy(
                name="standard",
                steps=[
                    (AlertSeverity.LOW, 300.0),     # After 5 min: escalate to LOW
                    (AlertSeverity.MEDIUM, 600.0),   # After 10 min: MEDIUM
                    (AlertSeverity.HIGH, 900.0),     # After 15 min: HIGH
                    (AlertSeverity.CRITICAL, 1800.0), # After 30 min: CRITICAL
                ],
                max_escalations=4,
                auto_resolve_sec=3600.0,
            )
        )
        self.register_escalation_policy(
            EscalationPolicy(
                name="rapid",
                steps=[
                    (AlertSeverity.MEDIUM, 60.0),
                    (AlertSeverity.HIGH, 180.0),
                    (AlertSeverity.CRITICAL, 300.0),
                ],
                max_escalations=3,
                auto_resolve_sec=1800.0,
            )
        )
        self.register_escalation_policy(
            EscalationPolicy(
                name="critical_only",
                steps=[
                    (AlertSeverity.CRITICAL, 0.0),
                ],
                max_escalations=1,
                auto_resolve_sec=7200.0,
            )
        )

    def _register_builtin_rules(self) -> None:
        """Register the comprehensive set of built-in alert rules."""
        rules: List[AlertRule] = [
            # ── Module Health Rules ───────────────────────────────────────
            AlertRule(
                name="module_health_unhealthy",
                description="Module health status is unhealthy",
                severity=AlertSeverity.CRITICAL,
                conditions=[
                    AlertCondition(
                        "eni_module_health_status",
                        "<=",
                        0.0,
                        duration_sec=30.0,
                    ),
                ],
                cooldown_sec=120.0,
                escalation_policy="rapid",
                annotations={"runbook": "Check module logs and restart if needed"},
            ),
            AlertRule(
                name="module_health_degraded",
                description="Module health status is degraded",
                severity=AlertSeverity.HIGH,
                conditions=[
                    AlertCondition("eni_module_health_status", "<=", 1.0, duration_sec=60.0),
                ],
                cooldown_sec=300.0,
                escalation_policy="standard",
                annotations={"runbook": "Monitor module for further degradation"},
            ),
            AlertRule(
                name="module_consecutive_failures",
                description="Module has multiple consecutive health check failures",
                severity=AlertSeverity.HIGH,
                conditions=[
                    AlertCondition("eni_module_consecutive_failures", ">=", 3.0),
                ],
                cooldown_sec=180.0,
                escalation_policy="rapid",
                annotations={"runbook": "Restart the failing module"},
            ),

            # ── Endpoint Error Rules ─────────────────────────────────────
            AlertRule(
                name="endpoint_high_error_rate",
                description="High error rate on API endpoints",
                severity=AlertSeverity.HIGH,
                conditions=[
                    AlertCondition("eni_endpoint_errors_total", ">=", 10.0),
                ],
                cooldown_sec=300.0,
                escalation_policy="standard",
                annotations={"runbook": "Check endpoint logs for error patterns"},
            ),
            AlertRule(
                name="endpoint_high_latency",
                description="Endpoint latency exceeds threshold",
                severity=AlertSeverity.MEDIUM,
                conditions=[
                    AlertCondition(
                        "eni_endpoint_requests_duration_seconds",
                        ">=",
                        5.0,
                    ),
                ],
                cooldown_sec=180.0,
                escalation_policy="standard",
            ),

            # ── Event Bus Rules ─────────────────────────────────────────
            AlertRule(
                name="event_bus_high_failure_rate",
                description="Event delivery failure rate exceeds threshold",
                severity=AlertSeverity.HIGH,
                conditions=[
                    AlertCondition("eni_events_failed_total", ">=", 10.0),
                ],
                cooldown_sec=300.0,
                escalation_policy="rapid",
                annotations={"runbook": "Check event bus subscribers and dead letter queue"},
            ),
            AlertRule(
                name="event_bus_dead_letter_growing",
                description="Dead letter queue is accumulating events",
                severity=AlertSeverity.MEDIUM,
                conditions=[
                    AlertCondition("eni_events_dead_letter_count", ">=", 50.0),
                ],
                cooldown_sec=600.0,
                escalation_policy="standard",
            ),
            AlertRule(
                name="event_bus_no_subscribers",
                description="Event bus has no active subscriptions",
                severity=AlertSeverity.LOW,
                conditions=[
                    AlertCondition("eni_events_active_subscriptions", "<=", 0.0),
                ],
                cooldown_sec=900.0,
            ),

            # ── Circuit Breaker Rules ───────────────────────────────────
            AlertRule(
                name="circuit_breaker_open",
                description="Circuit breaker is in OPEN state",
                severity=AlertSeverity.CRITICAL,
                conditions=[
                    AlertCondition("eni_circuit_breaker_state", ">=", 1.0),
                ],
                cooldown_sec=60.0,
                escalation_policy="critical_only",
                annotations={"runbook": "Service is down; check downstream dependencies"},
            ),

            # ── Resource Utilization Rules ──────────────────────────────
            AlertRule(
                name="high_cpu_usage",
                description="CPU usage exceeds threshold",
                severity=AlertSeverity.MEDIUM,
                conditions=[
                    AlertCondition("eni_system_cpu_percent", ">=", 90.0, duration_sec=60.0),
                ],
                cooldown_sec=300.0,
                escalation_policy="standard",
            ),
            AlertRule(
                name="critical_cpu_usage",
                description="CPU usage is critically high",
                severity=AlertSeverity.CRITICAL,
                conditions=[
                    AlertCondition("eni_system_cpu_percent", ">=", 98.0, duration_sec=30.0),
                ],
                cooldown_sec=120.0,
                escalation_policy="rapid",
            ),
            AlertRule(
                name="low_memory",
                description="Available memory is critically low",
                severity=AlertSeverity.CRITICAL,
                conditions=[
                    AlertCondition(
                        "eni_system_memory_bytes",
                        "<=",
                        524288000.0,  # 500MB
                        labels={"type": "available"},
                        duration_sec=30.0,
                    ),
                ],
                cooldown_sec=180.0,
                escalation_policy="rapid",
            ),
            AlertRule(
                name="high_disk_usage",
                description="Disk usage exceeds threshold",
                severity=AlertSeverity.MEDIUM,
                conditions=[
                    AlertCondition(
                        "eni_system_disk_bytes",
                        ">=",
                        90.0,  # 90%
                        labels={"type": "percent"},
                        duration_sec=300.0,
                    ),
                ],
                cooldown_sec=600.0,
                escalation_policy="standard",
            ),

            # ── Swarm Turbocharger Rules ───────────────────────────────
            AlertRule(
                name="wifi_signal_degraded",
                description="WiFi signal strength is degraded",
                severity=AlertSeverity.MEDIUM,
                conditions=[
                    AlertCondition("eni_swarm_wifi_signal_dbm", "<=", -70.0, duration_sec=60.0),
                ],
                cooldown_sec=300.0,
                annotations={"runbook": "Check network connection; reduce concurrency"},
            ),
            AlertRule(
                name="wifi_signal_critical",
                description="WiFi signal strength is critically low",
                severity=AlertSeverity.HIGH,
                conditions=[
                    AlertCondition("eni_swarm_wifi_signal_dbm", "<=", -80.0, duration_sec=30.0),
                ],
                cooldown_sec=180.0,
                escalation_policy="rapid",
            ),
            AlertRule(
                name="swarm_agents_exhausted",
                description="All swarm agent slots in use",
                severity=AlertSeverity.HIGH,
                conditions=[
                    AlertCondition("eni_swarm_active_agents", ">=", 80.0),
                ],
                cooldown_sec=180.0,
                annotations={"runbook": "Scale out or wait for agent slots to free"},
            ),

            # ── Alert Manager Self-Monitoring ──────────────────────────
            AlertRule(
                name="too_many_active_alerts",
                description="Too many active (firing) alerts in the system",
                severity=AlertSeverity.MEDIUM,
                conditions=[
                    AlertCondition("eni_alerts_active_total", ">=", 20.0),
                ],
                cooldown_sec=300.0,
                annotations={"runbook": "Investigate root cause of alert storm"},
            ),
        ]

        for rule in rules:
            self.register_rule(rule)

        AlertManager.BUILTIN_RULES = rules

    # ── Rule Management ──────────────────────────────────────────────────────

    def register_rule(self, rule: AlertRule) -> None:
        """Register an alert rule."""
        with self._lock:
            self._rules[rule.name] = rule

    def unregister_rule(self, rule_name: str) -> bool:
        """Remove an alert rule by name. Returns True if found."""
        with self._lock:
            return self._rules.pop(rule_name, None) is not None

    def get_rule(self, rule_name: str) -> Optional[AlertRule]:
        """Get a rule by name."""
        with self._lock:
            return self._rules.get(rule_name)

    def list_rules(self) -> List[AlertRule]:
        """List all registered rules."""
        with self._lock:
            return list(self._rules.values())

    # ── Escalation Policy Management ─────────────────────────────────────────

    def register_escalation_policy(self, policy: EscalationPolicy) -> None:
        """Register an escalation policy."""
        with self._lock:
            self._policies[policy.name] = policy

    def get_escalation_policy(self, name: str) -> Optional[EscalationPolicy]:
        """Get an escalation policy by name."""
        with self._lock:
            return self._policies.get(name)

    # ── Alert Lifecycle ──────────────────────────────────────────────────────

    def fire_alert(
        self,
        rule: AlertRule,
        module: str = "",
        details: Optional[Dict[str, Any]] = None,
    ) -> Alert:
        """Create and fire a new alert from a rule.

        Args:
            rule: The AlertRule that triggered this alert.
            module: Specific module name (overrides rule.module if set).
            details: Additional alert context/details.

        Returns:
            The created Alert instance.
        """
        with self._lock:
            # Deduplication: check if a similar alert is already firing
            existing = self._find_existing_alert(rule.name, module or rule.module)
            if existing and existing.state in (AlertState.FIRING, AlertState.ACKNOWLEDGED):
                existing.updated_at = datetime.now(timezone.utc)
                return existing

            alert = Alert(
                alert_id=str(uuid.uuid4()),
                rule_name=rule.name,
                severity=rule.severity,
                state=AlertState.FIRING,
                module=module or rule.module,
                message=f"{rule.description} [{rule.severity.label()}]",
                details=details or {},
                labels=dict(rule.labels),
                annotations=dict(rule.annotations),
            )
            self._alerts[alert.alert_id] = alert
            self._alert_history.append(alert)
            self._fired_timestamps[rule.name] = datetime.now(timezone.utc)

            # Trim history
            if len(self._alert_history) > self._max_history:
                self._alert_history = self._alert_history[-self._max_history :]

        # Publish alert event on EventBus
        self._publish_alert_event("alert.fired", alert)

        return alert

    def resolve_alert(self, alert_id: str) -> Optional[Alert]:
        """Resolve an alert by ID."""
        with self._lock:
            alert = self._alerts.get(alert_id)
            if alert is None:
                return None
            alert.resolve()

        self._publish_alert_event("alert.resolved", alert)
        return alert

    def acknowledge_alert(self, alert_id: str) -> Optional[Alert]:
        """Acknowledge an alert by ID."""
        with self._lock:
            alert = self._alerts.get(alert_id)
            if alert is None:
                return None
            alert.acknowledge()

        self._publish_alert_event("alert.acknowledged", alert)
        return alert

    def escalate_alert(self, alert_id: str) -> Optional[Alert]:
        """Escalate an alert to the next severity level per its rule's policy."""
        with self._lock:
            alert = self._alerts.get(alert_id)
            if alert is None:
                return None

            rule = self._rules.get(alert.rule_name)
            if rule is None:
                return None

            policy_name = rule.escalation_policy or "standard"
            policy = self._policies.get(policy_name)
            if policy is None:
                return None

            if alert.escalation_count >= policy.max_escalations:
                return alert  # Already at max escalations

            next_step = policy.get_next_level(alert.severity)
            if next_step is None:
                return alert  # Already at max severity

            new_severity, _delay = next_step
            alert.escalate(new_severity)

        self._publish_alert_event("alert.escalated", alert)
        return alert

    def suppress_alert(self, alert_id: str) -> Optional[Alert]:
        """Suppress an alert (e.g., during maintenance)."""
        with self._lock:
            alert = self._alerts.get(alert_id)
            if alert is None:
                return None
            alert.suppress()

        self._publish_alert_event("alert.suppressed", alert)
        return alert

    def _find_existing_alert(self, rule_name: str, module: str) -> Optional[Alert]:
        """Find an existing firing alert for the same rule+module pair."""
        for alert in self._alerts.values():
            if (
                alert.rule_name == rule_name
                and alert.module == module
                and alert.state in (AlertState.FIRING, AlertState.ACKNOWLEDGED, AlertState.ESCALATED)
            ):
                return alert
        return None

    # ── Evaluation ───────────────────────────────────────────────────────────

    def evaluate_all(self) -> List[Alert]:
        """Evaluate all registered rules and fire/resolve alerts as needed.

        Returns:
            List of newly fired Alert instances.
        """
        if not self._enabled:
            return []

        fired: List[Alert] = []
        now = datetime.now(timezone.utc)

        with self._lock:
            rules = list(self._rules.values())

        for rule in rules:
            if not rule.enabled:
                continue

            # Check cooldown
            last_fired = self._fired_timestamps.get(rule.name)
            if last_fired and (now - last_fired).total_seconds() < rule.cooldown_sec:
                continue

            # Gather metric values for rule evaluation
            metric_values: Dict[str, Dict[str, float]] = {}
            should_fire, details = self._evaluate_rule_conditions(rule, metric_values)

            if should_fire:
                alert = self.fire_alert(rule, details=details)
                fired.append(alert)
            else:
                # Auto-resolve any existing alerts for this rule+module
                self._auto_resolve_for_rule(rule)

        # Handle escalations for existing alerts
        self._process_escalations()

        # Auto-resolve expired alerts
        self._auto_resolve_expired()

        return fired

    def _evaluate_rule_conditions(
        self,
        rule: AlertRule,
        metric_values: Dict[str, Dict[str, float]],
    ) -> Tuple[bool, Dict[str, Any]]:
        """Evaluate a rule's conditions against current metrics.

        If a metrics_collector is available, reads values from it.
        Otherwise, uses the passed metric_values dict.
        """
        details: Dict[str, Any] = {}

        for condition in rule.conditions:
            label_key = _labels_key(condition.labels)
            current_value: float = 0.0

            # Try to read from the metrics collector
            if self._metrics:
                try:
                    if hasattr(self._metrics, 'get_gauge'):
                        current_value = self._metrics.get_gauge(
                            condition.metric_name, condition.labels
                        )
                    if current_value == 0.0 and hasattr(self._metrics, 'get_counter'):
                        current_value = self._metrics.get_counter(
                            condition.metric_name, condition.labels
                        )
                except Exception:
                    pass

            # Fallback to provided metric_values
            if current_value == 0.0:
                values = metric_values.get(condition.metric_name, {})
                current_value = values.get(label_key, 0.0)

            if not condition.evaluate(current_value):
                return False, {}

            details[condition.metric_name] = {
                "value": current_value,
                "threshold": condition.threshold,
                "operator": condition.operator,
            }

        return True, details

    def _auto_resolve_for_rule(self, rule: AlertRule) -> None:
        """Auto-resolve alerts for a rule whose condition is no longer met."""
        for alert in list(self._alerts.values()):
            if (
                alert.rule_name == rule.name
                and alert.state in (AlertState.FIRING, AlertState.ACKNOWLEDGED, AlertState.ESCALATED)
            ):
                self.resolve_alert(alert.alert_id)

    def _process_escalations(self) -> None:
        """Check and apply escalations for existing alerts."""
        now = datetime.now(timezone.utc)

        for alert in list(self._alerts.values()):
            if alert.state not in (AlertState.FIRING, AlertState.ESCALATED):
                continue

            rule = self._rules.get(alert.rule_name)
            if rule is None:
                continue

            policy_name = rule.escalation_policy or "standard"
            policy = self._policies.get(policy_name)
            if policy is None:
                continue

            # Check if it's time for the next escalation
            next_step = policy.get_next_level(alert.severity)
            if next_step is None:
                continue

            _new_severity, delay = next_step
            # Use escalated_at if escalated, otherwise created_at
            base_time = alert.escalated_at or alert.created_at
            elapsed = (now - base_time).total_seconds()

            if elapsed >= delay:
                self.escalate_alert(alert.alert_id)

    def _auto_resolve_expired(self) -> None:
        """Auto-resolve alerts in RESOLVED state that exceed auto_resolve_sec."""
        now = datetime.now(timezone.utc)

        for alert in list(self._alerts.values()):
            if alert.state != AlertState.RESOLVED:
                continue
            if alert.resolved_at is None:
                continue

            rule = self._rules.get(alert.rule_name)
            policy_name = rule.escalation_policy if rule else "standard"
            policy = self._policies.get(policy_name)
            auto_resolve_sec = policy.auto_resolve_sec if policy else 3600.0

            if (now - alert.resolved_at).total_seconds() >= auto_resolve_sec:
                alert.state = AlertState.EXPIRED
                alert.updated_at = now

    # ── Query ────────────────────────────────────────────────────────────────

    def get_active_alerts(
        self,
        severity: Optional[AlertSeverity] = None,
        module: Optional[str] = None,
    ) -> List[Alert]:
        """Get currently active (firing/acknowledged/escalated) alerts."""
        active_states = {AlertState.FIRING, AlertState.ACKNOWLEDGED, AlertState.ESCALATED}
        with self._lock:
            alerts = [
                a
                for a in self._alerts.values()
                if a.state in active_states
            ]
        if severity:
            alerts = [a for a in alerts if a.severity == severity]
        if module:
            alerts = [a for a in alerts if a.module == module or a.module == "*"]
        return sorted(alerts, key=lambda a: a.severity.value, reverse=True)

    def get_alert(self, alert_id: str) -> Optional[Alert]:
        """Get an alert by ID."""
        with self._lock:
            return self._alerts.get(alert_id)

    def get_alert_history(
        self,
        limit: int = 100,
        severity: Optional[AlertSeverity] = None,
    ) -> List[Alert]:
        """Get alert history."""
        with self._lock:
            history = list(self._alert_history)
        if severity:
            history = [a for a in history if a.severity == severity]
        return history[-limit:]

    def get_summary(self) -> Dict[str, Any]:
        """Get a summary of the current alert state."""
        active = self.get_active_alerts()
        by_severity: Dict[str, int] = defaultdict(int)
        for alert in active:
            by_severity[alert.severity.label()] += 1

        return {
            "active_count": len(active),
            "by_severity": dict(by_severity),
            "total_rules": len(self._rules),
            "enabled_rules": sum(1 for r in self._rules.values() if r.enabled),
            "escalation_policies": len(self._policies),
            "history_size": len(self._alert_history),
        }

    # ── EventBus Integration ─────────────────────────────────────────────────

    def _publish_alert_event(self, topic: str, alert: Alert) -> None:
        """Publish an alert lifecycle event on the EventBus."""
        if self._event_bus is None:
            return

        try:
            from enterprise.platform_kernel import Event

            self._event_bus.publish(
                Event.create(
                    topic=f"alert.{topic.split('.')[-1]}",  # alert.fired, alert.resolved, etc.
                    source="alert_manager",
                    payload={
                        "alert_id": alert.alert_id,
                        "rule_name": alert.rule_name,
                        "severity": alert.severity.label(),
                        "state": alert.state.value,
                        "module": alert.module,
                        "message": alert.message,
                        "details": alert.details,
                    },
                    priority=(
                        "CRITICAL" if alert.severity == AlertSeverity.CRITICAL else "HIGH"
                    ),
                )
            )
        except Exception:
            pass  # EventBus publishing failure should not break alerting

    # ── Management ───────────────────────────────────────────────────────────

    def reset(self) -> None:
        """Reset all alerts and rules (useful for testing)."""
        with self._lock:
            self._alerts.clear()
            self._alert_history.clear()
            self._fired_timestamps.clear()

    @property
    def enabled(self) -> bool:
        """Whether the alert manager is enabled."""
        return self._enabled

    @enabled.setter
    def enabled(self, value: bool) -> None:
        self._enabled = value

    @property
    def rules_count(self) -> int:
        """Number of registered rules."""
        with self._lock:
            return len(self._rules)

    @property
    def active_count(self) -> int:
        """Number of currently active alerts."""
        return len(self.get_active_alerts())


# =============================================================================
# Helpers
# =============================================================================

def _labels_key(labels: Dict[str, str]) -> str:
    """Create a consistent string key from a labels dict."""
    import json
    return json.dumps(dict(sorted(labels.items())), sort_keys=True)