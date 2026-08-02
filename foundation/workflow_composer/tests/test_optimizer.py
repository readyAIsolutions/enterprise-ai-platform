"""
Unit tests for PipelineOptimizer.
"""

import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from composer import (
    ComposedPipeline,
    ExecutionMode,
    Stage,
    Module,
    ModuleCapability,
    ModuleConstraint,
)
from optimizer import (
    PipelineOptimizer,
    CostEstimate,
    OptimizationResult,
    DEFAULT_TOKEN_COSTS,
)


# ------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------

@pytest.fixture
def module_registry():
    return {
        "summarizer": Module(
            name="summarizer",
            capabilities=[ModuleCapability("text_summarization", 0.95, tags={"nlp"})],
            input_schema={"text": "str"},
            output_schema={"summary": "str"},
            estimated_tokens=500,
            metadata={"model": "gpt-4"},
        ),
        "cheap_summarizer": Module(
            name="cheap_summarizer",
            capabilities=[ModuleCapability("text_summarization", 0.85, tags={"nlp"})],
            input_schema={"text": "str"},
            output_schema={"summary": "str"},
            estimated_tokens=200,
            metadata={"model": "gpt-3.5-turbo"},
        ),
        "classifier": Module(
            name="classifier",
            capabilities=[ModuleCapability("text_classification", 0.92)],
            input_schema={"text": "str"},
            output_schema={"label": "str"},
            estimated_tokens=400,
            metadata={"model": "gpt-4"},
        ),
        "cheap_classifier": Module(
            name="cheap_classifier",
            capabilities=[ModuleCapability("text_classification", 0.80)],
            input_schema={"text": "str"},
            output_schema={"label": "str"},
            estimated_tokens=150,
            metadata={"model": "gpt-3.5-turbo"},
        ),
        "entity_extractor": Module(
            name="entity_extractor",
            capabilities=[ModuleCapability("entity_extraction", 0.90)],
            input_schema={"text": "str"},
            output_schema={"entities": "list"},
            estimated_tokens=800,
            metadata={"model": "gpt-4"},
        ),
    }


@pytest.fixture
def pipeline(module_registry):
    stages = [
        Stage(
            module_name="summarizer",
            mode=ExecutionMode.SEQUENTIAL,
            input_mapping={"text": "text"},
            output_mapping={"summary": "summary"},
        ),
        Stage(
            module_name="classifier",
            mode=ExecutionMode.SEQUENTIAL,
            input_mapping={"text": "summary"},
            output_mapping={"label": "label"},
        ),
    ]
    return ComposedPipeline(
        stages=stages,
        estimated_total_tokens=900,
        required_inputs={"text"},
        produced_outputs={"summary", "label"},
    )


@pytest.fixture
def optimizer(module_registry):
    return PipelineOptimizer(module_registry=module_registry)


# ------------------------------------------------------------------
# Cost Estimation Tests
# ------------------------------------------------------------------

class TestCostEstimation:
    """Tests for module and pipeline cost estimation."""

    def test_estimate_module_cost(self, optimizer):
        mod = optimizer._modules["summarizer"]
        cost = optimizer.estimate_module_cost(mod)
        assert cost.tokens == 500
        assert cost.estimated_cost_usd > 0
        assert "base_tokens" in cost.breakdown

    def test_estimate_module_cost_default_model(self, optimizer):
        mod = Module(name="test", estimated_tokens=100)
        cost = optimizer.estimate_module_cost(mod)
        assert cost.tokens == 100

    def test_estimate_pipeline_cost(self, optimizer, pipeline):
        cost = optimizer.estimate_pipeline_cost(pipeline)
        assert cost.tokens == 900
        assert cost.estimated_cost_usd > 0
        assert "summarizer" in cost.breakdown
        assert "classifier" in cost.breakdown

    def test_cost_estimation_dataclass(self):
        ce = CostEstimate(tokens=100, estimated_cost_usd=0.0005)
        assert ce.tokens == 100
        assert ce.estimated_cost_usd == 0.0005
        assert ce.breakdown == {}

    def test_different_models_have_different_costs(self):
        gpt4 = Module(name="gpt4", estimated_tokens=1000, metadata={"model": "gpt-4"})
        cheap = Module(name="cheap", estimated_tokens=1000, metadata={"model": "gpt-3.5-turbo"})
        optimizer = PipelineOptimizer()
        cost_gpt4 = optimizer.estimate_module_cost(gpt4)
        cost_cheap = optimizer.estimate_module_cost(cheap)
        assert cost_gpt4.estimated_cost_usd > cost_cheap.estimated_cost_usd


# ------------------------------------------------------------------
# Alternative Exploration Tests
# ------------------------------------------------------------------

class TestFindAlternatives:
    """Tests for alternative module discovery."""

    def test_find_alternatives(self, optimizer):
        alts = optimizer.find_alternatives("summarizer")
        assert len(alts) == 1
        assert alts[0].name == "cheap_summarizer"

    def test_find_alternatives_with_capability(self, optimizer):
        alts = optimizer.find_alternatives("summarizer", capability="text_summarization")
        assert len(alts) == 1
        assert alts[0].name == "cheap_summarizer"

    def test_find_alternatives_nonexistent(self, optimizer):
        alts = optimizer.find_alternatives("nonexistent")
        assert alts == []

    def test_find_alternatives_no_shared_caps(self, optimizer):
        # entity_extractor doesn't share capabilities with summarizer/classifier
        alts = optimizer.find_alternatives("entity_extractor")
        assert len(alts) == 0

    def test_find_alternatives_sorted_by_cost(self, optimizer):
        # Add a third summarizer that's even cheaper
        optimizer.register_module(Module(
            name="ultra_cheap_summarizer",
            capabilities=[ModuleCapability("text_summarization", 0.70)],
            input_schema={"text": "str"},
            output_schema={"summary": "str"},
            estimated_tokens=50,
        ))
        alts = optimizer.find_alternatives("summarizer")
        assert len(alts) >= 2
        assert alts[0].estimated_tokens <= alts[-1].estimated_tokens


# ------------------------------------------------------------------
# Explore Alternatives Tests
# ------------------------------------------------------------------

class TestExploreAlternatives:
    """Tests for comprehensive alternative pipeline exploration."""

    def test_explore_alternatives(self, optimizer, pipeline):
        alts = optimizer.explore_alternatives(pipeline, max_combinations=10)
        assert len(alts) > 0
        assert all(isinstance(a, ComposedPipeline) for a in alts)

    def test_explore_respects_max_combinations(self, optimizer, pipeline):
        alts = optimizer.explore_alternatives(pipeline, max_combinations=2)
        assert len(alts) <= 2

    def test_explore_no_duplicates(self, optimizer, pipeline):
        alts = optimizer.explore_alternatives(pipeline)
        sigs = [tuple(s.module_name for s in a.stages) for a in alts]
        assert len(sigs) == len(set(sigs))


# ------------------------------------------------------------------
# Greedy Optimization Tests
# ------------------------------------------------------------------

class TestGreedyOptimization:
    """Tests for greedy optimization strategy."""

    def test_optimize_greedy(self, optimizer, pipeline):
        result = optimizer.optimize_greedy(pipeline)
        assert isinstance(result, OptimizationResult)
        assert result.original_pipeline is not None
        assert result.optimized_pipeline is not None

    def test_optimize_greedy_reduces_cost(self, optimizer, pipeline):
        result = optimizer.optimize_greedy(pipeline, validate=False)
        # The optimized pipeline should have cheaper modules
        mod_names = [s.module_name for s in result.optimized_pipeline.stages]
        # Both stages should be replaced by cheaper alternatives
        assert "cheap_summarizer" in mod_names or "cheap_classifier" in mod_names

    def test_optimize_greedy_saves_tokens(self, optimizer, pipeline):
        result = optimizer.optimize_greedy(pipeline, validate=False)
        assert result.savings >= 0
        assert result.savings_percent >= 0

    def test_optimize_greedy_with_validation(self, optimizer, pipeline):
        result = optimizer.optimize_greedy(pipeline, validate=True)
        assert isinstance(result, OptimizationResult)

    def test_optimization_result_dataclass(self, pipeline):
        result = OptimizationResult(
            original_pipeline=pipeline,
            optimized_pipeline=pipeline,
            original_cost=CostEstimate(tokens=900),
            optimized_cost=CostEstimate(tokens=500),
            savings=400,
            savings_percent=44.44,
            alternatives_explored=10,
        )
        assert result.savings == 400
        assert result.savings_percent == 44.44
        assert result.alternatives_explored == 10


# ------------------------------------------------------------------
# Full Optimization Pipeline Tests
# ------------------------------------------------------------------

class TestOptimize:
    """Tests for the main optimize() entry point."""

    def test_optimize_greedy_strategy(self, optimizer, pipeline):
        result = optimizer.optimize(pipeline, strategy="greedy", validate=False)
        assert isinstance(result, OptimizationResult)
        assert result.metadata["strategy"] == "greedy"

    def test_optimize_unknown_strategy(self, optimizer, pipeline):
        with pytest.raises(ValueError, match="Unknown optimization strategy"):
            optimizer.optimize(pipeline, strategy="brute_force")


# ------------------------------------------------------------------
# Select Cheapest for Capability Tests
# ------------------------------------------------------------------

class TestSelectCheapestForCapability:
    """Tests for select_cheapest_for_capability."""

    def test_select_cheapest(self, optimizer):
        mod = optimizer.select_cheapest_for_capability("text_summarization")
        assert mod is not None
        assert mod.name == "cheap_summarizer"  # 200 tokens vs 500

    def test_select_cheapest_min_confidence(self, optimizer):
        mod = optimizer.select_cheapest_for_capability(
            "text_summarization", min_confidence=0.95
        )
        assert mod is not None
        assert mod.name == "summarizer"  # cheap_summarizer has 0.85, below threshold

    def test_select_cheapest_no_match(self, optimizer):
        mod = optimizer.select_cheapest_for_capability("nonexistent_capability")
        assert mod is None

    def test_select_cheapest_with_token_constraint(self, optimizer):
        constraints = [ModuleConstraint("max_tokens", 300)]
        mod = optimizer.select_cheapest_for_capability(
            "text_summarization",
            required_constraints=constraints,
        )
        # summarizer=500 exceeds 300, cheap_summarizer=200 fits
        assert mod is not None
        assert mod.name == "cheap_summarizer"


# ------------------------------------------------------------------
# Token Cost Configuration Tests
# ------------------------------------------------------------------

class TestTokenCosts:
    """Tests for token cost configuration."""

    def test_default_costs_loaded(self):
        opt = PipelineOptimizer()
        assert "default" in opt._token_costs
        assert "gpt-4" in opt._token_costs

    def test_custom_costs(self):
        custom = {"custom_model": 0.001}
        opt = PipelineOptimizer(token_costs=custom)
        assert opt._token_costs["custom_model"] == 0.001
        # Defaults still present
        assert "default" in opt._token_costs

    def test_custom_cost_overrides_default(self):
        custom = {"gpt-4": 0.000001}  # Override
        opt = PipelineOptimizer(token_costs=custom)
        assert opt._token_costs["gpt-4"] == 0.000001


# ------------------------------------------------------------------
# Edge Cases
# ------------------------------------------------------------------

class TestEdgeCases:
    """Edge case tests for optimizer."""

    def test_optimize_empty_pipeline(self):
        opt = PipelineOptimizer()
        pipeline = ComposedPipeline(stages=[])
        result = opt.optimize_greedy(pipeline)
        assert isinstance(result, OptimizationResult)
        assert result.savings == 0

    def test_optimize_single_stage(self, optimizer):
        pipeline = ComposedPipeline(
            stages=[Stage("entity_extractor")],
            estimated_total_tokens=800,
        )
        result = optimizer.optimize_greedy(pipeline, validate=False)
        # No alternative for entity_extractor, so should be unchanged
        assert result.savings == 0

    def test_cost_zero_tokens(self):
        mod = Module(name="free_mod", estimated_tokens=0,
                     capabilities=[ModuleCapability("test")])
        opt = PipelineOptimizer()
        cost = opt.estimate_module_cost(mod)
        assert cost.tokens == 0
        assert cost.estimated_cost_usd == 0.0

    def test_register_module_updates_registry(self, optimizer):
        optimizer.register_module(
            Module("new_mod", capabilities=[ModuleCapability("test")])
        )
        assert "new_mod" in optimizer._modules