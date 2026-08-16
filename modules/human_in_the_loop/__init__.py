"""Human-in-the-Loop module — a human-oversight orchestration layer for the
compute layer.

Grounded in the real pulled JE Van Clief transcript "Afternoon tea: Why Humans
Belong in the Compute Layer" (30N9gLucrHg), whose central thesis is that
humans belong *inside* the compute layer and should never be removed from it:

  * "humans in the compute layer is super important. We don't want them
     removed from it. Humans are extremely compute efficient."  →  humans must
     stay in the loop for judgment, not be bypassed by autonomous agents.
  * "Augmenting Human Intellect" (Douglas Engelbart)  →  humans + machines
     collaborate; escalating uncertain or high-stakes work to a human keeps the
     machine useful without letting it act alone where it is unsure.

From that thesis this module provides an approval / escalation / routing /
audit engine:

  * ApprovalPolicy    — when must a human sign off (low confidence, high stakes).
  * HumanInTheLoop    — confidence-based routing + prioritized escalation queue.
  * EscalationQueue   — priority/deadline-ordered work awaiting a human.
  * DecisionAudit     — transparent record of every routing & override.

Export surface:
  * ApprovalPolicy, Action, Escalation, AuditEntry — pure engine types.
  * HumanInTheLoop, make_human_in_the_loop          — the orchestration engine.
  * HumanInTheLoopModule                            — the ENI platform wrapper.
  * create_human_in_the_loop_module(config)         — factory used by platform.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from enterprise.platform_kernel import HealthStatus, Module, module

from .human_in_the_loop import (  # noqa: F401
    ApprovalPolicy,
    Action,
    AuditEntry,
    Escalation,
    EscalationQueue,
    HumanInTheLoop,
    make_human_in_the_loop,
)

logger = logging.getLogger("eni.human_in_the_loop")
__version__ = "1.0.0"


@module(
    name="human_in_the_loop",
    version="1.0.0",
    config_defaults={
        "auto_confidence": 0.85,
        "review_confidence": 0.62,
        "high_stake_review_threshold": 0.90,
        "default_approver": "reviewer",
        "max_reviewers": 2,
    },
)
class HumanInTheLoopModule(Module):
    """ENI platform wrapper around the HumanInTheLoop engine."""

    def __init__(self, config: Optional[dict[str, Any]] = None) -> None:
        super().__init__(config)
        self.engine: Optional[HumanInTheLoop] = None

    async def initialize(self) -> None:
        policy = ApprovalPolicy(
            auto_confidence=float(self._config.get("auto_confidence", 0.85)),
            review_confidence=float(self._config.get("review_confidence", 0.62)),
            high_stake_review_threshold=float(
                self._config.get("high_stake_review_threshold", 0.90)
            ),
            default_approver=str(self._config.get("default_approver", "reviewer")),
            max_reviewers=int(self._config.get("max_reviewers", 2)),
        )
        self.engine = HumanInTheLoop(policy=policy)
        self.status = HealthStatus.HEALTHY
        logger.info("human_in_the_loop module initialized")

    async def health_check(self) -> HealthStatus:
        return (HealthStatus.HEALTHY if self.engine is not None
                else HealthStatus.UNHEALTHY)

    async def shutdown(self) -> None:
        self.engine = None
        self.status = HealthStatus.UNKNOWN

    # ------------------------------------------------------------- facade
    def route_action(self, action_id: str, description: str,
                     confidence: float,
                     stakes: str = "low") -> Dict[str, Any]:
        """Submit an action to the human-in-the-loop layer for routing."""
        action = Action(action_id=action_id, description=description,
                        confidence=confidence, stakes=stakes)
        return self.engine.route(action)

    def resolve_action(self, escalation_id: str, approver: str,
                       approved: bool, note: str = "") -> Dict[str, Any]:
        """A human resolves an escalated action (approve / reject)."""
        return self.engine.resolve(escalation_id, approver, approved, note)

    def pending_escalations(self) -> List[Dict[str, Any]]:
        """Prioritized list of actions still awaiting a human."""
        return self.engine.pending()

    def audit_log(self) -> List[Dict[str, Any]]:
        """Full decision/audit log for transparency."""
        return self.engine.audit_log()

    def queue_stats(self) -> Dict[str, Any]:
        """Counts of routed actions and queue state."""
        return self.engine.queue_stats()


def create_human_in_the_loop_module(
    config: Optional[dict[str, Any]] = None,
) -> HumanInTheLoopModule:
    return HumanInTheLoopModule(config=config or {})


__all__ = [
    "ApprovalPolicy",
    "Action",
    "AuditEntry",
    "Escalation",
    "EscalationQueue",
    "HumanInTheLoop",
    "HumanInTheLoopModule",
    "create_human_in_the_loop_module",
    "make_human_in_the_loop",
    "__version__",
]
