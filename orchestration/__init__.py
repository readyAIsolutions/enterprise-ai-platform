"""
Enterprise Orchestration Layer.

Provides:
  - Workflow Composer: DAG-based declarative workflow builder and execution engine.
  - Plugin Framework: Discovery, loading, hot-reload, sandboxing, version compatibility.
  - Feature Flags: Dynamic config, targeting rules, gradual rollouts, audit logging.
"""

from enterprise.orchestration.workflow_composer import (
    # Core
    Workflow,
    WorkflowBuilder,
    WorkflowNode,
    DAG,
    # Data models
    Edge,
    WorkflowResult,
    NodeResult,
    RetryPolicy,
    # Enums
    ExecutionMode,
    ExecutionPolicy,
    NodeState,
    # Exceptions
    WorkflowError,
    CycleDetectedError,
    NodeNotFoundError,
    WorkflowExecutionError,
    NodeTimeoutError,
    # Prebuilt patterns
    sequential_pipeline,
    parallel_fanout,
    conditional_branch,
)

from enterprise.orchestration.plugin_framework import (
    # Core
    PluginManager,
    PluginRegistry,
    PluginBase,
    PluginDiscovery,
    # Data models
    PluginManifest,
    PluginCapability,
    RegistryEntry,
    SemVer,
    # Sandbox
    SandboxPolicy,
    SubprocessSandbox,
    # Enums
    PluginState,
    # Exceptions
    PluginError,
    PluginNotFoundError,
    PluginLoadError,
    IncompatibleVersionError,
    SandboxViolationError,
    CircularDependencyError,
    # Utilities
    hot_reload_module,
)

from enterprise.orchestration.feature_flags import (
    # Core
    FeatureFlagEngine,
    ConfigVersionStore,
    AuditLogger,
    # Data models
    FlagDefinition,
    TargetRule,
    TargetingRuleSet,
    AuditEntry,
    ConfigSnapshot,
    # Enums
    FlagType,
    FlagState,
    TargetOperator,
    AuditAction,
    # Exceptions
    FeatureFlagError,
    FlagNotFoundError,
    FlagDependencyError,
    FlagValidationError,
    ConfigVersionError,
    # Factory
    create_engine,
)

__all__ = [
    # Workflow Composer
    "Workflow",
    "WorkflowBuilder",
    "WorkflowNode",
    "DAG",
    "Edge",
    "WorkflowResult",
    "NodeResult",
    "RetryPolicy",
    "ExecutionMode",
    "ExecutionPolicy",
    "NodeState",
    "WorkflowError",
    "CycleDetectedError",
    "NodeNotFoundError",
    "WorkflowExecutionError",
    "NodeTimeoutError",
    "sequential_pipeline",
    "parallel_fanout",
    "conditional_branch",
    # Plugin Framework
    "PluginManager",
    "PluginRegistry",
    "PluginBase",
    "PluginDiscovery",
    "PluginManifest",
    "PluginCapability",
    "RegistryEntry",
    "SemVer",
    "SandboxPolicy",
    "SubprocessSandbox",
    "PluginState",
    "PluginError",
    "PluginNotFoundError",
    "PluginLoadError",
    "IncompatibleVersionError",
    "SandboxViolationError",
    "CircularDependencyError",
    "hot_reload_module",
    # Feature Flags
    "FeatureFlagEngine",
    "ConfigVersionStore",
    "AuditLogger",
    "FlagDefinition",
    "TargetRule",
    "TargetingRuleSet",
    "AuditEntry",
    "ConfigSnapshot",
    "FlagType",
    "FlagState",
    "TargetOperator",
    "AuditAction",
    "FeatureFlagError",
    "FlagNotFoundError",
    "FlagDependencyError",
    "FlagValidationError",
    "ConfigVersionError",
    "create_engine",
]