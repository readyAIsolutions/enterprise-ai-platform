"""
ENI Enterprise — Safety & Governance OS v1.0.0
AI Safety, Security, Guardrails, Evaluation, Monitoring, Incident Response.
"""

__version__ = "1.0.0"

from .evaluator import AccuracyScorer, SafetyEvaluator
from .governance import GovernanceBoard, RiskRegister
from .guardrails import GuardrailResult, SafetyGuardrail
from .incident import IncidentManager, IncidentSeverity
from .monitoring import Alert, SafetyMonitor
from .scoring import (
    CooccurrenceModel,
    RefusalScorer,
    SafetyResult as ScoringSafetyResult,
    SafetyScorer,
    SafetyVerdict,
    ToxicityCategory,
    ToxicityScorer as ScoringToxicityScorer,
    create_safety_scorer,
)

__all__ = [
    "SafetyGuardrail",
    "GuardrailResult",
    "SafetyEvaluator",
    "AccuracyScorer",
    "GovernanceBoard",
    "RiskRegister",
    "SafetyMonitor",
    "Alert",
    "IncidentManager",
    "IncidentSeverity",
    # SafetyScoring engine
    "ToxicityCategory",
    "SafetyVerdict",
    "ScoringToxicityScorer",
    "RefusalScorer",
    "CooccurrenceModel",
    "ScoringSafetyResult",
    "SafetyScorer",
    "create_safety_scorer",
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
from typing import Any, Dict, Optional  # noqa: F401

from enterprise.platform_kernel import HealthStatus, Module, module

_KERNEL_VERSION = globals().get("__version__", "1.0.0")


_logger = logging.getLogger("enterprise.safety_governance")


@module(name="safety_governance", version=_KERNEL_VERSION)
class SafetyGovernanceModule(Module):
    """Kernel-managed wrapper around the safety_governance OS module.

    Wraps the most representative entrypoint (SafetyEvaluator) so the platform kernel
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
                self._component = SafetyEvaluator(config={})
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
                self._component.run_toxicity_eval(["kernel probe"])
                return HealthStatus.HEALTHY
            except Exception as e:  # pragma: no cover
                _logger.warning("%s health probe failed: %s", self.name, e)
                return HealthStatus.DEGRADED

    async def shutdown(self) -> None:
        with self._lock:
            self._status = HealthStatus.STOPPING
            self._component = None
            self._init_error = None


def create_safety_governance_module(
    config: dict[str, Any] | None = None,
) -> SafetyGovernanceModule:
    """Factory: create a safety_governance module instance."""
    return SafetyGovernanceModule(config)
