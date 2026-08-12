"""
ENI Enterprise MLOps/LLMOps Lifecycle Module — Complete Agent Experiment Lifecycle Management
============================================================================================

This module provides a comprehensive MLOps/LLMOps lifecycle for agent experiments,
integrating with the ENI Enterprise Platform modules:

- Experiment Tracking: Full lifecycle management via innovation_rd
- Configuration Management: Versioned, reproducible experiment configs
- Feature/Label Store: Persistent storage for training/validation data
- Canary Rollouts: Runtime feature flags via release_change
- Evaluation Gates: Automated quality gates via eval_gate
- Observability: OpenTelemetry GenAI tracing via llmops_trace
- Drift Detection: Statistical drift monitoring for models/data
- Rollback Strategies: Automated and manual rollback capabilities

Architecture:
    MLOpsLifecycleModule (Module)
    ├── ExperimentTracker       — CRUD + lineage for experiments
    ├── ConfigManager           — Versioned configs with schema validation
    ├── FeatureLabelStore       — SQLite/Parquet feature + label storage
    ├── CanaryManager           — Feature flags + progressive rollouts
    ├── EvalGateEngine          — Automated evaluation pipelines
    ├── ObservabilityEngine     — Tracing, metrics, logging aggregation
    ├── DriftDetector           — Statistical drift detection (PSI, KS, etc.)
    ├── RollbackController      — Automated + manual rollback with safety
    └── LifecycleOrchestrator   — End-to-end pipeline coordination

All components are local-first, offline-capable, and stdlib-only where possible.
"""

from __future__ import annotations

__version__ = "1.0.0"

# Core exports
from .experiment_tracker import (
    ExperimentTracker,
    ExperimentRecord,
    ExperimentConfig,
    ExperimentStatus,
    ExperimentLineage,
    create_experiment_tracker,
)

from .config_manager import (
    ConfigManager,
    ExperimentConfiguration,
    ConfigSchema,
    ConfigVersion,
    ConfigValidator,
    create_config_manager,
)

from .feature_label_store import (
    FeatureLabelStore,
    FeatureSet,
    LabelSet,
    FeatureVector,
    DataVersion,
    create_feature_label_store,
)

from .canary_manager import (
    CanaryManager,
    CanaryDeployment,
    RolloutStrategy,
    RolloutPhase,
    CanaryMetrics,
    create_canary_manager,
)

from .eval_gate_engine import (
    EvalGateEngine,
    EvaluationPipeline,
    GateResult,
    GatePolicy,
    EvaluationReport,
    create_eval_gate_engine,
)

from .observability_engine import (
    ObservabilityEngine,
    TraceContext,
    MetricPoint,
    LogEntry,
    AlertRule,
    create_observability_engine,
)

from .drift_detector import (
    DriftDetector,
    DriftMetric,
    DriftAlert,
    DriftType,
    DetectionMethod,
    create_drift_detector,
)

from .rollback_controller import (
    RollbackController,
    RollbackPlan,
    RollbackAction,
    RollbackTrigger,
    SafetyCheck,
    create_rollback_controller,
)

from .lifecycle_orchestrator import (
    LifecycleOrchestrator,
    PipelineStage,
    PipelineRun,
    StageResult,
    OrchestrationPolicy,
    create_lifecycle_orchestrator,
)

# Module factory
from .module import (
    MLOpsLifecycleModule,
    create_mlops_lifecycle_module,
)

__all__ = [
    # Experiment Tracking
    "ExperimentTracker",
    "ExperimentRecord",
    "ExperimentConfig",
    "ExperimentStatus",
    "ExperimentLineage",
    "create_experiment_tracker",
    # Config Management
    "ConfigManager",
    "ExperimentConfiguration",
    "ConfigSchema",
    "ConfigVersion",
    "ConfigValidator",
    "create_config_manager",
    # Feature/Label Store
    "FeatureLabelStore",
    "FeatureSet",
    "LabelSet",
    "FeatureVector",
    "DataVersion",
    "create_feature_label_store",
    # Canary Management
    "CanaryManager",
    "CanaryDeployment",
    "RolloutStrategy",
    "RolloutPhase",
    "CanaryMetrics",
    "create_canary_manager",
    # Evaluation Gates
    "EvalGateEngine",
    "EvaluationPipeline",
    "GateResult",
    "GatePolicy",
    "EvaluationReport",
    "create_eval_gate_engine",
    # Observability
    "ObservabilityEngine",
    "TraceContext",
    "MetricPoint",
    "LogEntry",
    "AlertRule",
    "create_observability_engine",
    # Drift Detection
    "DriftDetector",
    "DriftMetric",
    "DriftAlert",
    "DriftType",
    "DetectionMethod",
    "create_drift_detector",
    # Rollback
    "RollbackController",
    "RollbackPlan",
    "RollbackAction",
    "RollbackTrigger",
    "SafetyCheck",
    "create_rollback_controller",
    # Orchestration
    "LifecycleOrchestrator",
    "PipelineStage",
    "PipelineRun",
    "StageResult",
    "OrchestrationPolicy",
    "create_lifecycle_orchestrator",
    # Module
    "MLOpsLifecycleModule",
    "create_mlops_lifecycle_module",
]