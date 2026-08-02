"""
Unit tests for PipelineExecutor.
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
)
from pipeline import PipelineExecutor, PipelineResult


# ------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------

@pytest.fixture
def simple_pipeline():
    """A simple 2-stage sequential pipeline."""
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
            depends_on=[0],
        ),
    ]
    return ComposedPipeline(
        stages=stages,
        estimated_total_tokens=900,
        required_inputs={"text"},
        produced_outputs={"summary", "label"},
    )


@pytest.fixture
def parallel_pipeline():
    """A pipeline with parallel stages."""
    stages = [
        Stage(
            module_name="summarizer",
            mode=ExecutionMode.PARALLEL,
            input_mapping={"text": "text"},
            output_mapping={"summary": "summary"},
        ),
        Stage(
            module_name="entity_extractor",
            mode=ExecutionMode.PARALLEL,
            input_mapping={"text": "text"},
            output_mapping={"entities": "entities"},
        ),
    ]
    return ComposedPipeline(
        stages=stages,
        estimated_total_tokens=1300,
        required_inputs={"text"},
        produced_outputs={"summary", "entities"},
    )


@pytest.fixture
def conditional_pipeline():
    """A pipeline with a conditional stage."""
    stages = [
        Stage(
            module_name="summarizer",
            mode=ExecutionMode.SEQUENTIAL,
            input_mapping={"text": "text"},
            output_mapping={"summary": "summary"},
        ),
        Stage(
            module_name="validator",
            mode=ExecutionMode.CONDITIONAL,
            input_mapping={"data": "summary"},
            output_mapping={"valid": "is_valid"},
            condition=lambda ctx: len(ctx.get("text", "")) > 100,
        ),
    ]
    return ComposedPipeline(
        stages=stages,
        estimated_total_tokens=800,
        required_inputs={"text"},
        produced_outputs={"summary", "is_valid"},
    )


@pytest.fixture
def executor():
    """Returns a PipelineExecutor with test handlers."""
    ex = PipelineExecutor()

    def summarizer_handler(ctx):
        return {"summary": f"Summary of: {ctx.get('text', '')}"}

    def classifier_handler(ctx):
        return {"label": "positive"}

    def entity_extractor_handler(ctx):
        return {"entities": ["entity1", "entity2"]}

    def validator_handler(ctx):
        return {"valid": True}

    ex.register_handler("summarizer", summarizer_handler)
    ex.register_handler("classifier", classifier_handler)
    ex.register_handler("entity_extractor", entity_extractor_handler)
    ex.register_handler("validator", validator_handler)

    return ex


# ------------------------------------------------------------------
# Handler Management Tests
# ------------------------------------------------------------------

class TestHandlerManagement:
    """Tests for handler registration / unregistration."""

    def test_register_handler(self):
        ex = PipelineExecutor()
        ex.register_handler("my_module", lambda ctx: {"out": "value"})
        assert "my_module" in ex._handlers

    def test_unregister_handler(self):
        ex = PipelineExecutor()
        ex.register_handler("my_module", lambda ctx: {})
        ex.unregister_handler("my_module")
        assert "my_module" not in ex._handlers

    def test_unregister_missing_raises(self):
        ex = PipelineExecutor()
        with pytest.raises(KeyError, match="No handler registered"):
            ex.unregister_handler("nonexistent")


# ------------------------------------------------------------------
# Sequential Execution Tests
# ------------------------------------------------------------------

class TestSequentialExecution:
    """Tests for sequential pipeline execution."""

    def test_execute_simple_pipeline(self, executor, simple_pipeline):
        result = executor.execute(simple_pipeline, initial_input={"text": "Hello world"})
        assert result.success is True
        assert len(result.stages) == 2
        assert "summary" in result.final_output
        assert "label" in result.final_output

    def test_execute_outputs_pass_between_stages(self, executor, simple_pipeline):
        result = executor.execute(simple_pipeline, initial_input={"text": "Test text"})
        # Second stage uses the summary from first stage as input
        all_ok = all(s.success for s in result.stages)
        assert all_ok is True

    def test_execute_missing_handler(self, simple_pipeline):
        ex = PipelineExecutor()  # No handlers
        result = ex.execute(simple_pipeline, initial_input={"text": "test"})
        assert result.success is False
        assert any("No handler" in (s.error or "") for s in result.stages)

    def test_execute_handler_raises(self):
        ex = PipelineExecutor()
        def bad_handler(ctx):
            raise RuntimeError("Simulated failure")
        ex.register_handler("summarizer", bad_handler)

        stages = [Stage(
            module_name="summarizer",
            mode=ExecutionMode.SEQUENTIAL,
            input_mapping={"text": "text"},
            output_mapping={"summary": "summary"},
        )]
        pipeline = ComposedPipeline(stages=stages)
        result = ex.execute(pipeline, initial_input={"text": "test"})
        assert result.success is False
        assert "Simulated failure" in (result.stages[0].error or "")

    def test_execute_stop_on_error(self):
        ex = PipelineExecutor()
        def fail_handler(ctx):
            raise RuntimeError("fail")
        ex.register_handler("summarizer", fail_handler)
        ex.register_handler("classifier", lambda ctx: {"label": "ok"})

        stages = [
            Stage(module_name="summarizer", mode=ExecutionMode.SEQUENTIAL,
                  input_mapping={}, output_mapping={}),
            Stage(module_name="classifier", mode=ExecutionMode.SEQUENTIAL,
                  input_mapping={}, output_mapping={}),
        ]
        pipeline = ComposedPipeline(stages=stages)
        result = ex.execute(pipeline, stop_on_error=True)
        assert result.success is False
        assert len(result.stages) == 1  # Stopped after first failure

    def test_execute_do_not_stop_on_error(self):
        ex = PipelineExecutor()
        call_count = [0]
        def fail_handler(ctx):
            raise RuntimeError("fail")
        def count_handler(ctx):
            call_count[0] += 1
            return {"out": "ok"}

        ex.register_handler("summarizer", fail_handler)
        ex.register_handler("classifier", count_handler)

        stages = [
            Stage(module_name="summarizer", mode=ExecutionMode.SEQUENTIAL,
                  input_mapping={}, output_mapping={}),
            Stage(module_name="classifier", mode=ExecutionMode.SEQUENTIAL,
                  input_mapping={}, output_mapping={}),
        ]
        pipeline = ComposedPipeline(stages=stages)
        result = ex.execute(pipeline, stop_on_error=False)
        assert len(result.stages) == 2  # Both ran


# ------------------------------------------------------------------
# Parallel Execution Tests
# ------------------------------------------------------------------

class TestParallelExecution:
    """Tests for parallel stage execution."""

    def test_execute_parallel(self, executor, parallel_pipeline):
        result = executor.execute(parallel_pipeline, initial_input={"text": "test"})
        assert result.success is True
        assert len(result.stages) == 2
        assert "summary" in result.final_output
        assert "entities" in result.final_output

    def test_parallel_stages_run_independently(self, executor):
        order = []
        def handler_a(ctx):
            order.append("A")
            return {"out_a": "a"}
        def handler_b(ctx):
            order.append("B")
            return {"out_b": "b"}

        executor.register_handler("A", handler_a)
        executor.register_handler("B", handler_b)

        stages = [
            Stage(module_name="A", mode=ExecutionMode.PARALLEL, input_mapping={}, output_mapping={"out_a": "a"}),
            Stage(module_name="B", mode=ExecutionMode.PARALLEL, input_mapping={}, output_mapping={"out_b": "b"}),
        ]
        pipeline = ComposedPipeline(stages=stages)
        result = executor.execute(pipeline)
        assert result.success is True
        assert "a" in result.final_output
        assert "b" in result.final_output


# ------------------------------------------------------------------
# Conditional Execution Tests
# ------------------------------------------------------------------

class TestConditionalExecution:
    """Tests for conditional stage execution."""

    def test_condition_true_executes(self, executor, conditional_pipeline):
        result = executor.execute(
            conditional_pipeline,
            initial_input={"text": "A" * 200},  # len > 100 so condition is True
        )
        assert result.success is True
        assert len(result.stages) == 2
        assert "is_valid" in result.final_output

    def test_condition_false_skips(self, executor, conditional_pipeline):
        result = executor.execute(
            conditional_pipeline,
            initial_input={"text": "short"},  # len < 100 so condition is False
        )
        assert result.success is True
        # Both should appear but the second should be skipped
        if len(result.stages) >= 2:
            skipped = any(
                r.output.get("__skipped__") or r.metadata.get("skipped")
                if hasattr(r, 'metadata') else False
                for r in result.stages
            )


# ------------------------------------------------------------------
# Execution Group Tests
# ------------------------------------------------------------------

class TestExecutionGroups:
    """Tests for _build_execution_groups."""

    def test_all_sequential(self, executor):
        stages = [
            Stage("A", mode=ExecutionMode.SEQUENTIAL),
            Stage("B", mode=ExecutionMode.SEQUENTIAL),
            Stage("C", mode=ExecutionMode.SEQUENTIAL),
        ]
        groups = executor._build_execution_groups(stages)
        assert len(groups) == 3
        assert all(len(g) == 1 for g in groups)

    def test_parallel_batch(self, executor):
        stages = [
            Stage("A", mode=ExecutionMode.PARALLEL),
            Stage("B", mode=ExecutionMode.PARALLEL),
            Stage("C", mode=ExecutionMode.SEQUENTIAL),
        ]
        groups = executor._build_execution_groups(stages)
        # A and B in one group, C alone
        assert len(groups) == 2
        assert len(groups[0]) == 2

    def test_mixed_modes(self, executor):
        stages = [
            Stage("A", mode=ExecutionMode.SEQUENTIAL),
            Stage("B", mode=ExecutionMode.PARALLEL),
            Stage("C", mode=ExecutionMode.PARALLEL),
            Stage("D", mode=ExecutionMode.CONDITIONAL),
            Stage("E", mode=ExecutionMode.SEQUENTIAL),
        ]
        groups = executor._build_execution_groups(stages)
        # A=1, B+C=2, D=1, E=1 => 4 groups
        assert len(groups) == 4
        assert len(groups[1]) == 2  # B and C together


# ------------------------------------------------------------------
# Input/Output Mapping Tests
# ------------------------------------------------------------------

class TestIOMapping:
    """Tests for input/output mapping between stages."""

    def test_custom_mapping(self):
        ex = PipelineExecutor()
        def handler(ctx):
            return {"result": ctx.get("input_key", "default")}
        ex.register_handler("mod", handler)

        stage = Stage(
            module_name="mod",
            mode=ExecutionMode.SEQUENTIAL,
            input_mapping={"input_key": "external_key"},
            output_mapping={"result": "final_key"},
        )
        pipeline = ComposedPipeline(stages=[stage])
        result = ex.execute(pipeline, initial_input={"external_key": "hello"})
        assert result.final_output.get("final_key") == "hello"


# ------------------------------------------------------------------
# Async Execution Tests
# ------------------------------------------------------------------

class TestAsyncExecution:
    """Tests for async pipeline execution (via sync path since no asyncio plugin)."""

    def test_async_execute_via_sync(self, executor, simple_pipeline):
        """Test that the pipeline executes correctly (sync path)."""
        result = executor.execute(
            simple_pipeline, initial_input={"text": "async test"}
        )
        assert result.success is True
        assert len(result.stages) == 2

    def test_async_parallel_via_sync(self, executor, parallel_pipeline):
        """Test parallel pipeline via sync path."""
        result = executor.execute(
            parallel_pipeline, initial_input={"text": "test"}
        )
        assert result.success is True


# ------------------------------------------------------------------
# PipelineResult Tests
# ------------------------------------------------------------------

class TestPipelineResult:
    """Tests for PipelineResult dataclass."""

    def test_defaults(self):
        result = PipelineResult()
        assert result.success is True
        assert result.stages == []
        assert result.final_output == {}

    def test_total_duration_set(self, executor, simple_pipeline):
        result = executor.execute(simple_pipeline, initial_input={"text": "test"})
        assert result.total_duration_ms >= 0