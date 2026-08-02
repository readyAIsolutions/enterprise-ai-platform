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
]