"""
Developer Experience OS Module
==============================
Enterprise-grade Developer Experience operating system providing
a unified framework for developer journey, standards, environments,
golden paths, internal platform, AI coding rules, documentation,
and productivity metrics.

Architecture:
    journey.py      - Developer lifecycle journey stages
    standards.py    - Repository standards enforcement
    environment.py  - Development environment specifications
    golden_paths.py - Approved golden-path workflows
    platform.py     - Internal Developer Platform (IDP) capabilities
    ai_rules.py     - AI coding agent governance rules
    docs.py         - Documentation standards and quality gates
    metrics.py      - Developer productivity and DORA metrics
"""

__version__ = "1.0.0"

from enterprise.modules.developer_experience.journey import (
    DeveloperJourney,
    JourneyStage,
    JourneyStageStatus,
    get_journey,
    get_all_journeys,
    get_stage,
    advance_stage,
)
from enterprise.modules.developer_experience.standards import (
    RepoStandard,
    StandardCategory,
    StandardSeverity,
    validate_repo_standards,
    get_required_standards,
    check_standard_compliance,
    generate_standard_report,
)
from enterprise.modules.developer_experience.environment import (
    DevEnvironment,
    EnvironmentProvider,
    EnvironmentStatus,
    create_environment,
    validate_environment,
    get_environment_spec,
    list_supported_providers,
)
from enterprise.modules.developer_experience.golden_paths import (
    GoldenPath,
    PathCategory,
    PathStatus,
    get_golden_path,
    list_golden_paths,
    execute_golden_path,
    validate_path_prerequisites,
)
from enterprise.modules.developer_experience.platform import (
    IDPCapability,
    CapabilityStatus,
    PlatformRequest,
    get_capability,
    list_capabilities,
    request_capability,
    get_service_catalog,
    self_service_action,
)
from enterprise.modules.developer_experience.ai_rules import (
    AIRule,
    AIRuleCategory,
    AIRuleSeverity,
    get_ai_rules,
    validate_ai_compliance,
    generate_ai_rules_report,
    enforce_ai_rules,
)
from enterprise.modules.developer_experience.docs import (
    DocStandard,
    DocQualityGate,
    DocStatus,
    validate_documentation,
    get_doc_standards,
    assess_doc_quality,
    generate_doc_report,
)
from enterprise.modules.developer_experience.metrics import (
    DXMetric,
    MetricCategory,
    DORAMetrics,
    collect_metric,
    get_metrics_dashboard,
    calculate_dora_metrics,
    generate_metrics_report,
    track_setup_time,
    track_build_duration,
    track_deploy_frequency,
)
from enterprise.modules.developer_experience.validation import (
    GoldenCheck,
    GoldenPath as GoldenPathChecklist,
    GoldenPathValidator,
    ValidationReport,
    CheckResult,
    DeliveryBand,
    DeployEvent,
    DeliveryMetrics,
    DXScore,
    letter_grade,
)

__all__ = [
    # Journey
    "DeveloperJourney",
    "JourneyStage",
    "JourneyStageStatus",
    "get_journey",
    "get_all_journeys",
    "get_stage",
    "advance_stage",
    # Standards
    "RepoStandard",
    "StandardCategory",
    "StandardSeverity",
    "validate_repo_standards",
    "get_required_standards",
    "check_standard_compliance",
    "generate_standard_report",
    # Environment
    "DevEnvironment",
    "EnvironmentProvider",
    "EnvironmentStatus",
    "create_environment",
    "validate_environment",
    "get_environment_spec",
    "list_supported_providers",
    # Golden Paths
    "GoldenPath",
    "PathCategory",
    "PathStatus",
    "get_golden_path",
    "list_golden_paths",
    "execute_golden_path",
    "validate_path_prerequisites",
    # Platform
    "IDPCapability",
    "CapabilityStatus",
    "PlatformRequest",
    "get_capability",
    "list_capabilities",
    "request_capability",
    "get_service_catalog",
    "self_service_action",
    # AI Rules
    "AIRule",
    "AIRuleCategory",
    "AIRuleSeverity",
    "get_ai_rules",
    "validate_ai_compliance",
    "generate_ai_rules_report",
    "enforce_ai_rules",
    # Docs
    "DocStandard",
    "DocQualityGate",
    "DocStatus",
    "validate_documentation",
    "get_doc_standards",
    "assess_doc_quality",
    "generate_doc_report",
    # Metrics
    "DXMetric",
    "MetricCategory",
    "DORAMetrics",
    "collect_metric",
    "get_metrics_dashboard",
    "calculate_dora_metrics",
    "generate_metrics_report",
    "track_setup_time",
    "track_build_duration",
    "track_deploy_frequency",
    # Validation (golden-path + delivery metrics)
    "GoldenCheck",
    "GoldenPathChecklist",
    "GoldenPathValidator",
    "ValidationReport",
    "CheckResult",
    "DeliveryBand",
    "DeployEvent",
    "DeliveryMetrics",
    "DXScore",
    "letter_grade",
]

# --------------------------------------------------------------------------

# --------------------------------------------------------------------------

# --------------------------------------------------------------------------

# --------------------------------------------------------------------------
# Kernel lifecycle registration -- makes this OS module discoverable by the
# ENI Platform Kernel for initialize/health_check/shutdown orchestration.
# --------------------------------------------------------------------------
import asyncio
import logging
import threading
from typing import Any, Dict, Optional

from enterprise.platform_kernel import HealthStatus, Module, module

_KERNEL_VERSION = globals().get("__version__", "1.0.0")

from .journey import DeveloperJourney

_logger = logging.getLogger("enterprise.developer_experience")


@module(name="developer_experience", version=_KERNEL_VERSION)
class DeveloperExperienceModule(Module):
    """Kernel-managed wrapper around the developer_experience OS module.

    Wraps the most representative entrypoint (DeveloperJourney) so the platform kernel
    can initialize it, probe its health, and shut it down as part of the ENI
    lifecycle. If the core component cannot be instantiated the module reports
    UNHEALTHY rather than crashing the platform.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(config)
        self._lock = threading.RLock()
        self._component = None
        self._init_error = None

    async def initialize(self) -> None:
        with self._lock:
            self._status = HealthStatus.STARTING
            try:
                self._component = DeveloperJourney(developer_id="kernel", developer_name="Kernel", team="platform", role="engineer")
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
                if not getattr(self._component, "stages", None) or len(self._component.stages) == 0:
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


def create_developer_experience_module(config: Optional[Dict[str, Any]] = None) -> DeveloperExperienceModule:
    """Factory: create a developer_experience module instance."""
    return DeveloperExperienceModule(config)
