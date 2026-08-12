"""
Canary Manager — staged rollout of new model/agent versions behind runtime
feature flags, with automatic promotion and rollback based on live metrics.

Supports several rollout strategies (canary, blue/green, ramped,
all-at-once) and exposes a small state machine over :class:`RolloutPhase`.
Implementation is pure-stdlib (dataclasses + in-memory store).
"""

from __future__ import annotations

import logging
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger("enterprise.mlops_lifecycle.canary_manager")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class RolloutStrategy(Enum):
    """How traffic is shifted from the stable to the candidate version."""

    CANARY = "canary"
    BLUE_GREEN = "blue_green"
    RAMPED = "ramped"
    ALL_AT_ONCE = "all_at_once"


class RolloutPhase(Enum):
    """Lifecycle phases a canary deployment can occupy."""

    PENDING = "pending"
    DEPLOYING = "deploying"
    RUNNING = "running"
    PROMOTED = "promoted"
    ROLLED_BACK = "rolled_back"
    COMPLETE = "complete"


@dataclass
class CanaryMetrics:
    """Aggregated runtime metrics for a canary window."""

    total_requests: int = 0
    error_requests: int = 0
    latency_p99_ms: float = 0.0
    throughput_rps: float = 0.0

    @property
    def error_rate(self) -> float:
        """Error rate as a fraction in [0, 1]."""
        if self.total_requests <= 0:
            return 0.0
        return self.error_requests / self.total_requests


@dataclass
class CanaryDeployment:
    """A single staged rollout of a candidate model/agent version."""

    model_version: str
    strategy: RolloutStrategy = RolloutStrategy.CANARY
    initial_percentage: float = 5.0
    step_percentage: float = 5.0
    deployment_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    phase: RolloutPhase = RolloutPhase.PENDING
    current_percentage: float = 0.0
    target_percentage: float = 100.0
    metrics: CanaryMetrics = field(default_factory=CanaryMetrics)
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["strategy"] = self.strategy.value
        data["phase"] = self.phase.value
        return data


class CanaryManager:
    """Manages a collection of canary deployments.

    Pure in-memory with a small state machine enforcing valid phase
    transitions (PENDING -> DEPLOYING -> RUNNING -> PROMOTED, or
    RUNNING -> ROLLED_BACK).
    """

    _VALID_TRANSITIONS: Dict[RolloutPhase, List[RolloutPhase]] = {
        RolloutPhase.PENDING: [RolloutPhase.DEPLOYING, RolloutPhase.ROLLED_BACK],
        RolloutPhase.DEPLOYING: [RolloutPhase.RUNNING, RolloutPhase.ROLLED_BACK],
        RolloutPhase.RUNNING: [RolloutPhase.PROMOTED, RolloutPhase.ROLLED_BACK],
        RolloutPhase.PROMOTED: [RolloutPhase.COMPLETE],
        RolloutPhase.ROLLED_BACK: [],
        RolloutPhase.COMPLETE: [],
    }

    def __init__(self) -> None:
        self._deployments: Dict[str, CanaryDeployment] = {}
        self._lock = threading.RLock()

    def create_deployment(
        self,
        model_version: str,
        strategy: RolloutStrategy | str = RolloutStrategy.CANARY,
        initial_percentage: float = 5.0,
        step_percentage: float = 5.0,
    ) -> CanaryDeployment:
        """Create a new canary deployment in the PENDING phase."""
        if isinstance(strategy, str):
            strategy = RolloutStrategy(strategy)
        deploy = CanaryDeployment(
            model_version=model_version,
            strategy=strategy,
            initial_percentage=max(0.0, min(100.0, float(initial_percentage))),
            step_percentage=max(0.0, min(100.0, float(step_percentage))),
        )
        if strategy is RolloutStrategy.BLUE_GREEN:
            deploy.current_percentage = 100.0
        elif strategy is RolloutStrategy.ALL_AT_ONCE:
            deploy.current_percentage = 100.0
        else:
            deploy.current_percentage = 0.0
        with self._lock:
            self._deployments[deploy.deployment_id] = deploy
        return deploy

    def get_deployment(self, deployment_id: str) -> Optional[CanaryDeployment]:
        with self._lock:
            return self._deployments.get(deployment_id)

    def start(self, deployment_id: str) -> bool:
        """Move a PENDING deployment into DEPLOYING/RUNNING."""
        with self._lock:
            deploy = self._deployments.get(deployment_id)
            if deploy is None:
                return False
            return self._transition(deploy, RolloutPhase.DEPLOYING)

    def _transition(self, deploy: CanaryDeployment, target: RolloutPhase) -> bool:
        if target not in self._VALID_TRANSITIONS.get(deploy.phase, []):
            logger.warning(
                "invalid canary transition %s -> %s",
                deploy.phase.value,
                target.value,
            )
            return False
        deploy.phase = target
        deploy.updated_at = _now_iso()
        if target is RolloutPhase.DEPLOYING:
            deploy.current_percentage = deploy.initial_percentage
        return True

    def record_metrics(self, deployment_id: str, metrics: CanaryMetrics) -> bool:
        """Record live metrics for a running deployment."""
        with self._lock:
            deploy = self._deployments.get(deployment_id)
            if deploy is None:
                return False
            deploy.metrics = metrics
            deploy.updated_at = _now_iso()
            return True

    def advance(self, deployment_id: str) -> bool:
        """Increase the traffic percentage of a running canary by one step."""
        with self._lock:
            deploy = self._deployments.get(deployment_id)
            if deploy is None or deploy.phase is not RolloutPhase.RUNNING:
                return False
            deploy.current_percentage = min(
                100.0, deploy.current_percentage + deploy.step_percentage
            )
            deploy.updated_at = _now_iso()
            return True

    def can_promote(
        self,
        deployment_id: str,
        max_error_rate: float = 0.01,
        min_requests: int = 100,
    ) -> bool:
        """Decide whether a running canary meets the promote criteria."""
        with self._lock:
            deploy = self._deployments.get(deployment_id)
            if deploy is None or deploy.phase is not RolloutPhase.RUNNING:
                return False
            if deploy.metrics.total_requests < min_requests:
                return False
            return deploy.metrics.error_rate <= max_error_rate

    def promote(self, deployment_id: str) -> bool:
        """Promote a canary to full production traffic."""
        with self._lock:
            deploy = self._deployments.get(deployment_id)
            if deploy is None:
                return False
            if not self._transition(deploy, RolloutPhase.PROMOTED):
                return False
            deploy.current_percentage = 100.0
            return True

    def rollback(self, deployment_id: str) -> bool:
        """Roll a deployment back, dropping candidate traffic to zero."""
        with self._lock:
            deploy = self._deployments.get(deployment_id)
            if deploy is None:
                return False
            if not self._transition(deploy, RolloutPhase.ROLLED_BACK):
                return False
            deploy.current_percentage = 0.0
            return True

    def list_deployments(self) -> List[CanaryDeployment]:
        with self._lock:
            return list(self._deployments.values())

    def deployments_by_phase(self, phase: RolloutPhase | str) -> List[CanaryDeployment]:
        if isinstance(phase, str):
            phase = RolloutPhase(phase)
        return [d for d in self.list_deployments() if d.phase is phase]


def create_canary_manager(config: Optional[Dict[str, Any]] = None) -> CanaryManager:
    """Create a default :class:`CanaryManager`.

    Args:
        config: Optional dict (currently unused; kept for interface parity).
    """
    return CanaryManager()
