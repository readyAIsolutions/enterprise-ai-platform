"""
Crisis management system.

Handles crisis declaration, role assignment, stakeholder communication,
regulatory notification, vendor/executive escalation, and crisis resolution.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger("enterprise.disaster_recovery.crisis")


class CrisisRole(str, Enum):
    """Roles assigned during a crisis."""

    INCIDENT_COMMANDER = "incident_commander"
    TECHNICAL_LEAD = "technical_lead"
    SECURITY_LEAD = "security_lead"
    COMMS_LEAD = "comms_lead"
    LEGAL_CONTACT = "legal_contact"


class CrisisSeverity(str, Enum):
    """Severity classification for a crisis."""

    SEV_1_CRITICAL = "sev1_critical"     # Production down, revenue impact
    SEV_2_MAJOR = "sev2_major"           # Major functionality degraded
    SEV_3_MINOR = "sev3_minor"           # Minor disruption
    SEV_4_INFORMATIONAL = "sev4_info"    # Observation / investigation


@dataclass
class CrisisTeam:
    """Team members assigned during a crisis."""

    roles: Dict[CrisisRole, str] = field(default_factory=dict)
    primary_contacts: List[str] = field(default_factory=list)
    escalation_contacts: List[str] = field(default_factory=list)

    def is_fully_staffed(self) -> bool:
        """Check if all critical roles are filled."""
        required = {CrisisRole.INCIDENT_COMMANDER, CrisisRole.TECHNICAL_LEAD}
        return required.issubset(set(self.roles.keys()))

    def to_dict(self) -> dict:
        return {
            "roles": {r.value: name for r, name in self.roles.items()},
            "primary_contacts": self.primary_contacts,
            "escalation_contacts": self.escalation_contacts,
        }


@dataclass
class CrisisPlan:
    """Active crisis tracking record."""

    incident_id: str
    severity: CrisisSeverity
    commander: str
    team: CrisisTeam = field(default_factory=CrisisTeam)
    customer_comms_process: str = ""
    internal_update_cadence_minutes: int = 30
    regulator_notification_required: bool = False
    vendor_escalation_list: List[str] = field(default_factory=list)
    executive_escalation_list: List[str] = field(default_factory=list)
    declared_at: datetime = field(default_factory=datetime.utcnow)
    resolved_at: Optional[datetime] = None
    status_updates: List[Dict[str, Any]] = field(default_factory=list)
    notifications_sent: Dict[str, datetime] = field(default_factory=dict)
    escalated_items: List[Dict[str, str]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_resolved(self) -> bool:
        return self.resolved_at is not None

    @property
    def duration_minutes(self) -> float:
        end = self.resolved_at or datetime.utcnow()
        return (end - self.declared_at).total_seconds() / 60.0

    def to_dict(self) -> dict:
        return {
            "incident_id": self.incident_id,
            "severity": self.severity.value,
            "commander": self.commander,
            "declared_at": self.declared_at.isoformat(),
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
            "duration_minutes": self.duration_minutes,
            "is_resolved": self.is_resolved,
        }


class CrisisManager:
    """
    Crisis management coordinator.

    Declares crises, assigns roles, manages stakeholder and customer
    communications, handles regulatory notifications, escalates to vendors
    and executives, and tracks crisis through to resolution.
    """

    def __init__(self) -> None:
        self._active_crises: Dict[str, CrisisPlan] = {}
        self._resolved_crises: Dict[str, CrisisPlan] = {}
        self._contacts: Dict[str, List[str]] = {
            "customers": [],
            "regulators": [],
            "vendors": {},
            "executives": [],
        }
        self._hooks: Dict[str, Callable] = {}
        self._role_roster: Dict[CrisisRole, List[str]] = {}

    # ------------------------------------------------------------------
    # Hooks
    # ------------------------------------------------------------------

    def register_hook(self, name: str, fn: Callable) -> None:
        """Register an external communication callable."""
        self._hooks[name] = fn
        logger.debug("Registered crisis hook: %s", name)

    def set_role_roster(self, role: CrisisRole, people: List[str]) -> None:
        """Define the roster of available people for a given crisis role."""
        self._role_roster[role] = people

    # ------------------------------------------------------------------
    # Crisis lifecycle
    # ------------------------------------------------------------------

    def declare_crisis(
        self,
        severity: CrisisSeverity,
        commander: str,
        customer_comms_process: str = "",
        internal_update_cadence_minutes: int = 30,
        regulator_notification_required: bool = False,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> CrisisPlan:
        """Declare a new crisis and return the plan."""
        incident_id = f"crisis-{uuid.uuid4().hex[:12]}"
        plan = CrisisPlan(
            incident_id=incident_id,
            severity=severity,
            commander=commander,
            team=CrisisTeam(roles={CrisisRole.INCIDENT_COMMANDER: commander}),
            customer_comms_process=customer_comms_process,
            internal_update_cadence_minutes=internal_update_cadence_minutes,
            regulator_notification_required=regulator_notification_required,
            metadata=metadata or {},
        )
        self._active_crises[incident_id] = plan
        logger.info("Crisis declared: %s (severity=%s, commander=%s)", incident_id, severity.value, commander)
        return plan

    def assign_roles(self, incident_id: str, assignments: Dict[CrisisRole, str]) -> bool:
        """Assign personnel to crisis roles."""
        plan = self._get_active(incident_id)
        if plan is None:
            return False

        for role, person in assignments.items():
            plan.team.roles[role] = person
            logger.info("Assigned %s to %s for %s", person, role.value, incident_id)

        return plan.team.is_fully_staffed()

    # ------------------------------------------------------------------
    # Communications
    # ------------------------------------------------------------------

    def notify_customers(
        self,
        incident_id: str,
        message: str,
        channels: Optional[List[str]] = None,
    ) -> bool:
        """Send customer-facing communication about the crisis."""
        plan = self._get_active(incident_id)
        if plan is None:
            return False

        if "notify_customers" in self._hooks:
            self._hooks["notify_customers"](
                incident_id=incident_id,
                message=message,
                channels=channels or ["email", "status_page"],
            )

        plan.notifications_sent["customers"] = datetime.utcnow()
        plan.status_updates.append({
            "type": "customer_notification",
            "message": message,
            "channels": channels,
            "timestamp": datetime.utcnow().isoformat(),
        })
        logger.info("Customers notified for %s: %s", incident_id, message[:100])
        return True

    def update_internal_stakeholders(
        self,
        incident_id: str,
        update_text: str,
    ) -> bool:
        """Send internal update to stakeholders."""
        plan = self._get_active(incident_id)
        if plan is None:
            return False

        if "internal_update" in self._hooks:
            self._hooks["internal_update"](incident_id=incident_id, update=update_text)

        plan.status_updates.append({
            "type": "internal_update",
            "update": update_text,
            "timestamp": datetime.utcnow().isoformat(),
        })
        logger.info("Internal stakeholders updated for %s", incident_id)
        return True

    # ------------------------------------------------------------------
    # Notifications & escalations
    # ------------------------------------------------------------------

    def notify_regulators(self, incident_id: str) -> bool:
        """Notify regulatory bodies if required."""
        plan = self._get_active(incident_id)
        if plan is None:
            return False
        if not plan.regulator_notification_required:
            logger.info("Regulator notification not required for %s", incident_id)
            return True

        if "notify_regulators" in self._hooks:
            self._hooks["notify_regulators"](incident_id=incident_id)

        plan.notifications_sent["regulators"] = datetime.utcnow()
        logger.info("Regulators notified for %s", incident_id)
        return True

    def escalate_to_vendor(
        self,
        incident_id: str,
        vendor: str,
        reason: str,
    ) -> bool:
        """Escalate an issue to a vendor."""
        plan = self._get_active(incident_id)
        if plan is None:
            return False

        if "escalate_vendor" in self._hooks:
            self._hooks["escalate_vendor"](incident_id=incident_id, vendor=vendor, reason=reason)

        plan.escalated_items.append({
            "type": "vendor",
            "target": vendor,
            "reason": reason,
            "timestamp": datetime.utcnow().isoformat(),
        })
        logger.info("Escalated to vendor '%s' for %s: %s", vendor, incident_id, reason)
        return True

    def escalate_to_executive(
        self,
        incident_id: str,
        executive: str,
        reason: str,
    ) -> bool:
        """Escalate an issue to executive leadership."""
        plan = self._get_active(incident_id)
        if plan is None:
            return False

        if "escalate_executive" in self._hooks:
            self._hooks["escalate_executive"](incident_id=incident_id, executive=executive, reason=reason)

        plan.escalated_items.append({
            "type": "executive",
            "target": executive,
            "reason": reason,
            "timestamp": datetime.utcnow().isoformat(),
        })
        logger.info("Escalated to executive '%s' for %s: %s", executive, incident_id, reason)
        return True

    # ------------------------------------------------------------------
    # Resolution
    # ------------------------------------------------------------------

    def track_resolution(self, incident_id: str, update: str) -> bool:
        """Log a resolution progress update."""
        plan = self._get_active(incident_id)
        if plan is None:
            return False

        plan.status_updates.append({
            "type": "resolution_update",
            "update": update,
            "timestamp": datetime.utcnow().isoformat(),
        })
        logger.info("Resolution progress for %s: %s", incident_id, update[:100])
        return True

    def close_crisis(
        self,
        incident_id: str,
        resolution_summary: str = "",
    ) -> bool:
        """Close a crisis and move it to resolved."""
        plan = self._get_active(incident_id)
        if plan is None:
            logger.warning("close_crisis: no active crisis %s", incident_id)
            return False

        plan.resolved_at = datetime.utcnow()
        plan.status_updates.append({
            "type": "resolution",
            "summary": resolution_summary,
            "timestamp": plan.resolved_at.isoformat(),
        })

        self._active_crises.pop(incident_id)
        self._resolved_crises[incident_id] = plan
        logger.info(
            "Crisis %s closed after %.1f minutes: %s",
            incident_id, plan.duration_minutes, resolution_summary[:100],
        )
        return True

    # ------------------------------------------------------------------
    # Accessors
    # ------------------------------------------------------------------

    def get_crisis(self, incident_id: str) -> Optional[CrisisPlan]:
        """Retrieve any crisis by ID (active or resolved)."""
        return self._active_crises.get(incident_id) or self._resolved_crises.get(incident_id)

    def list_active(self) -> List[CrisisPlan]:
        """Return all currently active crises."""
        return list(self._active_crises.values())

    def list_resolved(self) -> List[CrisisPlan]:
        """Return all resolved crises."""
        return list(self._resolved_crises.values())

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _get_active(self, incident_id: str) -> Optional[CrisisPlan]:
        return self._active_crises.get(incident_id)