"""Unit tests for the agent_graph enterprise module.

Covers the langgraph-style stateful agent graph engine:

  - GraphNode / GraphEdge primitives and build-time validation.
  - add_node / add_edge validation (undefined node targets raise ValueError).
  - Linear chain execution in topological order.
  - Branching via conditional edges (only one path taken).
  - Cycle / back-edge handling (bounded loops + cycle protection).
  - START / END marker handling and entry-point resolution.
  - Checkpoint persistence (per-run, exact reload, sequence replay).
  - StateCopy semantics (caller dict never mutated).
  - SupervisorGraph coordinator/worker routing.
  - AgentGraphFacade public surface.
  - Module lifecycle (initialize/health_check/shutdown) + event publishing.

Run with:
    python3 -m pytest modules/agent_graph/tests -q
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent.parent))

from enterprise.modules.agent_graph import (  # noqa: E402
    END,
    START,
    AgentGraph,
    AgentGraphFacade,
    AgentGraphModule,
    GraphEdge,
    GraphNode,
    GraphRun,
    StateCheckpointStore,
    SupervisorGraph,
)
from enterprise.platform_kernel import EventBus, HealthStatus  # noqa: E402

# ---------------------------------------------------------------------------
# Node / edge primitives
# ---------------------------------------------------------------------------


def test_graph_node_invokes_fn_and_merges():
    node = GraphNode("inc", lambda s: {"count": s.get("count", 0) + 1})
    assert node.name == "inc"
    assert node({"count": 3}) == {"count": 4}
    assert node({}) == {"count": 1}


def test_graph_node_none_returns_empty_update():
    node = GraphNode("noop", lambda s: None)
    assert node({"a": 1}) == {}


def test_graph_node_non_dict_return_raises():
    node = GraphNode("bad", lambda s: 42)
    with pytest.raises(TypeError, match="expected dict"):
        node({"a": 1})


def test_graph_edge_repr():
    edge = GraphEdge("a", "b")
    assert edge.from_node == "a" and edge.to_node == "b"
    assert "a -> b" in repr(edge)
    cond_edge = GraphEdge("a", "c", condition=lambda s: True)
    assert "conditional" in repr(cond_edge)


# ---------------------------------------------------------------------------
# Build-time validation
# ---------------------------------------------------------------------------


def test_add_node_empty_name_raises():
    g = AgentGraph()
    with pytest.raises(ValueError, match="non-empty"):
        g.add_node("", lambda s: s)


def test_add_duplicate_node_raises():
    g = AgentGraph()
    g.add_node("a", lambda s: s)
    with pytest.raises(ValueError, match="already exists"):
        g.add_node("a", lambda s: s)


def test_edge_undefined_target_raises_valueerror():
    g = AgentGraph()
    g.add_node("a", lambda s: s)
    with pytest.raises(ValueError, match="undefined target"):
        g.add_edge("a", "missing")


def test_edge_undefined_source_raises_valueerror():
    g = AgentGraph()
    g.add_node("b", lambda s: s)
    with pytest.raises(ValueError, match="undefined source"):
        g.add_edge("missing", "b")


def test_edge_to_end_marker_allowed_without_node():
    g = AgentGraph()
    g.add_node("a", lambda s: s)
    edge = g.add_edge("a", END)
    assert edge.to_node == END


def test_edge_bad_condition_type_raises():
    g = AgentGraph()
    g.add_node("a", lambda s: s)
    with pytest.raises(TypeError, match="callable"):
        g.add_edge("a", END, condition="yes")


# ---------------------------------------------------------------------------
# Linear chain / topo order
# ---------------------------------------------------------------------------


def test_linear_chain_executes_in_order():
    g = AgentGraph()
    order: list[str] = []

    g.add_node("a", lambda s: order.append("a") or {"v": 1})
    g.add_node("b", lambda s: order.append("b") or {"v": 2})
    g.add_node("c", lambda s: order.append("c") or {"v": 3})
    g.add_edge("a", "b")
    g.add_edge("b", "c")

    run = g.run({})
    assert order == ["a", "b", "c"]
    assert run.final_state["v"] == 3
    assert run.path == ["a", "b", "c"]


def test_nodes_receive_and_merge_state():
    g = AgentGraph()
    g.add_node("a", lambda s: {"sum": s.get("sum", 0) + 2})
    g.add_node("b", lambda s: {"sum": s.get("sum", 0) + 3})
    g.add_edge("a", "b")
    run = g.run({"sum": 1})
    assert run.final_state["sum"] == 6


def test_run_does_not_mutate_caller_state():
    g = AgentGraph()
    g.add_node("a", lambda s: {"n": s.get("n", 0) + 1})
    source = {"n": 10}
    g.run(source)
    assert source == {"n": 10}


# ---------------------------------------------------------------------------
# Conditional branching
# ---------------------------------------------------------------------------


def test_conditional_branch_only_taken_path_runs():
    g = AgentGraph()
    seen: list[str] = []

    def decision(s):
        seen.append("decision")
        return {}

    g.add_node("decision", decision)
    g.add_node("left", lambda s: seen.append("left") or {"branch": "left"})
    g.add_node("right", lambda s: seen.append("right") or {"branch": "right"})
    g.add_edge("decision", "left", condition=lambda s: s.get("go_left") is True)
    g.add_edge("decision", "right", condition=lambda s: s.get("go_left") is not True)

    run = g.run({"go_left": True})
    assert seen == ["decision", "left"]
    assert run.final_state["branch"] == "left"
    assert "right" not in seen


def test_conditional_branch_takes_other_path():
    g = AgentGraph()
    seen: list[str] = []
    g.add_node("decision", lambda s: seen.append("decision") or {})
    g.add_node("left", lambda s: seen.append("left") or {"branch": "left"})
    g.add_node("right", lambda s: seen.append("right") or {"branch": "right"})
    g.add_edge("decision", "left", condition=lambda s: s.get("x") == "L")
    g.add_edge("decision", "right", condition=lambda s: s.get("x") == "R")
    run = g.run({"x": "R"})
    assert seen == ["decision", "right"]
    assert run.final_state["branch"] == "right"


def test_conditional_branch_no_match_terminates():
    g = AgentGraph()
    g.add_node("decision", lambda s: {})
    g.add_node("left", lambda s: {"branch": "left"})
    g.add_edge("decision", "left", condition=lambda s: s.get("go") == "yes")
    run = g.run({"go": "no"})
    assert run.path == ["decision"]
    assert "branch" not in run.final_state


def test_condition_result_must_be_bool():
    g = AgentGraph()
    g.add_node("a", lambda s: {})
    g.add_node("b", lambda s: {})
    g.add_edge("a", "b", condition=lambda s: "not a bool")
    with pytest.raises(TypeError, match="return a bool"):
        g.run({})


# ---------------------------------------------------------------------------
# Cycles / back-edges
# ---------------------------------------------------------------------------


def test_bounded_backedge_loop_executes_limited_times():
    g = AgentGraph(max_steps=100)
    g.add_node("begin", lambda s: {"n": s.get("n", 0)})
    g.add_node("counter", lambda s: {"n": s.get("n", 0) + 1})
    g.add_edge("begin", "counter")
    # Back-edge first, a conditional exit when n reaches the bound.
    g.add_edge("counter", "counter", condition=lambda s: s.get("n", 0) < 3)
    g.add_edge("counter", END, condition=lambda s: s.get("n", 0) >= 3)

    run = g.run({"n": 0})
    # 3 loop iterations then exit via the conditional edge -> END.
    assert run.final_state["n"] == 3
    assert run.path == ["begin", "counter", "counter", "counter"]


def test_unbounded_cycle_raises_runtime_error():
    g = AgentGraph(max_steps=5)
    g.add_node("a", lambda s: {})
    g.add_node("loop", lambda s: {})
    g.add_edge("a", "loop")
    g.add_edge("loop", "loop")
    with pytest.raises(RuntimeError, match="max_steps"):
        g.run({})


# ---------------------------------------------------------------------------
# START / END markers + entry-point resolution
# ---------------------------------------------------------------------------


def test_explicit_start_node_is_used():
    g = AgentGraph(start=START, end=END)
    g.add_node(START, lambda s: {"entered": True})
    g.add_node("work", lambda s: {"done": True})
    g.add_edge(START, "work")
    run = g.run({})
    assert run.path == [START, "work"]
    assert run.final_state["entered"] is True
    assert run.final_state["done"] is True


def test_implicit_single_root_is_used():
    g = AgentGraph()
    g.add_node("root", lambda s: {"r": 1})
    g.add_node("leaf", lambda s: {"l": 1})
    g.add_edge("root", "leaf")
    run = g.run({})
    assert run.path == ["root", "leaf"]


def test_no_entry_point_raises():
    g = AgentGraph()
    # Two nodes with no edges -> both are roots -> ambiguous.
    g.add_node("a", lambda s: {})
    g.add_node("b", lambda s: {})
    with pytest.raises(ValueError, match="multiple entry points"):
        g.run({})


def test_end_marker_terminates_without_executing():
    g = AgentGraph()
    g.add_node("a", lambda s: {"x": 1})
    g.add_edge("a", END)
    run = g.run({})
    assert run.final_state == {"x": 1}
    assert run.path == ["a"]


# ---------------------------------------------------------------------------
# Checkpoints
# ---------------------------------------------------------------------------


def test_checkpoint_saved_per_run():
    store = StateCheckpointStore()
    g = AgentGraph(store=store)
    g.add_node("a", lambda s: {"n": 1})
    g.add_edge("a", END)
    g.run({"seed": 0}, run_id="run-1")
    g.run({"seed": 9}, run_id="run-2")
    assert store.has("run-1")
    assert store.has("run-2")
    assert store.list_runs() == ["run-1", "run-2"]


def test_checkpoint_reload_returns_exact_final_state():
    g = AgentGraph()
    g.add_node("a", lambda s: {"v": s.get("v", 0) + 10})
    g.add_edge("a", END)
    run = g.run({"v": 5}, run_id="exact-1")
    history = g.store.load("exact-1")
    assert history[-1] == run.final_state
    assert history[-1]["v"] == 15


def test_checkpoint_reload_full_sequence():
    store = StateCheckpointStore()
    g = AgentGraph(store=store)
    g.add_node("a", lambda s: {"step": 1})
    g.add_node("b", lambda s: {"step": 2})
    g.add_edge("a", "b")
    run = g.run({}, run_id="seq-1")
    history = store.load("seq-1")
    # Initial + after-a + after-b
    assert len(history) == 3
    assert history[0] == {}
    assert history[1]["step"] == 1
    assert history[2]["step"] == 2
    assert list(run.checkpoints) == history


def test_load_missing_run_raises_keyerror():
    g = AgentGraph()
    with pytest.raises(KeyError, match="run-unknown"):
        g.store.load("run-unknown")


def test_store_save_load_and_clear():
    store = StateCheckpointStore()
    store.save("r1", {"a": 1})
    store.save("r1", {"a": 2})
    assert store.latest("r1") == {"a": 2}
    store.clear()
    assert store.list_runs() == []
    assert len(store) == 0


def test_checkpoint_states_are_deep_copied():
    store = StateCheckpointStore()
    nested = {"list": [1, 2, 3]}
    store.save("r", nested)
    nested["list"].append(4)
    assert store.load("r")[0]["list"] == [1, 2, 3]


def test_run_id_generated_when_omitted():
    g = AgentGraph()
    g.add_node("a", lambda s: {})
    r1 = g.run({})
    r2 = g.run({})
    assert r1.run_id != r2.run_id


def test_mode_passed_through():
    g = AgentGraph()
    g.add_node("a", lambda s: {})
    r = g.run({}, mode="reflect")
    assert r.mode == "reflect"
    assert isinstance(r, GraphRun)


# ---------------------------------------------------------------------------
# SupervisorGraph
# ---------------------------------------------------------------------------


def test_supervisor_routes_to_right_worker_by_state_key():
    sup = SupervisorGraph(route_key="task")
    sup.add_worker("translate", lambda s: {"output": "Translated"})
    sup.add_worker("summarize", lambda s: {"output": "Summarized"})

    run = sup.run({"task": "translate"})
    assert "translate" in run.path
    assert run.final_state["output"] == "Translated"
    assert "summarize" not in run.path


def test_supervisor_routes_to_different_workers():
    sup = SupervisorGraph(route_key="task")
    sup.add_worker("translate", lambda s: {"output": "T"})
    sup.add_worker("summarize", lambda s: {"output": "S"})
    run = sup.run({"task": "summarize"})
    assert run.final_state["output"] == "S"
    assert run.path == ["coordinator", "summarize"]


def test_supervisor_custom_route_value():
    sup = SupervisorGraph(route_key="kind")
    sup.add_worker("a", lambda s: {"r": "a"}, route="alpha")
    sup.add_worker("b", lambda s: {"r": "b"}, route="beta")
    run = sup.run({"kind": "beta"})
    assert run.final_state["r"] == "b"


def test_supervisor_duplicate_worker_raises():
    sup = SupervisorGraph()
    sup.add_worker("w", lambda s: {})
    with pytest.raises(ValueError, match="already exists"):
        sup.add_worker("w", lambda s: {})


def test_supervisor_workers_listing():
    sup = SupervisorGraph()
    sup.add_worker("a", lambda s: {})
    sup.add_worker("b", lambda s: {})
    assert set(sup.workers) == {"a", "b"}


# ---------------------------------------------------------------------------
# AgentGraphFacade
# ---------------------------------------------------------------------------


def test_facade_build_add_run():
    facade = AgentGraphFacade()
    g = facade.build_graph()
    g.add_node("tool", lambda s: {"result": s.get("q") * 2})
    g.add_edge("tool", END)
    run = facade.run_graph({"q": 21})
    assert run.final_state["result"] == 42


def test_facade_add_node_add_edge_delegation():
    facade = AgentGraphFacade()
    facade.build_graph()
    facade.add_node("x", lambda s: {"x": 1})
    facade.add_edge("x", END)
    run = facade.run_graph({})
    assert run.final_state["x"] == 1


def test_facade_get_checkpoint_and_list_runs():
    facade = AgentGraphFacade()
    g = facade.build_graph()
    g.add_node("a", lambda s: {"n": 7})
    g.add_edge("a", END)
    run = facade.run_graph({}, run_id="facade-1")
    assert facade.list_runs() == ["facade-1"]
    assert facade.get_checkpoint("facade-1")[-1] == run.final_state


def test_facade_requires_graph_before_ops():
    facade = AgentGraphFacade()
    with pytest.raises(RuntimeError, match="build_graph"):
        facade.add_node("a", lambda s: {})
    with pytest.raises(RuntimeError, match="build_graph"):
        facade.run_graph({})


def test_facade_clear_checkpoints():
    facade = AgentGraphFacade()
    g = facade.build_graph()
    g.add_node("a", lambda s: {})
    g.add_edge("a", END)
    facade.run_graph({}, run_id="r")
    assert facade.list_runs() == ["r"]
    facade.clear()
    assert facade.list_runs() == []


# ---------------------------------------------------------------------------
# Module lifecycle
# ---------------------------------------------------------------------------


class TestAgentGraphModule:
    async def test_initialize_healthy(self):
        mod = AgentGraphModule()
        await mod.initialize()
        assert mod.status is HealthStatus.HEALTHY
        assert mod.facade is not None
        assert mod.name == "agent_graph"
        assert mod.max_steps == 1000

    async def test_health_check(self):
        mod = AgentGraphModule()
        assert mod.status is HealthStatus.UNKNOWN
        await mod.initialize()
        assert await mod.health_check() is HealthStatus.HEALTHY

    async def test_shutdown(self):
        mod = AgentGraphModule()
        await mod.initialize()
        await mod.shutdown()
        assert mod.facade is None
        assert await mod.health_check() is HealthStatus.UNKNOWN

    async def test_operation_before_init_raises(self):
        mod = AgentGraphModule()
        with pytest.raises(RuntimeError, match="not initialized"):
            mod.run_graph({})

    async def test_module_run_facade(self):
        mod = AgentGraphModule()
        await mod.initialize()
        mod.build_graph()
        mod.add_node("a", lambda s: {"done": True})
        mod.add_edge("a", END)
        run = mod.run_graph({})
        assert run.final_state["done"] is True
        assert mod.list_runs() == [run.run_id]

    async def test_set_event_bus_emits_event(self):
        bus = EventBus(config={"async_dispatch": False})
        received: list[str] = []

        @bus.subscribe("agent_graph.run.completed")
        def _on_completed(event: Any) -> None:
            received.append(event.topic)

        mod = AgentGraphModule()
        mod.set_event_bus(bus)
        await mod.initialize()
        mod.build_graph()
        mod.add_node("a", lambda s: {"x": 1})
        mod.add_edge("a", END)
        mod.run_graph({})
        assert "agent_graph.run.completed" in received

    async def test_registered_with_platform(self):
        from enterprise.platform_kernel import _MODULE_REGISTRY

        assert "agent_graph" in _MODULE_REGISTRY
        cls = _MODULE_REGISTRY["agent_graph"]
        assert issubclass(cls, AgentGraphModule)
