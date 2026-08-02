"""
Governance Board Module

Enterprise-grade governance board for managing model changes, prompt approvals,
security reviews, incident reviews, compliance tracking, user feedback aggregation,
performance trend analysis, and risk registration.

Thread-safe, self-contained module with full type annotations and dataclass-based
data models.

Author: Eni Builder
Version: 1.0.0
Python: 3.10+
"""

import re
import time
import json
import logging
import threading
import uuid
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Dict, List, Optional, Set, Tuple, Union
from collections import defaultdict, deque, OrderedDict

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class ReviewStatus(Enum):
    """Status of a review within the governance pipeline."""
    PENDING = "pending"
    IN_REVIEW = "in_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    NEEDS_CHANGES = "needs_changes"
    DEFERRED = "deferred"
    WITHDRAWN = "withdrawn"


class ChangeType(Enum):
    """Type of change being proposed."""
    MODEL = "model"
    PROMPT = "prompt"
    TOOL = "tool"
    SECURITY = "security"
    CONFIGURATION = "configuration"
    INFRASTRUCTURE = "infrastructure"


class RiskLevel(Enum):
    """Severity level for a risk."""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    NEGLIGIBLE = "negligible"


class RiskStatus(Enum):
    """Lifecycle status of a risk."""
    IDENTIFIED = "identified"
    ASSESSING = "assessing"
    MITIGATING = "mitigating"
    MONITORED = "monitored"
    ACCEPTED = "accepted"
    CLOSED = "closed"


class ImpactLevel(Enum):
    """Level of impact from a change."""
    CRITICAL = "critical"
    MAJOR = "major"
    MODERATE = "moderate"
    MINOR = "minor"
    NONE = "none"


class ApprovalStage(Enum):
    """Sequential stages in a prompt change approval pipeline."""
    DRAFT = "draft"
    TECHNICAL_REVIEW = "technical_review"
    SECURITY_REVIEW = "security_review"
    LEGAL_REVIEW = "legal_review"
    ETHICS_REVIEW = "ethics_review"
    FINAL_APPROVAL = "final_approval"


class ComplianceFramework(Enum):
    """Regulatory / compliance frameworks."""
    SOC2 = "soc2"
    ISO27001 = "iso27001"
    GDPR = "gdpr"
    HIPAA = "hipaa"
    PCI_DSS = "pci_dss"
    NIST_AI_RMF = "nist_ai_rmf"
    EU_AI_ACT = "eu_ai_act"
    CUSTOM = "custom"


class TrendDirection(Enum):
    """Direction of a performance trend."""
    IMPROVING = "improving"
    STABLE = "stable"
    DECLINING = "declining"
    VOLATILE = "volatile"
    UNKNOWN = "unknown"


class FeedbackSentiment(Enum):
    """Sentiment classification for user feedback."""
    POSITIVE = "positive"
    NEUTRAL = "neutral"
    NEGATIVE = "negative"
    MIXED = "mixed"


# Alias for backward compatibility with __init__.py
Sentiment = FeedbackSentiment


class ChangeApprovalStatus(Enum):
    """Status of a change approval in the governance pipeline."""
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    IN_REVIEW = "in_review"
    NEEDS_CHANGES = "needs_changes"
    DEFERRED = "deferred"
    CANCELLED = "cancelled"


class IncidentSeverity(Enum):
    """Severity levels for incidents."""
    SEV1 = "sev1"
    SEV2 = "sev2"
    SEV3 = "sev3"
    SEV4 = "sev4"
    SEV5 = "sev5"


class IncidentStatus(Enum):
    """Lifecycle status of an incident."""
    OPEN = "open"
    INVESTIGATING = "investigating"
    CONTAINED = "contained"
    RESOLVED = "resolved"
    CLOSED = "closed"
    REOPENED = "reopened"


class MeetingType(Enum):
    """Types of governance board meetings."""
    REGULAR = "regular"
    EMERGENCY = "emergency"
    REVIEW = "review"
    AUDIT = "audit"
    STRATEGIC = "strategic"


# ---------------------------------------------------------------------------
# Result Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class ReviewDecision:
    """Captures the outcome of a model change review.

    Attributes:
        review_id: Unique identifier for the review.
        status: Final status of the review.
        approved_by: List of reviewers who approved.
        rejected_by: List of reviewers who rejected.
        comments: List of comment dicts {reviewer, comment, timestamp}.
        timestamp: When the decision was finalized.
        conditions: Any conditions attached to approval.
    """
    review_id: str
    status: ReviewStatus
    approved_by: List[str] = field(default_factory=list)
    rejected_by: List[str] = field(default_factory=list)
    comments: List[Dict[str, Any]] = field(default_factory=list)
    timestamp: datetime = field(default_factory=datetime.utcnow)
    conditions: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "review_id": self.review_id,
            "status": self.status.value,
            "approved_by": list(self.approved_by),
            "rejected_by": list(self.rejected_by),
            "comments": list(self.comments),
            "timestamp": self.timestamp.isoformat(),
            "conditions": list(self.conditions),
        }


@dataclass
class ImpactAssessment:
    """Assessment of the impact of a proposed tool/configuration change.

    Attributes:
        change_id: ID of the change being assessed.
        impact_level: Assessed impact level.
        affected_components: Components that would be affected.
        rollback_plan: Plan for rolling back the change.
        risk_factors: Identified risk factors.
        mitigation_steps: Steps to mitigate identified risks.
    """
    change_id: str
    impact_level: ImpactLevel
    affected_components: List[str] = field(default_factory=list)
    rollback_plan: str = ""
    risk_factors: List[str] = field(default_factory=list)
    mitigation_steps: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "change_id": self.change_id,
            "impact_level": self.impact_level.value,
            "affected_components": list(self.affected_components),
            "rollback_plan": self.rollback_plan,
            "risk_factors": list(self.risk_factors),
            "mitigation_steps": list(self.mitigation_steps),
        }


@dataclass
class RiskEntry:
    """A single risk entry in the risk register.

    Attributes:
        risk_id: Unique identifier.
        title: Short title.
        description: Detailed description.
        level: Risk severity level.
        status: Current lifecycle status.
        likelihood: Probability of occurrence (0.0 - 1.0).
        impact: Impact magnitude (0.0 - 1.0).
        score: Calculated risk score (likelihood * impact).
        owner: Person/team responsible.
        mitigation: Mitigation strategy.
        identified_date: When risk was first identified.
        last_reviewed: When risk was last reviewed.
    """
    risk_id: str
    title: str
    description: str
    level: RiskLevel
    status: RiskStatus
    likelihood: float
    impact: float
    score: float
    owner: str
    mitigation: str = ""
    identified_date: datetime = field(default_factory=datetime.utcnow)
    last_reviewed: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> dict:
        return {
            "risk_id": self.risk_id,
            "title": self.title,
            "description": self.description,
            "level": self.level.value,
            "status": self.status.value,
            "likelihood": self.likelihood,
            "impact": self.impact,
            "score": self.score,
            "owner": self.owner,
            "mitigation": self.mitigation,
            "identified_date": self.identified_date.isoformat(),
            "last_reviewed": self.last_reviewed.isoformat(),
        }


@dataclass
class ComplianceReport:
    """Report on compliance status for a specific framework.

    Attributes:
        framework: The compliance framework.
        overall_status: Aggregated status string.
        control_scores: Mapping of control_id to score.
        gaps: List of gap dicts {control_id, description, severity}.
        last_audit: When last audit occurred.
        next_audit: When next audit is scheduled.
    """
    framework: ComplianceFramework
    overall_status: str = "unknown"
    control_scores: Dict[str, float] = field(default_factory=dict)
    gaps: List[Dict[str, Any]] = field(default_factory=list)
    last_audit: Optional[datetime] = None
    next_audit: Optional[datetime] = None

    def to_dict(self) -> dict:
        return {
            "framework": self.framework.value,
            "overall_status": self.overall_status,
            "control_scores": dict(self.control_scores),
            "gaps": list(self.gaps),
            "last_audit": self.last_audit.isoformat() if self.last_audit else None,
            "next_audit": self.next_audit.isoformat() if self.next_audit else None,
        }


@dataclass
class FeedbackSummary:
    """Aggregated summary of user feedback.

    Attributes:
        total_feedback: Total number of feedback items.
        sentiment_distribution: Count per sentiment.
        top_themes: Most common themes extracted.
        average_rating: Average numeric rating.
        trend: Directional trend of sentiment.
    """
    total_feedback: int = 0
    sentiment_distribution: Dict[FeedbackSentiment, int] = field(default_factory=dict)
    top_themes: List[str] = field(default_factory=list)
    average_rating: float = 0.0
    trend: TrendDirection = TrendDirection.UNKNOWN

    def to_dict(self) -> dict:
        return {
            "total_feedback": self.total_feedback,
            "sentiment_distribution": {
                k.value: v for k, v in self.sentiment_distribution.items()
            },
            "top_themes": list(self.top_themes),
            "average_rating": self.average_rating,
            "trend": self.trend.value,
        }


@dataclass
class PerformanceTrend:
    """Analysis of a performance metric's trend.

    Attributes:
        metric_name: Name of the metric.
        direction: Trend direction.
        current_value: Most recent value.
        previous_value: Prior comparison value.
        change_percent: Percentage change.
        data_points: Historical data points [{timestamp, value}].
        forecast: Forecasted future value if available.
    """
    metric_name: str
    direction: TrendDirection = TrendDirection.UNKNOWN
    current_value: float = 0.0
    previous_value: float = 0.0
    change_percent: float = 0.0
    data_points: List[Dict[str, Any]] = field(default_factory=list)
    forecast: Optional[float] = None

    def to_dict(self) -> dict:
        return {
            "metric_name": self.metric_name,
            "direction": self.direction.value,
            "current_value": self.current_value,
            "previous_value": self.previous_value,
            "change_percent": self.change_percent,
            "data_points": list(self.data_points),
            "forecast": self.forecast,
        }


@dataclass
class ChangeApprovalEntry:
    """A single entry in the change approval log.

    Attributes:
        entry_id: Unique identifier.
        change_type: Type of change being proposed.
        title: Short description.
        requester: Who requested the change.
        status: Current approval status.
        risk_level: Assessed risk level.
        reviewers: List of reviewer identifiers.
        comments: List of comment dicts.
        created_at: When the entry was created.
        updated_at: When last updated.
    """
    entry_id: str
    change_type: ChangeType
    title: str
    requester: str
    status: ChangeApprovalStatus = ChangeApprovalStatus.PENDING
    risk_level: RiskLevel = RiskLevel.MEDIUM
    reviewers: List[str] = field(default_factory=list)
    comments: List[Dict[str, Any]] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> dict:
        return {
            "entry_id": self.entry_id,
            "change_type": self.change_type.value,
            "title": self.title,
            "requester": self.requester,
            "status": self.status.value,
            "risk_level": self.risk_level.value,
            "reviewers": list(self.reviewers),
            "comments": list(self.comments),
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }


@dataclass
class ChangeRecord:
    """Full record of a change through the governance process.

    Attributes:
        change_id: Unique identifier.
        approval_entry: The associated approval entry.
        diff: Human-readable diff of the change.
        rollback_plan: Plan to reverse the change.
        deployment_status: Current deployment state.
        deployed_at: When change was deployed.
    """
    change_id: str
    approval_entry: ChangeApprovalEntry
    diff: str = ""
    rollback_plan: str = ""
    deployment_status: str = "pending"
    deployed_at: Optional[datetime] = None

    def to_dict(self) -> dict:
        return {
            "change_id": self.change_id,
            "approval_entry": self.approval_entry.to_dict(),
            "diff": self.diff,
            "rollback_plan": self.rollback_plan,
            "deployment_status": self.deployment_status,
            "deployed_at": self.deployed_at.isoformat() if self.deployed_at else None,
        }


@dataclass
class IncidentRecord:
    """Record of a safety or operational incident.

    Attributes:
        incident_id: Unique identifier.
        title: Short title.
        description: Detailed description.
        severity: Incident severity level.
        status: Current incident status.
        detected_at: When the incident was first detected.
        resolved_at: When the incident was resolved.
        affected_systems: List of affected components.
        root_cause: Root cause analysis.
        timeline: List of timeline entries.
    """
    incident_id: str
    title: str
    description: str
    severity: IncidentSeverity
    status: IncidentStatus = IncidentStatus.OPEN
    detected_at: datetime = field(default_factory=datetime.utcnow)
    resolved_at: Optional[datetime] = None
    affected_systems: List[str] = field(default_factory=list)
    root_cause: str = ""
    timeline: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "incident_id": self.incident_id,
            "title": self.title,
            "description": self.description,
            "severity": self.severity.value,
            "status": self.status.value,
            "detected_at": self.detected_at.isoformat(),
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
            "affected_systems": list(self.affected_systems),
            "root_cause": self.root_cause,
            "timeline": list(self.timeline),
        }


@dataclass
class ComplianceStatus:
    """Snapshot of compliance status for a framework.

    Attributes:
        framework: The compliance framework.
        overall_status: Aggregated status label.
        control_count: Total number of controls.
        passing_count: Number of controls passing.
        failing_count: Number of controls failing.
        last_assessment: When last assessed.
        next_assessment: When next assessment is due.
    """
    framework: ComplianceFramework
    overall_status: str = "unknown"
    control_count: int = 0
    passing_count: int = 0
    failing_count: int = 0
    last_assessment: Optional[datetime] = None
    next_assessment: Optional[datetime] = None

    def to_dict(self) -> dict:
        return {
            "framework": self.framework.value,
            "overall_status": self.overall_status,
            "control_count": self.control_count,
            "passing_count": self.passing_count,
            "failing_count": self.failing_count,
            "last_assessment": self.last_assessment.isoformat() if self.last_assessment else None,
            "next_assessment": self.next_assessment.isoformat() if self.next_assessment else None,
        }


@dataclass
class TrendDataPoint:
    """A single data point in a trend analysis.

    Attributes:
        timestamp: When the data point was recorded.
        value: The observed value.
        label: Optional label for the data point.
    """
    timestamp: datetime = field(default_factory=datetime.utcnow)
    value: float = 0.0
    label: str = ""

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp.isoformat(),
            "value": self.value,
            "label": self.label,
        }


@dataclass
class UserFeedback:
    """A single user feedback entry.

    Attributes:
        feedback_id: Unique identifier.
        user_id: Identifier of the user.
        category: Feedback category.
        rating: Numeric rating.
        comment: Free-text comment.
        sentiment: Detected sentiment.
        metadata: Arbitrary additional data.
        timestamp: When feedback was submitted.
    """
    feedback_id: str
    user_id: str
    category: str
    rating: float
    comment: str = ""
    sentiment: Sentiment = Sentiment.NEUTRAL
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> dict:
        return {
            "feedback_id": self.feedback_id,
            "user_id": self.user_id,
            "category": self.category,
            "rating": self.rating,
            "comment": self.comment,
            "sentiment": self.sentiment.value,
            "metadata": dict(self.metadata),
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class BoardMeetingMinutes:
    """Minutes from a governance board meeting.

    Attributes:
        meeting_id: Unique identifier.
        meeting_type: Type of meeting.
        date: When the meeting occurred.
        attendees: List of attendees.
        agenda: Meeting agenda items.
        decisions: Decisions made during the meeting.
        action_items: Action items assigned.
        next_meeting: When the next meeting is scheduled.
    """
    meeting_id: str
    meeting_type: MeetingType
    date: datetime = field(default_factory=datetime.utcnow)
    attendees: List[str] = field(default_factory=list)
    agenda: List[str] = field(default_factory=list)
    decisions: List[Dict[str, Any]] = field(default_factory=list)
    action_items: List[Dict[str, Any]] = field(default_factory=list)
    next_meeting: Optional[datetime] = None

    def to_dict(self) -> dict:
        return {
            "meeting_id": self.meeting_id,
            "meeting_type": self.meeting_type.value,
            "date": self.date.isoformat(),
            "attendees": list(self.attendees),
            "agenda": list(self.agenda),
            "decisions": list(self.decisions),
            "action_items": list(self.action_items),
            "next_meeting": self.next_meeting.isoformat() if self.next_meeting else None,
        }


# ---------------------------------------------------------------------------
# Helper Utilities
# ---------------------------------------------------------------------------

def _generate_id(prefix: str = "") -> str:
    """Generate a short unique identifier with an optional prefix."""
    short = uuid.uuid4().hex[:12]
    return f"{prefix}_{short}" if prefix else short


def _now() -> datetime:
    """Return current UTC datetime."""
    return datetime.utcnow()


def _compute_risk_score(likelihood: float, impact: float) -> float:
    """Compute a 0.0-1.0 risk score from likelihood and impact."""
    return round(min(max(likelihood, 0.0), 1.0) * min(max(impact, 0.0), 1.0), 4)


def _level_from_score(score: float) -> RiskLevel:
    """Map a numeric score to a RiskLevel."""
    if score >= 0.8:
        return RiskLevel.CRITICAL
    elif score >= 0.6:
        return RiskLevel.HIGH
    elif score >= 0.35:
        return RiskLevel.MEDIUM
    elif score >= 0.1:
        return RiskLevel.LOW
    else:
        return RiskLevel.NEGLIGIBLE


# ---------------------------------------------------------------------------
# 1. ModelChangeReview
# ---------------------------------------------------------------------------

class ModelChangeReview:
    """Manages the lifecycle of model change reviews.

    Tracks submissions, reviewer decisions, and enforces required-approver
    thresholds. Thread-safe for concurrent access.

    Args:
        required_approvers: Number of distinct approvers required for approval.
        auto_approve_low_risk: If True, low/negligible risk changes auto-approve.
    """

    def __init__(self, required_approvers: int = 2, auto_approve_low_risk: bool = False):
        self.required_approvers = max(1, required_approvers)
        self.auto_approve_low_risk = auto_approve_low_risk
        self._lock = threading.Lock()
        # Internal storage keyed by review_id
        self._reviews: Dict[str, Dict[str, Any]] = {}
        self._history: deque = deque(maxlen=10000)

    def submit_change(
        self,
        model_name: str,
        change_description: str,
        requester: str,
        risk_level: RiskLevel,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Submit a new model change for review.

        Args:
            model_name: Name of the model being changed.
            change_description: Description of the proposed change.
            requester: Identity of the requester.
            risk_level: Assessed risk level of the change.
            metadata: Optional arbitrary metadata.

        Returns:
            The generated review_id.
        """
        review_id = _generate_id("mcr")
        entry: Dict[str, Any] = {
            "review_id": review_id,
            "model_name": model_name,
            "change_description": change_description,
            "requester": requester,
            "risk_level": risk_level,
            "status": ReviewStatus.PENDING,
            "approvals": set(),
            "rejections": set(),
            "comments": [],
            "conditions": [],
            "metadata": metadata or {},
            "created_at": _now(),
            "updated_at": _now(),
        }
        with self._lock:
            self._reviews[review_id] = entry
            self._history.append({
                "action": "submit",
                "review_id": review_id,
                "timestamp": _now().isoformat(),
            })
        logger.info(
            "Model change submitted: review_id=%s model=%s risk=%s requester=%s",
            review_id, model_name, risk_level.value, requester,
        )
        # Auto-approve low-risk if enabled
        if self.auto_approve_low_risk and risk_level in (RiskLevel.LOW, RiskLevel.NEGLIGIBLE):
            self._auto_approve(review_id)
        return review_id

    def review(
        self,
        review_id: str,
        reviewer: str,
        decision: ReviewStatus,
        comments: str = "",
    ) -> Optional[ReviewDecision]:
        """Record a reviewer's decision on a pending review.

        Args:
            review_id: The review to act on.
            reviewer: Identity of the reviewer.
            decision: The reviewer's decision.
            comments: Optional comments.

        Returns:
            ReviewDecision if the review reaches a terminal state, else None.

        Raises:
            ValueError: If review_id is unknown.
        """
        with self._lock:
            if review_id not in self._reviews:
                raise ValueError(f"Unknown review_id: {review_id}")
            entry = self._reviews[review_id]
            if entry["status"] in (ReviewStatus.APPROVED, ReviewStatus.REJECTED, ReviewStatus.WITHDRAWN):
                logger.warning("Review %s already in terminal state: %s", review_id, entry["status"].value)
                return None

            entry["status"] = ReviewStatus.IN_REVIEW
            entry["updated_at"] = _now()

            if decision == ReviewStatus.APPROVED:
                entry["approvals"].add(reviewer)
            elif decision == ReviewStatus.REJECTED:
                entry["rejections"].add(reviewer)
            elif decision == ReviewStatus.NEEDS_CHANGES:
                pass  # handled below

            if comments:
                entry["comments"].append({
                    "reviewer": reviewer,
                    "comment": comments,
                    "timestamp": _now().isoformat(),
                })

            # Determine if we can finalize
            if decision == ReviewStatus.REJECTED:
                entry["status"] = ReviewStatus.REJECTED
            elif decision == ReviewStatus.NEEDS_CHANGES:
                entry["status"] = ReviewStatus.NEEDS_CHANGES
            elif len(entry["approvals"]) >= self.required_approvers:
                entry["status"] = ReviewStatus.APPROVED

            self._history.append({
                "action": "review",
                "review_id": review_id,
                "reviewer": reviewer,
                "decision": decision.value,
                "timestamp": _now().isoformat(),
            })

            if entry["status"] in (ReviewStatus.APPROVED, ReviewStatus.REJECTED):
                return self._build_decision(entry)
        return None

    def get_status(self, review_id: str) -> ReviewDecision:
        """Get the current decision for a review.

        Args:
            review_id: The review to query.

        Returns:
            ReviewDecision with current state.

        Raises:
            ValueError: If review_id is unknown.
        """
        with self._lock:
            if review_id not in self._reviews:
                raise ValueError(f"Unknown review_id: {review_id}")
            return self._build_decision(self._reviews[review_id])

    def get_pending_reviews(self) -> List[Dict[str, Any]]:
        """Return all reviews that have not reached a terminal state."""
        with self._lock:
            return [
                {
                    "review_id": r["review_id"],
                    "model_name": r["model_name"],
                    "requester": r["requester"],
                    "risk_level": r["risk_level"].value,
                    "status": r["status"].value,
                    "approval_count": len(r["approvals"]),
                    "required_approvers": self.required_approvers,
                }
                for r in self._reviews.values()
                if r["status"] not in (ReviewStatus.APPROVED, ReviewStatus.REJECTED, ReviewStatus.WITHDRAWN)
            ]

    def get_history(self, model_name: Optional[str] = None) -> List[Dict[str, Any]]:
        """Return review history, optionally filtered by model_name."""
        with self._lock:
            entries = list(self._history)
        if model_name:
            entries = [
                e for e in entries
                if e.get("model_name", "") == model_name
            ]
        return entries[-500:]  # limit return size

    def to_dict(self) -> dict:
        """Serialize the full state of this board."""
        with self._lock:
            return {
                "required_approvers": self.required_approvers,
                "auto_approve_low_risk": self.auto_approve_low_risk,
                "pending_count": sum(
                    1 for r in self._reviews.values()
                    if r["status"] not in (ReviewStatus.APPROVED, ReviewStatus.REJECTED, ReviewStatus.WITHDRAWN)
                ),
                "total_reviews": len(self._reviews),
            }

    # --- internal helpers ---

    def _build_decision(self, entry: Dict[str, Any]) -> ReviewDecision:
        return ReviewDecision(
            review_id=entry["review_id"],
            status=entry["status"],
            approved_by=sorted(entry["approvals"]),
            rejected_by=sorted(entry["rejections"]),
            comments=list(entry["comments"]),
            timestamp=entry["updated_at"],
            conditions=list(entry["conditions"]),
        )

    def _auto_approve(self, review_id: str) -> None:
        """Automatically approve a low/negligible risk review."""
        with self._lock:
            entry = self._reviews.get(review_id)
            if entry:
                entry["status"] = ReviewStatus.APPROVED
                entry["updated_at"] = _now()
                entry["approvals"].add("__auto__")
                entry["comments"].append({
                    "reviewer": "__system__",
                    "comment": "Auto-approved (low risk).",
                    "timestamp": _now().isoformat(),
                })
                self._history.append({
                    "action": "auto_approve",
                    "review_id": review_id,
                    "timestamp": _now().isoformat(),
                })


# ---------------------------------------------------------------------------
# 2. PromptChangeApproval
# ---------------------------------------------------------------------------

class PromptChangeApproval:
    """Manages a staged approval pipeline for prompt changes.

    Prompts move sequentially through configurable approval stages.  Each
    stage requires at least one reviewer to approve before advancing.

    Args:
        stages: Ordered list of ApprovalStage values to traverse.
    """

    DEFAULT_STAGES: List[ApprovalStage] = [
        ApprovalStage.DRAFT,
        ApprovalStage.TECHNICAL_REVIEW,
        ApprovalStage.SECURITY_REVIEW,
        ApprovalStage.ETHICS_REVIEW,
        ApprovalStage.FINAL_APPROVAL,
    ]

    def __init__(self, stages: Optional[List[ApprovalStage]] = None):
        self._stages: List[ApprovalStage] = stages or list(self.DEFAULT_STAGES)
        self._lock = threading.Lock()
        self._changes: Dict[str, Dict[str, Any]] = {}
        self._history: deque = deque(maxlen=10000)

    def submit_prompt_change(
        self,
        prompt_name: str,
        old_prompt: str,
        new_prompt: str,
        requester: str,
        justification: str,
    ) -> str:
        """Submit a prompt change for staged approval.

        Args:
            prompt_name: Name/identifier of the prompt.
            old_prompt: Current prompt text.
            new_prompt: Proposed new prompt text.
            requester: Identity of the requester.
            justification: Business/technical justification.

        Returns:
            The generated change_id.
        """
        change_id = _generate_id("pca")
        entry: Dict[str, Any] = {
            "change_id": change_id,
            "prompt_name": prompt_name,
            "old_prompt": old_prompt,
            "new_prompt": new_prompt,
            "requester": requester,
            "justification": justification,
            "current_stage_index": 0,
            "stage_approvals": {s.value: [] for s in self._stages},
            "comments": [],
            "created_at": _now(),
            "updated_at": _now(),
        }
        with self._lock:
            self._changes[change_id] = entry
            self._history.append({
                "action": "submit",
                "change_id": change_id,
                "prompt_name": prompt_name,
                "timestamp": _now().isoformat(),
            })
        logger.info("Prompt change submitted: %s (%s)", change_id, prompt_name)
        return change_id

    def advance_stage(
        self,
        change_id: str,
        reviewer: str,
        approved: bool,
        comments: str = "",
    ) -> Optional[ApprovalStage]:
        """Record a reviewer's decision at the current stage.

        If approved, the change advances to the next stage.  If rejected,
        the change is returned to DRAFT.

        Args:
            change_id: The change to act on.
            reviewer: Identity of the reviewer.
            approved: Whether the reviewer approves.
            comments: Optional comments.

        Returns:
            The new current stage after processing, or None if change unknown.

        Raises:
            ValueError: If change_id is unknown.
        """
        with self._lock:
            if change_id not in self._changes:
                raise ValueError(f"Unknown change_id: {change_id}")
            entry = self._changes[change_id]
            idx = entry["current_stage_index"]
            if idx >= len(self._stages):
                logger.warning("Change %s already fully approved.", change_id)
                return self._stages[-1]

            current_stage = self._stages[idx]
            stage_key = current_stage.value

            if comments:
                entry["comments"].append({
                    "stage": stage_key,
                    "reviewer": reviewer,
                    "comment": comments,
                    "approved": approved,
                    "timestamp": _now().isoformat(),
                })

            if approved:
                entry["stage_approvals"][stage_key].append(reviewer)
                entry["current_stage_index"] = idx + 1
                entry["updated_at"] = _now()
                self._history.append({
                    "action": "advance",
                    "change_id": change_id,
                    "from_stage": stage_key,
                    "reviewer": reviewer,
                    "timestamp": _now().isoformat(),
                })
                logger.info("Prompt change %s advanced past %s", change_id, stage_key)
            else:
                # Rejection sends back to DRAFT
                entry["current_stage_index"] = 0
                entry["updated_at"] = _now()
                self._history.append({
                    "action": "reject",
                    "change_id": change_id,
                    "stage": stage_key,
                    "reviewer": reviewer,
                    "timestamp": _now().isoformat(),
                })
                logger.info("Prompt change %s rejected at %s, returned to DRAFT", change_id, stage_key)

            new_idx = entry["current_stage_index"]
            return self._stages[new_idx] if new_idx < len(self._stages) else None

    def get_current_stage(self, change_id: str) -> ApprovalStage:
        """Return the current approval stage for a change.

        Raises:
            ValueError: If change_id is unknown.
        """
        with self._lock:
            if change_id not in self._changes:
                raise ValueError(f"Unknown change_id: {change_id}")
            entry = self._changes[change_id]
            idx = entry["current_stage_index"]
            if idx >= len(self._stages):
                return self._stages[-1]  # fully approved
            return self._stages[idx]

    def get_diff(self, change_id: str) -> Dict[str, Any]:
        """Return the old-vs-new diff for a prompt change.

        Raises:
            ValueError: If change_id is unknown.
        """
        import difflib
        with self._lock:
            if change_id not in self._changes:
                raise ValueError(f"Unknown change_id: {change_id}")
            entry = self._changes[change_id]
            old_lines = entry["old_prompt"].splitlines(keepends=True)
            new_lines = entry["new_prompt"].splitlines(keepends=True)
            diff = list(difflib.unified_diff(
                old_lines, new_lines,
                fromfile="old_prompt", tofile="new_prompt",
            ))
            return {
                "change_id": change_id,
                "prompt_name": entry["prompt_name"],
                "diff": "".join(diff),
                "old_length": len(entry["old_prompt"]),
                "new_length": len(entry["new_prompt"]),
            }

    def get_pending_approvals(self) -> List[Dict[str, Any]]:
        """Return all changes that have not yet passed all stages."""
        with self._lock:
            results = []
            for entry in self._changes.values():
                idx = entry["current_stage_index"]
                if idx >= len(self._stages):
                    continue  # fully approved
                current = self._stages[idx]
                results.append({
                    "change_id": entry["change_id"],
                    "prompt_name": entry["prompt_name"],
                    "requester": entry["requester"],
                    "current_stage": current.value,
                    "created_at": entry["created_at"].isoformat(),
                })
            return results

    def rollback(self, change_id: str, requester: str) -> bool:
        """Rollback a change (marks it as returned to DRAFT).

        Args:
            change_id: The change to rollback.
            requester: Identity requesting rollback.

        Returns:
            True if rollback succeeded, False if change not found.
        """
        with self._lock:
            if change_id not in self._changes:
                return False
            entry = self._changes[change_id]
            entry["current_stage_index"] = 0
            entry["updated_at"] = _now()
            entry["comments"].append({
                "stage": "__rollback__",
                "reviewer": requester,
                "comment": "Rollback requested.",
                "approved": False,
                "timestamp": _now().isoformat(),
            })
            self._history.append({
                "action": "rollback",
                "change_id": change_id,
                "requester": requester,
                "timestamp": _now().isoformat(),
            })
            logger.info("Prompt change %s rolled back by %s", change_id, requester)
            return True

    def to_dict(self) -> dict:
        """Serialize the full state of this pipeline."""
        with self._lock:
            return {
                "stages": [s.value for s in self._stages],
                "total_changes": len(self._changes),
                "pending_count": sum(
                    1 for e in self._changes.values()
                    if e["current_stage_index"] < len(self._stages)
                ),
            }


# ---------------------------------------------------------------------------
# 3. ToolChangeImpactAssessment
# ---------------------------------------------------------------------------

class ToolChangeImpactAssessment:
    """Assesses the impact of proposed changes to tool configurations.

    Produces an ImpactAssessment with affected components, risk factors,
    mitigation steps, and a rollback plan.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._assessments: Dict[str, ImpactAssessment] = {}

    def assess(
        self,
        tool_name: str,
        current_config: Dict[str, Any],
        proposed_config: Dict[str, Any],
    ) -> ImpactAssessment:
        """Assess the impact of a proposed tool configuration change.

        Args:
            tool_name: Name of the tool being changed.
            current_config: Current configuration dict.
            proposed_config: Proposed configuration dict.

        Returns:
            An ImpactAssessment detailing the impact.
        """
        change_id = _generate_id("tia")

        # Determine affected keys
        all_keys = set(current_config.keys()) | set(proposed_config.keys())
        changed_keys = []
        added_keys = []
        removed_keys = []
        for k in all_keys:
            in_cur = k in current_config
            in_prop = k in proposed_config
            if in_cur and in_prop:
                if current_config[k] != proposed_config[k]:
                    changed_keys.append(k)
            elif in_prop and not in_cur:
                added_keys.append(k)
            elif in_cur and not in_prop:
                removed_keys.append(k)

        affected_components = [tool_name]
        risk_factors: List[str] = []
        mitigation_steps: List[str] = []

        # Simple heuristic impact analysis
        change_count = len(changed_keys) + len(added_keys) + len(removed_keys)

        if "api_key" in changed_keys or "secret" in changed_keys or "token" in changed_keys:
            risk_factors.append("Sensitive credential modification detected.")
            mitigation_steps.append("Verify new credential validity before deploying.")

        if "endpoint" in changed_keys or "base_url" in changed_keys:
            risk_factors.append("Endpoint URL change — connectivity risk.")
            mitigation_steps.append("Run connectivity test against new endpoint.")

        if change_count > 5:
            risk_factors.append(f"Large change surface: {change_count} keys modified.")
            mitigation_steps.append("Stage rollout and monitor all affected paths.")
            impact_level = ImpactLevel.MAJOR
        elif change_count > 2:
            impact_level = ImpactLevel.MODERATE
        elif change_count > 0:
            impact_level = ImpactLevel.MINOR
        else:
            impact_level = ImpactLevel.NONE

        if removed_keys:
            risk_factors.append(f"Removed keys: {removed_keys}")
            mitigation_steps.append("Ensure no downstream consumers depend on removed keys.")

        rollback_plan = (
            f"To rollback {tool_name}: restore previous configuration. "
            f"Changed keys: {changed_keys}, Added: {added_keys}, Removed: {removed_keys}."
        )

        assessment = ImpactAssessment(
            change_id=change_id,
            impact_level=impact_level,
            affected_components=affected_components + list(all_keys),
            rollback_plan=rollback_plan,
            risk_factors=risk_factors,
            mitigation_steps=mitigation_steps,
        )

        with self._lock:
            self._assessments[change_id] = assessment

        logger.info(
            "Tool impact assessed: %s change_id=%s impact=%s",
            tool_name, change_id, impact_level.value,
        )
        return assessment

    def simulate_impact(self, tool_name: str, change: Dict[str, Any]) -> Dict[str, Any]:
        """Simulate the effect of a change without persisting.

        Args:
            tool_name: Name of the tool.
            change: Dict mapping key->new_value for proposed changes.

        Returns:
            Simulation result dict with predicted effects.
        """
        sim_id = _generate_id("sim")
        affected = list(change.keys())
        risk_score = min(len(affected) * 0.15, 1.0)
        return {
            "simulation_id": sim_id,
            "tool_name": tool_name,
            "affected_keys": affected,
            "predicted_risk_score": risk_score,
            "recommendation": (
                "safe_to_proceed" if risk_score < 0.4
                else "caution_advised" if risk_score < 0.7
                else "high_risk_review_required"
            ),
            "timestamp": _now().isoformat(),
        }

    def generate_rollback_plan(self, tool_name: str, proposed_config: Dict[str, Any]) -> str:
        """Generate a human-readable rollback plan.

        Args:
            tool_name: Name of the tool.
            proposed_config: The proposed configuration.

        Returns:
            Rollback plan as a string.
        """
        keys = list(proposed_config.keys())
        steps = [
            f"Rollback plan for {tool_name}:",
            f"1. Stop any active processes using {tool_name}.",
            f"2. Restore previous configuration for keys: {', '.join(keys[:10])}.",
            "3. Validate configuration integrity.",
            f"4. Restart {tool_name} and verify functionality.",
            "5. Monitor for 15 minutes post-rollback.",
        ]
        return "\n".join(steps)

    def to_dict(self) -> dict:
        """Serialize the full state."""
        with self._lock:
            return {
                "total_assessments": len(self._assessments),
            }


# ---------------------------------------------------------------------------
# 4. SecurityChangeReview
# ---------------------------------------------------------------------------

class SecurityChangeReview:
    """Manages security-focused reviews for infrastructure or config changes.

    Tracks risk levels, affected systems, security officer approvals,
    and maintains a security posture summary.

    Args:
        security_officers: List of authorized security officer identifiers.
    """

    def __init__(self, security_officers: Optional[List[str]] = None):
        self._officers: Set[str] = set(security_officers or [])
        self._lock = threading.Lock()
        self._reviews: Dict[str, Dict[str, Any]] = {}
        self._security_events: deque = deque(maxlen=5000)

    def submit_review(
        self,
        change_description: str,
        affected_systems: List[str],
        risk_level: RiskLevel,
        requester: str,
    ) -> str:
        """Submit a security change for review.

        Args:
            change_description: Description of the change.
            affected_systems: List of affected system names.
            risk_level: Assessed risk level.
            requester: Identity of the requester.

        Returns:
            The generated review_id.
        """
        review_id = _generate_id("scr")
        entry: Dict[str, Any] = {
            "review_id": review_id,
            "change_description": change_description,
            "affected_systems": list(affected_systems),
            "risk_level": risk_level,
            "requester": requester,
            "status": ReviewStatus.PENDING,
            "approvals": [],
            "rejections": [],
            "conditions": [],
            "created_at": _now(),
            "updated_at": _now(),
        }
        with self._lock:
            self._reviews[review_id] = entry
            self._security_events.append({
                "event": "submit",
                "review_id": review_id,
                "timestamp": _now().isoformat(),
            })
        logger.info("Security review submitted: %s risk=%s", review_id, risk_level.value)
        return review_id

    def approve(
        self,
        review_id: str,
        officer: str,
        conditions: Optional[List[str]] = None,
    ) -> bool:
        """Approve a security review.

        Args:
            review_id: The review to approve.
            officer: The approving officer's identifier.
            conditions: Optional conditions attached to approval.

        Returns:
            True if approval succeeded.

        Raises:
            ValueError: If review_id is unknown.
        """
        with self._lock:
            if review_id not in self._reviews:
                raise ValueError(f"Unknown review_id: {review_id}")
            entry = self._reviews[review_id]
            entry["approvals"].append({
                "officer": officer,
                "timestamp": _now().isoformat(),
            })
            if conditions:
                entry["conditions"].extend(conditions)
            entry["status"] = ReviewStatus.APPROVED
            entry["updated_at"] = _now()
            self._security_events.append({
                "event": "approve",
                "review_id": review_id,
                "officer": officer,
                "timestamp": _now().isoformat(),
            })
            logger.info("Security review %s approved by %s", review_id, officer)
            return True

    def reject(self, review_id: str, officer: str, reason: str) -> bool:
        """Reject a security review.

        Args:
            review_id: The review to reject.
            officer: The rejecting officer's identifier.
            reason: Reason for rejection.

        Returns:
            True if rejection succeeded.

        Raises:
            ValueError: If review_id is unknown.
        """
        with self._lock:
            if review_id not in self._reviews:
                raise ValueError(f"Unknown review_id: {review_id}")
            entry = self._reviews[review_id]
            entry["rejections"].append({
                "officer": officer,
                "reason": reason,
                "timestamp": _now().isoformat(),
            })
            entry["status"] = ReviewStatus.REJECTED
            entry["updated_at"] = _now()
            self._security_events.append({
                "event": "reject",
                "review_id": review_id,
                "officer": officer,
                "timestamp": _now().isoformat(),
            })
            logger.info("Security review %s rejected by %s: %s", review_id, officer, reason)
            return True

    def get_security_posture(self) -> Dict[str, Any]:
        """Return a summary of the current security posture."""
        with self._lock:
            total = len(self._reviews)
            approved = sum(1 for r in self._reviews.values() if r["status"] == ReviewStatus.APPROVED)
            rejected = sum(1 for r in self._reviews.values() if r["status"] == ReviewStatus.REJECTED)
            pending = sum(1 for r in self._reviews.values() if r["status"] == ReviewStatus.PENDING)
            critical_pending = sum(
                1 for r in self._reviews.values()
                if r["status"] == ReviewStatus.PENDING and r["risk_level"] == RiskLevel.CRITICAL
            )
            return {
                "total_reviews": total,
                "approved": approved,
                "rejected": rejected,
                "pending": pending,
                "critical_pending": critical_pending,
                "officers": sorted(self._officers),
                "last_event": self._security_events[-1] if self._security_events else None,
            }

    def to_dict(self) -> dict:
        """Serialize the full state."""
        return self.get_security_posture()


# ---------------------------------------------------------------------------
# 5. IncidentReviewBoard
# ---------------------------------------------------------------------------

class IncidentReviewBoard:
    """Coordinates post-incident review board activities.

    Tracks convened boards, findings, action items, and resolution status.

    Args:
        board_members: List of board member identifiers.
    """

    def __init__(self, board_members: Optional[List[str]] = None):
        self._members: List[str] = list(board_members or [])
        self._lock = threading.Lock()
        self._incidents: Dict[str, Dict[str, Any]] = {}

    def convene(self, incident_id: str, severity: str) -> Dict[str, Any]:
        """Convene the review board for an incident.

        Args:
            incident_id: Identifier of the incident.
            severity: Severity label (e.g., 'SEV1', 'SEV2').

        Returns:
            The incident board record.
        """
        board_id = _generate_id("irb")
        record: Dict[str, Any] = {
            "board_id": board_id,
            "incident_id": incident_id,
            "severity": severity,
            "members": list(self._members),
            "findings": {},
            "action_items": [],
            "status": "convened",
            "convened_at": _now(),
            "resolved_at": None,
        }
        with self._lock:
            self._incidents[incident_id] = record
        logger.info("IRB convened for incident %s (severity=%s)", incident_id, severity)
        return dict(record)

    def document_findings(self, incident_id: str, findings: Dict[str, Any]) -> bool:
        """Record the board's findings for an incident.

        Args:
            incident_id: The incident identifier.
            findings: Dict of findings (root_cause, timeline, impact, etc.).

        Returns:
            True if findings were recorded, False if incident not found.
        """
        with self._lock:
            if incident_id not in self._incidents:
                return False
            self._incidents[incident_id]["findings"] = findings
            self._incidents[incident_id]["status"] = "findings_documented"
        logger.info("Findings documented for incident %s", incident_id)
        return True

    def assign_action_items(self, incident_id: str, items: List[Dict[str, Any]]) -> bool:
        """Assign action items resulting from the review.

        Args:
            incident_id: The incident identifier.
            items: List of action item dicts {assignee, description, due_date}.

        Returns:
            True if items were assigned, False if incident not found.
        """
        with self._lock:
            if incident_id not in self._incidents:
                return False
            for item in items:
                item.setdefault("status", "open")
                item.setdefault("created_at", _now().isoformat())
            self._incidents[incident_id]["action_items"].extend(items)
            self._incidents[incident_id]["status"] = "actions_assigned"
        logger.info("Action items assigned for incident %s", incident_id)
        return True

    def track_resolution(self, incident_id: str) -> Dict[str, Any]:
        """Get the resolution tracking status for an incident.

        Args:
            incident_id: The incident identifier.

        Returns:
            Dict with resolution status, or error if not found.
        """
        with self._lock:
            if incident_id not in self._incidents:
                return {"error": f"Unknown incident: {incident_id}"}
            rec = self._incidents[incident_id]
            total_actions = len(rec["action_items"])
            closed_actions = sum(1 for a in rec["action_items"] if a.get("status") == "closed")
            return {
                "incident_id": incident_id,
                "board_status": rec["status"],
                "severity": rec["severity"],
                "total_actions": total_actions,
                "closed_actions": closed_actions,
                "open_actions": total_actions - closed_actions,
                "convened_at": rec["convened_at"].isoformat(),
                "resolved_at": rec["resolved_at"].isoformat() if rec["resolved_at"] else None,
            }

    def get_open_actions(self) -> List[Dict[str, Any]]:
        """Return all open action items across all incidents."""
        with self._lock:
            result = []
            for incident_id, rec in self._incidents.items():
                for item in rec["action_items"]:
                    if item.get("status") != "closed":
                        result.append({
                            "incident_id": incident_id,
                            **item,
                        })
            return result

    def to_dict(self) -> dict:
        """Serialize the full state."""
        with self._lock:
            return {
                "members": list(self._members),
                "total_incidents": len(self._incidents),
                "open_actions": len(self.get_open_actions()),
            }


# ---------------------------------------------------------------------------
# 6. ComplianceDashboard
# ---------------------------------------------------------------------------

class ComplianceDashboard:
    """Tracks compliance across multiple frameworks.

    Maintains control scores, gap analysis, and audit scheduling per framework.

    Args:
        frameworks: Optional initial list of frameworks to track.
    """

    def __init__(self, frameworks: Optional[List[ComplianceFramework]] = None):
        self._lock = threading.Lock()
        # framework -> ComplianceReport
        self._reports: Dict[ComplianceFramework, ComplianceReport] = {}
        if frameworks:
            for fw in frameworks:
                self.add_framework(fw)

    def add_framework(self, framework: ComplianceFramework) -> None:
        """Register a new compliance framework for tracking.

        Args:
            framework: The framework to add.
        """
        with self._lock:
            if framework not in self._reports:
                self._reports[framework] = ComplianceReport(framework=framework)
                logger.info("Compliance framework added: %s", framework.value)

    def update_control(
        self,
        framework: ComplianceFramework,
        control_id: str,
        score: float,
        evidence: str = "",
    ) -> None:
        """Update the score for a specific control within a framework.

        Args:
            framework: The target framework.
            control_id: The control identifier.
            score: Numeric score (0.0 - 1.0).
            evidence: Optional evidence string.

        Raises:
            ValueError: If framework is not registered.
        """
        with self._lock:
            if framework not in self._reports:
                raise ValueError(f"Framework not registered: {framework.value}")
            report = self._reports[framework]
            clamped = min(max(score, 0.0), 1.0)
            report.control_scores[control_id] = clamped
            if evidence:
                # store evidence alongside gap data if score is low
                if clamped < 0.7:
                    existing_gap = next(
                        (g for g in report.gaps if g.get("control_id") == control_id), None
                    )
                    if existing_gap:
                        existing_gap["evidence"] = evidence
                        existing_gap["score"] = clamped
            self._update_overall_status(framework)
            logger.debug("Control %s/%s updated to %.2f", framework.value, control_id, clamped)

    def get_status(self) -> List[ComplianceReport]:
        """Return compliance reports for all tracked frameworks."""
        with self._lock:
            return list(self._reports.values())

    def get_gaps(self) -> List[Dict[str, Any]]:
        """Return all compliance gaps across frameworks."""
        with self._lock:
            result = []
            for fw, report in self._reports.items():
                for control_id, score in report.control_scores.items():
                    if score < 0.7:
                        gap = next(
                            (g for g in report.gaps if g.get("control_id") == control_id),
                            {"control_id": control_id, "description": "Below threshold", "severity": "medium"},
                        )
                        result.append({
                            "framework": fw.value,
                            "control_id": control_id,
                            "score": score,
                            **gap,
                        })
                # also include explicitly documented gaps not yet scored
                for gap in report.gaps:
                    if gap.get("control_id") not in report.control_scores:
                        result.append({
                            "framework": fw.value,
                            "control_id": gap.get("control_id", "unknown"),
                            "score": 0.0,
                            **gap,
                        })
            return result

    def schedule_audit(self, framework: ComplianceFramework, date: datetime) -> None:
        """Schedule the next audit for a framework.

        Args:
            framework: The target framework.
            date: When the next audit should occur.

        Raises:
            ValueError: If framework is not registered.
        """
        with self._lock:
            if framework not in self._reports:
                raise ValueError(f"Framework not registered: {framework.value}")
            report = self._reports[framework]
            report.next_audit = date
            logger.info("Audit scheduled for %s on %s", framework.value, date.isoformat())

    def to_dict(self) -> dict:
        """Serialize the full state."""
        with self._lock:
            return {
                "frameworks": [fw.value for fw in self._reports.keys()],
                "reports": [r.to_dict() for r in self._reports.values()],
            }

    # --- internal ---

    def _update_overall_status(self, framework: ComplianceFramework) -> None:
        report = self._reports[framework]
        if not report.control_scores:
            report.overall_status = "no_data"
            return
        avg = sum(report.control_scores.values()) / len(report.control_scores)
        if avg >= 0.9:
            report.overall_status = "compliant"
        elif avg >= 0.7:
            report.overall_status = "mostly_compliant"
        elif avg >= 0.5:
            report.overall_status = "partially_compliant"
        else:
            report.overall_status = "non_compliant"


# ---------------------------------------------------------------------------
# 7. UserFeedbackAggregator
# ---------------------------------------------------------------------------

class UserFeedbackAggregator:
    """Collects, aggregates, and analyzes user feedback.

    Supports sentiment detection, theme extraction, and time-windowed
    aggregation for trend analysis.
    """

    # Simple sentiment keyword lists
    _POSITIVE_WORDS: Set[str] = {
        "great", "excellent", "good", "love", "amazing", "helpful", "fantastic",
        "wonderful", "perfect", "best", "thank", "thanks", "brilliant", "awesome",
        "happy", "pleased", "impressed", "outstanding",
    }
    _NEGATIVE_WORDS: Set[str] = {
        "bad", "terrible", "awful", "hate", "poor", "worst", "broken", "useless",
        "frustrating", "annoying", "disappointed", "slow", "bug", "error", "fail",
        "failure", "incorrect", "wrong", "confusing", "difficult",
    }

    def __init__(self):
        self._lock = threading.Lock()
        self._feedback: deque = deque(maxlen=50000)
        self._id_counter: int = 0

    def collect_feedback(
        self,
        user_id: str,
        category: str,
        rating: float,
        comment: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Collect a single user feedback entry.

        Args:
            user_id: Identifier of the user.
            category: Feedback category (e.g., 'ui', 'performance').
            rating: Numeric rating (e.g., 1-5).
            comment: Optional free-text comment.
            metadata: Optional additional data.

        Returns:
            The feedback entry ID.
        """
        with self._lock:
            self._id_counter += 1
            feeback_id = f"fb_{self._id_counter}"
            sentiment = self.detect_sentiment(comment) if comment else FeedbackSentiment.NEUTRAL
            entry = {
                "feedback_id": feeback_id,
                "user_id": user_id,
                "category": category,
                "rating": float(rating),
                "comment": comment,
                "sentiment": sentiment,
                "metadata": metadata or {},
                "timestamp": _now(),
            }
            self._feedback.append(entry)
            logger.debug("Feedback collected: %s from %s", feeback_id, user_id)
            return feeback_id

    def aggregate(self, time_window: Optional[timedelta] = None) -> FeedbackSummary:
        """Aggregate feedback, optionally within a time window.

        Args:
            time_window: Optional timedelta to limit the lookback.

        Returns:
            FeedbackSummary with aggregated metrics.
        """
        with self._lock:
            entries = list(self._feedback)
        now = _now()
        if time_window:
            cutoff = now - time_window
            entries = [e for e in entries if e["timestamp"] >= cutoff]

        total = len(entries)
        if total == 0:
            return FeedbackSummary()

        # Sentiment distribution
        dist: Dict[FeedbackSentiment, int] = defaultdict(int)
        for e in entries:
            dist[e["sentiment"]] += 1

        # Average rating
        avg_rating = sum(e["rating"] for e in entries) / total

        # Theme extraction from comments
        comments = [e["comment"] for e in entries if e["comment"]]
        themes = self.extract_themes(comments)

        # Trend detection
        trend = self._compute_trend(entries)

        return FeedbackSummary(
            total_feedback=total,
            sentiment_distribution=dict(dist),
            top_themes=themes[:10],
            average_rating=round(avg_rating, 2),
            trend=trend,
        )

    def extract_themes(self, comments: List[str]) -> List[str]:
        """Extract common themes from a list of comment strings.

        Uses simple word-frequency heuristics.

        Args:
            comments: List of comment strings.

        Returns:
            List of extracted theme keywords, sorted by frequency.
        """
        if not comments:
            return []

        word_counts: Dict[str, int] = defaultdict(int)
        stop_words = {
            "the", "a", "an", "is", "are", "was", "were", "it", "and", "or",
            "but", "in", "on", "to", "for", "of", "with", "at", "from", "by",
            "this", "that", "i", "you", "he", "she", "they", "we", "my", "your",
            "me", "be", "have", "has", "do", "does", "not", "so", "if", "no",
            "yes", "just", "very", "really", "too", "can", "will", "would",
        }
        for comment in comments:
            words = re.findall(r'\b[a-zA-Z]{3,}\b', comment.lower())
            for word in words:
                if word not in stop_words:
                    word_counts[word] += 1

        return sorted(word_counts, key=word_counts.get, reverse=True)

    def detect_sentiment(self, text: str) -> FeedbackSentiment:
        """Detect the sentiment of a text string.

        Uses keyword-matching heuristics.

        Args:
            text: The text to analyze.

        Returns:
            Detected FeedbackSentiment.
        """
        if not text:
            return FeedbackSentiment.NEUTRAL
        lowered = text.lower()
        positive_count = sum(1 for w in self._POSITIVE_WORDS if w in lowered)
        negative_count = sum(1 for w in self._NEGATIVE_WORDS if w in lowered)

        if positive_count > 0 and negative_count > 0:
            return FeedbackSentiment.MIXED
        elif positive_count > 0:
            return FeedbackSentiment.POSITIVE
        elif negative_count > 0:
            return FeedbackSentiment.NEGATIVE
        else:
            return FeedbackSentiment.NEUTRAL

    def to_dict(self) -> dict:
        """Serialize the full state."""
        with self._lock:
            return {
                "total_feedback": len(self._feedback),
                "aggregate": self.aggregate().to_dict(),
            }

    # --- internal ---

    def _compute_trend(self, entries: List[Dict[str, Any]]) -> TrendDirection:
        if len(entries) < 5:
            return TrendDirection.UNKNOWN
        # Compare first half to second half average ratings
        mid = len(entries) // 2
        first_half = entries[:mid]
        second_half = entries[mid:]
        avg1 = sum(e["rating"] for e in first_half) / len(first_half)
        avg2 = sum(e["rating"] for e in second_half) / len(second_half)
        diff = avg2 - avg1
        if diff > 0.3:
            return TrendDirection.IMPROVING
        elif diff < -0.3:
            return TrendDirection.DECLINING
        elif abs(diff) < 0.1:
            return TrendDirection.STABLE
        else:
            return TrendDirection.VOLATILE


# ---------------------------------------------------------------------------
# 8. PerformanceTrendAnalyzer
# ---------------------------------------------------------------------------

class PerformanceTrendAnalyzer:
    """Records performance metrics and analyzes trends over time.

    Supports regression detection, trend analysis, and simple forecasting
    using moving averages.

    Args:
        history_size: Maximum number of data points per metric.
    """

    def __init__(self, history_size: int = 1000):
        self._history_size = max(100, history_size)
        self._lock = threading.Lock()
        self._metrics: Dict[str, deque] = defaultdict(
            lambda: deque(maxlen=self._history_size)
        )

    def record_metric(
        self,
        name: str,
        value: float,
        timestamp: Optional[datetime] = None,
    ) -> None:
        """Record a performance metric data point.

        Args:
            name: The metric name.
            value: The observed value.
            timestamp: When the observation occurred (default: now).
        """
        ts = timestamp or _now()
        with self._lock:
            self._metrics[name].append({"timestamp": ts, "value": value})
        logger.debug("Metric recorded: %s = %.4f", name, value)

    def analyze_trend(
        self,
        name: str,
        window: Optional[timedelta] = None,
    ) -> PerformanceTrend:
        """Analyze the trend of a metric over a time window.

        Args:
            name: The metric name.
            window: Optional timedelta window; if None, uses all data.

        Returns:
            PerformanceTrend with analysis results.
        """
        with self._lock:
            points = list(self._metrics[name])

        if window:
            cutoff = _now() - window
            points = [p for p in points if p["timestamp"] >= cutoff]

        if len(points) < 2:
            return PerformanceTrend(
                metric_name=name,
                direction=TrendDirection.UNKNOWN,
                current_value=points[-1]["value"] if points else 0.0,
                data_points=points,
            )

        current = points[-1]["value"]
        previous = points[0]["value"]
        change = 0.0
        if previous != 0:
            change = ((current - previous) / abs(previous)) * 100
        change = round(change, 2)

        direction = TrendDirection.UNKNOWN
        if change > 5:
            direction = TrendDirection.IMPROVING
        elif change < -5:
            direction = TrendDirection.DECLINING
        elif abs(change) <= 2:
            direction = TrendDirection.STABLE
        else:
            direction = TrendDirection.VOLATILE

        forecast = self.forecast(name) if len(points) >= 5 else None

        return PerformanceTrend(
            metric_name=name,
            direction=direction,
            current_value=current,
            previous_value=previous,
            change_percent=change,
            data_points=[{"timestamp": p["timestamp"].isoformat(), "value": p["value"]} for p in points],
            forecast=forecast,
        )

    def detect_regression(
        self,
        name: str,
        threshold: float = 0.1,
    ) -> Optional[Dict[str, Any]]:
        """Detect if a metric has regressed beyond a threshold.

        Compares the latest value to the rolling average.

        Args:
            name: The metric name.
            threshold: Fractional threshold for flagging (default 0.1 = 10%).

        Returns:
            Dict with regression details, or None if no regression detected.
        """
        with self._lock:
            points = list(self._metrics[name])
        if len(points) < 5:
            return None

        recent = [p["value"] for p in points[-5:]]
        avg_recent = sum(recent) / len(recent)
        older = [p["value"] for p in points[:-5]]
        avg_older = sum(older) / len(older) if older else avg_recent

        if avg_older == 0:
            return None

        drop = (avg_older - avg_recent) / avg_older
        if drop > threshold:
            return {
                "metric": name,
                "regression_detected": True,
                "drop_percent": round(drop * 100, 2),
                "recent_average": round(avg_recent, 4),
                "baseline_average": round(avg_older, 4),
                "threshold": threshold,
                "timestamp": _now().isoformat(),
            }
        return None

    def forecast(self, name: str, horizon_days: int = 7) -> Optional[float]:
        """Simple moving-average forecast for a metric.

        Args:
            name: The metric name.
            horizon_days: Number of days to forecast forward.

        Returns:
            Forecasted value, or None if insufficient data.
        """
        with self._lock:
            points = list(self._metrics[name])
        if len(points) < 5:
            return None

        values = [p["value"] for p in points]
        # Simple linear regression on index
        n = len(values)
        x_mean = (n - 1) / 2.0
        y_mean = sum(values) / n
        num = sum((i - x_mean) * (values[i] - y_mean) for i in range(n))
        den = sum((i - x_mean) ** 2 for i in range(n))
        if den == 0:
            return y_mean
        slope = num / den
        intercept = y_mean - slope * x_mean
        # Determine how many points 'horizon_days' represents
        if len(points) >= 2:
            td = (points[-1]["timestamp"] - points[0]["timestamp"]).total_seconds()
            if td > 0:
                points_per_day = n / (td / 86400.0)
                horizon_points = int(horizon_days * points_per_day)
            else:
                horizon_points = horizon_days
        else:
            horizon_points = horizon_days

        future_x = n - 1 + max(1, horizon_points)
        forecast_val = slope * future_x + intercept
        return round(max(0.0, forecast_val), 4)

    def to_dict(self) -> dict:
        """Serialize the full state."""
        with self._lock:
            return {
                "metric_names": list(self._metrics.keys()),
                "total_metrics": len(self._metrics),
                "history_size": self._history_size,
            }


# ---------------------------------------------------------------------------
# 9. RiskRegister
# ---------------------------------------------------------------------------

class RiskRegister:
    """Enterprise risk register for identifying, assessing, and mitigating risks.

    Supports risk scoring, prioritization, risk matrix generation, and lifecycle
    management from identification through closure.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._risks: Dict[str, RiskEntry] = {}
        self._history: deque = deque(maxlen=10000)

    def identify_risk(
        self,
        title: str,
        description: str,
        likelihood: float,
        impact: float,
        owner: str,
        category: str = "general",
    ) -> str:
        """Identify and register a new risk.

        Args:
            title: Short risk title.
            description: Detailed description.
            likelihood: Probability of occurrence (0.0-1.0).
            impact: Impact magnitude (0.0-1.0).
            owner: Person/team responsible.
            category: Risk category label.

        Returns:
            The generated risk_id.
        """
        risk_id = _generate_id("risk")
        score = _compute_risk_score(likelihood, impact)
        level = _level_from_score(score)
        entry = RiskEntry(
            risk_id=risk_id,
            title=title,
            description=description,
            level=level,
            status=RiskStatus.IDENTIFIED,
            likelihood=likelihood,
            impact=impact,
            score=score,
            owner=owner,
            mitigation="",
            identified_date=_now(),
            last_reviewed=_now(),
        )
        with self._lock:
            self._risks[risk_id] = entry
            self._history.append({
                "action": "identify",
                "risk_id": risk_id,
                "title": title,
                "category": category,
                "timestamp": _now().isoformat(),
            })
        logger.info("Risk identified: %s level=%s score=%.4f", risk_id, level.value, score)
        return risk_id

    def assess_risk(self, risk_id: str) -> RiskEntry:
        """Retrieve a risk entry and mark it as assessing.

        Args:
            risk_id: The risk to assess.

        Returns:
            The RiskEntry.

        Raises:
            ValueError: If risk_id is unknown.
        """
        with self._lock:
            if risk_id not in self._risks:
                raise ValueError(f"Unknown risk_id: {risk_id}")
            entry = self._risks[risk_id]
            if entry.status == RiskStatus.IDENTIFIED:
                entry.status = RiskStatus.ASSESSING
                entry.last_reviewed = _now()
            return entry

    def update_risk(self, risk_id: str, **kwargs: Any) -> bool:
        """Update fields on an existing risk.

        Accepts keyword arguments for any mutable RiskEntry field.

        Args:
            risk_id: The risk to update.
            **kwargs: Fields to update (title, description, likelihood,
                      impact, owner, mitigation, status).

        Returns:
            True if updated, False if not found.

        Raises:
            ValueError: If risk_id is unknown.
        """
        with self._lock:
            if risk_id not in self._risks:
                raise ValueError(f"Unknown risk_id: {risk_id}")
            entry = self._risks[risk_id]
            for key, val in kwargs.items():
                if hasattr(entry, key):
                    setattr(entry, key, val)
            # Recalculate score & level if likelihood/impact changed
            if "likelihood" in kwargs or "impact" in kwargs:
                entry.score = _compute_risk_score(entry.likelihood, entry.impact)
                entry.level = _level_from_score(entry.score)
            entry.last_reviewed = _now()
            self._history.append({
                "action": "update",
                "risk_id": risk_id,
                "fields": list(kwargs.keys()),
                "timestamp": _now().isoformat(),
            })
            return True

    def add_mitigation(self, risk_id: str, mitigation: str) -> bool:
        """Add or update the mitigation strategy for a risk.

        Args:
            risk_id: The risk to update.
            mitigation: Mitigation strategy description.

        Returns:
            True if updated.

        Raises:
            ValueError: If risk_id is unknown.
        """
        with self._lock:
            if risk_id not in self._risks:
                raise ValueError(f"Unknown risk_id: {risk_id}")
            entry = self._risks[risk_id]
            entry.mitigation = mitigation
            entry.status = RiskStatus.MITIGATING
            entry.last_reviewed = _now()
            self._history.append({
                "action": "mitigate",
                "risk_id": risk_id,
                "timestamp": _now().isoformat(),
            })
            logger.info("Mitigation added for risk %s", risk_id)
            return True

    def get_top_risks(self, n: int = 10) -> List[RiskEntry]:
        """Return the top N risks sorted by score descending.

        Args:
            n: Number of risks to return.

        Returns:
            Sorted list of RiskEntry objects.
        """
        with self._lock:
            sorted_risks = sorted(
                self._risks.values(),
                key=lambda r: r.score,
                reverse=True,
            )
            return sorted_risks[:n]

    def get_risk_matrix(self) -> Dict[str, List[RiskEntry]]:
        """Return risks grouped by level for a risk matrix view.

        Returns:
            Dict mapping level name to list of RiskEntry.
        """
        with self._lock:
            matrix: Dict[str, List[RiskEntry]] = defaultdict(list)
            for entry in self._risks.values():
                matrix[entry.level.value].append(entry)
            return dict(matrix)

    def close_risk(self, risk_id: str, resolution: str) -> bool:
        """Close a risk with a resolution description.

        Args:
            risk_id: The risk to close.
            resolution: Description of how the risk was resolved.

        Returns:
            True if closed.

        Raises:
            ValueError: If risk_id is unknown.
        """
        with self._lock:
            if risk_id not in self._risks:
                raise ValueError(f"Unknown risk_id: {risk_id}")
            entry = self._risks[risk_id]
            entry.status = RiskStatus.CLOSED
            entry.mitigation = resolution
            entry.last_reviewed = _now()
            self._history.append({
                "action": "close",
                "risk_id": risk_id,
                "resolution": resolution,
                "timestamp": _now().isoformat(),
            })
            logger.info("Risk %s closed: %s", risk_id, resolution)
            return True

    def to_dict(self) -> dict:
        """Serialize the full state."""
        with self._lock:
            return {
                "total_risks": len(self._risks),
                "open_risks": sum(
                    1 for r in self._risks.values()
                    if r.status != RiskStatus.CLOSED
                ),
                "top_5": [r.to_dict() for r in self.get_top_risks(5)],
            }


# ---------------------------------------------------------------------------
# 10. GovernanceReport
# ---------------------------------------------------------------------------

@dataclass
class GovernanceReport:
    """Aggregated governance report across all domains.

    Attributes:
        report_id: Unique report identifier.
        generated_at: When the report was generated.
        period_start: Start of the reporting period.
        period_end: End of the reporting period.
        model_review_summary: Summary from model change reviews.
        prompt_approval_summary: Summary from prompt approvals.
        security_summary: Summary from security reviews.
        incident_summary: Summary from incident board.
        compliance_summary: Summary from compliance dashboard.
        risk_summary: Summary from risk register.
        feedback_summary: Summary from user feedback.
        trend_summary: Summary from trend analysis.
        recommendations: List of board recommendations.
    """
    report_id: str = field(default_factory=lambda: _generate_id("gvr"))
    generated_at: datetime = field(default_factory=datetime.utcnow)
    period_start: Optional[datetime] = None
    period_end: Optional[datetime] = None
    model_review_summary: Dict[str, Any] = field(default_factory=dict)
    prompt_approval_summary: Dict[str, Any] = field(default_factory=dict)
    security_summary: Dict[str, Any] = field(default_factory=dict)
    incident_summary: Dict[str, Any] = field(default_factory=dict)
    compliance_summary: Dict[str, Any] = field(default_factory=dict)
    risk_summary: Dict[str, Any] = field(default_factory=dict)
    feedback_summary: Dict[str, Any] = field(default_factory=dict)
    trend_summary: Dict[str, Any] = field(default_factory=dict)
    recommendations: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "report_id": self.report_id,
            "generated_at": self.generated_at.isoformat(),
            "period_start": self.period_start.isoformat() if self.period_start else None,
            "period_end": self.period_end.isoformat() if self.period_end else None,
            "model_review_summary": self.model_review_summary,
            "prompt_approval_summary": self.prompt_approval_summary,
            "security_summary": self.security_summary,
            "incident_summary": self.incident_summary,
            "compliance_summary": self.compliance_summary,
            "risk_summary": self.risk_summary,
            "feedback_summary": self.feedback_summary,
            "trend_summary": self.trend_summary,
            "recommendations": list(self.recommendations),
        }


# ---------------------------------------------------------------------------
# 11. AuditEntry & AuditTrail
# ---------------------------------------------------------------------------

@dataclass
class AuditEntry:
    """A single entry in the governance audit trail.

    Attributes:
        audit_id: Unique identifier.
        action: The action performed.
        actor: Who performed the action.
        resource: The resource acted upon.
        details: Additional action details.
        timestamp: When the action occurred.
        outcome: Result of the action.
    """
    audit_id: str = field(default_factory=lambda: _generate_id("aud"))
    action: str = ""
    actor: str = ""
    resource: str = ""
    details: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.utcnow)
    outcome: str = "success"

    def to_dict(self) -> dict:
        return {
            "audit_id": self.audit_id,
            "action": self.action,
            "actor": self.actor,
            "resource": self.resource,
            "details": dict(self.details),
            "timestamp": self.timestamp.isoformat(),
            "outcome": self.outcome,
        }


class AuditTrail:
    """Immutable audit trail for governance actions.

    Records all governance-related actions with actor, resource,
    and outcome tracking. Thread-safe.

    Args:
        max_entries: Maximum number of entries to retain.
    """

    def __init__(self, max_entries: int = 100000):
        self._max_entries = max_entries
        self._lock = threading.Lock()
        self._entries: deque = deque(maxlen=max_entries)
        self._index: Dict[str, List[int]] = defaultdict(list)  # resource -> position indices

    def record(
        self,
        action: str,
        actor: str,
        resource: str,
        details: Optional[Dict[str, Any]] = None,
        outcome: str = "success",
    ) -> str:
        """Record an audit entry.

        Args:
            action: The action performed.
            actor: Who performed the action.
            resource: The resource acted upon.
            details: Optional additional details.
            outcome: Result of the action.

        Returns:
            The generated audit_id.
        """
        entry = AuditEntry(
            action=action,
            actor=actor,
            resource=resource,
            details=details or {},
            outcome=outcome,
        )
        with self._lock:
            position = len(self._entries)
            self._entries.append(entry)
            self._index[resource].append(position)
        logger.debug("Audit: %s by %s on %s -> %s", action, actor, resource, outcome)
        return entry.audit_id

    def query(
        self,
        actor: Optional[str] = None,
        resource: Optional[str] = None,
        action: Optional[str] = None,
        limit: int = 100,
    ) -> List[AuditEntry]:
        """Query audit entries by actor, resource, and/or action.

        Args:
            actor: Filter by actor.
            resource: Filter by resource.
            action: Filter by action.
            limit: Maximum results to return.

        Returns:
            List of matching AuditEntry objects.
        """
        with self._lock:
            entries = list(self._entries)
        results = []
        for e in reversed(entries):
            if actor and e.actor != actor:
                continue
            if resource and e.resource != resource:
                continue
            if action and e.action != action:
                continue
            results.append(e)
            if len(results) >= limit:
                break
        return results

    def get_recent(self, n: int = 50) -> List[AuditEntry]:
        """Return the most recent N audit entries."""
        with self._lock:
            return list(self._entries)[-n:]

    def to_dict(self) -> dict:
        """Serialize the audit trail."""
        with self._lock:
            return {
                "total_entries": len(self._entries),
                "recent": [e.to_dict() for e in list(self._entries)[-20:]],
            }


# ---------------------------------------------------------------------------
# 11. GovernanceBoard (Main Orchestrator)  (re-numbered from 10)
# ---------------------------------------------------------------------------

class GovernanceBoard:
    """Central orchestrator for all governance sub-modules.

    Provides unified access to model review, prompt approval, tool impact
    assessment, security reviews, incident review, compliance tracking,
    user feedback aggregation, trend analysis, and risk registration.

    Args:
        config: Optional configuration dict. Supported keys:
            - required_approvers (int): For ModelChangeReview.
            - auto_approve_low_risk (bool): For ModelChangeReview.
            - security_officers (List[str]): For SecurityChangeReview.
            - board_members (List[str]): For IncidentReviewBoard.
            - frameworks (List[str]): Framework names to preload.
            - trend_history_size (int): For PerformanceTrendAnalyzer.
            - approval_stages (List[str]): Stage names for PromptChangeApproval.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        cfg = config or {}

        # -- Model Change Review --
        self._model_review = ModelChangeReview(
            required_approvers=cfg.get("required_approvers", 2),
            auto_approve_low_risk=cfg.get("auto_approve_low_risk", False),
        )

        # -- Prompt Change Approval --
        stages_raw = cfg.get("approval_stages")
        if stages_raw:
            try:
                stages = [ApprovalStage(s) for s in stages_raw]
            except ValueError:
                stages = None
        else:
            stages = None
        self._prompt_approval = PromptChangeApproval(stages=stages)

        # -- Tool Impact Assessment --
        self._tool_impact = ToolChangeImpactAssessment()

        # -- Security Change Review --
        self._security_review = SecurityChangeReview(
            security_officers=cfg.get("security_officers"),
        )

        # -- Incident Review Board --
        self._incident_board = IncidentReviewBoard(
            board_members=cfg.get("board_members"),
        )

        # -- Compliance Dashboard --
        self._compliance = ComplianceDashboard()
        frameworks_raw = cfg.get("frameworks", [])
        for fw_name in frameworks_raw:
            try:
                fw = ComplianceFramework(fw_name)
                self._compliance.add_framework(fw)
            except ValueError:
                logger.warning("Unknown compliance framework: %s", fw_name)

        # -- User Feedback Aggregator --
        self._feedback = UserFeedbackAggregator()

        # -- Performance Trend Analyzer --
        self._trend_analyzer = PerformanceTrendAnalyzer(
            history_size=cfg.get("trend_history_size", 1000),
        )

        # -- Risk Register --
        self._risk_register = RiskRegister()

        self._config = cfg
        self._created_at = _now()
        logger.info("GovernanceBoard initialized with config keys: %s", list(cfg.keys()))

    # ---- Accessors ----

    def get_model_review_board(self) -> ModelChangeReview:
        """Return the ModelChangeReview sub-module."""
        return self._model_review

    def get_prompt_approval_pipeline(self) -> PromptChangeApproval:
        """Return the PromptChangeApproval sub-module."""
        return self._prompt_approval

    def get_tool_impact_assessor(self) -> ToolChangeImpactAssessment:
        """Return the ToolChangeImpactAssessment sub-module."""
        return self._tool_impact

    def get_security_review_board(self) -> SecurityChangeReview:
        """Return the SecurityChangeReview sub-module."""
        return self._security_review

    def get_incident_board(self) -> IncidentReviewBoard:
        """Return the IncidentReviewBoard sub-module."""
        return self._incident_board

    def get_compliance_dashboard(self) -> ComplianceDashboard:
        """Return the ComplianceDashboard sub-module."""
        return self._compliance

    def get_feedback_aggregator(self) -> UserFeedbackAggregator:
        """Return the UserFeedbackAggregator sub-module."""
        return self._feedback

    def get_trend_analyzer(self) -> PerformanceTrendAnalyzer:
        """Return the PerformanceTrendAnalyzer sub-module."""
        return self._trend_analyzer

    def get_risk_register(self) -> RiskRegister:
        """Return the RiskRegister sub-module."""
        return self._risk_register

    # ---- Reporting ----

    def generate_board_report(self) -> Dict[str, Any]:
        """Generate a comprehensive governance board report.

        Aggregates state from all sub-modules into a single dict.

        Returns:
            Dict with summary from each governance component.
        """
        now = _now().isoformat()
        return {
            "generated_at": now,
            "model_review": self._model_review.to_dict(),
            "prompt_approval": self._prompt_approval.to_dict(),
            "tool_impact": self._tool_impact.to_dict(),
            "security_review": self._security_review.to_dict(),
            "incident_board": self._incident_board.to_dict(),
            "compliance": self._compliance.to_dict(),
            "feedback": self._feedback.to_dict(),
            "trend_analyzer": self._trend_analyzer.to_dict(),
            "risk_register": self._risk_register.to_dict(),
        }

    def to_dict(self) -> dict:
        """Serialize the full GovernanceBoard state."""
        return self.generate_board_report()


# ---------------------------------------------------------------------------
# Module-level convenience
# ---------------------------------------------------------------------------

__all__ = [
    # Enums
    "ReviewStatus",
    "ChangeType",
    "RiskLevel",
    "RiskStatus",
    "ImpactLevel",
    "ApprovalStage",
    "ComplianceFramework",
    "TrendDirection",
    "FeedbackSentiment",
    "Sentiment",
    "ChangeApprovalStatus",
    "IncidentSeverity",
    "IncidentStatus",
    "MeetingType",
    # Dataclasses
    "ReviewDecision",
    "ImpactAssessment",
    "RiskEntry",
    "ComplianceReport",
    "FeedbackSummary",
    "PerformanceTrend",
    "ChangeApprovalEntry",
    "ChangeRecord",
    "IncidentRecord",
    "ComplianceStatus",
    "TrendDataPoint",
    "UserFeedback",
    "BoardMeetingMinutes",
    "GovernanceReport",
    "AuditEntry",
    # Classes
    "ModelChangeReview",
    "PromptChangeApproval",
    "ToolChangeImpactAssessment",
    "SecurityChangeReview",
    "IncidentReviewBoard",
    "ComplianceDashboard",
    "UserFeedbackAggregator",
    "PerformanceTrendAnalyzer",
    "RiskRegister",
    "AuditTrail",
    "GovernanceBoard",
]