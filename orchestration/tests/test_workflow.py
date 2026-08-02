"""
Tests for the Workflow Composer module.

Covers:
  - DAG construction, cycle detection, topological sort
  - WorkflowBuilder fluent API (sequential, parallel, fan-out, conditional)
  - Execution (sync/async), retry, timeout, failure policies
  - Prebuilt pattern factories
"""

import asyncio
import time
from unittest.mock import MagicMock, patch

import pytest

from enterprise.orchestration.workflow_composer import (
    DAG,
    Workflow,
    WorkflowBuilder,
    WorkflowNode,
    Edge,
    WorkflowResult,
    NodeResult,
    RetryPolicy,
    ExecutionMode,
    ExecutionPolicy,
    NodeState,
    WorkflowError,
    CycleDetectedError,
    NodeNotFoundError,
    WorkflowExecutionError,
    NodeTimeoutError,
    sequential_pipeline,
    parallel_fanout,
    conditional_branch,
)


# ---------------------------------------------------------------------------
# DAG Tests
# ---------------------------------------------------------------------------

class TestDAG:
    """Tests for the DAG (Directed Acyclic Graph) class."""

    def test_add_node(self):
        dag = DAG()
        dag.add_node("a")
        assert "a" in dag.nodes()
        dag.add_node("a")  # no-op
        assert len(dag) == 1

    def test_add_edge_simple(self):
        dag = DAG()
        dag.add_node("a")
        dag.add_node("b")
        dag.add_edge("a", "b")
        assert dag.successors("a") == {"b"}
        assert dag.predecessors("b") == {"a"}

    def test_add_edge_missing_node_raises(self):
        dag = DAG()
        dag.add_node("a")
        with pytest.raises(NodeNotFoundError):
            dag.add_edge("a", "b")

    def test_cycle_detection_simple(self):
        dag = DAG()
        dag.add_node("a")
        dag.add_node("b")
        dag.add_node("c")
        dag.add_edge("a", "b")
        dag.add_edge("b", "c")
        with pytest.raises(CycleDetectedError):
            dag.add_edge("c", "a")

    def test_cycle_detection_self_loop(self):
        dag = DAG()
        dag.add_node("a")
        with pytest.raises(CycleDetectedError):
            dag.add_edge("a", "a")

    def test_topological_order_linear(self):
        dag = DAG()
        dag.add_node("a")
        dag.add_node("b")
        dag.add_node("c")
        dag.add_edge("a", "b")
        dag.add_edge("b", "c")
        order = dag.topological_order()
        assert order == ["a", "b", "c"]

    def test_topological_order_diamond(self):
        dag = DAG()
        for n in ("a", "b1", "b2", "c"):
            dag.add_node(n)
        dag.add_edge("a", "b1")
        dag.add_edge("a", "b2")
        dag.add_edge("b1", "c")
        dag.add_edge("b2", "c")
        order = dag.topological_order()
        assert order[0] == "a"
        assert order[3] == "c"
        assert set(order[1:3]) == {"b1", "b2"}

    def test_topological_order_raises_on_cycle(self):
        dag = DAG()
        dag.add_node("a")
        dag.add_node("b")
        dag.add_node("c")
        dag.add_edge("a", "b")
        dag.add_edge("b", "c")
        # Manually create a cycle by hacking internal state
        dag._adj["c"].add("a")
        dag._rev_adj["a"].add("c")
        with pytest.raises(CycleDetectedError):
            dag.topological_order()

    def test_roots_and_leaves(self):
        dag = DAG()
        dag.add_node("a")
        dag.add_node("b")
        dag.add_node("c")
        dag.add_edge("a", "b")
        dag.add_edge("b", "c")
        assert dag.roots() == {"a"}
        assert dag.leaves() == {"c"}


# ---------------------------------------------------------------------------
# WorkflowBuilder Tests
# ---------------------------------------------------------------------------

class TestWorkflowBuilder:
    """Tests for the fluent WorkflowBuilder API."""

    def test_build_simple_workflow(self):
        def handler(ctx):
            return ctx.get("x", 0) + 1

        wf = (WorkflowBuilder("test")
              .node("step1", handler)
              .node("step2", handler, depends_on=["step1"])
              .edge("step1", "step2")
              .build())

        assert wf.name == "test"
        assert len(wf.nodes) == 2
        assert wf._dag.topological_order() == ["step1", "step2"]

    def test_sequential_pattern(self):
        results = []

        def make_handler(name):
            def h(ctx):
                results.append(name)
                return name
            return h

        wf = (WorkflowBuilder("seq")
              .sequential("a", "b", "c", handler_factory=make_handler)
              .build())

        wf.execute()
        assert results == ["a", "b", "c"]

    def test_parallel_pattern(self):
        tracker = set()

        def make_handler(name):
            def h(ctx):
                tracker.add(name)
                return name
            return h

        wf = (WorkflowBuilder("parallel-test")
              .node("src", lambda ctx: ctx)
              .parallel("p1", "p2", "p3", join_on="collect",
                        handler_factory=make_handler)
              .fan_out("src", ["p1", "p2", "p3"])
              .build())

        wf.execute()
        assert "p1" in tracker
        assert "p2" in tracker
        assert "p3" in tracker
        assert len(tracker) == 3

    def test_fan_out_pattern(self):
        received = []

        def source(ctx):
            return "data"

        def worker(name):
            def h(ctx):
                received.append(name)
                return name
            return h

        wf = (WorkflowBuilder("fanout")
              .node("src", source)
              .node("w1", worker("w1"))
              .node("w2", worker("w2"))
              .node("w3", worker("w3"))
              .fan_out("src", ["w1", "w2", "w3"])
              .build())

        wf.execute()
        assert len(received) == 3
        assert set(received) == {"w1", "w2", "w3"}

    def test_conditional_pattern_true(self):
        def cond(ctx):
            return True

        def true_handler(ctx):
            return "true"

        def false_handler(ctx):
            return "false"

        wf = (WorkflowBuilder("cond-true")
              .conditional("check", cond, true_handler, false_handler)
              .build())

        result = wf.execute()
        assert result.node_results["check_true"].output == "true"

    def test_conditional_pattern_false(self):
        def cond(ctx):
            return False

        def true_handler(ctx):
            return "true"

        def false_handler(ctx):
            return "false"

        wf = (WorkflowBuilder("cond-false")
              .conditional("check", cond, true_handler, false_handler)
              .build())

        result = wf.execute()
        assert result.node_results["check_false"].output == "false"

    def test_validation_detects_issues(self):
        wf = (WorkflowBuilder("broken")
              .node("a", lambda ctx: ctx, depends_on=["missing"])
              .build())
        issues = wf.validate()
        assert any("missing" in i for i in issues)

    def test_execution_policy_fail_fast(self):
        def failing(ctx):
            raise ValueError("boom")

        def should_not_run(ctx):
            return "should_not_run"

        wf = (WorkflowBuilder("fail")
              .node("a", failing)
              .node("b", should_not_run, depends_on=["a"])
              .edge("a", "b")
              .with_policy(ExecutionPolicy.FAIL_FAST)
              .build())

        result = wf.execute()
        assert result.success is False
        assert "a" in result.errors

    def test_retry_policy(self):
        call_count = {"count": 0}

        def flaky(ctx):
            call_count["count"] += 1
            if call_count["count"] < 3:
                raise ValueError("transient")
            return "ok"

        wf = (WorkflowBuilder("retry")
              .node("a", flaky, retry_policy=RetryPolicy(
                  max_retries=3,
                  backoff_base=0.01,
              ))
              .build())

        result = wf.execute()
        assert result.success
        assert call_count["count"] == 3
        assert result.node_results["a"].retries == 2


# ---------------------------------------------------------------------------
# Execution Tests
# ---------------------------------------------------------------------------

class TestWorkflowExecution:
    """Tests for Workflow execution behaviour."""

    def test_simple_linear_execution(self):
        order = []

        def a(ctx):
            order.append("a")
            return "a_out"

        def b(ctx):
            order.append("b")
            assert ctx.get("a") == "a_out"
            return "b_out"

        wf = (WorkflowBuilder("linear")
              .node("a", a)
              .node("b", b, depends_on=["a"])
              .edge("a", "b")
              .build())

        result = wf.execute()
        assert order == ["a", "b"]
        assert result.success
        assert result.node_results["a"].output == "a_out"
        assert result.node_results["b"].output == "b_out"

    def test_context_propagation(self):
        def a(ctx):
            return 42

        def b(ctx):
            # output key defaults to node_id
            return ctx.get("a") * 2

        wf = (WorkflowBuilder("ctx")
              .node("a", a)
              .node("b", b, depends_on=["a"])
              .edge("a", "b")
              .build())

        result = wf.execute()
        assert result.node_results["b"].output == 84

    def test_initial_context(self):
        def step(ctx):
            return ctx["injected"] * 10

        wf = (WorkflowBuilder("init-ctx")
              .node("step", step)
              .build())

        result = wf.execute(initial_context={"injected": 7})
        assert result.node_results["step"].output == 70

    def test_async_handler(self):
        async def async_step(ctx):
            await asyncio.sleep(0.01)
            return "async_done"

        wf = (WorkflowBuilder("async")
              .node("step", async_step)
              .build())

        result = wf.execute()
        assert result.success
        assert result.node_results["step"].output == "async_done"

    def test_empty_workflow(self):
        wf = WorkflowBuilder("empty").build()
        result = wf.execute()
        assert result.success

    def test_output_key_override(self):
        def handler(ctx):
            return "custom_value"

        wf = (WorkflowBuilder("override")
              .node("step", handler, output_key="custom_key")
              .build())

        result = wf.execute()
        assert result.node_results["step"].output == "custom_value"


# ---------------------------------------------------------------------------
# Prebuilt Pattern Tests
# ---------------------------------------------------------------------------

class TestPrebuiltPatterns:
    """Tests for convenience factory functions."""

    def test_sequential_pipeline(self):
        calls = []

        def make_handler(name):
            def h(ctx):
                calls.append(name)
                return name
            return h

        wf = sequential_pipeline("pipe", [
            ("s1", make_handler("s1")),
            ("s2", make_handler("s2")),
            ("s3", make_handler("s3")),
        ])
        result = wf.execute()
        assert calls == ["s1", "s2", "s3"]
        assert result.success

    def test_parallel_fanout(self):
        collected = set()

        def source(ctx):
            return list(range(3))

        def worker(ctx):
            i = int(ctx.get("worker_id", 0))
            return i * 2

        workers = [(f"w{i}", worker) for i in range(4)]

        wf = parallel_fanout("fan", "src", source, workers)
        result = wf.execute()
        assert result.success
        assert "src" in result.node_results
        assert "collect" in result.node_results

    def test_conditional_branch(self):
        def cond(ctx):
            return ctx.get("mode") == "A"

        def true_h(ctx):
            return "mode_A"

        def false_h(ctx):
            return "mode_B"

        def after(ctx):
            t = ctx.get("true_branch", "")
            f = ctx.get("false_branch", "")
            return f"after:{t or f}"

        wf = conditional_branch("branch", cond, true_h, false_h, after)
        result = wf.execute(initial_context={"mode": "A"})
        assert "mode_A" in str(result.node_results["after"].output)


# ---------------------------------------------------------------------------
# Edge Case Tests
# ---------------------------------------------------------------------------

class TestEdgeCases:
    """Edge case and stress tests."""

    def test_many_nodes(self):
        n = 50
        builder = WorkflowBuilder("many")
        for i in range(n):
            builder.node(f"n{i}", lambda ctx, i=i: i)
            if i > 0:
                builder.edge(f"n{i-1}", f"n{i}")
        wf = builder.build()
        result = wf.execute()
        assert result.success
        assert len(result.node_results) == n

    def test_dump_graph(self):
        wf = (WorkflowBuilder("graph")
              .node("a", lambda ctx: None)
              .node("b", lambda ctx: None)
              .edge("a", "b")
              .build())
        graph_str = wf.dump_graph()
        assert "graph TD" in graph_str
        assert "a" in graph_str
        assert "b" in graph_str

    def test_node_timeout(self):
        def slow(ctx):
            time.sleep(10)
            return "slow"

        wf = (WorkflowBuilder("timeout")
              .node("a", slow, timeout=0.05)
              .build())

        result = wf.execute()
        nr = result.node_results["a"]
        assert nr.state == NodeState.TIMED_OUT