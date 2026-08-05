"""
Release & Change Management OS Module

Enterprise-grade release and change management for the ENI platform.
Manages the full lifecycle of changes: classification, workflow,
deployment strategies, quality gates, and deliverables.

Supports:
  - Structured change workflows with 14 stages
  - Risk-based classification (13 change types, 4 risk levels)
  - 8 deployment strategies (canary, blue-green, staged rollout, etc.)
  - 10 quality gate checks
  - 10 deliverable types for compliance and audit readiness

Version: 1.0.0
"""

__version__ = "1.0.0"

from .changes import ChangeClassifier, ChangeTemplate, ChangeType, RiskLevel
from .deliverables import Deliverable, DeliverableManager, DeliverableType
from .flags import (
    AuditEntry,
    AuditLog,
    Canary,
    CanaryState,
    FeatureFlag,
    FlagEngine,
    GateDecision,
    ReleaseGate,
    RuleOp,
    TargetingRule,
    hash_bucket,
)
from .quality_gates import GateStatus, GateType, QualityGate, QualityGateEngine
from .strategies import DeploymentStrategy, StrategyEngine, StrategyType
from .workflow import ChangeRecord, ChangeStage, ChangeWorkflow

__all__ = [
    # Workflow
    "ChangeStage",
    "ChangeRecord",
    "ChangeWorkflow",
    # Changes
    "ChangeType",
    "RiskLevel",
    "ChangeTemplate",
    "ChangeClassifier",
    # Strategies
    "StrategyType",
    "DeploymentStrategy",
    "StrategyEngine",
    # Quality Gates
    "GateType",
    "GateStatus",
    "QualityGate",
    "QualityGateEngine",
    # Deliverables
    "DeliverableType",
    "Deliverable",
    "DeliverableManager",
    # Runtime Feature Flags / Canary
    "RuleOp",
    "TargetingRule",
    "FeatureFlag",
    "FlagEngine",
    "CanaryState",
    "Canary",
    "GateDecision",
    "ReleaseGate",
    "AuditEntry",
    "AuditLog",
    "hash_bucket",
]

# --------------------------------------------------------------------------

# --------------------------------------------------------------------------

# --------------------------------------------------------------------------

# --------------------------------------------------------------------------
# Kernel lifecycle registration -- makes this OS module discoverable by the
# ENI Platform Kernel for initialize/health_check/shutdown orchestration.
# --------------------------------------------------------------------------
import asyncio  # noqa: F401
import logging
import threading
from typing import Any  # noqa: F401

from enterprise.platform_kernel import HealthStatus, Module, module

_KERNEL_VERSION = globals().get("__version__", "1.0.0")


_logger = logging.getLogger("enterprise.release_change")


@module(name="release_change", version=_KERNEL_VERSION)
class ReleaseChangeModule(Module):
    """Kernel-managed wrapper around the release_change OS module.

    Wraps the most representative entrypoint (ChangeWorkflow) so the platform kernel
    can initialize it, probe its health, and shut it down as part of the ENI
    lifecycle. If the core component cannot be instantiated the module reports
    UNHEALTHY rather than crashing the platform.
    """

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        super().__init__(config)
        self._lock = threading.RLock()
        self._component = None
        self._init_error = None

    async def initialize(self) -> None:
        with self._lock:
            self._status = HealthStatus.STARTING
            try:
                self._component = ChangeWorkflow()
                self._status = HealthStatus.HEALTHY
                _logger.info("%s module initialized", self.name)
            except Exception as e:  # pragma: no cover - degrade gracefully
                self._init_error = str(e)
                self._status = HealthStatus.UNHEALTHY
                _logger.warning("%s module failed to initialize: %s", self.name, e)

    async def health_check(self) -> HealthStatus:
        with self._lock:
            if self._component is None:
                return HealthStatus.UNHEALTHY if self._init_error else HealthStatus.DEGRADED
            try:
                if not hasattr(self._component, "_changes"):
                    return HealthStatus.DEGRADED
                return HealthStatus.HEALTHY
            except Exception as e:  # pragma: no cover
                _logger.warning("%s health probe failed: %s", self.name, e)
                return HealthStatus.DEGRADED

    async def shutdown(self) -> None:
        with self._lock:
            self._status = HealthStatus.STOPPING
            self._component = None
            self._init_error = None


def create_release_change_module(config: dict[str, Any] | None = None) -> ReleaseChangeModule:
    """Factory: create a release_change module instance."""
    return ReleaseChangeModule(config)
