"""
Change Classification Engine

Classifies changes by type, determines risk levels, assesses urgency,
and calculates impact radius. Provides templates for standard change types.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger("enterprise.release_change")


class ChangeType(str, Enum):
    """Classification of change types."""
    STANDARD = "standard"
    NORMAL = "normal"
    MAJOR = "major"
    EMERGENCY = "emergency"
    SECURITY = "security"
    DATABASE = "database"
    INFRASTRUCTURE = "infrastructure"
    AI_MODEL = "ai_model"
    PROMPT = "prompt"
    AGENT = "agent"
    API = "api"
    COMPLIANCE = "compliance"
    CONFIGURATION = "configuration"

    @property
    def is_high_stakes(self) -> bool:
        """Whether this change type carries inherently high stakes."""
        return self in (
            ChangeType.EMERGENCY, ChangeType.SECURITY, ChangeType.MAJOR,
            ChangeType.COMPLIANCE,
        )

    @property
    def default_cab_required(self) -> bool:
        """Whether a CAB (Change Advisory Board) approval is typically needed."""
        return self in (
            ChangeType.MAJOR, ChangeType.EMERGENCY, ChangeType.COMPLIANCE,
            ChangeType.SECURITY, ChangeType.INFRASTRUCTURE, ChangeType.DATABASE,
        )


class RiskLevel(str, Enum):
    """Risk classification for changes."""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"

    @classmethod
    def from_score(cls, score: float) -> "RiskLevel":
        """Determine risk level from a numeric score (0.0-1.0)."""
        if score >= 0.85:
            return cls.CRITICAL
        elif score >= 0.65:
            return cls.HIGH
        elif score >= 0.35:
            return cls.MEDIUM
        return cls.LOW

    @property
    def numeric_level(self) -> int:
        """Numeric representation for comparison (0=low, 3=critical)."""
        return {RiskLevel.LOW: 0, RiskLevel.MEDIUM: 1, RiskLevel.HIGH: 2, RiskLevel.CRITICAL: 3}[self]


@dataclass
class ChangeTemplate:
    """Pre-defined template for a specific change type.

    Attributes:
        change_type: The type of change this template applies to.
        default_risk: Default risk level for this change type.
        required_approvals: Minimum number of approvals needed.
        required_tests: List of test categories required (unit, integration, e2e, etc.).
        standard_rollback: Standard rollback procedure description.
        max_downtime_minutes: Maximum acceptable downtime in minutes.
        notification_required: Whether advance notification is required.
        cab_approval_required: Whether CAB approval is required.
    """
    change_type: ChangeType
    default_risk: RiskLevel = RiskLevel.MEDIUM
    required_approvals: int = 1
    required_tests: List[str] = field(default_factory=list)
    standard_rollback: str = "Roll back to previous known-good version"
    max_downtime_minutes: int = 60
    notification_required: bool = False
    cab_approval_required: bool = False

    def to_dict(self) -> Dict[str, Any]:
        """Serialize the template to a dictionary."""
        return {
            "change_type": self.change_type.value,
            "default_risk": self.default_risk.value,
            "required_approvals": self.required_approvals,
            "required_tests": self.required_tests,
            "standard_rollback": self.standard_rollback,
            "max_downtime_minutes": self.max_downtime_minutes,
            "notification_required": self.notification_required,
            "cab_approval_required": self.cab_approval_required,
        }


# ─── Default Templates ────────────────────────────────────────────────────────

DEFAULT_TEMPLATES: Dict[ChangeType, ChangeTemplate] = {
    ChangeType.STANDARD: ChangeTemplate(
        change_type=ChangeType.STANDARD,
        default_risk=RiskLevel.LOW,
        required_approvals=1,
        required_tests=["unit", "integration"],
        max_downtime_minutes=5,
        notification_required=False,
        cab_approval_required=False,
    ),
    ChangeType.NORMAL: ChangeTemplate(
        change_type=ChangeType.NORMAL,
        default_risk=RiskLevel.MEDIUM,
        required_approvals=1,
        required_tests=["unit", "integration"],
        max_downtime_minutes=15,
        notification_required=True,
        cab_approval_required=False,
    ),
    ChangeType.MAJOR: ChangeTemplate(
        change_type=ChangeType.MAJOR,
        default_risk=RiskLevel.HIGH,
        required_approvals=2,
        required_tests=["unit", "integration", "e2e", "performance", "load"],
        max_downtime_minutes=60,
        notification_required=True,
        cab_approval_required=True,
    ),
    ChangeType.EMERGENCY: ChangeTemplate(
        change_type=ChangeType.EMERGENCY,
        default_risk=RiskLevel.CRITICAL,
        required_approvals=1,
        required_tests=["unit", "integration", "smoke"],
        standard_rollback="Immediate rollback upon any anomaly detection",
        max_downtime_minutes=5,
        notification_required=True,
        cab_approval_required=True,
    ),
    ChangeType.SECURITY: ChangeTemplate(
        change_type=ChangeType.SECURITY,
        default_risk=RiskLevel.CRITICAL,
        required_approvals=2,
        required_tests=["unit", "integration", "security_scan", "penetration"],
        standard_rollback="Revert to last secure baseline; rotate exposed secrets",
        max_downtime_minutes=15,
        notification_required=True,
        cab_approval_required=True,
    ),
    ChangeType.DATABASE: ChangeTemplate(
        change_type=ChangeType.DATABASE,
        default_risk=RiskLevel.HIGH,
        required_approvals=2,
        required_tests=["unit", "integration", "migration", "rollback"],
        standard_rollback="Revert schema via migration rollback; restore from snapshot",
        max_downtime_minutes=120,
        notification_required=True,
        cab_approval_required=True,
    ),
    ChangeType.INFRASTRUCTURE: ChangeTemplate(
        change_type=ChangeType.INFRASTRUCTURE,
        default_risk=RiskLevel.HIGH,
        required_approvals=2,
        required_tests=["unit", "integration", "infra_validation", "drift_detection"],
        standard_rollback="Re-apply previous IaC state; validate resource consistency",
        max_downtime_minutes=30,
        notification_required=True,
        cab_approval_required=True,
    ),
    ChangeType.AI_MODEL: ChangeTemplate(
        change_type=ChangeType.AI_MODEL,
        default_risk=RiskLevel.MEDIUM,
        required_approvals=1,
        required_tests=["unit", "evaluation", "fairness", "accuracy"],
        standard_rollback="Switch to previous model version via model registry",
        max_downtime_minutes=10,
        notification_required=False,
        cab_approval_required=False,
    ),
    ChangeType.PROMPT: ChangeTemplate(
        change_type=ChangeType.PROMPT,
        default_risk=RiskLevel.LOW,
        required_approvals=1,
        required_tests=["unit", "prompt_eval"],
        standard_rollback="Revert to previous prompt template version",
        max_downtime_minutes=0,
        notification_required=False,
        cab_approval_required=False,
    ),
    ChangeType.AGENT: ChangeTemplate(
        change_type=ChangeType.AGENT,
        default_risk=RiskLevel.MEDIUM,
        required_approvals=1,
        required_tests=["unit", "integration", "behavioral", "safety"],
        standard_rollback="Stop agent instance; restart with previous version",
        max_downtime_minutes=5,
        notification_required=False,
        cab_approval_required=False,
    ),
    ChangeType.API: ChangeTemplate(
        change_type=ChangeType.API,
        default_risk=RiskLevel.MEDIUM,
        required_approvals=1,
        required_tests=["unit", "integration", "contract", "backward_compat"],
        standard_rollback="Deploy previous API version; drain connections gracefully",
        max_downtime_minutes=5,
        notification_required=True,
        cab_approval_required=False,
    ),
    ChangeType.COMPLIANCE: ChangeTemplate(
        change_type=ChangeType.COMPLIANCE,
        default_risk=RiskLevel.CRITICAL,
        required_approvals=3,
        required_tests=["unit", "integration", "compliance_check", "audit_trail"],
        standard_rollback="Revert to last compliant baseline; notify compliance officer",
        max_downtime_minutes=15,
        notification_required=True,
        cab_approval_required=True,
    ),
    ChangeType.CONFIGURATION: ChangeTemplate(
        change_type=ChangeType.CONFIGURATION,
        default_risk=RiskLevel.LOW,
        required_approvals=1,
        required_tests=["unit", "config_validation"],
        standard_rollback="Revert to previous configuration version",
        max_downtime_minutes=0,
        notification_required=False,
        cab_approval_required=False,
    ),
}


class ChangeClassifier:
    """Classifies and assesses changes for risk, urgency, and impact.

    Usage:
        classifier = ChangeClassifier()
        template = classifier.get_template(ChangeType.SECURITY)
        risk = classifier.determine_risk(ChangeType.MAJOR, affected_systems=15, data_changes=True)
    """

    def __init__(self, templates: Optional[Dict[ChangeType, ChangeTemplate]] = None) -> None:
        self._templates: Dict[ChangeType, ChangeTemplate] = dict(templates or DEFAULT_TEMPLATES)
        self._classification_count = 0

    # ── Template Management ────────────────────────────────────────────────

    def get_template(self, change_type: ChangeType) -> ChangeTemplate:
        """Get the default template for a change type.

        Returns a copy to prevent mutation of the master template.
        """
        template = self._templates.get(change_type)
        if template is None:
            logger.warning("No template for %s, returning default", change_type.value)
            template = ChangeTemplate(change_type=change_type)
        return ChangeTemplate(
            change_type=template.change_type,
            default_risk=template.default_risk,
            required_approvals=template.required_approvals,
            required_tests=list(template.required_tests),
            standard_rollback=template.standard_rollback,
            max_downtime_minutes=template.max_downtime_minutes,
            notification_required=template.notification_required,
            cab_approval_required=template.cab_approval_required,
        )

    def register_template(self, template: ChangeTemplate) -> None:
        """Register or override a template for a change type."""
        self._templates[template.change_type] = template
        logger.info("Registered template for %s", template.change_type.value)

    def list_templates(self) -> List[ChangeTemplate]:
        """List all registered templates."""
        return list(self._templates.values())

    # ── Classification ─────────────────────────────────────────────────────

    def classify_change(
        self,
        change_type: ChangeType,
        title: str = "",
        description: str = "",
    ) -> Dict[str, Any]:
        """Classify a change and return its classification details.

        Returns a dict with type, risk, approvals needed, tests needed, etc.
        """
        self._classification_count += 1
        template = self.get_template(change_type)
        return {
            "change_type": change_type.value,
            "default_risk": template.default_risk.value,
            "required_approvals": template.required_approvals,
            "required_tests": template.required_tests,
            "standard_rollback": template.standard_rollback,
            "max_downtime_minutes": template.max_downtime_minutes,
            "notification_required": template.notification_required,
            "cab_approval_required": template.cab_approval_required,
            "is_high_stakes": change_type.is_high_stakes,
        }

    def determine_risk(
        self,
        change_type: ChangeType,
        affected_systems: int = 1,
        data_changes: bool = False,
        user_facing: bool = False,
        dependency_count: int = 0,
        past_incidents: int = 0,
    ) -> RiskLevel:
        """Determine the risk level based on multiple factors.

        Weighted heuristic:
          - change_type base score (from template default_risk)
          - affected_systems count (more = riskier)
          - data_changes flag (adds risk)
          - user_facing flag (adds risk)
          - dependency_count (more dependencies = more risk)
          - past_incidents (more past incidents = higher risk)

        Returns:
            The calculated RiskLevel.
        """
        template = self.get_template(change_type)
        base = template.default_risk.numeric_level / 3.0  # Normalize to 0–1

        # Normalize each factor to 0–1
        systems_factor = min(1.0, affected_systems / 50.0)
        data_factor = 0.80 if data_changes else 0.0
        user_factor = 0.20 if user_facing else 0.0
        dep_factor = min(1.0, dependency_count / 20.0)
        incident_factor = min(1.0, past_incidents / 5.0)

        # Weighted sum
        weights = {
            "base": 0.35,
            "systems": 0.15,
            "data": 0.18,
            "user": 0.10,
            "deps": 0.12,
            "incidents": 0.10,
        }
        score = (
            weights["base"] * base
            + weights["systems"] * systems_factor
            + weights["data"] * data_factor
            + weights["user"] * user_factor
            + weights["deps"] * dep_factor
            + weights["incidents"] * incident_factor
        )
        score = min(1.0, max(0.0, score))
        return RiskLevel.from_score(score)

    def get_required_approvals(self, change_type: ChangeType) -> int:
        """Get the minimum number of approvals required for a change type."""
        return self.get_template(change_type).required_approvals

    def assess_urgency(
        self,
        change_type: ChangeType,
        incident_active: bool = False,
        sla_hours_remaining: float = 24.0,
        revenue_impact: bool = False,
    ) -> str:
        """Assess the urgency level of a change.

        Returns one of: 'immediate', 'high', 'medium', 'low', 'scheduled'.
        """
        if incident_active or change_type == ChangeType.EMERGENCY:
            return "immediate"
        if change_type == ChangeType.SECURITY:
            return "high"
        if sla_hours_remaining < 4:
            return "high"
        if revenue_impact:
            return "high"
        if sla_hours_remaining < 24:
            return "medium"
        if change_type in (ChangeType.MAJOR, ChangeType.COMPLIANCE):
            return "medium"
        return "scheduled"

    def calculate_impact_radius(
        self,
        affected_systems: List[str],
        dependencies: Optional[Dict[str, List[str]]] = None,
    ) -> Dict[str, Any]:
        """Calculate the blast radius / impact radius of a change.

        Uses a dependency map to compute transitive closure of affected systems.

        Args:
            affected_systems: Systems directly affected.
            dependencies: Mapping of system -> list of downstream systems.

        Returns:
            Dict with direct, indirect, and total affected counts.
        """
        direct = set(affected_systems)
        indirect: set = set()
        deps = dependencies or {}

        # BFS for transitive dependencies
        queue = list(direct)
        visited = set(queue)
        while queue:
            sys = queue.pop(0)
            if sys in deps:
                for downstream in deps[sys]:
                    if downstream not in visited:
                        visited.add(downstream)
                        indirect.add(downstream)
                        queue.append(downstream)

        return {
            "direct_impact": sorted(direct),
            "indirect_impact": sorted(indirect),
            "total_affected": len(direct | indirect),
            "direct_count": len(direct),
            "indirect_count": len(indirect),
            "radius_score": min(1.0, (len(direct) + len(indirect) * 0.5) / 100.0),
        }

    @property
    def classification_count(self) -> int:
        """Number of classifications performed."""
        return self._classification_count