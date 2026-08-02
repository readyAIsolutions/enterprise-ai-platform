"""
Pipeline Optimizer: Optimize module selection to minimize token/cost usage.

Implements cost estimation, alternative path exploration, and greedy
optimization strategies for finding minimum-cost pipeline configurations.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

try:
    from .composer import (
        ComposedPipeline,
        ExecutionMode,
        Module,
        ModuleCapability,
        ModuleConstraint,
        Stage,
    )
    from .validator import PipelineValidator, ValidationReport
except ImportError:
    from composer import (
        ComposedPipeline,
        ExecutionMode,
        Module,
        ModuleCapability,
        ModuleConstraint,
        Stage,
    )
    from validator import PipelineValidator, ValidationReport


@dataclass
class CostEstimate:
    """Estimated cost breakdown for a module or pipeline.

    Attributes:
        tokens: Estimated token usage.
        estimated_cost_usd: Estimated dollar cost.
        breakdown: Per-component cost details.
    """
    tokens: int = 0
    estimated_cost_usd: float = 0.0
    breakdown: Dict[str, float] = field(default_factory=dict)


@dataclass
class OptimizationResult:
    """Result of a pipeline optimization run.

    Attributes:
        original_pipeline: The pipeline before optimization.
        optimized_pipeline: The pipeline after optimization.
        original_cost: Cost estimate of the original pipeline.
        optimized_cost: Cost estimate of the optimized pipeline.
        savings: Token savings achieved.
        savings_percent: Percentage reduction in cost.
        alternatives_explored: Number of alternative paths evaluated.
        metadata: Additional optimization metadata.
    """
    original_pipeline: ComposedPipeline
    optimized_pipeline: ComposedPipeline
    original_cost: CostEstimate = field(default_factory=CostEstimate)
    optimized_cost: CostEstimate = field(default_factory=CostEstimate)
    savings: int = 0
    savings_percent: float = 0.0
    alternatives_explored: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)


# Default cost-per-token estimates (approximate, 2024-era pricing)
DEFAULT_TOKEN_COSTS: Dict[str, float] = {
    "gpt-4": 0.00003,       # ~$30/1M tokens input
    "gpt-4-turbo": 0.00001,  # ~$10/1M tokens
    "gpt-3.5-turbo": 0.0000015,  # ~$1.5/1M tokens
    "claude-3": 0.000015,     # ~$15/1M tokens
    "claude-3-haiku": 0.00000125,  # ~$1.25/1M tokens
    "default": 0.000005,       # ~$5/1M tokens fallback
}


class PipelineOptimizer:
    """Optimizes pipeline module selection to minimize total token/cost usage.

    Strategies:
    - Greedy substitution: For each capability, try substituting a cheaper
      module that provides equivalent functionality.
    - Alternative path exploration: Evaluate alternative module combinations.
    - Constraint-aware: Respects module constraints while optimizing.

    Usage:
        optimizer = PipelineOptimizer(module_registry={...})
        result = optimizer.optimize(pipeline)
    """

    def __init__(
        self,
        module_registry: Optional[Dict[str, Module]] = None,
        token_costs: Optional[Dict[str, float]] = None,
        validator: Optional[PipelineValidator] = None,
    ):
        """Initialize the optimizer.

        Args:
            module_registry: Dict of all available modules for substitution.
            token_costs: Per-model token cost overrides.
            validator: Optional PipelineValidator for validating alternatives.
        """
        self._modules: Dict[str, Module] = module_registry or {}
        self._token_costs = {**DEFAULT_TOKEN_COSTS, **(token_costs or {})}
        self._validator = validator or PipelineValidator(module_registry=self._modules)

    # ------------------------------------------------------------------
    # Module Registry
    # ------------------------------------------------------------------

    def register_module(self, module: Module) -> None:
        """Register a module available for optimization substitution.

        Args:
            module: Module to register.
        """
        self._modules[module.name] = module
        self._validator = PipelineValidator(module_registry=self._modules)

    # ------------------------------------------------------------------
    # Cost Estimation
    # ------------------------------------------------------------------

    def estimate_module_cost(self, module: Module) -> CostEstimate:
        """Estimate the cost of executing a single module.

        Args:
            module: The module to estimate.

        Returns:
            A CostEstimate with token count and dollar cost.
        """
        model = module.metadata.get("model", "default")
        cost_per_token = self._token_costs.get(model, self._token_costs["default"])
        estimated_cost = module.estimated_tokens * cost_per_token

        return CostEstimate(
            tokens=module.estimated_tokens,
            estimated_cost_usd=round(estimated_cost, 8),
            breakdown={
                "base_tokens": module.estimated_tokens,
                "cost_per_token": cost_per_token,
            },
        )

    def estimate_pipeline_cost(self, pipeline: ComposedPipeline) -> CostEstimate:
        """Estimate the total cost of executing a composed pipeline.

        Args:
            pipeline: The pipeline to estimate.

        Returns:
            A CostEstimate aggregating all stages.
        """
        total_tokens = 0
        total_cost = 0.0
        stage_breakdown: Dict[str, float] = {}

        for stage in pipeline.stages:
            mod = self._modules.get(stage.module_name)
            if mod:
                cost = self.estimate_module_cost(mod)
                total_tokens += cost.tokens
                total_cost += cost.estimated_cost_usd
                stage_breakdown[stage.module_name] = cost.estimated_cost_usd
            else:
                total_tokens += stage.metadata.get("estimated_tokens", 0)

        return CostEstimate(
            tokens=total_tokens,
            estimated_cost_usd=round(total_cost, 8),
            breakdown=stage_breakdown,
        )

    # ------------------------------------------------------------------
    # Alternative Path Exploration
    # ------------------------------------------------------------------

    def find_alternatives(
        self,
        module_name: str,
        capability: Optional[str] = None,
    ) -> List[Module]:
        """Find alternative modules that can substitute for a given module.

        Searches for modules that share capabilities with the target module
        and have lower or comparable cost.

        Args:
            module_name: The module to find alternatives for.
            capability: Optional specific capability to match on.

        Returns:
            List of alternative Module instances sorted by ascending cost.
        """
        target = self._modules.get(module_name)
        if not target:
            return []

        alternatives: List[Tuple[Module, float]] = []

        for name, mod in self._modules.items():
            if name == module_name:
                continue

            # Check shared capabilities
            target_caps = {c.name for c in target.capabilities}
            alt_caps = {c.name for c in mod.capabilities}

            if capability and capability not in alt_caps:
                continue

            shared = target_caps & alt_caps
            if not shared:
                continue

            # Score by cost (lower is better) and shared capability count
            cost = self.estimate_module_cost(mod)
            score = cost.tokens  # primary sort key: lower tokens
            alternatives.append((mod, score))

        alternatives.sort(key=lambda x: x[1])
        return [m for m, _ in alternatives]

    def explore_alternatives(
        self,
        pipeline: ComposedPipeline,
        max_combinations: int = 50,
    ) -> List[ComposedPipeline]:
        """Generate alternative pipeline configurations by swapping modules.

        For each stage, finds alternative modules and generates new pipeline
        variants. Returns up to max_combinations distinct pipelines.

        Args:
            pipeline: Original pipeline to explore from.
            max_combinations: Maximum number of alternatives to return.

        Returns:
            List of alternative ComposedPipeline instances.
        """
        alternatives: List[ComposedPipeline] = []
        seen_combos: Set[Tuple[str, ...]] = set()

        # Original signature
        original_sig = tuple(s.module_name for s in pipeline.stages)
        seen_combos.add(original_sig)

        for i, stage in enumerate(pipeline.stages):
            alt_modules = self.find_alternatives(stage.module_name)
            for alt_mod in alt_modules:
                if len(alternatives) >= max_combinations:
                    break

                # Build variant by swapping stage i
                new_stages = copy.deepcopy(pipeline.stages)
                new_stages[i].module_name = alt_mod.name

                # Clear input/output mappings since schemas may differ
                new_stages[i].input_mapping = {k: k for k in alt_mod.input_schema}
                new_stages[i].output_mapping = {k: k for k in alt_mod.output_schema}

                sig = tuple(s.module_name for s in new_stages)
                if sig not in seen_combos:
                    seen_combos.add(sig)
                    new_pipeline = ComposedPipeline(
                        stages=new_stages,
                        estimated_total_tokens=sum(
                            self._modules.get(s.module_name, Module(name=s.module_name)).estimated_tokens
                            for s in new_stages
                        ),
                        required_inputs=pipeline.required_inputs,
                        produced_outputs=pipeline.produced_outputs,
                        metadata={"derived_from": "alternative_exploration"},
                    )
                    alternatives.append(new_pipeline)

        return alternatives

    # ------------------------------------------------------------------
    # Greedy Optimization
    # ------------------------------------------------------------------

    def optimize_greedy(
        self,
        pipeline: ComposedPipeline,
        *,
        validate: bool = True,
    ) -> OptimizationResult:
        """Apply greedy optimization to minimize pipeline token usage.

        For each stage, tries to substitute the module with the cheapest
        alternative that still satisfies constraints. Iterates until no
        further improvement is possible.

        Args:
            pipeline: Pipeline to optimize.
            validate: Whether to validate alternatives before accepting.

        Returns:
            OptimizationResult with original/optimized pipelines and savings.
        """
        original_cost = self.estimate_pipeline_cost(pipeline)
        optimized = copy.deepcopy(pipeline)
        alternatives_explored = 0
        improved = True
        iterations = 0

        while improved and iterations < 10:
            improved = False
            iterations += 1

            for i, stage in enumerate(optimized.stages):
                alt_modules = self.find_alternatives(stage.module_name)

                for alt_mod in alt_modules:
                    alternatives_explored += 1

                    # Create candidate pipeline
                    candidate = copy.deepcopy(optimized)
                    candidate.stages[i].module_name = alt_mod.name
                    candidate.stages[i].input_mapping = {k: k for k in alt_mod.input_schema}
                    candidate.stages[i].output_mapping = {k: k for k in alt_mod.output_schema}

                    # Recalculate token total
                    candidate.estimated_total_tokens = sum(
                        self._modules.get(s.module_name, Module(name=s.module_name)).estimated_tokens
                        for s in candidate.stages
                    )

                    # Validate if requested (only structural — skip I/O for speed)
                    if validate:
                        quick_ok = self._validator.validate_quick(candidate)
                        if not quick_ok:
                            continue

                    # Check if this is an improvement
                    if candidate.estimated_total_tokens < optimized.estimated_total_tokens:
                        optimized = candidate
                        improved = True
                        break  # Take first improvement per stage, then restart

        optimized_cost = self.estimate_pipeline_cost(optimized)
        savings = original_cost.tokens - optimized_cost.tokens
        savings_pct = (savings / original_cost.tokens * 100) if original_cost.tokens > 0 else 0.0

        return OptimizationResult(
            original_pipeline=pipeline,
            optimized_pipeline=optimized,
            original_cost=original_cost,
            optimized_cost=optimized_cost,
            savings=max(0, savings),
            savings_percent=round(max(0, savings_pct), 2),
            alternatives_explored=alternatives_explored,
            metadata={
                "iterations": iterations,
                "strategy": "greedy",
            },
        )

    # ------------------------------------------------------------------
    # Full Optimization Pipeline
    # ------------------------------------------------------------------

    def optimize(
        self,
        pipeline: ComposedPipeline,
        *,
        strategy: str = "greedy",
        validate: bool = True,
        max_alternatives: int = 50,
    ) -> OptimizationResult:
        """Run full optimization on a pipeline.

        Args:
            pipeline: Pipeline to optimize.
            strategy: Optimization strategy ('greedy' is currently supported).
            validate: Whether to validate alternatives.
            max_alternatives: Maximum alternative combinations to explore.

        Returns:
            OptimizationResult.
        """
        if strategy == "greedy":
            return self.optimize_greedy(pipeline, validate=validate)
        else:
            raise ValueError(f"Unknown optimization strategy: '{strategy}'")

    # ------------------------------------------------------------------
    # Constraint-Aware Selection
    # ------------------------------------------------------------------

    def select_cheapest_for_capability(
        self,
        capability: str,
        required_constraints: Optional[List[ModuleConstraint]] = None,
        min_confidence: float = 0.5,
    ) -> Optional[Module]:
        """Select the cheapest module that provides a given capability.

        Sorts candidates by estimated token cost and returns the first
        that meets all constraints and confidence thresholds.

        Args:
            capability: Required capability name.
            required_constraints: Constraints that must be satisfied.
            min_confidence: Minimum confidence threshold.

        Returns:
            The cheapest suitable Module, or None if none found.
        """
        candidates: List[Tuple[Module, int]] = []

        for mod in self._modules.values():
            conf = mod.capability_confidence(capability)
            if conf < min_confidence:
                continue

            # Check constraints
            if required_constraints:
                satisfied = True
                for req_c in required_constraints:
                    if req_c.constraint_type == "max_tokens":
                        if mod.estimated_tokens > req_c.value:
                            satisfied = False
                            break
                    elif req_c.constraint_type == "excludes_module":
                        # Deferred — handled at composition time
                        pass
                if not satisfied:
                    continue

            candidates.append((mod, mod.estimated_tokens))

        if not candidates:
            return None

        candidates.sort(key=lambda x: x[1])
        return candidates[0][0]