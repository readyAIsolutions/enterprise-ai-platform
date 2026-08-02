"""
Support Ticket Management Engine.

Handles the complete lifecycle of support tickets from creation
through resolution, including SLA tracking, escalation, and
root-cause analysis.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger("enterprise.customer_experience")


class SeverityLevel(Enum):
    """Support ticket severity levels."""

    SEV1_CRITICAL = ("sev1_critical", 15, 1)      # response min, resolution hrs
    SEV2_HIGH = ("sev2_high", 30, 4)
    SEV3_MEDIUM = ("sev3_medium", 60, 8)
    SEV4_LOW = ("sev4_low", 240, 24)
    SEV5_COSMETIC = ("sev5_cosmetic", 480, 72)

    def __init__(self, value: str, response_minutes: int, resolution_hours: int):
        self._value_ = value
        self.response_minutes = response_minutes
        self.resolution_hours = resolution_hours

    @classmethod
    def from_string(cls, name: str) -> "SeverityLevel":
        for sev in cls:
            if sev.name == name.upper():
                return sev
        raise ValueError(f"Unknown severity: {name}")


class TicketStatus(Enum):
    """Statuses a support ticket can transition through."""

    NEW = "new"
    TRIAGED = "triaged"
    IN_PROGRESS = "in_progress"
    WAITING_CUSTOMER = "waiting_customer"
    WAITING_VENDOR = "waiting_vendor"
    RESOLVED = "resolved"
    CLOSED = "closed"
    REOPENED = "reopened"


# Allowed transitions from each status
_VALID_TRANSITIONS: Dict[TicketStatus, List[TicketStatus]] = {
    TicketStatus.NEW: [
        TicketStatus.TRIAGED,
        TicketStatus.IN_PROGRESS,
        TicketStatus.CLOSED,
    ],
    TicketStatus.TRIAGED: [
        TicketStatus.IN_PROGRESS,
        TicketStatus.WAITING_CUSTOMER,
    ],
    TicketStatus.IN_PROGRESS: [
        TicketStatus.WAITING_CUSTOMER,
        TicketStatus.WAITING_VENDOR,
        TicketStatus.RESOLVED,
    ],
    TicketStatus.WAITING_CUSTOMER: [
        TicketStatus.IN_PROGRESS,
        TicketStatus.CLOSED,
    ],
    TicketStatus.WAITING_VENDOR: [
        TicketStatus.IN_PROGRESS,
        TicketStatus.RESOLVED,
    ],
    TicketStatus.RESOLVED: [
        TicketStatus.CLOSED,
        TicketStatus.REOPENED,
        TicketStatus.WAITING_CUSTOMER,
    ],
    TicketStatus.CLOSED: [TicketStatus.REOPENED],
    TicketStatus.REOPENED: [
        TicketStatus.IN_PROGRESS,
        TicketStatus.TRIAGED,
    ],
}


@dataclass
class SupportTicket:
    """A single support ticket with full lifecycle metadata."""

    ticket_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    severity: SeverityLevel = SeverityLevel.SEV4_LOW
    status: TicketStatus = TicketStatus.NEW
    subject: str = ""
    description: str = ""
    customer_id: str = ""
    assigned_to: Optional[str] = None
    response_target_minutes: int = 240
    resolution_target_hours: int = 24
    escalation_level: int = 0
    root_cause: Optional[str] = None
    resolution: Optional[str] = None
    kb_article_updated: bool = False
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    resolved_at: Optional[datetime] = None
    status_history: List[Dict[str, Any]] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)


class SupportEngine:
    """Engine for managing support ticket workflows."""

    def __init__(self) -> None:
        self._tickets: Dict[str, SupportTicket] = {}
        logger.info("SupportEngine initialized")

    # ------------------------------------------------------------------
    # Ticket CRUD
    # ------------------------------------------------------------------

    def create_ticket(
        self,
        customer_id: str,
        subject: str,
        description: str,
        severity: SeverityLevel = SeverityLevel.SEV4_LOW,
    ) -> SupportTicket:
        """Create and register a new support ticket."""
        ticket = SupportTicket(
            severity=severity,
            subject=subject,
            description=description,
            customer_id=customer_id,
            response_target_minutes=severity.response_minutes,
            resolution_target_hours=severity.resolution_hours,
        )
        ticket.status_history.append({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "from": None,
            "to": TicketStatus.NEW.value,
        })
        self._tickets[ticket.ticket_id] = ticket
        logger.info(
            "Created ticket %s [%s] for customer '%s'",
            ticket.ticket_id,
            severity.name,
            customer_id,
        )
        return ticket

    def get_ticket(self, ticket_id: str) -> Optional[SupportTicket]:
        return self._tickets.get(ticket_id)

    # ------------------------------------------------------------------
    # Workflow actions
    # ------------------------------------------------------------------

    def triage(self, ticket_id: str) -> SupportTicket:
        """Triage a new ticket, setting first severity assessment."""
        ticket = self._get_or_raise(ticket_id)
        self._transition(ticket, TicketStatus.TRIAGED)
        logger.info("Ticket %s triaged", ticket_id)
        return ticket

    def assign(self, ticket_id: str, assignee: str) -> SupportTicket:
        """Assign a ticket to a support agent."""
        ticket = self._get_or_raise(ticket_id)
        ticket.assigned_to = assignee
        ticket.notes.append(
            f"{datetime.now(timezone.utc).isoformat()}: Assigned to {assignee}"
        )
        # Auto-transition to in-progress if still NEW
        if ticket.status == TicketStatus.NEW:
            self._transition(ticket, TicketStatus.IN_PROGRESS)
        elif ticket.status == TicketStatus.TRIAGED:
            self._transition(ticket, TicketStatus.IN_PROGRESS)
        logger.info("Ticket %s assigned to '%s'", ticket_id, assignee)
        return ticket

    def update_status(
        self,
        ticket_id: str,
        new_status: TicketStatus,
        comment: Optional[str] = None,
    ) -> SupportTicket:
        """Transition a ticket to a new status."""
        ticket = self._get_or_raise(ticket_id)
        self._transition(ticket, new_status)

        if new_status == TicketStatus.RESOLVED and ticket.resolved_at is None:
            ticket.resolved_at = datetime.now(timezone.utc)
        if new_status == TicketStatus.REOPENED:
            ticket.resolved_at = None

        if comment:
            ticket.notes.append(
                f"{datetime.now(timezone.utc).isoformat()}: {comment}"
            )

        logger.info("Ticket %s -> %s", ticket_id, new_status.value)
        return ticket

    def escalate(self, ticket_id: str) -> SupportTicket:
        """Escalate a ticket to the next severity level."""
        ticket = self._get_or_raise(ticket_id)
        if ticket.escalation_level >= 4:
            logger.warning("Ticket %s already at max escalation", ticket_id)
            return ticket

        ticket.escalation_level += 1
        sev_order = list(SeverityLevel)
        idx = sev_order.index(ticket.severity)
        if idx > 0:
            ticket.severity = sev_order[idx - 1]
            ticket.response_target_minutes = ticket.severity.response_minutes
            ticket.resolution_target_hours = ticket.severity.resolution_hours

        ticket.notes.append(
            f"{datetime.now(timezone.utc).isoformat()}: Escalated to "
            f"level {ticket.escalation_level} ({ticket.severity.value})"
        )
        logger.warning(
            "Ticket %s escalated to %s (level %d)",
            ticket_id,
            ticket.severity.value,
            ticket.escalation_level,
        )
        return ticket

    # ------------------------------------------------------------------
    # SLA calculations
    # ------------------------------------------------------------------

    def calculate_response_sla(self, ticket_id: str) -> Dict[str, Any]:
        """Calculate response-time SLA status for a ticket."""
        ticket = self._get_or_raise(ticket_id)
        now = datetime.now(timezone.utc)
        elapsed = now - ticket.created_at
        elapsed_minutes = elapsed.total_seconds() / 60.0
        target = ticket.response_target_minutes

        # First non-NEW status timestamp for actual response
        first_responded_at: Optional[datetime] = None
        for entry in ticket.status_history:
            if entry["to"] not in (TicketStatus.NEW.value,):
                first_responded_at = datetime.fromisoformat(entry["timestamp"])
                break

        actual_response = None
        if first_responded_at:
            actual_response = (first_responded_at - ticket.created_at).total_seconds() / 60.0

        breached = actual_response is not None and actual_response > target
        remaining = max(0.0, target - elapsed_minutes) if not actual_response else 0.0

        result = {
            "ticket_id": ticket_id,
            "severity": ticket.severity.value,
            "target_minutes": target,
            "elapsed_minutes": round(elapsed_minutes, 1),
            "actual_response_minutes": round(actual_response, 1) if actual_response else None,
            "breached": breached,
            "remaining_minutes": round(remaining, 1),
            "sla_status": (
                "breached"
                if breached
                else "met"
                if actual_response is not None
                else "pending"
            ),
        }
        logger.debug("Response SLA for %s: %s", ticket_id, result["sla_status"])
        return result

    def calculate_resolution_sla(self, ticket_id: str) -> Dict[str, Any]:
        """Calculate resolution-time SLA status for a ticket."""
        ticket = self._get_or_raise(ticket_id)
        now = datetime.now(timezone.utc)
        elapsed_hours = (now - ticket.created_at).total_seconds() / 3600.0
        target = ticket.resolution_target_hours

        actual_hours = None
        if ticket.resolved_at:
            actual_hours = (
                ticket.resolved_at - ticket.created_at
            ).total_seconds() / 3600.0

        breached = actual_hours is not None and actual_hours > target
        at_risk = not ticket.resolved_at and elapsed_hours > (target * 0.75)

        result = {
            "ticket_id": ticket_id,
            "severity": ticket.severity.value,
            "target_hours": target,
            "elapsed_hours": round(elapsed_hours, 1),
            "actual_resolution_hours": round(actual_hours, 1) if actual_hours else None,
            "breached": breached,
            "at_risk": at_risk,
            "sla_status": (
                "breached"
                if breached
                else "at_risk"
                if at_risk
                else "met"
                if actual_hours is not None
                else "pending"
            ),
        }
        logger.debug("Resolution SLA for %s: %s", ticket_id, result["sla_status"])
        return result

    # ------------------------------------------------------------------
    # Customer communication
    # ------------------------------------------------------------------

    def generate_customer_update(
        self,
        ticket_id: str,
        include_eta: bool = True,
    ) -> Dict[str, str]:
        """Generate a clear, professional customer-facing update."""
        ticket = self._get_or_raise(ticket_id)
        status_map = {
            TicketStatus.NEW: "received and queued for triage",
            TicketStatus.TRIAGED: "triaged and being prioritized",
            TicketStatus.IN_PROGRESS: "being actively worked on by our team",
            TicketStatus.WAITING_CUSTOMER: "waiting for additional information from you",
            TicketStatus.WAITING_VENDOR: "escalated to our vendor team",
            TicketStatus.RESOLVED: "marked as resolved",
            TicketStatus.CLOSED: "closed",
            TicketStatus.REOPENED: "reopened and under investigation",
        }

        sla = self.calculate_resolution_sla(ticket_id)
        eta = ""
        if include_eta and sla["sla_status"] == "pending":
            remaining = ticket.resolution_target_hours - sla["elapsed_hours"]
            if remaining > 0:
                eta = f" Estimated resolution within {remaining:.1f} hours."

        update = {
            "ticket_id": ticket_id,
            "subject": ticket.subject,
            "status": status_map.get(ticket.status, "under review"),
            "message": (
                f"Your support request (#{ticket_id}) regarding '{ticket.subject}' "
                f"is currently {status_map.get(ticket.status, 'under review')}.{eta}"
            ),
        }

        if ticket.resolution:
            update["resolution"] = ticket.resolution

        return update

    # ------------------------------------------------------------------
    # Knowledge base and root cause
    # ------------------------------------------------------------------

    def update_knowledge_base(
        self,
        ticket_id: str,
        article_content: str,
    ) -> SupportTicket:
        """Mark a ticket's knowledge-base article as updated."""
        ticket = self._get_or_raise(ticket_id)
        ticket.kb_article_updated = True
        ticket.notes.append(
            f"{datetime.now(timezone.utc).isoformat()}: Knowledge base updated"
        )
        logger.info("KB article updated for ticket %s", ticket_id)
        return ticket

    def perform_root_cause_analysis(
        self,
        ticket_id: str,
        root_cause: str,
    ) -> SupportTicket:
        """Record root-cause findings and update resolution."""
        ticket = self._get_or_raise(ticket_id)
        ticket.root_cause = root_cause
        ticket.notes.append(
            f"{datetime.now(timezone.utc).isoformat()}: RCA completed - {root_cause}"
        )
        logger.info("RCA complete for ticket %s: %s", ticket_id, root_cause)
        return ticket

    # ------------------------------------------------------------------
    # Bulk operations
    # ------------------------------------------------------------------

    def list_by_severity(self, severity: SeverityLevel) -> List[SupportTicket]:
        return [t for t in self._tickets.values() if t.severity == severity]

    def list_by_status(self, status: TicketStatus) -> List[SupportTicket]:
        return [t for t in self._tickets.values() if t.status == status]

    def list_by_customer(self, customer_id: str) -> List[SupportTicket]:
        return [t for t in self._tickets.values() if t.customer_id == customer_id]

    def sla_summary(self) -> Dict[str, Any]:
        """Return a summary of SLA status for all tickets."""
        total = len(self._tickets)
        if total == 0:
            return {"total": 0}

        response_breaches = 0
        resolution_breaches = 0
        at_risk = 0

        for ticket_id in self._tickets:
            r = self.calculate_resolution_sla(ticket_id)
            if r["sla_status"] == "breached":
                resolution_breaches += 1
            elif r["sla_status"] == "at_risk":
                at_risk += 1

            resp = self.calculate_response_sla(ticket_id)
            if resp["sla_status"] == "breached":
                response_breaches += 1

        return {
            "total": total,
            "response_sla_breaches": response_breaches,
            "resolution_sla_breaches": resolution_breaches,
            "at_risk": at_risk,
            "response_compliance_pct": round(
                (total - response_breaches) / total * 100, 1
            ) if total else 0.0,
            "resolution_compliance_pct": round(
                (total - resolution_breaches) / total * 100, 1
            ) if total else 0.0,
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_or_raise(self, ticket_id: str) -> SupportTicket:
        ticket = self._tickets.get(ticket_id)
        if ticket is None:
            raise KeyError(f"Ticket '{ticket_id}' not found")
        return ticket

    @staticmethod
    def _transition(ticket: SupportTicket, new_status: TicketStatus) -> None:
        valid = _VALID_TRANSITIONS.get(ticket.status, [])
        if new_status not in valid:
            raise ValueError(
                f"Cannot transition from {ticket.status.value} to {new_status.value}. "
                f"Allowed: {[s.value for s in valid]}"
            )
        ticket.status_history.append({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "from": ticket.status.value,
            "to": new_status.value,
        })
        ticket.status = new_status