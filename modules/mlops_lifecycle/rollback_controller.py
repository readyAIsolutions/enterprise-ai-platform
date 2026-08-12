"""
Rollback Controller — plans and executes safe rollbacks of failed model/agent
deployments.

A rollback is captured as a :class:`RollbackPlan` made of ordered
:class:`RollbackAction` steps, guarded by :class:`SafetyCheck` items and
triggered by a :class:`RollbackTrigger`. Execution only proceeds if every
safety check passes, and actions are applied in declaration order.
"""

from __future__ import annotations

import logging
import threading
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger("enterprise.mlops_lifecycle.rollback_controller")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class PlanStatus(Enum):
    DRAFT = "draft"
    READY = "ready"
    EXECUTING = "executing"
    COMPLETE = "complete"
    FAILED = "failed"
    ABORTED = "aborted"


class ActionStatus(Enum):
    PENDING = "pending"
    EXECUTED = "executed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class RollbackAction:
    """A single reversible remediation step."""

    action_type: str  # e.g. revert_code, restore_model, disable_flag, stop_traffic
    description: str = ""
    action_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    status: ActionStatus = ActionStatus.PENDING
    executed_at: Optional[str] = None
    handler: Optional[Any] = None  # optional zero-arg callable invoked on execute

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["status"] = self.status.value
        data.pop("handler", None)
        return data


@dataclass
class SafetyCheck:
    """A pre-condition that must pass before rollback executes."""

    name: str
    # A callable with zero args returning bool, or a plain bool result.
    check: Any = True
    passed: Optional[bool] = None
    details: str = ""

    def run(self) -> bool:
        if callable(self.check):
            self.passed = bool(self.check())
        else:
            self.passed = bool(self.check)
        return self.passed


@dataclass
class RollbackTrigger:
    """Why the rollback was invoked."""

    reason: str
    source: str = "canary"
    trigger_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: str = field(default_factory=_now_iso)


@dataclass
class RollbackPlan:
    """A complete rollback: trigger + safety checks + ordered actions."""

    deployment_id: str
    trigger: RollbackTrigger
    status: PlanStatus = PlanStatus.DRAFT
    plan_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: str = field(default_factory=_now_iso)
    completed_at: Optional[str] = None
    safety_checks: List[SafetyCheck] = field(default_factory=list)
    actions: List[RollbackAction] = field(default_factory=list)

    def add_safety_check(self, check: SafetyCheck) -> None:
        self.safety_checks.append(check)

    def add_action(self, action: RollbackAction) -> None:
        self.actions.append(action)

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["status"] = self.status.value
        data["trigger"] = asdict(self.trigger)
        data["safety_checks"] = [
            {"name": c.name, "passed": c.passed, "details": c.details} for c in self.safety_checks
        ]
        data["actions"] = [a.to_dict() for a in self.actions]
        return data


class RollbackController:
    """Creates and executes rollback plans."""

    def __init__(self) -> None:
        self._plans: Dict[str, RollbackPlan] = {}
        self._lock = threading.RLock()

    def create_plan(
        self,
        deployment_id: str,
        reason: str,
        source: str = "canary",
    ) -> RollbackPlan:
        trigger = RollbackTrigger(reason=reason, source=source)
        plan = RollbackPlan(deployment_id=deployment_id, trigger=trigger)
        with self._lock:
            self._plans[plan.plan_id] = plan
        return plan

    def get_plan(self, plan_id: str) -> Optional[RollbackPlan]:
        with self._lock:
            return self._plans.get(plan_id)

    def finalize_plan(self, plan_id: str) -> bool:
        """Mark a draft plan as READY for execution."""
        with self._lock:
            plan = self._plans.get(plan_id)
            if plan is None or plan.status is not PlanStatus.DRAFT:
                return False
            plan.status = PlanStatus.READY
            return True

    def run_safety_checks(self, plan_id: str) -> bool:
        """Run all safety checks; returns True only if all pass."""
        with self._lock:
            plan = self._plans.get(plan_id)
            if plan is None:
                return False
            results = [check.run() for check in plan.safety_checks]
            return all(results)

    def execute_plan(self, plan_id: str) -> bool:
        """Execute a rollback plan end-to-end.

        Returns True on completion; raises ``RuntimeError`` if a safety gate
        fails or an action fails midway.
        """
        with self._lock:
            plan = self._plans.get(plan_id)
            if plan is None:
                return False
            if plan.status is PlanStatus.DRAFT:
                plan.status = PlanStatus.READY
            if plan.status not in (PlanStatus.READY, PlanStatus.EXECUTING):
                return False

            plan.status = PlanStatus.EXECUTING
            if not all(check.run() for check in plan.safety_checks):
                plan.status = PlanStatus.FAILED
                raise RuntimeError(f"rollback {plan_id} blocked by safety checks")

            for action in plan.actions:
                # If an action carries a callable handler, it is invoked here.
                handler = getattr(action, "handler", None)
                if callable(handler):
                    try:
                        handler()
                    except Exception as exc:  # noqa: BLE001
                        action.status = ActionStatus.FAILED
                        plan.status = PlanStatus.FAILED
                        raise RuntimeError(f"rollback action {action.action_id} failed: {exc}") from exc
                action.status = ActionStatus.EXECUTED
                action.executed_at = _now_iso()

            plan.status = PlanStatus.COMPLETE
            plan.completed_at = _now_iso()
            return True

    def abort_plan(self, plan_id: str) -> bool:
        with self._lock:
            plan = self._plans.get(plan_id)
            if plan is None or plan.status is PlanStatus.COMPLETE:
                return False
            plan.status = PlanStatus.ABORTED
            for action in plan.actions:
                if action.status is ActionStatus.PENDING:
                    action.status = ActionStatus.SKIPPED
            return True

    def completed_plans(self) -> List[RollbackPlan]:
        with self._lock:
            return [p for p in self._plans.values() if p.status is PlanStatus.COMPLETE]

    def plans_for_deployment(self, deployment_id: str) -> List[RollbackPlan]:
        with self._lock:
            return [p for p in self._plans.values() if p.deployment_id == deployment_id]


def create_rollback_controller(config: Optional[Dict[str, Any]] = None) -> RollbackController:
    """Create a default :class:`RollbackController`.

    Args:
        config: Optional dict (currently unused; kept for interface parity).
    """
    return RollbackController()
