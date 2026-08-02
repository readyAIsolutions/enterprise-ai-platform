"""
Active recovery engine.

Manages recovery plans, failover execution, data reconciliation,
infrastructure rebuild, secret recovery, and alternate communication channels.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger("enterprise.disaster_recovery.recovery")


class RecoveryMode(str, Enum):
    """Mode of recovery execution."""

    AUTOMATED = "automated"
    ASSISTED = "assisted"
    MANUAL = "manual"


@dataclass
class RecoveryPlan:
    """Configuration and state for service recovery."""

    name: str
    mode: RecoveryMode = RecoveryMode.AUTOMATED
    multi_zone: bool = False
    multi_region: bool = False
    replication_enabled: bool = False
    failover_enabled: bool = True
    graceful_degradation: bool = True
    queue_durability: bool = True
    data_reconciliation_enabled: bool = True
    iac_enabled: bool = True
    auto_rebuild: bool = True
    config_backed_up: bool = True
    secret_recovery_enabled: bool = True
    alt_communication_channels: List[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: Optional[datetime] = None
    last_failover_at: Optional[datetime] = None

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "mode": self.mode.value,
            "multi_zone": self.multi_zone,
            "multi_region": self.multi_region,
            "failover_enabled": self.failover_enabled,
            "auto_rebuild": self.auto_rebuild,
            "alt_communication_channels": self.alt_communication_channels,
        }


class RecoveryEngine:
    """
    Active recovery engine.

    Creates and maintains recovery plans, executes failovers, reconciles data,
    rebuilds infrastructure, recovers secrets, and validates successful recovery.
    """

    def __init__(self) -> None:
        self._plans: Dict[str, RecoveryPlan] = {}
        self._recovery_log: List[Dict[str, Any]] = []
        self._hooks: Dict[str, Callable] = {}
        self._infra_state: Dict[str, Any] = {}
        self._secrets_store: Dict[str, str] = {}
        self._communication: Dict[str, bool] = {}

    # ------------------------------------------------------------------
    # Hook registration
    # ------------------------------------------------------------------

    def register_hook(self, name: str, fn: Callable) -> None:
        """Register an external callable for a named recovery action."""
        self._hooks[name] = fn
        logger.debug("Registered recovery hook: %s", name)

    # ------------------------------------------------------------------
    # Plan management
    # ------------------------------------------------------------------

    def create_plan(
        self,
        name: str,
        mode: RecoveryMode = RecoveryMode.AUTOMATED,
        multi_zone: bool = False,
        multi_region: bool = False,
        replication_enabled: bool = False,
        failover_enabled: bool = True,
        graceful_degradation: bool = True,
        queue_durability: bool = True,
        data_reconciliation_enabled: bool = True,
        iac_enabled: bool = True,
        auto_rebuild: bool = True,
        config_backed_up: bool = True,
        secret_recovery_enabled: bool = True,
        alt_communication_channels: Optional[List[str]] = None,
    ) -> RecoveryPlan:
        """Create a named recovery plan."""
        plan = RecoveryPlan(
            name=name,
            mode=mode,
            multi_zone=multi_zone,
            multi_region=multi_region,
            replication_enabled=replication_enabled,
            failover_enabled=failover_enabled,
            graceful_degradation=graceful_degradation,
            queue_durability=queue_durability,
            data_reconciliation_enabled=data_reconciliation_enabled,
            iac_enabled=iac_enabled,
            auto_rebuild=auto_rebuild,
            config_backed_up=config_backed_up,
            secret_recovery_enabled=secret_recovery_enabled,
            alt_communication_channels=alt_communication_channels or [],
        )
        self._plans[name] = plan
        logger.info("Created recovery plan: %s (mode=%s)", name, mode.value)
        return plan

    def get_plan(self, name: str) -> Optional[RecoveryPlan]:
        """Retrieve a recovery plan by name."""
        return self._plans.get(name)

    # ------------------------------------------------------------------
    # Core recovery actions
    # ------------------------------------------------------------------

    def execute_failover(self, plan_name: str) -> bool:
        """Execute failover for the named plan.

        Triggers external hooks if registered, then records the event.
        """
        plan = self._plans.get(plan_name)
        if plan is None:
            logger.error("execute_failover: unknown plan '%s'", plan_name)
            return False
        if not plan.failover_enabled:
            logger.warning("Failover not enabled for plan '%s'", plan_name)
            return False

        if "failover" in self._hooks:
            self._hooks["failover"](plan_name=plan_name)

        plan.last_failover_at = datetime.utcnow()
        self._log_recovery("failover", plan_name, success=True)
        logger.info("Failover executed for plan '%s'", plan_name)
        return True

    def reconcile_data(self, plan_name: str) -> bool:
        """Reconcile data between primary and replica after a disruption."""
        plan = self._plans.get(plan_name)
        if plan is None:
            logger.error("reconcile_data: unknown plan '%s'", plan_name)
            return False
        if not plan.data_reconciliation_enabled:
            logger.info("Data reconciliation not enabled for plan '%s'", plan_name)
            return True

        if "reconcile" in self._hooks:
            self._hooks["reconcile"](plan_name=plan_name)

        self._log_recovery("reconcile_data", plan_name, success=True)
        logger.info("Data reconciled for plan '%s'", plan_name)
        return True

    def rebuild_infrastructure(self, plan_name: str) -> Dict[str, Any]:
        """Rebuild infrastructure from IaC for the named plan.

        Returns the infrastructure state after rebuild.
        """
        plan = self._plans.get(plan_name)
        if plan is None:
            logger.error("rebuild_infrastructure: unknown plan '%s'", plan_name)
            return {}

        if not plan.iac_enabled:
            logger.warning("IaC not enabled for plan '%s'; cannot rebuild", plan_name)
            return self._infra_state

        if "rebuild" in self._hooks:
            result = self._hooks["rebuild"](plan_name=plan_name)
            if isinstance(result, dict):
                self._infra_state.update(result)

        rebuild_id = str(uuid.uuid4())[:8]
        state = {
            "plan": plan_name,
            "rebuild_id": rebuild_id,
            "status": "completed",
            "timestamp": datetime.utcnow().isoformat(),
            "multi_zone": plan.multi_zone,
            "multi_region": plan.multi_region,
        }
        self._infra_state[plan_name] = state
        self._log_recovery("rebuild_infrastructure", plan_name, success=True)
        logger.info("Infrastructure rebuilt for plan '%s' (id=%s)", plan_name, rebuild_id)
        return state

    def recover_secrets(self, plan_name: str) -> Dict[str, str]:
        """Recover secrets from the encrypted secrets store."""
        plan = self._plans.get(plan_name)
        if plan is None:
            logger.error("recover_secrets: unknown plan '%s'", plan_name)
            return {}
        if not plan.secret_recovery_enabled:
            logger.info("Secret recovery not enabled for plan '%s'", plan_name)
            return {}

        if "recover_secrets" in self._hooks:
            secrets = self._hooks["recover_secrets"](plan_name=plan_name)
            if isinstance(secrets, dict):
                self._secrets_store.update(secrets)

        self._log_recovery("recover_secrets", plan_name, success=True)
        logger.info("Secrets recovered for plan '%s'", plan_name)
        return dict(self._secrets_store)

    def establish_alt_comms(self, plan_name: str) -> bool:
        """Establish alternate communication channels for crisis coordination."""
        plan = self._plans.get(plan_name)
        if plan is None:
            logger.error("establish_alt_comms: unknown plan '%s'", plan_name)
            return False

        for channel in plan.alt_communication_channels:
            self._communication[channel] = True
            logger.info("Alt communication channel '%s' established for plan '%s'", channel, plan_name)

        self._log_recovery("establish_alt_comms", plan_name, success=True)
        return True

    # ------------------------------------------------------------------
    # Validation & rollback
    # ------------------------------------------------------------------

    def validate_recovery(self, plan_name: str) -> Dict[str, bool]:
        """Validate that all recovery steps completed successfully."""
        plan = self._plans.get(plan_name)
        if plan is None:
            return {"valid": False, "reason": "plan_not_found"}

        checks: Dict[str, bool] = {
            "failover_executed": plan.last_failover_at is not None,
            "infrastructure_rebuilt": plan_name in self._infra_state,
            "alt_comms_established": len(self._communication) > 0 or not plan.alt_communication_channels,
            "plan_current": plan.updated_at is not None or plan.created_at is not None,
        }
        all_valid = all(checks.values())
        logger.info("Recovery validation for '%s': %s", plan_name, "PASS" if all_valid else "FAIL")
        checks["valid"] = all_valid
        return checks

    def rollback(self, plan_name: str) -> bool:
        """Roll back the last failover or infrastructure change."""
        plan = self._plans.get(plan_name)
        if plan is None:
            logger.error("rollback: unknown plan '%s'", plan_name)
            return False

        if "rollback" in self._hooks:
            self._hooks["rollback"](plan_name=plan_name)

        self._infra_state.pop(plan_name, None)
        plan.last_failover_at = None
        self._log_recovery("rollback", plan_name, success=True)
        logger.info("Rollback completed for plan '%s'", plan_name)
        return True

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _log_recovery(self, action: str, plan_name: str, success: bool) -> None:
        self._recovery_log.append({
            "action": action,
            "plan_name": plan_name,
            "success": success,
            "timestamp": datetime.utcnow().isoformat(),
        })

    def get_recovery_log(self) -> List[Dict[str, Any]]:
        """Return the full recovery action log."""
        return list(self._recovery_log)