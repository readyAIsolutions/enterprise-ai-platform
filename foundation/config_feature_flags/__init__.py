"""
Config & Feature Flags enterprise module.

Provides centralized configuration management, feature flag evaluation,
gradual rollouts, audit trailing, and A/B experiment support.

Modules:
    config:      ConfigManager - layered configuration with schema validation
    flags:       FeatureFlagManager - feature flags with targeting rules
    rollout:     RolloutManager - staged rollouts and canary releases
    audit:       AuditTrail - immutable configuration change auditing
    experiments: ExperimentManager - A/B testing and statistical analysis
"""

from .config import ConfigManager, ConfigLayer, ConfigValidationError
from .flags import FeatureFlagManager, Flag, FlagTargetingRule, FlagEvaluationResult
from .rollout import RolloutManager, RolloutStage, RolloutStatus, CanaryRelease
from .audit import AuditTrail, AuditEntry, AuditReport
from .experiments import ExperimentManager, Experiment, Variant, ExperimentResult

__all__ = [
    # Config
    "ConfigManager",
    "ConfigLayer",
    "ConfigValidationError",
    # Flags
    "FeatureFlagManager",
    "Flag",
    "FlagTargetingRule",
    "FlagEvaluationResult",
    # Rollout
    "RolloutManager",
    "RolloutStage",
    "RolloutStatus",
    "CanaryRelease",
    # Audit
    "AuditTrail",
    "AuditEntry",
    "AuditReport",
    # Experiments
    "ExperimentManager",
    "Experiment",
    "Variant",
    "ExperimentResult",
]