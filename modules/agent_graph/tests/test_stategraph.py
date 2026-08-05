"""Tests for the durable, resumable state-graph DSL added to agent_graph.

Covers the LangGraph-style :class:`StateGraph` / :class:`DiGraphBuilder` with
SQLite checkpointing and conditional edges:

  - builder topological ordering over static edges
  - conditional edges following a runtime router
  - cycle protection via max_steps
  - checkpoint persistence across a store re-open
  - resume() replaying from the last checkpoint, skipping completed nodes
  - supervisor fan-out to subgraphs and callable workers
  - error cases (missing node / edge / ambiguous entry / bad router target)

Run with:
    python3 -m pytest modules/agent_graph -q
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent.parent))

from enterprise.modules.agent_graph import (  # noqa: E402
    END,
    START,
    DiGraphBuilder,
    SqliteCheckpointStore,
    StateGraph,
    StateGraphRun,
)

# ---------------------------------------------------------------------------
# Builder + topological order
# ---------------------------------------------------------------------------


def test_digraph_builder_is_stategraph_alias() -> None:
    assert DiGraphBuilder is StateGraph


def test_builder_linear_chain_topological_order() -> None:
    g = StateGraph(db_path=None)
    g.add_node("a", lambda _s: {"n": 1})
    g.add_node("b", lambda _s: {"n": 2})
    g.add_node("c", lambda _s: {"n": 3})
    g.add_edge("a", "b")
    g.add_edge("b", "c")
    assert g.topological_order() == ["a", "b", "c"]


def test_builder_run_executes_in_topo_order_and_merges_state() -> None:
    g = StateGraph(db_path=None)
    order: list[str] = []
    g.add_node("a", lambda s: order.append("a") or {"sum": s.get("sum", 0) + 2})
    g.add_node("b", lambda s: order.append("b") or {"sum": s.get("sum", 0) + 3})
    g.add_edge("a", "b")
    run = g.run({"sum": 1})
    assert order == ["a", "b"]
    assert run.final_state["sum"] == 6
    assert isinstance(run, StateGraphRun)


def test_builder_add_node_returns_self_for_chaining() -> None:
    g = StateGraph(db_path=None)
    ret = g.add_node("a", lambda _s: {}).add_node("b", lambda _s: {}).add_edge("a", "b")
    assert ret is g
    assert g.nodes == ["a", "b"]


def test_builder_diamond_topological_order() -> None:
    g = StateGraph(db_path=None)
    g.add_node("a", lambda _s: {})
    g.add_node("b", lambda _s: {})
    g.add_node("c", lambda _s: {})
    g.add_node("d", lambda _s: {})
    g.add_edge("a", "b")
    g.add_edge("a", "c")
    g.add_edge("b", "d")
    g.add_edge("c", "d")
    topo = g.topological_order()
    assert topo.index("a") < topo.index("b")
    assert topo.index("a") < topo.index("c")
    assert topo.index("b") < topo.index("d")
    assert topo.index("c") < topo.index("d")


# ---------------------------------------------------------------------------
# Conditional edges
# ---------------------------------------------------------------------------


def test_conditional_edge_follows_router() -> None:
    g = StateGraph(db_path=None)
    g.add_node(START, lambda _s: {})
    g.add_node("decide", lambda _s: {})
    g.add_node("left", lambda _s: {"branch": "L"})
    g.add_node("right", lambda _s: {"branch": "R"})
    g.add_edge(START, "decide")
    g.add_conditional_edge("decide", lambda s: "left" if s.get("go") else "right")
    g.add_edge("left", END)
    g.add_edge("right", END)
    run = g.run({"go": True})
    assert "left" in run.path
    assert "right" not in run.path
    assert run.final_state["branch"] == "L"


def test_conditional_edge_routes_to_other_branch() -> None:
    g = StateGraph(db_path=None)
    g.add_node("decide", lambda _s: {})
    g.add_node("left", lambda _s: {"branch": "L"})
    g.add_node("right", lambda _s: {"branch": "R"})
    g.add_conditional_edge("decide", lambda _s: "right")
    g.add_edge("left", END)
    g.add_edge("right", END)
    run = g.run({})
    assert run.path == ["decide", "right"]
    assert run.final_state["branch"] == "R"


def test_conditional_edge_routing_to_end_terminates() -> None:
    g = StateGraph(db_path=None)
    g.add_node("a", lambda _s: {"done": True})
    g.add_conditional_edge("a", lambda _s: END)
    run = g.run({})
    assert run.path == ["a"]
    assert run.final_state["done"] is True


def test_conditional_edge_router_undefined_target_raises() -> None:
    g = StateGraph(db_path=None)
    g.add_node("a", lambda _s: {})
    g.add_conditional_edge("a", lambda _s: "missing")
    with pytest.raises(ValueError, match="undefined node 'missing'"):
        g.run({})


# ---------------------------------------------------------------------------
# Cycles
# ---------------------------------------------------------------------------


def test_cycle_guarded_by_max_steps() -> None:
    g = StateGraph(db_path=None, max_steps=6)
    g.add_node("loop", lambda _s: {})
    g.add_conditional_edge("loop", lambda _s: "loop")  # unconditional self-loop
    with pytest.raises(RuntimeError, match="max_steps"):
        g.run({})


def test_bounded_loop_via_conditional_router_exits() -> None:
    g = StateGraph(db_path=None)
    g.add_node("begin", lambda s: {"n": s.get("n", 0)})
    g.add_node("counter", lambda s: {"n": s.get("n", 0) + 1})
    g.add_edge("begin", "counter")
    g.add_conditional_edge("counter", lambda s: "counter" if s["n"] < 3 else END)
    run = g.run({"n": 0})
    assert run.final_state["n"] == 3
    assert run.path == ["begin", "counter", "counter", "counter"]


# ---------------------------------------------------------------------------
# Checkpoint persistence
# ---------------------------------------------------------------------------


def test_checkpoint_snapshotted_after_each_node() -> None:
    g = StateGraph(db_path=None)
    g.add_node("a", lambda _s: {"step": 1})
    g.add_node("b", lambda _s: {"step": 2})
    g.add_edge("a", "b")
    g.run({}, run_id="seq")
    frames = g.store.load("seq")
    # initial + after-a + after-b
    assert len(frames) == 3
    assert frames[0] == {}
    assert frames[1]["step"] == 1
    assert frames[2]["step"] == 2
    assert g.store.completed_nodes("seq") == ["a", "b"]


def test_checkpoint_persists_across_store_reopen(tmp_path: Path) -> None:
    db = tmp_path / "state.db"
    store1 = SqliteCheckpointStore(db_path=db)
    g = StateGraph(checkpoint_store=store1)
    g.add_node("a", lambda s: {"n": s.get("n", 0) + 10})
    g.add_edge("a", END)
    g.run({"n": 5}, run_id="persist-1")
    store1.close()

    store2 = SqliteCheckpointStore(db_path=db)
    assert store2.has("persist-1")
    assert store2.load("persist-1")[-1]["n"] == 15
    assert store2.completed_nodes("persist-1") == ["a"]
    assert "persist-1" in store2.list_runs()
    store2.close()


def test_in_memory_store_isolation() -> None:
    s1 = SqliteCheckpointStore(db_path=None)
    s2 = SqliteCheckpointStore(db_path=None)
    s1.save_initial("r", {"x": 1})
    assert s1.has("r")
    assert not s2.has("r")


# ---------------------------------------------------------------------------
# Resume
# ---------------------------------------------------------------------------


def test_resume_replays_from_last_checkpoint_skipping_completed() -> None:
    g = StateGraph(db_path=None)
    counts = {"a": 0, "b": 0}

    def node_a(_s: dict[str, object]) -> dict[str, object]:
        counts["a"] += 1
        return {"a": "done"}

    def node_b(_s: dict[str, object]) -> dict[str, object]:
        counts["b"] += 1
        if counts["b"] == 1:
            msg = "transient b failure"
            raise RuntimeError(msg)
        return {"b": "ok"}

    g.add_node("a", node_a)
    g.add_node("b", node_b)
    g.add_node("c", lambda _s: {"c": 1})
    g.add_edge("a", "b")
    g.add_edge("b", "c")
    g.add_edge("c", END)

    with pytest.raises(RuntimeError, match="transient"):
        g.run({"seed": 0}, run_id="res-1")

    # 'a' completed (skipped on resume); 'b' failed so must be re-run.
    assert g.store.completed_nodes("res-1") == ["a"]
    assert counts == {"a": 1, "b": 1}

    run = g.resume("res-1")
    assert run.resumed is True
    assert counts == {"a": 1, "b": 2}  # a skipped, b re-run, c run once
    assert run.path == ["b", "c"]
    assert run.all_path == ["a", "b", "c"]
    assert run.final_state["c"] == 1
    assert run.status == "complete"


def test_resume_completed_run_is_noop_and_skips_nodes() -> None:
    g = StateGraph(db_path=None)
    runs = {"a": 0, "b": 0}
    g.add_node("a", lambda _s: runs.__setitem__("a", runs["a"] + 1) or {})
    g.add_node("b", lambda _s: runs.__setitem__("b", runs["b"] + 1) or {})
    g.add_edge("a", "b")
    g.add_edge("b", END)
    first = g.run({}, run_id="done-1")
    assert first.status == "complete"
    assert runs == {"a": 1, "b": 1}

    resumed = g.resume("done-1")
    assert resumed.resumed is True
    assert resumed.path == []
    assert runs == {"a": 1, "b": 1}  # nothing re-executed


def test_resume_missing_run_raises_keyerror() -> None:
    g = StateGraph(db_path=None)
    with pytest.raises(KeyError, match="nope"):
        g.resume("nope")


def test_resume_across_store_reopen(tmp_path: Path) -> None:
    db = tmp_path / "dur.db"
    store1 = SqliteCheckpointStore(db_path=db)
    counts = {"b": 0}

    def node_b(_s: dict[str, object]) -> dict[str, object]:
        counts["b"] += 1
        if counts["b"] == 1:
            msg = "boom"
            raise RuntimeError(msg)
        return {"b": "done"}

    g1 = StateGraph(checkpoint_store=store1)
    g1.add_node("a", lambda _s: {"a": 1})
    g1.add_node("b", node_b)
    g1.add_node("c", lambda _s: {"c": 1})
    g1.add_edge("a", "b")
    g1.add_edge("b", "c")
    g1.add_edge("c", END)
    with pytest.raises(RuntimeError, match="boom"):
        g1.run({}, run_id="dur-1")
    store1.close()

    # Reopen the DB and resume the durable run from the new process.
    store2 = SqliteCheckpointStore(db_path=db)
    g2 = StateGraph(checkpoint_store=store2)
    g2.add_node("a", lambda _s: {"a": 1})
    g2.add_node("b", node_b)
    g2.add_node("c", lambda _s: {"c": 1})
    g2.add_edge("a", "b")
    g2.add_edge("b", "c")
    g2.add_edge("c", END)
    run = g2.resume("dur-1")
    assert run.resumed is True
    assert run.final_state["c"] == 1
    assert run.final_state["b"] == "done"
    assert g2.store.status("dur-1") == "complete"
    store2.close()


# ---------------------------------------------------------------------------
# Supervisor fan-out
# ---------------------------------------------------------------------------


def test_supervisor_fans_out_to_subgraph() -> None:
    sub = StateGraph(name="math_sub", db_path=None)
    sub.add_node("subwork", lambda s: {"sub_result": s.get("val", 0) * 2})
    sub.add_edge("subwork", END)

    parent = StateGraph(db_path=None)
    parent.add_node("pre", lambda _s: {"val": 21})
    parent.add_supervisor("supervisor", route_key="kind", workers={"math": sub})
    parent.add_edge("pre", "supervisor")
    parent.add_edge("supervisor", END)

    run = parent.run({"kind": "math"})
    assert run.final_state["val"] == 21
    assert run.final_state["sub_result"] == 42


def test_supervisor_fans_out_to_callable_worker() -> None:
    parent = StateGraph(db_path=None)
    parent.add_node("pre", lambda _s: {"x": 1})
    parent.add_supervisor(
        "supervisor",
        route_key="service",
        workers={"double": lambda s: {"out": s.get("x", 0) * 2}},
    )
    parent.add_edge("pre", "supervisor")
    parent.add_edge("supervisor", END)
    run = parent.run({"service": "double"})
    assert run.final_state["out"] == 2


def test_supervisor_missing_route_raises_keyerror() -> None:
    parent = StateGraph(db_path=None)
    parent.add_supervisor("supervisor", route_key="service", workers={"a": lambda _s: {}})
    parent.add_edge("supervisor", END)
    with pytest.raises(KeyError, match="no worker"):
        parent.run({"service": "b"})


# ---------------------------------------------------------------------------
# Error cases
# ---------------------------------------------------------------------------


def test_add_duplicate_node_raises() -> None:
    g = StateGraph(db_path=None)
    g.add_node("a", lambda _s: {})
    with pytest.raises(ValueError, match="already exists"):
        g.add_node("a", lambda _s: {})


def test_add_edge_missing_source_raises() -> None:
    g = StateGraph(db_path=None)
    g.add_node("b", lambda _s: {})
    with pytest.raises(ValueError, match="undefined node 'missing'"):
        g.add_edge("missing", "b")


def test_add_edge_missing_target_raises() -> None:
    g = StateGraph(db_path=None)
    g.add_node("a", lambda _s: {})
    with pytest.raises(ValueError, match="undefined node 'nope'"):
        g.add_edge("a", "nope")


def test_add_conditional_edge_on_static_node_raises() -> None:
    g = StateGraph(db_path=None)
    g.add_node("a", lambda _s: {})
    g.add_node("b", lambda _s: {})
    g.add_edge("a", "b")
    with pytest.raises(ValueError, match="already has a static edge"):
        g.add_conditional_edge("a", lambda _s: "b")


def test_node_returning_non_dict_raises() -> None:
    g = StateGraph(db_path=None)
    g.add_node("bad", lambda _s: 42)
    with pytest.raises(TypeError, match="expected dict"):
        g.run({})


def test_multiple_entry_points_raise() -> None:
    g = StateGraph(db_path=None)
    g.add_node("a", lambda _s: {})
    g.add_node("b", lambda _s: {})
    with pytest.raises(ValueError, match="multiple entry points"):
        g.run({})
