"""Deterministic, network-free tests for the agentic RAG planner."""

from __future__ import annotations

import asyncio

from enterprise.modules.agentic_rag_planner import (
    AgenticRagPlannerModule,
    GRAPH,
    HYBRID,
    InMemoryTool,
    PlanExecutor,
    QueryClassifier,
    RagPlanner,
    VECTOR,
    create_agentic_rag_planner_module,
)
from enterprise.platform_kernel import HealthStatus


# --------------------------------------------------------------------- routing
def test_relationship_query_routes_to_graph() -> None:
    planner = RagPlanner()
    plan = planner.plan("How is Google connected to OpenAI?")
    assert plan.strategy is GRAPH
    assert plan.tools == [GRAPH]
    assert len(plan.steps) == 1


def test_conceptual_query_routes_to_vector() -> None:
    planner = RagPlanner()
    plan = planner.plan("Explain how transformers work")
    assert plan.strategy is VECTOR
    assert plan.tools == [VECTOR]


def test_mixed_query_yields_hybrid_with_both_steps() -> None:
    planner = RagPlanner()
    # "what is" (conceptual/vector) + "relationship between" (graph)
    plan = planner.plan(
        "What is the relationship between OpenAI and Microsoft and explain it?"
    )
    assert plan.strategy is HYBRID
    assert plan.is_hybrid()
    assert VECTOR in plan.tools
    assert GRAPH in plan.tools
    # VECTOR comes before GRAPH in a hybrid plan.
    assert plan.tools.index(VECTOR) < plan.tools.index(GRAPH)


def test_rationale_is_non_empty() -> None:
    planner = RagPlanner()
    for q in [
        "How is X connected to Y?",
        "Explain how transformers work",
        "What is the relationship between A and B, explain it",
    ]:
        assert planner.plan(q).rationale.strip()


def test_classifier_temporal_signal_routes_graph() -> None:
    clf = QueryClassifier()
    result = clf.classify("How did the pricing change over time?")
    assert result.strategy is GRAPH
    assert result.graph_score > 0


# ------------------------------------------------------------------- executor
def test_executor_merges_and_dedups_in_plan_order() -> None:
    vector_tool = InMemoryTool(VECTOR, [{"id": "a", "src": "v"}, {"id": "b", "src": "v"}])
    graph_tool = InMemoryTool(GRAPH, [{"id": "b", "src": "g"}, {"id": "c", "src": "g"}])
    executor = PlanExecutor({VECTOR: vector_tool, GRAPH: graph_tool})

    planner = RagPlanner()
    plan = planner.plan(
        "What is the relationship between A and B, explain the connection?"
    )
    assert plan.is_hybrid()

    merged = executor.execute(plan)
    ids = [r["id"] for r in merged]
    # dedup on 'id', first-seen order: vector step (a,b) then graph step (c).
    assert ids == ["a", "b", "c"]
    # 'b' kept its first-seen (vector) source.
    assert next(r for r in merged if r["id"] == "b")["src"] == "v"


# ------------------------------------------------------------------ refinement
def test_refinement_adds_fallback_when_tool_returns_empty() -> None:
    planner = RagPlanner()
    base = planner.plan("Explain how transformers work")  # single VECTOR step
    assert base.tools == [VECTOR]

    # Simulate the vector step returning zero results.
    refined = planner.plan_multi("Explain how transformers work", prior_result_counts=[0])
    assert GRAPH in refined.tools
    assert len(refined.steps) == len(base.steps) + 1
    assert refined.steps[-1].tool is GRAPH
    assert "fall back" in refined.steps[-1].reason.lower()


def test_refinement_no_fallback_when_results_present() -> None:
    planner = RagPlanner()
    refined = planner.plan_multi("Explain how transformers work", prior_result_counts=[5])
    assert refined.tools == [VECTOR]


def test_executor_counts_drive_refinement() -> None:
    empty_vector = InMemoryTool(VECTOR, [])
    graph_tool = InMemoryTool(GRAPH, [{"id": "z"}])
    executor = PlanExecutor({VECTOR: empty_vector, GRAPH: graph_tool})

    planner = RagPlanner()
    base = planner.plan("Explain how attention works")
    counts = executor.execute_counts(base)
    assert counts == [0]
    refined = planner.plan_multi("Explain how attention works", prior_result_counts=counts)
    merged = executor.execute(refined)
    assert [r["id"] for r in merged] == ["z"]


# --------------------------------------------------------------------- module
def test_module_lifecycle() -> None:
    mod = create_agentic_rag_planner_module()
    assert isinstance(mod, AgenticRagPlannerModule)

    asyncio.run(mod.initialize())
    status = asyncio.run(mod.health_check())
    assert status is HealthStatus.HEALTHY

    plan = mod.plan("How is X connected to Y?")
    assert plan.strategy is GRAPH

    asyncio.run(mod.shutdown())
    assert mod.status is HealthStatus.STOPPING


def test_module_metadata() -> None:
    mod = create_agentic_rag_planner_module()
    assert mod.name == "agentic_rag_planner"
    assert mod.version == "1.0.0"
