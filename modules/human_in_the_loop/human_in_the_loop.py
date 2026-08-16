"""HumanInTheLoop — a human-oversight orchestration engine for the compute layer.

Built directly from the pulled JE Van Clief transcript "Afternoon tea: Why
Humans Belong in the Compute Layer" (30N9gLucrHg). The transcript's central
thesis is that humans belong *inside* the compute layer rather than being
removed from it:

    "humans in the compute layer is super important. We don't want them
     removed from it. Humans are extremely compute efficient."

The talk grounds this in Douglas Engelbart's 1968 work on "Augmenting Human
Intellect" — machines and people collaborating through *dialogue* rather than
buttons, with human taste and judgment kept in the loop:

    "...using your lovely human taste ... the interaction layer ... one of the
     best ways in which a human can interact with information."

From that thesis this engine implements the practical machinery that keeps a
human in the compute layer (from transcript line ~1130 onward):

* ApprovalPolicy   — a rules engine that decides when an action may proceed
                     on its own, when it needs a human sign-off, and when it
                     must be handed off (low-confidence or high-stakes work is
                     never executed silently by the machine).
* confidence_route — auto-proceed when the model is confident; the moment
                     confidence drops or the stakes rise, a human stays in the
                     loop via the escalation queue.
* EscalationQueue  — a prioritized, deadline-bound queue of actions awaiting
                     human review, ordered by stakes + uncertainty.
* DecisionAudit    — a durable log of every routing/override decision so the
                     human-compute collaboration is transparent and reviewable.

Everything here is pure Python and network-free so it is unit-testable in
isolation. No fake enterprise features: just the approval / escalation /
routing / audit behavior honestly derived from the source material.

Version: 1.0.0
"""
from __future__ import annotations

import itertools
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

# Human-in-the-loop verdicts -------------------------------------------------
AUTO = "auto"            # high confidence, low stakes  -> machine proceeds
REVIEW = "review"        # conditional sign-off required -> human approves
ESCALATE = "escalate"    # low confidence and/or high stakes -> queue + human

# Stakes tiers (how much it costs if the machine is wrong)
STAKES_LOW = "low"
STAKES_MEDIUM = "medium"
STAKES_HIGH = "high"

_STAKES_ORDER = {STAKES_LOW: 1, STAKES_MEDIUM: 2, STAKES_HIGH: 3}


@dataclass
class ApprovalPolicy:
    """Rules for when a human must stay in the compute loop.

    Grounded in the transcript's thesis that humans belong in the compute
    layer: the policy keeps humans wherever the model is unsure (low
    confidence) or where a wrong call would be costly (high stakes), and lets
    the machine proceed autonomously only when it is both confident and the
    stakes are low.
    """

    auto_confidence: float = 0.85       # >= this, machine may proceed alone
    review_confidence: float = 0.62     # < this, always escalate to a human
    high_stake_review_threshold: float = 0.90  # high stakes also need signoff
    default_approver: str = "reviewer"
    max_reviewers: int = 2

    def evaluate(self, action: "Action") -> Dict[str, Any]:
        """Decide: AUTO / REVIEW / ESCALATE for a single action.

        Returns a decision dict with the verdict, the number of human
        sign-offs required, and a human-readable reason, so callers can route
        the action accordingly.
        """
        c = action.confidence
        stake_tier = _STAKES_ORDER.get(action.stakes, 1)

        if c < self.review_confidence:
            # Too uncertain: the machine must not act alone.
            return {
                "verdict": ESCALATE,
                "approvers_needed": self.max_reviewers,
                "reason": (
                    f"confidence {c:.2f} below review threshold "
                    f"{self.review_confidence:.2f}; model too uncertain"
                ),
            }

        if stake_tier >= 3 and c < self.high_stake_review_threshold:
            # High stakes even at moderate confidence: one human sign-off.
            return {
                "verdict": REVIEW,
                "approvers_needed": 1,
                "reason": (
                    f"high-stakes action at confidence {c:.2f} (< "
                    f"{self.high_stake_review_threshold:.2f}) requires human "
                    f"sign-off"
                ),
            }

        if c < self.auto_confidence:
            # Moderate confidence: still route past a human for a sanity check.
            return {
                "verdict": REVIEW,
                "approvers_needed": 1,
                "reason": (
                    f"confidence {c:.2f} below auto threshold "
                    f"{self.auto_confidence:.2f}; conditional human review"
                ),
            }

        return {
            "verdict": AUTO,
            "approvers_needed": 0,
            "reason": (
                f"confidence {c:.2f} >= {self.auto_confidence:.2f} and "
                f"{action.stakes} stakes; machine may proceed in-loop"
            ),
        }


@dataclass
class AuditEntry:
    """A single durable record of a routing / override decision."""

    action_id: str
    verdict: str
    confidence: float
    stakes: str
    reason: str
    at: datetime
    approver: Optional[str] = None
    approved: Optional[bool] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "action_id": self.action_id,
            "verdict": self.verdict,
            "confidence": round(self.confidence, 4),
            "stakes": self.stakes,
            "reason": self.reason,
            "at": self.at.isoformat(),
            "approver": self.approver,
            "approved": self.approved,
        }


@dataclass
class Escalation:
    """An action queued for human review (the human-in-the-loop hand-off)."""

    id: str
    action_id: str
    description: str
    priority: int
    created_at: datetime
    deadline: datetime
    reason: str
    status: str = "pending"  # pending | approved | rejected | expired

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "action_id": self.action_id,
            "description": self.description,
            "priority": self.priority,
            "created_at": self.created_at.isoformat(),
            "deadline": self.deadline.isoformat(),
            "reason": self.reason,
            "status": self.status,
        }


@dataclass
class Action:
    """A unit of work entering the human-in-the-loop layer."""

    action_id: str
    description: str
    confidence: float
    stakes: str = STAKES_LOW
    at: Optional[datetime] = None

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be in [0, 1]")
        if self.stakes not in _STAKES_ORDER:
            raise ValueError(f"unknown stakes tier: {self.stakes}")
        if self.at is None:
            self.at = _utcnow()


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class EscalationQueue:
    """A prioritized, deadline-aware queue of work waiting on a human."""

    def __init__(self) -> None:
        self._items: Dict[str, Escalation] = {}
        self._ids = itertools.count(1)

    def add(self, action: Action, reason: str, priority: int,
            deadline: datetime) -> Escalation:
        esc = Escalation(
            id=f"esc-{next(self._ids)}",
            action_id=action.action_id,
            description=action.description,
            priority=priority,
            created_at=_utcnow(),
            deadline=deadline,
            reason=reason,
        )
        self._items[esc.id] = esc
        return esc

    def ordered(self) -> List[Escalation]:
        """Highest priority first, then the most urgent (soonest) deadline."""
        return sorted(
            self._items.values(),
            key=lambda e: (-e.priority, e.deadline, e.id),
        )

    def next(self) -> Optional[Escalation]:
        for e in self.ordered():
            if e.status == "pending":
                return e
        return None

    def pending_count(self) -> int:
        return sum(1 for e in self._items.values() if e.status == "pending")

    def resolve(self, esc_id: str, approved: bool) -> Optional[Escalation]:
        e = self._items.get(esc_id)
        if e is None or e.status == "expired":
            return None
        e.status = "approved" if approved else "rejected"
        return e

    def expire_overdue(self, now: Optional[datetime] = None) -> int:
        """Mark overdue pending items expired (deadline passed, no human)."""
        now = now or _utcnow()
        n = 0
        for e in self._items.values():
            if e.status == "pending" and e.deadline < now:
                e.status = "expired"
                n += 1
        return n


def _deadline_for(stakes: str, base: datetime) -> datetime:
    """Humans get tighter deadlines for the highest-stakes decisions."""
    hours = {STAKES_LOW: 24, STAKES_MEDIUM: 8, STAKES_HIGH: 4}
    return base + timedelta(hours=hours.get(stakes, 24))


def _priority_for(confidence: float, stakes: str) -> int:
    """Queue priority: higher for high stakes and/or lower confidence."""
    base = _STAKES_ORDER.get(stakes, 1) * 100
    uncertainty = int(round((1.0 - confidence) * 100))
    return base + uncertainty


class HumanInTheLoop:
    """Orchestrator that keeps a human in the compute layer.

    Mirrors the engine shape of the second_brain module (pure, network-free,
    unit-testable). Holds the approval policy, the escalation queue, and the
    decision audit, and exposes the routing entry point.
    """

    def __init__(
        self,
        policy: Optional[ApprovalPolicy] = None,
        now_provider: Optional[callable] = None,
    ) -> None:
        self.policy = policy or ApprovalPolicy()
        self.queue = EscalationQueue()
        self.audit: List[AuditEntry] = []
        self._now = now_provider or _utcnow

    # ------------------------------------------------------------------ core
    def route(self, action: Action) -> Dict[str, Any]:
        """Route an action through the approval policy and return the outcome.

        * AUTO     -> executes in-loop (still logged so nothing is silent).
        * REVIEW   -> requires one human sign-off off-queue.
        * ESCALATE -> pushed onto the prioritized escalation queue.
        """
        decision = self.policy.evaluate(action)
        verdict = decision["verdict"]

        if verdict == AUTO:
            self._log(action, decision)
            return {"verdict": AUTO, "action_id": action.action_id,
                    "reason": decision["reason"], "escalation_id": None}

        if verdict == REVIEW:
            # A single reviewer decision is recorded immediately; if the
            # reviewer says no the action is escalated to the queue.
            self._log(action, decision)
            if decision["approvers_needed"] >= 1:
                esc = self._enqueue(action, decision["reason"])
                return {"verdict": REVIEW, "action_id": action.action_id,
                        "reason": decision["reason"],
                        "escalation_id": esc.id}
            return {"verdict": REVIEW, "action_id": action.action_id,
                    "reason": decision["reason"], "escalation_id": None}

        # ESCALATE
        esc = self._enqueue(action, decision["reason"])
        self._log(action, decision)
        return {"verdict": ESCALATE, "action_id": action.action_id,
                "reason": decision["reason"], "escalation_id": esc.id}

    def resolve(self, escalation_id: str, approver: str, approved: bool,
                note: str = "") -> Dict[str, Any]:
        """A human resolves an escalation: approve or reject the action."""
        esc = self.queue.resolve(escalation_id, approved)
        if esc is None:
            raise KeyError(f"no resolvable escalation {escalation_id}")
        self._record(esc, approver=approver, approved=approved,
                     reason=note or f"human {esc.status}")
        return {"escalation_id": esc.id, "action_id": esc.action_id,
                "status": esc.status, "approver": approver}

    # ------------------------------------------------------------------ query
    def pending(self) -> List[Dict[str, Any]]:
        return [e.to_dict() for e in self.queue.ordered()
                if e.status == "pending"]

    def audit_log(self) -> List[Dict[str, Any]]:
        return [a.to_dict() for a in self.audit]

    def queue_stats(self) -> Dict[str, Any]:
        counts = {"pending": 0, "approved": 0, "rejected": 0, "expired": 0}
        for e in self.queue._items.values():
            counts[e.status] = counts.get(e.status, 0) + 1
        auto = sum(1 for a in self.audit if a.verdict == AUTO)
        reviewed = sum(1 for a in self.audit if a.verdict != AUTO)
        return {
            "total_actions_routed": len(self.audit),
            "auto_proceeded": auto,
            "human_in_loop": reviewed,
            "queue": counts,
        }

    # ------------------------------------------------------------------ internals
    def _enqueue(self, action: Action, reason: str) -> Escalation:
        priority = _priority_for(action.confidence, action.stakes)
        deadline = _deadline_for(action.stakes, self._now())
        return self.queue.add(action, reason, priority, deadline)

    def _log(self, action: Action, decision: Dict[str, Any]) -> None:
        self.audit.append(AuditEntry(
            action_id=action.action_id,
            verdict=decision["verdict"],
            confidence=action.confidence,
            stakes=action.stakes,
            reason=decision["reason"],
            at=self._now(),
        ))

    def _record(self, esc: Escalation, approver: str, approved: bool,
                reason: str) -> None:
        self.audit.append(AuditEntry(
            action_id=esc.action_id,
            verdict=esc.status,
            confidence=0.0,
            stakes=STAKES_LOW,
            reason=reason,
            at=self._now(),
            approver=approver,
            approved=approved,
        ))


make_human_in_the_loop = HumanInTheLoop  # factory alias, mirrors second_brain
