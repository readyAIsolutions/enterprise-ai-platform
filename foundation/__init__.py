"""
Enterprise Foundation — Core infrastructure for the Eni Builder platform.

This package provides three cornerstone modules that power the entire
enterprise AI platform:

    prompt_registry   — Prompt versioning, A/B testing, template inheritance,
                        approval workflows, and searchable catalogs.

    policy_engine     — Policy definition (JSON/YAML), rule-based enforcement,
                        audit logging, conflict detection, compliance mapping.

    evaluation_engine — Model evaluation framework, benchmark runner,
                        comparison matrix, regression detection, quality scoring.

All modules follow the same design philosophy: Python 3.10+, full type hints,
dataclass-driven data models, and production-quality error handling.
"""

from .prompt_registry import (
    # Enums
    PromptStatus,
    VariantAllocation,
    # Exceptions
    PromptRegistryError,
    PromptNotFoundError,
    InvalidTransitionError,
    TemplateError,
    ABTestError,
    # Template
    PromptTemplate,
    TemplateBlock,
    # Version & Record
    PromptVersion,
    PromptRecord,
    # A/B Testing
    ABTest,
    ABTestVariant,
    # Catalog
    PromptCatalog,
    SearchFilter,
    # Registry
    PromptRegistry,
    # Utilities
    parse_semver,
    semver_key,
)

from .policy_engine import (
    # Enums
    Severity,
    EnforcementAction,
    ComplianceFramework,
    # Exceptions
    PolicyError,
    PolicyDefinitionError,
    PolicyConflictError,
    PolicyEnforcementError,
    # Core data models
    RuleCondition,
    PolicyRule,
    PolicyDefinition,
    Violation,
    # Enforcement
    PolicySet,
    PolicyEnforcer,
    EnforcementResult,
    # Audit
    AuditLogger,
    AuditEntry,
    # Conflict detection
    ConflictDetector,
    ConflictReport,
    # Compliance mapping
    ComplianceMapper,
    ComplianceMapping,
    # Presets
    DataPrivacyPreset,
    SecurityPreset,
)

from .evaluation_engine import (
    # Enums
    QualityDimension,
    SuiteStatus,
    RegressionDirection,
    # Exceptions
    EvaluationError,
    SuiteNotFoundError,
    RegressionThresholdExceeded,
    # Core
    EvalCase,
    EvalSuite,
    DimensionScore,
    EvalResult,
    EvalRun,
    ScorerConfig,
    QualityScorer,
    # Benchmark Runner
    BenchmarkRunner,
    ModelInvoker,
    # Comparison
    ComparisonMatrix,
    ComparisonEntry,
    RankingEntry,
    # Regression
    RegressionDetector,
    RegressionSignal,
    RegressionReport,
    # Store
    EvalStore,
    # Presets
    StandardBenchmarks,
)

__all__ = [
    # ── Prompt Registry ──
    "PromptStatus",
    "VariantAllocation",
    "PromptRegistryError",
    "PromptNotFoundError",
    "InvalidTransitionError",
    "TemplateError",
    "ABTestError",
    "PromptTemplate",
    "TemplateBlock",
    "PromptVersion",
    "PromptRecord",
    "ABTest",
    "ABTestVariant",
    "PromptCatalog",
    "SearchFilter",
    "PromptRegistry",
    "parse_semver",
    "semver_key",
    # ── Policy Engine ──
    "Severity",
    "EnforcementAction",
    "ComplianceFramework",
    "PolicyError",
    "PolicyDefinitionError",
    "PolicyConflictError",
    "PolicyEnforcementError",
    "RuleCondition",
    "PolicyRule",
    "PolicyDefinition",
    "Violation",
    "PolicySet",
    "PolicyEnforcer",
    "EnforcementResult",
    "AuditLogger",
    "AuditEntry",
    "ConflictDetector",
    "ConflictReport",
    "ComplianceMapper",
    "ComplianceMapping",
    "DataPrivacyPreset",
    "SecurityPreset",
    # ── Evaluation Engine ──
    "QualityDimension",
    "SuiteStatus",
    "RegressionDirection",
    "EvaluationError",
    "SuiteNotFoundError",
    "RegressionThresholdExceeded",
    "EvalCase",
    "EvalSuite",
    "DimensionScore",
    "EvalResult",
    "EvalRun",
    "ScorerConfig",
    "QualityScorer",
    "BenchmarkRunner",
    "ModelInvoker",
    "ComparisonMatrix",
    "ComparisonEntry",
    "RankingEntry",
    "RegressionDetector",
    "RegressionSignal",
    "RegressionReport",
    "EvalStore",
    "StandardBenchmarks",
]