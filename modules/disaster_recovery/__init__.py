"""
Disaster Recovery OS Module

Enterprise-grade disaster recovery, business continuity, and crisis management.
Covers backup, recovery, cyber recovery, AI continuity, exercises, and crisis coordination.

Version: 1.0.0
"""

import logging

logger = logging.getLogger("enterprise.disaster_recovery")

__version__ = "1.0.0"
__all__ = [
    # BIA
    "CriticalityLevel",
    "ImpactCategory",
    "BIAAsset",
    "BIAEngine",
    # RTO/RPO
    "RecoveryTier",
    "RTOPlan",
    "RTOPlanner",
    # Scenarios
    "ScenarioType",
    "Scenario",
    "ScenarioLibrary",
    # Backup
    "BackupType",
    "BackupPolicy",
    "BackupManager",
    # Snapshot / restore (real backup executor)
    "SnapshotEngine",
    "Snapshot",
    "ManifestEntry",
    "RestoreReport",
    "snapshot_to_dict",
    # Recovery
    "RecoveryMode",
    "RecoveryPlan",
    "RecoveryEngine",
    # Cyber Recovery
    "CyberRecoveryPhase",
    "CyberRecoveryPlan",
    "CyberRecoveryManager",
    # AI Continuity
    "AIDisruptionType",
    "AIContinuityPlan",
    "AIContinuityManager",
    # Crisis
    "CrisisRole",
    "CrisisTeam",
    "CrisisPlan",
    "CrisisManager",
    # Exercises
    "ExerciseType",
    "Exercise",
    "ExerciseManager",
]

# --------------------------------------------------------------------------
# --------------------------------------------------------------------------
# --------------------------------------------------------------------------
# --------------------------------------------------------------------------
# Kernel lifecycle registration -- makes this OS module discoverable by the
# ENI Platform Kernel for initialize/health_check/shutdown orchestration.
# --------------------------------------------------------------------------
import asyncio  # noqa: E402, F401
import logging  # noqa: E402
import threading  # noqa: E402
from typing import Any, Optional  # noqa: E402, F401

from enterprise.platform_kernel import HealthStatus, Module, module  # noqa: E402

from .ai_continuity import AIContinuityManager, AIContinuityPlan, AIDisruptionType  # noqa: E402
from .backup import BackupManager, BackupPolicy, BackupType  # noqa: E402
from .bia import BIAAsset, BIAEngine, CriticalityLevel, ImpactCategory  # noqa: E402
from .crisis import CrisisManager, CrisisPlan, CrisisRole, CrisisTeam  # noqa: E402
from .cyber_recovery import (  # noqa: E402
    CyberRecoveryManager,
    CyberRecoveryPhase,
    CyberRecoveryPlan,
)
from .exercises import Exercise, ExerciseManager, ExerciseType  # noqa: E402
from .recovery import RecoveryEngine, RecoveryMode, RecoveryPlan  # noqa: E402
from .rto_rpo import RecoveryTier, RTOPlan, RTOPlanner  # noqa: E402
from .scenarios import Scenario, ScenarioLibrary, ScenarioType  # noqa: E402
from .snapshot import (  # noqa: E402
    ManifestEntry,
    RestoreReport,
    Snapshot,
    SnapshotEngine,
    snapshot_to_dict,
)

_KERNEL_VERSION = globals().get("__version__", "1.0.0")


_logger = logging.getLogger("enterprise.disaster_recovery")


@module(name="disaster_recovery", version=_KERNEL_VERSION)
class DisasterRecoveryModule(Module):
    """Kernel-managed wrapper around the disaster_recovery OS module.

    Wraps the most representative entrypoint (RecoveryEngine) so the platform kernel
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
                self._component = RecoveryEngine()
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
                self._component.create_plan(name="kernel_probe")
                return HealthStatus.HEALTHY
            except Exception as e:  # pragma: no cover
                _logger.warning("%s health probe failed: %s", self.name, e)
                return HealthStatus.DEGRADED

    async def shutdown(self) -> None:
        with self._lock:
            self._status = HealthStatus.STOPPING
            self._component = None
            self._init_error = None


def create_disaster_recovery_module(
    config: dict[str, Any] | None = None,
) -> DisasterRecoveryModule:
    """Factory: create a disaster_recovery module instance."""
    return DisasterRecoveryModule(config)
