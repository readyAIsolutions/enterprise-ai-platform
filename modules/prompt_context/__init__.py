"""
Prompt & Context Management OS Module
======================================

Enterprise-grade module for prompt lifecycle management, context orchestration,
optimization, token budgeting, evaluation, and quality gating.

Modules:
- prompt_registry: Prompt definition, versioning, lifecycle, rollback
- context_manager: Hierarchical context blocks with priorities and TTLs
- optimizer: Deduplication, compression, conflict detection, summarization
- token_budget: Token allocation, truncation, caching, model routing
- evaluator: Multi-metric evaluation, hallucination detection, grading
- quality_gates: Pre-execution checks to block/warn on quality issues
"""

from .prompt_registry import (
    # Core
    PromptRegistry,
    PromptRegistryError,
    PromptNotFoundError,
    VersionNotFoundError,
    InvalidTransitionError,
    RollbackError,
    # Data models
    PromptStatus,
    ChangeType,
    MetricName,
    ChangelogEntry,
    PerformanceMetric,
    PromptVersion,
    PromptRecord,
    # Utilities
    SemanticVersion,
    PromptIDGenerator,
    detect_template_issues,
)

from .context_manager import (
    # Core
    ContextManager,
    ContextManagerError,
    ContextNotFoundError,
    ContextWindowExceededError,
    # Data models
    ContextType,
    ContextPriority,
    ContextSource,
    ContextBlock,
    ContextSnapshot,
    ContextWindow,
)

from .optimizer import (
    # Core
    ContextOptimizer,
    OptimizerError,
    # Data models
    OptimizationStrategy,
    OptimizerPreset,
    OptimizationAction,
    OptimizationResult,
    OptimizerConfig,
)

from .token_budget import (
    # Core
    TokenBudgetManager,
    TokenBudgetError,
    BudgetExceededError,
    # Data models
    TruncationStrategy,
    BudgetAllocation,
    CacheStrategy,
    TokenBudget,
    CacheEntry,
    BudgetReport,
    ModelRoute,
)

from .evaluator import (
    # Core
    PromptEvaluator,
    EvaluatorError,
    # Data models
    EvalMetric,
    EvalGrade,
    EvalScore,
    EvaluationResult,
    EvalSummary,
    HallucinationCheck,
)

from .quality_gates import (
    # Core
    QualityGates,
    QualityGateError,
    QualityGateBlockedError,
    # Data models
    GateSeverity,
    GateStatus,
    GateCategory,
    GateCheck,
    QualityGateResult,
    GateConfig,
)


__all__ = [
    # Registry
    "PromptRegistry",
    "PromptRegistryError",
    "PromptNotFoundError",
    "VersionNotFoundError",
    "InvalidTransitionError",
    "RollbackError",
    "PromptStatus",
    "ChangeType",
    "MetricName",
    "ChangelogEntry",
    "PerformanceMetric",
    "PromptVersion",
    "PromptRecord",
    "SemanticVersion",
    "PromptIDGenerator",
    "detect_template_issues",
    # Context Manager
    "ContextManager",
    "ContextManagerError",
    "ContextNotFoundError",
    "ContextWindowExceededError",
    "ContextType",
    "ContextPriority",
    "ContextSource",
    "ContextBlock",
    "ContextSnapshot",
    "ContextWindow",
    # Optimizer
    "ContextOptimizer",
    "OptimizerError",
    "OptimizationStrategy",
    "OptimizerPreset",
    "OptimizationAction",
    "OptimizationResult",
    "OptimizerConfig",
    # Token Budget
    "TokenBudgetManager",
    "TokenBudgetError",
    "BudgetExceededError",
    "TruncationStrategy",
    "BudgetAllocation",
    "CacheStrategy",
    "TokenBudget",
    "CacheEntry",
    "BudgetReport",
    "ModelRoute",
    # Evaluator
    "PromptEvaluator",
    "EvaluatorError",
    "EvalMetric",
    "EvalGrade",
    "EvalScore",
    "EvaluationResult",
    "EvalSummary",
    "HallucinationCheck",
    # Quality Gates
    "QualityGates",
    "QualityGateError",
    "QualityGateBlockedError",
    "GateSeverity",
    "GateStatus",
    "GateCategory",
    "GateCheck",
    "QualityGateResult",
    "GateConfig",
]

__version__ = "1.0.0"
__author__ = "Eni Builder Enterprise"
__description__ = "Prompt & Context Management OS - Enterprise-grade prompt lifecycle, context orchestration, optimization, and quality gating."