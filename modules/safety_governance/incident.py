"""
AI Safety & Governance OS — Incident Response Module
====================================================
Enterprise-grade incident response for AI safety: classification, containment,
isolation, capability disablement, notification, log preservation, root cause
investigation, remediation tracking, retesting, lessons learned, guardrail
updates, and post-incident review automation.

All major classes are thread-safe and self-contained.
"""

import re
import time
import json
import logging
import threading
import uuid
import hashlib
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Dict, List, Optional, Set, Tuple, Union
from collections import defaultdict, deque, OrderedDict

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class IncidentSeverity(Enum):
    """Severity levels for incidents (SEV1-SEV5 standard)."""
    SEV1 = "sev1"  # Critical — system-wide outage, safety breach, active exploitation
    SEV2 = "sev2"  # High — major functionality broken, significant risk
    SEV3 = "sev3"  # Medium — partial degradation, limited impact
    SEV4 = "sev4"  # Low — minor issue, cosmetic, edge case
    SEV5 = "sev5"  # Informational — observation, not an active incident


class IncidentStatus(Enum):
    """Lifecycle status of an incident."""
    DETECTED = "detected"
    TRIAGING = "triaging"
    CONTAINING = "containing"
    INVESTIGATING = "investigating"
    REMEDIATING = "remediating"
    RESOLVED = "resolved"
    CLOSED = "closed"
    POST_MORTEM = "post_mortem"


class ContainmentType(Enum):
    """Types of containment actions available."""
    IMMEDIATE_QUARANTINE = "immediate_quarantine"
    GRACEFUL_SHUTDOWN = "graceful_shutdown"
    CAPABILITY_RESTRICTION = "capability_restriction"
    TRAFFIC_DIVERSION = "traffic_diversion"
    ROLLBACK = "rollback"


class DisablementScope(Enum):
    """Scope of capability disablement."""
    MODEL = "model"
    TOOL = "tool"
    AGENT = "agent"
    ENDPOINT = "endpoint"
    FEATURE_FLAG = "feature_flag"
    FULL_SYSTEM = "full_system"


class EscalationLevel(Enum):
    """Levels of incident escalation."""
    L1_SUPPORT = "l1_support"
    L2_ENGINEERING = "l2_engineering"
    L3_SRE = "l3_sre"
    L4_SECURITY = "l4_security"
    L5_EXECUTIVE = "l5_executive"


class RootCauseCategory(Enum):
    """Categories of root causes for incidents."""
    MODEL_ERROR = "model_error"
    PROMPT_INJECTION = "prompt_injection"
    TOOL_MISUSE = "tool_misuse"
    INFRASTRUCTURE = "infrastructure"
    CONFIGURATION = "configuration"
    HUMAN_ERROR = "human_error"
    EXTERNAL = "external"
    UNKNOWN = "unknown"


class RemediationStatus(Enum):
    """Status of remediation items."""
    PLANNED = "planned"
    IN_PROGRESS = "in_progress"
    DEPLOYED = "deployed"
    VERIFIED = "verified"
    FAILED = "failed"


# ---------------------------------------------------------------------------
# Result Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class Incident:
    """An AI safety incident record."""
    incident_id: str = ""
    severity: IncidentSeverity = IncidentSeverity.SEV5
    status: IncidentStatus = IncidentStatus.DETECTED
    title: str = ""
    description: str = ""
    detected_at: datetime = field(default_factory=datetime.utcnow)
    resolved_at: Optional[datetime] = None
    affected_components: List[str] = field(default_factory=list)
    containment_applied: bool = False
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "incident_id": self.incident_id,
            "severity": self.severity.value,
            "status": self.status.value,
            "title": self.title,
            "description": self.description,
            "detected_at": self.detected_at.isoformat(),
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
            "affected_components": self.affected_components,
            "containment_applied": self.containment_applied,
            "details": self.details,
        }


@dataclass
class ContainmentAction:
    """A containment action applied to an incident."""
    action_id: str = ""
    containment_type: ContainmentType = ContainmentType.IMMEDIATE_QUARANTINE
    applied_at: datetime = field(default_factory=datetime.utcnow)
    applied_by: str = ""
    scope: DisablementScope = DisablementScope.FULL_SYSTEM
    target: str = ""
    rollback_plan: str = ""
    effective: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "action_id": self.action_id,
            "containment_type": self.containment_type.value,
            "applied_at": self.applied_at.isoformat(),
            "applied_by": self.applied_by,
            "scope": self.scope.value,
            "target": self.target,
            "rollback_plan": self.rollback_plan,
            "effective": self.effective,
        }


@dataclass
class EscalationRecord:
    """Record of an incident escalation."""
    incident_id: str = ""
    escalated_from: EscalationLevel = EscalationLevel.L1_SUPPORT
    escalated_to: EscalationLevel = EscalationLevel.L2_ENGINEERING
    escalated_at: datetime = field(default_factory=datetime.utcnow)
    escalated_by: str = ""
    reason: str = ""
    acknowledged: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "incident_id": self.incident_id,
            "escalated_from": self.escalated_from.value,
            "escalated_to": self.escalated_to.value,
            "escalated_at": self.escalated_at.isoformat(),
            "escalated_by": self.escalated_by,
            "reason": self.reason,
            "acknowledged": self.acknowledged,
        }


@dataclass
class RootCauseReport:
    """Root cause investigation report."""
    incident_id: str = ""
    category: RootCauseCategory = RootCauseCategory.UNKNOWN
    description: str = ""
    contributing_factors: List[str] = field(default_factory=list)
    timeline: List[Dict[str, Any]] = field(default_factory=list)
    confidence: float = 0.0
    evidence: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "incident_id": self.incident_id,
            "category": self.category.value,
            "description": self.description,
            "contributing_factors": self.contributing_factors,
            "timeline": self.timeline,
            "confidence": self.confidence,
            "evidence": self.evidence,
        }


@dataclass
class RemediationItem:
    """A remediation item for an incident."""
    item_id: str = ""
    incident_id: str = ""
    description: str = ""
    owner: str = ""
    status: RemediationStatus = RemediationStatus.PLANNED
    due_date: Optional[datetime] = None
    verification_method: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "item_id": self.item_id,
            "incident_id": self.incident_id,
            "description": self.description,
            "owner": self.owner,
            "status": self.status.value,
            "due_date": self.due_date.isoformat() if self.due_date else None,
            "verification_method": self.verification_method,
        }


@dataclass
class LessonsLearned:
    """Lessons learned from an incident."""
    incident_id: str = ""
    what_went_well: List[str] = field(default_factory=list)
    what_went_wrong: List[str] = field(default_factory=list)
    action_items: List[str] = field(default_factory=list)
    guardrail_updates: List[Dict] = field(default_factory=list)
    follow_up_date: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "incident_id": self.incident_id,
            "what_went_well": self.what_went_well,
            "what_went_wrong": self.what_went_wrong,
            "action_items": self.action_items,
            "guardrail_updates": self.guardrail_updates,
            "follow_up_date": self.follow_up_date.isoformat() if self.follow_up_date else None,
        }


@dataclass
class PostIncidentReview:
    """Complete post-incident review."""
    incident_id: str = ""
    incident_summary: str = ""
    root_cause: Optional[RootCauseReport] = None
    timeline: List[Dict] = field(default_factory=list)
    remediation: List[RemediationItem] = field(default_factory=list)
    lessons: Optional[LessonsLearned] = None
    participants: List[str] = field(default_factory=list)
    review_date: datetime = field(default_factory=datetime.utcnow)
    published: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "incident_id": self.incident_id,
            "incident_summary": self.incident_summary,
            "root_cause": self.root_cause.to_dict() if self.root_cause else None,
            "timeline": self.timeline,
            "remediation": [r.to_dict() for r in self.remediation],
            "lessons": self.lessons.to_dict() if self.lessons else None,
            "participants": self.participants,
            "review_date": self.review_date.isoformat(),
            "published": self.published,
        }


# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------

def _generate_id(prefix: str = "") -> str:
    """Generate a short unique identifier."""
    return prefix + uuid.uuid4().hex[:12]


def _compute_hash(data: str) -> str:
    """Compute SHA-256 hash for integrity verification."""
    return hashlib.sha256(data.encode()).hexdigest()


# ---------------------------------------------------------------------------
# 1. IncidentClassifier
# ---------------------------------------------------------------------------

class IncidentClassifier:
    """
    Classifies and assigns severity to incidents based on description
    and affected components.
    """

    # Severity classification keywords
    _SEV1_KEYWORDS = [
        "system-wide", "full outage", "safety breach", "active exploitation",
        "data breach", "critical vulnerability", "complete failure",
        "user harm", "life safety",
    ]
    _SEV2_KEYWORDS = [
        "major", "significant", "widespread", "production down",
        "model serving failure", "injection success", "jailbreak success",
        "unsafe output in production",
    ]
    _SEV3_KEYWORDS = [
        "partial", "degradation", "latency spike", "accuracy drop",
        "hallucination spike", "cost surge",
    ]
    _SEV4_KEYWORDS = [
        "minor", "cosmetic", "edge case", "low impact",
        "isolated", "single user",
    ]

    def __init__(self) -> None:
        self._lock = threading.RLock()

    def classify(
        self,
        title: str,
        description: str,
        affected_components: List[str],
        initial_evidence: Dict[str, Any],
    ) -> Incident:
        """
        Classify a new incident based on provided information.
        Returns a fully populated Incident dataclass.
        """
        incident_id = _generate_id("inc-")
        severity = self.auto_classify_severity(description, affected_components)
        now = datetime.utcnow()

        return Incident(
            incident_id=incident_id,
            severity=severity,
            status=IncidentStatus.DETECTED,
            title=title,
            description=description,
            detected_at=now,
            affected_components=affected_components,
            details={
                "initial_evidence": initial_evidence,
                "classification_method": "auto",
            },
        )

    def auto_classify_severity(
        self, description: str, affected_components: List[str]
    ) -> IncidentSeverity:
        """
        Automatically classify incident severity based on description
        keywords and scope of affected components.
        """
        desc_lower = description.lower()
        component_count = len(affected_components)

        # Check SEV1 keywords first
        for kw in self._SEV1_KEYWORDS:
            if kw in desc_lower:
                return IncidentSeverity.SEV1

        # Full system or many components -> SEV1
        if "full_system" in affected_components or component_count >= 5:
            for kw in self._SEV2_KEYWORDS:
                if kw in desc_lower:
                    return IncidentSeverity.SEV1

        # Check SEV2
        for kw in self._SEV2_KEYWORDS:
            if kw in desc_lower:
                return IncidentSeverity.SEV2

        # Check SEV3
        for kw in self._SEV3_KEYWORDS:
            if kw in desc_lower:
                return IncidentSeverity.SEV3

        # Check SEV4
        for kw in self._SEV4_KEYWORDS:
            if kw in desc_lower:
                return IncidentSeverity.SEV4

        # Default: SEV3 for unknown issues, SEV5 for purely informational
        if "informational" in desc_lower or "observation" in desc_lower:
            return IncidentSeverity.SEV5
        return IncidentSeverity.SEV3

    def to_dict(self) -> dict:
        return {
            "classifier_type": "IncidentClassifier",
            "sev1_keywords": self._SEV1_KEYWORDS,
            "sev2_keywords": self._SEV2_KEYWORDS,
            "sev3_keywords": self._SEV3_KEYWORDS,
        }


# ---------------------------------------------------------------------------
# 2. ContainmentProcedure
# ---------------------------------------------------------------------------

class ContainmentProcedure:
    """
    Executes containment procedures for active incidents.

    Supports immediate quarantine, graceful shutdown, capability restriction,
    traffic diversion, and rollback operations.
    """

    def __init__(self) -> None:
        self._containment_history: Dict[str, ContainmentAction] = {}
        self._quarantined: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.RLock()

    def execute_containment(
        self,
        incident: Incident,
        containment_type: ContainmentType,
        operator: str,
    ) -> ContainmentAction:
        """
        Execute a containment action for an incident.
        Updates the incident status to CONTAINING.
        """
        action_id = _generate_id("ctn-")
        scope = DisablementScope.FULL_SYSTEM

        # Determine scope based on affected components
        if incident.affected_components:
            first_comp = incident.affected_components[0]
            if "model" in first_comp.lower():
                scope = DisablementScope.MODEL
            elif "tool" in first_comp.lower():
                scope = DisablementScope.TOOL
            elif "agent" in first_comp.lower():
                scope = DisablementScope.AGENT
            elif "endpoint" in first_comp.lower():
                scope = DisablementScope.ENDPOINT

        success = False
        rollback_plan = ""

        if containment_type == ContainmentType.IMMEDIATE_QUARANTINE:
            success = self.quarantine(scope, incident.incident_id)
            rollback_plan = f"De-quarantine {scope.value} after investigation confirms safety"
        elif containment_type == ContainmentType.GRACEFUL_SHUTDOWN:
            success = self.graceful_shutdown(incident.incident_id)
            rollback_plan = "Restart affected components after remediation"
        elif containment_type == ContainmentType.CAPABILITY_RESTRICTION:
            success = self.restrict_capabilities(
                incident.incident_id,
                allowed_capabilities=["read_only"],
            )
            rollback_plan = "Restore full capabilities after fix deployment"
        elif containment_type == ContainmentType.TRAFFIC_DIVERSION:
            success = self.divert_traffic(incident.incident_id, "fallback_model")
            rollback_plan = "Restore traffic routing to primary"
        elif containment_type == ContainmentType.ROLLBACK:
            success = True  # Rollback itself is the action
            rollback_plan = "Re-deploy latest version after fix"

        action = ContainmentAction(
            action_id=action_id,
            containment_type=containment_type,
            applied_at=datetime.utcnow(),
            applied_by=operator,
            scope=scope,
            target=incident.incident_id,
            rollback_plan=rollback_plan,
            effective=success,
        )

        with self._lock:
            self._containment_history[action_id] = action
            incident.status = IncidentStatus.CONTAINING
            incident.containment_applied = True

        logger.info(
            "ContainmentProcedure: executed %s for incident %s (effective=%s)",
            containment_type.value, incident.incident_id, success
        )
        return action

    def quarantine(self, scope: DisablementScope, target: str) -> bool:
        """Quarantine a component by scope and target."""
        with self._lock:
            key = f"{scope.value}:{target}"
            self._quarantined[key] = {
                "scope": scope.value,
                "target": target,
                "quarantined_at": datetime.utcnow(),
                "active": True,
            }
            logger.warning("ContainmentProcedure: QUARANTINE %s -> %s", scope.value, target)
            return True

    def graceful_shutdown(self, target: str) -> bool:
        """Perform a graceful shutdown of the target."""
        with self._lock:
            logger.warning("ContainmentProcedure: GRACEFUL SHUTDOWN of %s", target)
            return True

    def restrict_capabilities(self, target: str, allowed_capabilities: List[str]) -> bool:
        """Restrict a component's capabilities to an allowlist."""
        with self._lock:
            logger.warning(
                "ContainmentProcedure: RESTRICT %s to capabilities: %s",
                target, allowed_capabilities,
            )
            return True

    def divert_traffic(self, target: str, diversion_target: str) -> bool:
        """Divert traffic from target to a diversion target."""
        with self._lock:
            logger.warning(
                "ContainmentProcedure: DIVERT traffic from %s to %s",
                target, diversion_target,
            )
            return True

    def to_dict(self) -> dict:
        with self._lock:
            return {
                "containment_actions": len(self._containment_history),
                "actively_quarantined": len(self._quarantined),
                "recent_actions": [
                    a.to_dict()
                    for a in list(self._containment_history.values())[-10:]
                ],
            }


# ---------------------------------------------------------------------------
# 3. IsolationWorkflow
# ---------------------------------------------------------------------------

class IsolationWorkflow:
    """
    Manages isolation of components into cleanroom environments for
    forensic investigation of AI safety incidents.
    """

    def __init__(self) -> None:
        self._isolated_components: Dict[str, Dict[str, Any]] = {}
        self._cleanrooms: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.RLock()

    def isolate_component(self, component_type: str, component_id: str) -> bool:
        """
        Isolate a component from production.

        Args:
            component_type: Type of component (model, agent, tool, endpoint).
            component_id: Unique identifier of the component.

        Returns:
            True if isolation was successful.
        """
        with self._lock:
            key = f"{component_type}:{component_id}"
            self._isolated_components[key] = {
                "component_type": component_type,
                "component_id": component_id,
                "isolated_at": datetime.utcnow(),
                "active": True,
            }
            logger.warning(
                "IsolationWorkflow: ISOLATED %s %s from production",
                component_type, component_id,
            )
            return True

    def create_cleanroom(self, incident_id: str) -> str:
        """
        Create a cleanroom environment for forensic investigation.

        Args:
            incident_id: The incident requiring a cleanroom.

        Returns:
            cleanroom_id: Unique identifier for the cleanroom.
        """
        with self._lock:
            cleanroom_id = _generate_id("cr-")
            self._cleanrooms[cleanroom_id] = {
                "cleanroom_id": cleanroom_id,
                "incident_id": incident_id,
                "created_at": datetime.utcnow(),
                "resources": [],
                "active": True,
            }
            logger.info(
                "IsolationWorkflow: created cleanroom %s for incident %s",
                cleanroom_id, incident_id,
            )
            return cleanroom_id

    def move_to_cleanroom(
        self, cleanroom_id: str, resource_type: str, resource_id: str
    ) -> None:
        """
        Move a resource into a cleanroom for investigation.

        Args:
            cleanroom_id: The target cleanroom.
            resource_type: Type of resource (log, model_snapshot, audit_trail, etc.).
            resource_id: Identifier of the resource.
        """
        with self._lock:
            if cleanroom_id not in self._cleanrooms:
                logger.error(
                    "IsolationWorkflow: cleanroom %s not found", cleanroom_id
                )
                return
            self._cleanrooms[cleanroom_id]["resources"].append({
                "resource_type": resource_type,
                "resource_id": resource_id,
                "moved_at": datetime.utcnow(),
            })
            logger.info(
                "IsolationWorkflow: moved %s %s to cleanroom %s",
                resource_type, resource_id, cleanroom_id,
            )

    def restore_from_isolation(self, component_id: str) -> bool:
        """
        Restore a component from isolation back to production.

        Args:
            component_id: The identifier of the component to restore.

        Returns:
            True if restoration was successful.
        """
        with self._lock:
            for key, data in list(self._isolated_components.items()):
                if data["component_id"] == component_id and data["active"]:
                    data["active"] = False
                    data["restored_at"] = datetime.utcnow()
                    logger.info(
                        "IsolationWorkflow: RESTORED %s from isolation", component_id
                    )
                    return True
            logger.warning(
                "IsolationWorkflow: component %s not found or not isolated", component_id
            )
            return False

    def to_dict(self) -> dict:
        with self._lock:
            return {
                "isolated_components": len(self._isolated_components),
                "active_cleanrooms": sum(
                    1 for c in self._cleanrooms.values() if c["active"]
                ),
                "isolated_list": [
                    {"key": k, **v}
                    for k, v in self._isolated_components.items()
                    if v["active"]
                ],
            }


# ---------------------------------------------------------------------------
# 4. CapabilityDisablement
# ---------------------------------------------------------------------------

class CapabilityDisablement:
    """
    Manages emergency disablement of AI capabilities (models, tools, agents,
    features) during safety incidents.
    """

    def __init__(self) -> None:
        self._disabled: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.RLock()

    def disable_model(self, model_name: str, reason: str, operator: str) -> bool:
        """Disable a model from serving."""
        return self._disable("model", model_name, reason, operator)

    def disable_tool(self, tool_name: str, reason: str, operator: str) -> bool:
        """Disable a tool from being called."""
        return self._disable("tool", tool_name, reason, operator)

    def disable_agent(self, agent_id: str, reason: str, operator: str) -> bool:
        """Disable an agent from operating."""
        return self._disable("agent", agent_id, reason, operator)

    def disable_feature(self, feature_name: str, reason: str, operator: str) -> bool:
        """Disable a feature flag."""
        return self._disable("feature", feature_name, reason, operator)

    def _disable(self, capability_type: str, name: str, reason: str, operator: str) -> bool:
        """Internal disable method."""
        with self._lock:
            capability_id = _generate_id("cap-")
            self._disabled[capability_id] = {
                "capability_id": capability_id,
                "type": capability_type,
                "name": name,
                "reason": reason,
                "operator": operator,
                "disabled_at": datetime.utcnow(),
                "active": True,
            }
            logger.critical(
                "CapabilityDisablement: DISABLED %s '%s' by %s: %s",
                capability_type, name, operator, reason,
            )
            return True

    def get_disabled_capabilities(self) -> List[Dict[str, Any]]:
        """Get all currently disabled capabilities."""
        with self._lock:
            return [
                {
                    "capability_id": cid,
                    "type": data["type"],
                    "name": data["name"],
                    "reason": data["reason"],
                    "operator": data["operator"],
                    "disabled_at": data["disabled_at"].isoformat(),
                }
                for cid, data in self._disabled.items()
                if data["active"]
            ]

    def restore_capability(self, capability_id: str, operator: str) -> bool:
        """Restore a disabled capability."""
        with self._lock:
            if capability_id in self._disabled and self._disabled[capability_id]["active"]:
                self._disabled[capability_id]["active"] = False
                self._disabled[capability_id]["restored_at"] = datetime.utcnow()
                self._disabled[capability_id]["restored_by"] = operator
                logger.info(
                    "CapabilityDisablement: RESTORED capability %s by %s",
                    capability_id, operator,
                )
                return True
            return False

    def to_dict(self) -> dict:
        with self._lock:
            return {
                "disabled_count": sum(
                    1 for d in self._disabled.values() if d["active"]
                ),
                "disabled_capabilities": self.get_disabled_capabilities(),
            }


# ---------------------------------------------------------------------------
# 5. OperatorNotification
# ---------------------------------------------------------------------------

class OperatorNotification:
    """
    Handles operator notification and escalation during incidents.

    Manages escalation matrix, on-call rosters, and acknowledgment tracking.
    """

    DEFAULT_ESCALATION_MATRIX: Dict[EscalationLevel, List[str]] = {
        EscalationLevel.L1_SUPPORT: ["l1-support@example.com"],
        EscalationLevel.L2_ENGINEERING: ["l2-engineering@example.com"],
        EscalationLevel.L3_SRE: ["l3-sre@example.com"],
        EscalationLevel.L4_SECURITY: ["l4-security@example.com"],
        EscalationLevel.L5_EXECUTIVE: ["l5-executive@example.com"],
    }

    def __init__(
        self, escalation_matrix: Optional[Dict[EscalationLevel, List[str]]] = None
    ) -> None:
        self.escalation_matrix: Dict[EscalationLevel, List[str]] = (
            escalation_matrix or self.DEFAULT_ESCALATION_MATRIX.copy()
        )
        self._escalations: List[EscalationRecord] = []
        self._acknowledgments: Dict[str, str] = {}
        self._lock = threading.RLock()

    def notify(
        self, incident: Incident, level: EscalationLevel, message: str
    ) -> bool:
        """
        Send a notification to operators at the specified escalation level.

        In production, this would send emails, pages, or Slack messages.
        """
        recipients = self.get_on_call(level)
        if not recipients:
            logger.warning(
                "OperatorNotification: no recipients for level %s", level.value
            )
            return False

        logger.info(
            "OperatorNotification: NOTIFY [%s] incident %s to %s: %s",
            level.value, incident.incident_id, recipients, message[:200],
        )
        return True

    def escalate(
        self,
        incident: Incident,
        from_level: EscalationLevel,
        reason: str,
        escalator: str,
    ) -> EscalationRecord:
        """
        Escalate an incident to the next level.

        Args:
            incident: The incident to escalate.
            from_level: Current escalation level.
            reason: Reason for escalation.
            escalator: Person initiating the escalation.

        Returns:
            EscalationRecord documenting the escalation.
        """
        levels = list(EscalationLevel)
        current_idx = levels.index(from_level)
        if current_idx >= len(levels) - 1:
            logger.error(
                "OperatorNotification: cannot escalate from %s (already at highest)",
                from_level.value,
            )
            to_level = from_level
        else:
            to_level = levels[current_idx + 1]

        with self._lock:
            record = EscalationRecord(
                incident_id=incident.incident_id,
                escalated_from=from_level,
                escalated_to=to_level,
                escalated_at=datetime.utcnow(),
                escalated_by=escalator,
                reason=reason,
            )
            self._escalations.append(record)

        # Auto-notify the new level
        self.notify(
            incident, to_level,
            f"ESCALATED from {from_level.value} to {to_level.value}: {reason}",
        )

        logger.warning(
            "OperatorNotification: ESCALATED incident %s: %s -> %s by %s",
            incident.incident_id, from_level.value, to_level.value, escalator,
        )
        return record

    def get_on_call(self, level: EscalationLevel) -> List[str]:
        """Get the current on-call contacts for a level."""
        return self.escalation_matrix.get(level, [])

    def acknowledge(self, incident_id: str, operator: str) -> None:
        """Record acknowledgment of an incident by an operator."""
        with self._lock:
            self._acknowledgments[incident_id] = operator
            logger.info(
                "OperatorNotification: incident %s acknowledged by %s",
                incident_id, operator,
            )

    def to_dict(self) -> dict:
        with self._lock:
            return {
                "escalation_matrix": {
                    k.value: v for k, v in self.escalation_matrix.items()
                },
                "escalations": [e.to_dict() for e in self._escalations],
                "acknowledgments": self._acknowledgments,
            }


# ---------------------------------------------------------------------------
# 6. LogPreserver
# ---------------------------------------------------------------------------

class LogPreserver:
    """
    Preserves logs for forensic investigation of AI safety incidents.

    Manages log archival, chain of custody, integrity verification,
    and secure transfer of evidence.
    """

    def __init__(self, retention_days: int = 90) -> None:
        self.retention_days = retention_days
        self._archives: Dict[str, Dict[str, Any]] = {}
        self._custody_chain: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        self._lock = threading.RLock()

    def preserve_logs(
        self,
        incident_id: str,
        time_range: Tuple[datetime, datetime],
        sources: List[str],
    ) -> str:
        """
        Preserve logs for an incident within a time range.

        Args:
            incident_id: The incident to preserve logs for.
            time_range: (start, end) datetime tuple.
            sources: List of log source identifiers.

        Returns:
            archive_id: Unique identifier for the log archive.
        """
        with self._lock:
            archive_id = _generate_id("log-")
            archive_data = {
                "archive_id": archive_id,
                "incident_id": incident_id,
                "time_range_start": time_range[0].isoformat(),
                "time_range_end": time_range[1].isoformat(),
                "sources": sources,
                "preserved_at": datetime.utcnow(),
                "retention_days": self.retention_days,
                "integrity_hash": _compute_hash(
                    f"{incident_id}:{time_range}:{sources}"
                ),
            }
            self._archives[archive_id] = archive_data

            logger.info(
                "LogPreserver: preserved logs for incident %s (%d sources, %s → %s)",
                incident_id, len(sources),
                time_range[0].isoformat(), time_range[1].isoformat(),
            )
            return archive_id

    def establish_chain_of_custody(self, archive_id: str, custodian: str) -> str:
        """
        Establish the chain of custody for a log archive.

        Returns a custody_id.
        """
        with self._lock:
            custody_id = _generate_id("coc-")
            entry = {
                "custody_id": custody_id,
                "archive_id": archive_id,
                "custodian": custodian,
                "established_at": datetime.utcnow(),
                "action": "established",
            }
            self._custody_chain[archive_id].append(entry)
            logger.info(
                "LogPreserver: chain of custody established for %s (custodian: %s)",
                archive_id, custodian,
            )
            return custody_id

    def transfer_custody(
        self, archive_id: str, from_person: str, to_person: str, reason: str
    ) -> None:
        """Transfer custody of a log archive from one person to another."""
        with self._lock:
            entry = {
                "custody_id": _generate_id("coc-"),
                "archive_id": archive_id,
                "from": from_person,
                "to": to_person,
                "reason": reason,
                "transferred_at": datetime.utcnow(),
                "action": "transferred",
            }
            self._custody_chain[archive_id].append(entry)
            logger.info(
                "LogPreserver: custody transferred for %s: %s → %s",
                archive_id, from_person, to_person,
            )

    def verify_integrity(self, archive_id: str) -> bool:
        """
        Verify the integrity of a log archive using its stored hash.

        Returns True if integrity is intact.
        """
        with self._lock:
            if archive_id not in self._archives:
                logger.error("LogPreserver: archive %s not found", archive_id)
                return False

            archive = self._archives[archive_id]
            expected_hash = archive["integrity_hash"]
            computed = _compute_hash(
                f"{archive['incident_id']}:"
                f"({archive['time_range_start']},{archive['time_range_end']}):"
                f"{archive['sources']}"
            )
            valid = expected_hash == computed
            logger.info(
                "LogPreserver: integrity check for %s: %s",
                archive_id, "PASSED" if valid else "FAILED",
            )
            return valid

    def to_dict(self) -> dict:
        with self._lock:
            return {
                "retention_days": self.retention_days,
                "archives_count": len(self._archives),
                "archives": {
                    aid: {
                        "incident_id": data["incident_id"],
                        "sources_count": len(data["sources"]),
                        "preserved_at": data["preserved_at"].isoformat(),
                    }
                    for aid, data in self._archives.items()
                },
            }


# ---------------------------------------------------------------------------
# 7. RootCauseInvestigator
# ---------------------------------------------------------------------------

class RootCauseInvestigator:
    """
    Investigates root causes of AI safety incidents.

    Builds event timelines, identifies contributing factors, and applies
    the Five Whys methodology for root cause analysis.
    """

    def __init__(self) -> None:
        self._investigations: Dict[str, RootCauseReport] = {}
        self._lock = threading.RLock()

    def investigate(
        self, incident: Incident, evidence: Dict[str, Any]
    ) -> RootCauseReport:
        """
        Conduct a root cause investigation for an incident.

        Args:
            incident: The incident to investigate.
            evidence: Dictionary of evidence collected.

        Returns:
            RootCauseReport with findings.
        """
        with self._lock:
            # Build timeline from evidence
            timeline = self.build_timeline(
                incident.incident_id, evidence.get("events", [])
            )

            # Identify contributing factors
            factors = self.identify_factors(evidence)

            # Run Five Whys on a problem statement
            problem_statement = (
                evidence.get("problem_statement")
                or incident.description[:200]
            )
            why_chain = self.five_whys(problem_statement)

            # Classify root cause category
            category = self._classify_root_cause(evidence, factors, why_chain)

            # Compute confidence based on evidence completeness
            evidence_keys = len(evidence)
            confidence = min(0.95, 0.3 + (evidence_keys * 0.1))

            report = RootCauseReport(
                incident_id=incident.incident_id,
                category=category,
                description=f"Root cause: {why_chain[-1] if why_chain else 'Undetermined'}",
                contributing_factors=factors,
                timeline=timeline,
                confidence=confidence,
                evidence=list(evidence.keys()),
            )
            self._investigations[incident.incident_id] = report

            logger.info(
                "RootCauseInvestigator: investigation complete for %s (category=%s, confidence=%.2f)",
                incident.incident_id, category.value, confidence,
            )
            return report

    def build_timeline(
        self, incident_id: str, events: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Build a chronological timeline of events for an incident.

        Args:
            incident_id: The incident identifier.
            events: List of events with 'timestamp' and 'description' keys.

        Returns:
            Chronologically sorted timeline entries.
        """
        timeline = []
        for event in events:
            ts = event.get("timestamp")
            if isinstance(ts, str):
                try:
                    ts = datetime.fromisoformat(ts)
                except ValueError:
                    ts = datetime.utcnow()

            timeline.append({
                "timestamp": ts.isoformat() if isinstance(ts, datetime) else str(ts),
                "description": event.get("description", "Unknown event"),
                "source": event.get("source", "unknown"),
                "incident_id": incident_id,
            })

        timeline.sort(key=lambda e: e["timestamp"])
        return timeline

    def identify_factors(self, evidence: Dict[str, Any]) -> List[str]:
        """Identify contributing factors from evidence."""
        factors = []

        if evidence.get("model_version"):
            factors.append(f"Model version: {evidence['model_version']}")
        if evidence.get("recent_changes"):
            factors.append(f"Recent changes: {evidence['recent_changes']}")
        if evidence.get("input_anomaly"):
            factors.append(f"Input anomaly detected: {evidence['input_anomaly']}")
        if evidence.get("configuration_error"):
            factors.append(f"Configuration error: {evidence['configuration_error']}")
        if evidence.get("external_trigger"):
            factors.append(f"External trigger: {evidence['external_trigger']}")
        if evidence.get("human_action"):
            factors.append(f"Human action: {evidence['human_action']}")

        if not factors:
            factors.append("No contributing factors identified from available evidence")

        return factors

    def five_whys(self, problem_statement: str) -> List[str]:
        """
        Apply the Five Whys methodology to a problem statement.

        Returns a list of answers, each one addressing "why" for the previous.
        """
        whys = [problem_statement]
        current = problem_statement

        for i in range(5):
            next_why = self._generate_why_answer(current, i + 1)
            if next_why == current:
                break
            whys.append(next_why)
            current = next_why

        return whys

    def _generate_why_answer(self, statement: str, level: int) -> str:
        """Generate a plausible 'why' answer based on statement analysis."""
        # In production, this would use an LLM or expert system
        statement_lower = statement.lower()

        if "unsafe output" in statement_lower:
            return "The content filter threshold was too permissive, allowing borderline content through."
        elif "hallucination" in statement_lower:
            return "The model lacked sufficient grounding data for the query domain."
        elif "latency" in statement_lower:
            return "Resource contention occurred due to concurrent high-load requests without adequate scaling."
        elif "accuracy" in statement_lower or "drift" in statement_lower:
            return "Input data distribution shifted from the training distribution without detection."
        elif "prompt injection" in statement_lower or "jailbreak" in statement_lower:
            return "Input sanitization rules did not cover the specific injection pattern used."
        elif "tool failure" in statement_lower:
            return "The upstream service returned an unexpected response that was not handled gracefully."
        elif "cost" in statement_lower:
            return "Token usage exceeded projections due to unexpectedly verbose model responses."
        elif "configuration" in statement_lower:
            return "A configuration change was deployed without sufficient testing in staging."
        elif level >= 5:
            return "Root cause identified: Insufficient guardrails and monitoring coverage for this failure mode."
        else:
            return f"Further investigation needed at level {level}."

    def _classify_root_cause(
        self,
        evidence: Dict[str, Any],
        factors: List[str],
        why_chain: List[str],
    ) -> RootCauseCategory:
        """Classify the root cause category from evidence and analysis."""
        combined = " ".join(why_chain).lower() + " " + json.dumps(factors).lower()

        if any(kw in combined for kw in ("prompt injection", "jailbreak", "attack")):
            return RootCauseCategory.PROMPT_INJECTION
        elif any(kw in combined for kw in ("model error", "hallucination", "accuracy")):
            return RootCauseCategory.MODEL_ERROR
        elif any(kw in combined for kw in ("tool misuse", "tool failure", "api error")):
            return RootCauseCategory.TOOL_MISUSE
        elif any(kw in combined for kw in ("infrastructure", "resource", "scaling")):
            return RootCauseCategory.INFRASTRUCTURE
        elif any(kw in combined for kw in ("configuration", "config", "setting")):
            return RootCauseCategory.CONFIGURATION
        elif any(kw in combined for kw in ("human", "operator", "mistake")):
            return RootCauseCategory.HUMAN_ERROR
        elif any(kw in combined for kw in ("external", "upstream", "third party")):
            return RootCauseCategory.EXTERNAL

        return RootCauseCategory.UNKNOWN

    def to_dict(self) -> dict:
        with self._lock:
            return {
                "investigations_count": len(self._investigations),
                "investigations": {
                    iid: r.to_dict()
                    for iid, r in self._investigations.items()
                },
            }


# ---------------------------------------------------------------------------
# 8. PatchRemediationTracker
# ---------------------------------------------------------------------------

class PatchRemediationTracker:
    """
    Tracks remediation items through their lifecycle from planning
    through deployment, verification, and closure.
    """

    def __init__(self) -> None:
        self._items: Dict[str, RemediationItem] = {}
        self._lock = threading.RLock()

    def create_remediation(
        self,
        incident_id: str,
        description: str,
        owner: str,
        due_date: Optional[datetime] = None,
    ) -> str:
        """
        Create a new remediation item.

        Returns the item_id.
        """
        with self._lock:
            item_id = _generate_id("rem-")
            item = RemediationItem(
                item_id=item_id,
                incident_id=incident_id,
                description=description,
                owner=owner,
                status=RemediationStatus.PLANNED,
                due_date=due_date,
            )
            self._items[item_id] = item
            logger.info(
                "PatchRemediationTracker: created remediation %s for incident %s",
                item_id, incident_id,
            )
            return item_id

    def update_status(
        self, item_id: str, status: RemediationStatus, notes: str = ""
    ) -> None:
        """Update the status of a remediation item."""
        with self._lock:
            if item_id in self._items:
                old_status = self._items[item_id].status
                self._items[item_id].status = status
                logger.info(
                    "PatchRemediationTracker: %s: %s → %s (%s)",
                    item_id, old_status.value, status.value, notes,
                )

    def verify_remediation(
        self, item_id: str, verification_method: str, result: bool
    ) -> None:
        """Record verification results for a remediation item."""
        with self._lock:
            if item_id in self._items:
                self._items[item_id].verification_method = verification_method
                if result:
                    self._items[item_id].status = RemediationStatus.VERIFIED
                else:
                    self._items[item_id].status = RemediationStatus.FAILED
                logger.info(
                    "PatchRemediationTracker: verified %s: %s",
                    item_id, "PASSED" if result else "FAILED",
                )

    def get_outstanding_items(self) -> List[RemediationItem]:
        """Get all remediation items that are not yet verified or failed."""
        with self._lock:
            return [
                item for item in self._items.values()
                if item.status not in (RemediationStatus.VERIFIED, RemediationStatus.FAILED)
            ]

    def to_dict(self) -> dict:
        with self._lock:
            return {
                "total_items": len(self._items),
                "outstanding": len(self.get_outstanding_items()),
                "items": {iid: item.to_dict() for iid, item in self._items.items()},
            }


# ---------------------------------------------------------------------------
# 9. RetestProtocol
# ---------------------------------------------------------------------------

class RetestProtocol:
    """
    Manages retesting of fixes and guardrails after incident remediation.

    Creates test plans, executes individual test cases, and runs full
    regression test suites to verify fixes.
    """

    def __init__(self) -> None:
        self._test_plans: Dict[str, Dict[str, Any]] = {}
        self._test_results: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        self._lock = threading.RLock()

    def create_test_plan(
        self, incident_id: str, test_cases: List[Dict[str, Any]]
    ) -> str:
        """
        Create a test plan for incident remediation verification.

        Returns a plan_id.
        """
        with self._lock:
            plan_id = _generate_id("tplan-")
            self._test_plans[plan_id] = {
                "plan_id": plan_id,
                "incident_id": incident_id,
                "test_cases": test_cases,
                "created_at": datetime.utcnow(),
                "total_cases": len(test_cases),
                "executed": False,
            }
            logger.info(
                "RetestProtocol: created test plan %s with %d cases",
                plan_id, len(test_cases),
            )
            return plan_id

    def execute_test(self, test_case: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute a single test case.

        Args:
            test_case: Dict with 'name', 'input', 'expected_behavior', etc.

        Returns:
            Result dict with pass/fail status and details.
        """
        name = test_case.get("name", "unnamed_test")
        input_data = test_case.get("input", "")
        expected = test_case.get("expected_behavior", "")

        # In production, this would actually run the test against the system
        # For now, simulate test execution
        result = {
            "test_name": name,
            "input_snippet": str(input_data)[:200],
            "expected_behavior": expected,
            "actual_behavior": f"Test executed for: {name}",
            "passed": True,  # Would be determined by actual test execution
            "executed_at": datetime.utcnow().isoformat(),
            "notes": "Simulated execution",
        }

        logger.info("RetestProtocol: executed test '%s': %s", name, "PASSED")
        return result

    def run_full_retest(self, plan_id: str) -> Dict[str, Any]:
        """
        Run all test cases in a test plan.

        Returns a summary of test execution results.
        """
        with self._lock:
            if plan_id not in self._test_plans:
                logger.error("RetestProtocol: test plan %s not found", plan_id)
                return {"error": "test_plan_not_found", "plan_id": plan_id}

            plan = self._test_plans[plan_id]
            results = []
            passed = 0
            failed = 0

            for test_case in plan["test_cases"]:
                result = self.execute_test(test_case)
                results.append(result)
                if result["passed"]:
                    passed += 1
                else:
                    failed += 1

            plan["executed"] = True
            plan["executed_at"] = datetime.utcnow()
            self._test_results[plan_id] = results

            summary = {
                "plan_id": plan_id,
                "incident_id": plan["incident_id"],
                "total_tests": len(results),
                "passed": passed,
                "failed": failed,
                "pass_rate": passed / max(1, len(results)),
                "all_passed": failed == 0,
                "results": results,
            }

            logger.info(
                "RetestProtocol: retest plan %s complete: %d/%d passed",
                plan_id, passed, len(results),
            )
            return summary

    def to_dict(self) -> dict:
        with self._lock:
            return {
                "test_plans": len(self._test_plans),
                "plans": {
                    pid: {
                        "incident_id": p["incident_id"],
                        "total_cases": p["total_cases"],
                        "executed": p["executed"],
                    }
                    for pid, p in self._test_plans.items()
                },
            }


# ---------------------------------------------------------------------------
# 10. LessonsLearnedDocumenter (avoids name collision with dataclass)
# ---------------------------------------------------------------------------

class LessonsLearnedDocumenter:
    """
    Documents lessons learned from incidents and identifies guardrail
    improvement opportunities.
    """

    def __init__(self) -> None:
        self._lessons: Dict[str, LessonsLearned] = {}
        self._lock = threading.RLock()

    def document(
        self,
        incident_id: str,
        what_went_well: List[str],
        what_went_wrong: List[str],
        action_items: List[str],
    ) -> str:
        """
        Document lessons learned from an incident.

        Returns a lesson_id.
        """
        with self._lock:
            lesson_id = _generate_id("ll-")
            guardrail_updates = self.identify_guardrail_updates(incident_id)

            lessons = LessonsLearned(
                incident_id=incident_id,
                what_went_well=what_went_well,
                what_went_wrong=what_went_wrong,
                action_items=action_items,
                guardrail_updates=guardrail_updates,
            )
            self._lessons[incident_id] = lessons
            logger.info(
                "LessonsLearnedDocumenter: documented lessons for %s", incident_id
            )
            return lesson_id

    def identify_guardrail_updates(self, incident_id: str) -> List[Dict[str, Any]]:
        """
        Identify guardrail improvements based on the incident.

        Returns a list of proposed guardrail update dictionaries.
        """
        updates = [
            {
                "guardrail": "input_sanitization",
                "proposed_change": "Add explicit patterns for newly discovered injection vectors",
                "priority": "high",
                "justification": f"Incident {incident_id} involved a prompt injection not caught by existing rules",
            },
            {
                "guardrail": "content_filtering",
                "proposed_change": "Lower the unsafe content threshold by 10%",
                "priority": "medium",
                "justification": f"Unsafe output detection gap identified in {incident_id}",
            },
            {
                "guardrail": "rate_limiting",
                "proposed_change": "Add per-user request rate limits with anomaly detection",
                "priority": "medium",
                "justification": "Prevent abuse patterns observed during the incident",
            },
            {
                "guardrail": "monitoring_alert",
                "proposed_change": "Add new alert rule for the specific failure mode",
                "priority": "high",
                "justification": "Earlier detection would have reduced incident duration",
            },
        ]
        return updates

    def get_lessons(self, incident_id: str) -> Optional[LessonsLearned]:
        """Get the lessons learned for a specific incident."""
        with self._lock:
            return self._lessons.get(incident_id)

    def to_dict(self) -> dict:
        with self._lock:
            return {
                "lessons_count": len(self._lessons),
                "lessons": {
                    iid: l.to_dict() for iid, l in self._lessons.items()
                },
            }


# ---------------------------------------------------------------------------
# 11. GuardrailUpdateWorkflow
# ---------------------------------------------------------------------------

class GuardrailUpdateWorkflow:
    """
    Manages the lifecycle of guardrail updates: proposal, testing,
    deployment, and rollback.
    """

    def __init__(self) -> None:
        self._proposals: Dict[str, Dict[str, Any]] = {}
        self._deployed: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.RLock()

    def propose_update(
        self,
        guardrail_name: str,
        current_config: Dict[str, Any],
        proposed_config: Dict[str, Any],
        justification: str,
        proposer: str,
    ) -> str:
        """
        Propose a guardrail configuration update.

        Returns a proposal_id.
        """
        with self._lock:
            proposal_id = _generate_id("gprop-")
            self._proposals[proposal_id] = {
                "proposal_id": proposal_id,
                "guardrail_name": guardrail_name,
                "current_config": current_config,
                "proposed_config": proposed_config,
                "justification": justification,
                "proposer": proposer,
                "proposed_at": datetime.utcnow(),
                "status": "proposed",
                "test_results": None,
                "deployed": False,
            }
            logger.info(
                "GuardrailUpdateWorkflow: proposed update for %s by %s",
                guardrail_name, proposer,
            )
            return proposal_id

    def test_update(self, proposal_id: str, test_results: Dict[str, Any]) -> None:
        """Record test results for a guardrail proposal."""
        with self._lock:
            if proposal_id in self._proposals:
                self._proposals[proposal_id]["test_results"] = test_results
                self._proposals[proposal_id]["status"] = "tested"
                logger.info(
                    "GuardrailUpdateWorkflow: tested proposal %s: %s",
                    proposal_id,
                    "PASSED" if test_results.get("passed", False) else "FAILED",
                )

    def deploy_update(self, proposal_id: str, deployer: str) -> None:
        """Deploy an approved guardrail update."""
        with self._lock:
            if proposal_id in self._proposals:
                proposal = self._proposals[proposal_id]
                proposal["status"] = "deployed"
                proposal["deployed"] = True
                proposal["deployed_at"] = datetime.utcnow()
                proposal["deployed_by"] = deployer
                self._deployed[proposal_id] = {
                    "guardrail_name": proposal["guardrail_name"],
                    "deployed_at": datetime.utcnow(),
                    "deployed_by": deployer,
                    "config_snapshot": proposal["proposed_config"],
                }
                logger.info(
                    "GuardrailUpdateWorkflow: DEPLOYED update %s for %s by %s",
                    proposal_id, proposal["guardrail_name"], deployer,
                )

    def rollback_update(self, proposal_id: str, reason: str) -> bool:
        """
        Rollback a deployed guardrail update.

        Returns True if rollback was successful.
        """
        with self._lock:
            if proposal_id in self._proposals:
                proposal = self._proposals[proposal_id]
                if not proposal["deployed"]:
                    logger.warning(
                        "GuardrailUpdateWorkflow: cannot rollback %s (not deployed)",
                        proposal_id,
                    )
                    return False

                proposal["status"] = "rolled_back"
                proposal["deployed"] = False
                proposal["rollback_reason"] = reason
                proposal["rolled_back_at"] = datetime.utcnow()

                if proposal_id in self._deployed:
                    del self._deployed[proposal_id]

                logger.warning(
                    "GuardrailUpdateWorkflow: ROLLED BACK %s for %s: %s",
                    proposal_id, proposal["guardrail_name"], reason,
                )
                return True
            return False

    def to_dict(self) -> dict:
        with self._lock:
            return {
                "proposals": len(self._proposals),
                "deployed": len(self._deployed),
                "proposal_statuses": {
                    pid: p["status"] for pid, p in self._proposals.items()
                },
            }


# ---------------------------------------------------------------------------
# 12. PostIncidentReviewAutomation
# ---------------------------------------------------------------------------

class PostIncidentReviewAutomation:
    """
    Automates the creation and publication of post-incident review documents.

    Combines root cause analysis, remediation tracking, and lessons learned
    into a comprehensive post-incident review.
    """

    def __init__(self) -> None:
        self._reviews: Dict[str, PostIncidentReview] = {}
        self._follow_ups: Dict[str, datetime] = {}
        self._lock = threading.RLock()

    def generate_review(
        self,
        incident: Incident,
        root_cause: RootCauseReport,
        remediation_items: List[RemediationItem],
        lessons: LessonsLearned,
        participants: List[str],
    ) -> PostIncidentReview:
        """
        Generate a post-incident review document.

        Args:
            incident: The incident being reviewed.
            root_cause: Root cause investigation results.
            remediation_items: List of remediation actions taken.
            lessons: Lessons learned from the incident.
            participants: List of people involved in the review.

        Returns:
            A complete PostIncidentReview.
        """
        with self._lock:
            review = PostIncidentReview(
                incident_id=incident.incident_id,
                incident_summary=(
                    f"{incident.title} (SEV: {incident.severity.value.upper()})\n\n"
                    f"Detected: {incident.detected_at.isoformat()}\n"
                    f"Description: {incident.description}\n"
                    f"Affected Components: {', '.join(incident.affected_components)}"
                ),
                root_cause=root_cause,
                timeline=root_cause.timeline,
                remediation=remediation_items,
                lessons=lessons,
                participants=participants,
                review_date=datetime.utcnow(),
                published=False,
            )
            self._reviews[incident.incident_id] = review
            logger.info(
                "PostIncidentReviewAutomation: generated review for %s",
                incident.incident_id,
            )
            return review

    def publish_review(self, review: PostIncidentReview) -> None:
        """Publish a post-incident review."""
        with self._lock:
            review.published = True
            logger.info(
                "PostIncidentReviewAutomation: published review for %s",
                review.incident_id,
            )

    def schedule_follow_up(self, review: PostIncidentReview, date: datetime) -> None:
        """Schedule a follow-up review at a future date."""
        with self._lock:
            self._follow_ups[review.incident_id] = date
            if review.lessons:
                review.lessons.follow_up_date = date
            logger.info(
                "PostIncidentReviewAutomation: scheduled follow-up for %s on %s",
                review.incident_id, date.isoformat(),
            )

    def to_dict(self) -> dict:
        with self._lock:
            return {
                "reviews_count": len(self._reviews),
                "published": sum(1 for r in self._reviews.values() if r.published),
                "follow_ups": {
                    iid: dt.isoformat() for iid, dt in self._follow_ups.items()
                },
            }


# ---------------------------------------------------------------------------
# 13. IncidentManager — Main Orchestrator
# ---------------------------------------------------------------------------

class IncidentManager:
    """
    Main orchestrator for the incident response system.

    Coordinates all subsystems: classification, containment, isolation,
    investigation, remediation, post-mortem, and guardrail updates.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        config = config or {}

        self.config = config
        self.classifier = IncidentClassifier()
        self.containment = ContainmentProcedure()
        self.isolation = IsolationWorkflow()
        self.capability_disablement = CapabilityDisablement()
        self.notification = OperatorNotification(
            escalation_matrix=config.get("escalation_matrix"),
        )
        self.log_preserver = LogPreserver(
            retention_days=config.get("log_retention_days", 90),
        )
        self.investigator = RootCauseInvestigator()
        self.remediation_tracker = PatchRemediationTracker()
        self.retest = RetestProtocol()
        self.lessons_documenter = LessonsLearnedDocumenter()
        self.guardrail_workflow = GuardrailUpdateWorkflow()
        self.review_automation = PostIncidentReviewAutomation()

        self._incidents: Dict[str, Incident] = {}
        self._incident_history: deque = deque(maxlen=1000)
        self._lock = threading.RLock()

        logger.info("IncidentManager initialized with config: %s", list(config.keys()))

    def declare_incident(
        self,
        title: str,
        description: str,
        affected_components: List[str],
        initial_evidence: Dict[str, Any],
    ) -> Incident:
        """
        Declare a new AI safety incident.

        Args:
            title: Short title describing the incident.
            description: Detailed description.
            affected_components: List of affected system components.
            initial_evidence: Initial evidence dict.

        Returns:
            The created Incident.
        """
        with self._lock:
            incident = self.classifier.classify(
                title=title,
                description=description,
                affected_components=affected_components,
                initial_evidence=initial_evidence,
            )
            self._incidents[incident.incident_id] = incident
            self._incident_history.append(incident)

            # Auto-notify based on severity
            if incident.severity in (IncidentSeverity.SEV1, IncidentSeverity.SEV2):
                self.notification.notify(
                    incident,
                    EscalationLevel.L2_ENGINEERING
                    if incident.severity == IncidentSeverity.SEV2
                    else EscalationLevel.L3_SRE,
                    f"NEW INCIDENT [{incident.severity.value.upper()}]: {title}",
                )

            logger.warning(
                "IncidentManager: DECLARED incident %s [%s]: %s",
                incident.incident_id,
                incident.severity.value.upper(),
                title,
            )
            return incident

    def contain(
        self,
        incident_id: str,
        containment_type: ContainmentType,
        operator: str,
    ) -> Optional[ContainmentAction]:
        """
        Apply containment to an active incident.

        Args:
            incident_id: The incident to contain.
            containment_type: Type of containment to apply.
            operator: Person/system applying containment.

        Returns:
            The ContainmentAction, or None if incident not found.
        """
        with self._lock:
            incident = self._incidents.get(incident_id)
            if not incident:
                logger.error("IncidentManager: incident %s not found", incident_id)
                return None

            action = self.containment.execute_containment(
                incident, containment_type, operator
            )
            incident.status = IncidentStatus.CONTAINING
            incident.containment_applied = True

            # For critical containment, also disable affected capabilities
            if containment_type in (
                ContainmentType.IMMEDIATE_QUARANTINE,
                ContainmentType.GRACEFUL_SHUTDOWN,
            ):
                for comp in incident.affected_components:
                    self.capability_disablement._disable(
                        "component", comp,
                        f"Containment of incident {incident_id}",
                        operator,
                    )

            return action

    def investigate(
        self, incident_id: str, evidence: Dict[str, Any]
    ) -> Optional[RootCauseReport]:
        """
        Launch a root cause investigation for an incident.

        Args:
            incident_id: The incident to investigate.
            evidence: Collected evidence for investigation.

        Returns:
            RootCauseReport, or None if incident not found.
        """
        with self._lock:
            incident = self._incidents.get(incident_id)
            if not incident:
                logger.error("IncidentManager: incident %s not found", incident_id)
                return None

            incident.status = IncidentStatus.INVESTIGATING
            report = self.investigator.investigate(incident, evidence)
            return report

    def remediate(
        self,
        incident_id: str,
        remediation_items: List[Dict[str, Any]],
    ) -> None:
        """
        Create and track remediation items for an incident.

        Args:
            incident_id: The incident to remediate.
            remediation_items: List of dicts with 'description', 'owner', 'due_date'.
        """
        with self._lock:
            incident = self._incidents.get(incident_id)
            if not incident:
                logger.error("IncidentManager: incident %s not found", incident_id)
                return

            incident.status = IncidentStatus.REMEDIATING
            for item in remediation_items:
                self.remediation_tracker.create_remediation(
                    incident_id=incident_id,
                    description=item.get("description", ""),
                    owner=item.get("owner", "unassigned"),
                    due_date=item.get("due_date"),
                )

            logger.info(
                "IncidentManager: created %d remediation items for %s",
                len(remediation_items), incident_id,
            )

    def conduct_post_mortem(
        self, incident_id: str, participants: List[str]
    ) -> Optional[PostIncidentReview]:
        """
        Conduct a full post-mortem for a resolved incident.

        Args:
            incident_id: The incident to review.
            participants: List of participants in the post-mortem.

        Returns:
            PostIncidentReview, or None if incident not found.
        """
        with self._lock:
            incident = self._incidents.get(incident_id)
            if not incident:
                logger.error("IncidentManager: incident %s not found", incident_id)
                return None

            # Get root cause investigation
            root_cause = self.investigator._investigations.get(
                incident_id,
                RootCauseReport(
                    incident_id=incident_id,
                    category=RootCauseCategory.UNKNOWN,
                    description="Investigation not completed",
                ),
            )

            # Get remediation items
            remediation_items = [
                item for item in self.remediation_tracker._items.values()
                if item.incident_id == incident_id
            ]

            # Document lessons learned
            self.lessons_documenter.document(
                incident_id=incident_id,
                what_went_well=[
                    f"Incident {incident_id} was detected and responded to",
                ],
                what_went_wrong=[
                    f"Root cause: {root_cause.category.value}",
                    f"Contributing factors: {', '.join(root_cause.contributing_factors)}",
                ],
                action_items=[
                    f"Implement guardrail updates based on incident {incident_id}",
                    "Schedule follow-up review",
                ],
            )
            lessons = self.lessons_documenter.get_lessons(incident_id)

            # Generate review
            review = self.review_automation.generate_review(
                incident=incident,
                root_cause=root_cause,
                remediation_items=remediation_items,
                lessons=lessons or LessonsLearned(incident_id=incident_id),
                participants=participants,
            )

            incident.status = IncidentStatus.POST_MORTEM
            logger.info(
                "IncidentManager: completed post-mortem for %s", incident_id
            )
            return review

    def get_active_incidents(self) -> List[Incident]:
        """Get all currently active (unresolved) incidents."""
        with self._lock:
            return [
                i for i in self._incidents.values()
                if i.status not in (IncidentStatus.RESOLVED, IncidentStatus.CLOSED)
            ]

    def get_incident_history(self, days: int = 30) -> List[Incident]:
        """Get incident history for the specified number of days."""
        with self._lock:
            cutoff = datetime.utcnow() - timedelta(days=days)
            return [
                i for i in self._incident_history
                if i.detected_at >= cutoff
            ]

    def to_dict(self) -> dict:
        with self._lock:
            return {
                "active_incidents": len(self.get_active_incidents()),
                "total_incidents": len(self._incidents),
                "incidents": {
                    iid: i.to_dict()
                    for iid, i in self._incidents.items()
                },
                "subsystems": {
                    "containment": self.containment.to_dict(),
                    "isolation": self.isolation.to_dict(),
                    "capability_disablement": self.capability_disablement.to_dict(),
                    "notification": self.notification.to_dict(),
                    "log_preserver": self.log_preserver.to_dict(),
                    "investigator": self.investigator.to_dict(),
                    "remediation": self.remediation_tracker.to_dict(),
                    "retest": self.retest.to_dict(),
                    "lessons": self.lessons_documenter.to_dict(),
                    "guardrail_workflow": self.guardrail_workflow.to_dict(),
                    "review_automation": self.review_automation.to_dict(),
                },
            }


# ---------------------------------------------------------------------------
# Module exports
# ---------------------------------------------------------------------------

__all__ = [
    # Enums
    "IncidentSeverity",
    "IncidentStatus",
    "ContainmentType",
    "DisablementScope",
    "EscalationLevel",
    "RootCauseCategory",
    "RemediationStatus",
    # Dataclasses
    "Incident",
    "ContainmentAction",
    "EscalationRecord",
    "RootCauseReport",
    "RemediationItem",
    "LessonsLearned",
    "PostIncidentReview",
    # Managers
    "IncidentClassifier",
    "ContainmentProcedure",
    "IsolationWorkflow",
    "CapabilityDisablement",
    "OperatorNotification",
    "LogPreserver",
    "RootCauseInvestigator",
    "PatchRemediationTracker",
    "RetestProtocol",
    "LessonsLearnedDocumenter",
    "GuardrailUpdateWorkflow",
    "PostIncidentReviewAutomation",
    "IncidentManager",
]