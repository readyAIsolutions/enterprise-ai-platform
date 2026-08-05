"""
Innovation R&D OS Module

Enterprise-grade innovation and research & development management system.
Provides tools for research tracking, experiment management, integrity checks,
sandboxed environments, technology scouting, and IP management.

Version: 1.0.0
"""

__version__ = "1.0.0"
__module__ = "innovation_rd"

from .experiment import Experiment, ExperimentStatus, ExperimentTracker
from .experiments import (
    AssessmentResult,
    Experiment as StatisticalExperiment,
    ExperimentRegistry,
    ExperimentRunner,
    HypothesisTest,
    assess,
    bootstrap_p_value,
    permutation_test,
    welch_t_test,
)
from .integrity import IntegrityCheck, IntegrityReport
from .ip import IPCategory, IPEntry, IPManager
from .isolation import IsolationConfig, IsolationManager
from .pipeline import (
    Assessment,
    Comparison,
    Decision,
    Documentation,
    ExperimentDesign,
    Hypothesis,
    InnovationPipeline,
    MetricsSnapshot,
    Opportunity,
    Prototype,
    ResearchResult,
    TransferPackage,
)
from .research import ResearchDomain, ResearchEntry, ResearchLibrary
from .scouting import ScoutEngine, ScoutEntry, ScoutTarget

__all__ = [
    "__version__",
    # Pipeline
    "InnovationPipeline",
    "Opportunity",
    "Hypothesis",
    "ResearchResult",
    "Assessment",
    "ExperimentDesign",
    "Prototype",
    "MetricsSnapshot",
    "Comparison",
    "Decision",
    "Documentation",
    "TransferPackage",
    # Research
    "ResearchDomain",
    "ResearchEntry",
    "ResearchLibrary",
    # Experiment
    "Experiment",
    "ExperimentStatus",
    "ExperimentTracker",
    # Statistical experiments (MASTER CLASS)
    "StatisticalExperiment",
    "ExperimentRegistry",
    "ExperimentRunner",
    "HypothesisTest",
    "AssessmentResult",
    "assess",
    "welch_t_test",
    "permutation_test",
    "bootstrap_p_value",
    # Integrity
    "IntegrityCheck",
    "IntegrityReport",
    # Isolation
    "IsolationConfig",
    "IsolationManager",
    # Scouting
    "ScoutTarget",
    "ScoutEntry",
    "ScoutEngine",
    # IP
    "IPCategory",
    "IPEntry",
    "IPManager",
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


_logger = logging.getLogger("enterprise.innovation_rd")


@module(name="innovation_rd", version=_KERNEL_VERSION)
class InnovationRDModule(Module):
    """Kernel-managed wrapper around the innovation_rd OS module.

    Wraps the most representative entrypoint (InnovationPipeline) so the platform kernel
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
                self._component = InnovationPipeline()
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
                self._component.identify_opportunity(problem_statement="kernel probe")
                return HealthStatus.HEALTHY
            except Exception as e:  # pragma: no cover
                _logger.warning("%s health probe failed: %s", self.name, e)
                return HealthStatus.DEGRADED

    async def shutdown(self) -> None:
        with self._lock:
            self._status = HealthStatus.STOPPING
            self._component = None
            self._init_error = None


def create_innovation_rd_module(config: dict[str, Any] | None = None) -> InnovationRDModule:
    """Factory: create a innovation_rd module instance."""
    return InnovationRDModule(config)
