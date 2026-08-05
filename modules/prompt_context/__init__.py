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

from .prompt_registry import PromptRegistry

_logger = logging.getLogger("enterprise.prompt_context")


@module(name="prompt_context", version=_KERNEL_VERSION)
class PromptContextModule(Module):
    """Kernel-managed wrapper around the prompt_context OS module.

    Wraps the most representative entrypoint (PromptRegistry) so the platform kernel
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
                self._component = PromptRegistry()
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
                if not hasattr(self._component, "_prompts"):
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


def create_prompt_context_module(config: Optional[Dict[str, Any]] = None) -> PromptContextModule:
    """Factory: create a prompt_context module instance."""
    return PromptContextModule(config)
