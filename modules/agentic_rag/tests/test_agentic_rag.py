"""Unit tests for the agentic_rag module (network-free, deterministic).

Coverage of the transcript's core concepts:
  * query decomposition / agentic planning (vector vs graph vs combined),
  * multi-hop knowledge-graph traversal,
  * retrieval + reranking of candidate chunks.
"""
from __future__ import annotations

from pathlib import Path

from enterprise.modules.agentic_rag import (
    AgenticRag,
    Chunk,
    KnowledgeGraph,
    VectorStore,
    create_agentic_rag_module,
    make_agentic_rag,
)
from enterprise.modules.agentic_rag.agentic_rag import (
    STRATEGY_COMBINED,
    STRATEGY_GRAPH,
    STRATEGY_VECTOR,
    rerank,
)


# ---------------------------------------------------------------------------
# Query decomposition / agentic planning
# ---------------------------------------------------------------------------


def test_single_entity_query_uses_vector_store():
    rag = make_agentic_rag()
    plan = rag.decompose_query("What are the AI initiatives for Google?")
    assert plan["entities"] == ["Google"]
    assert plan["strategy"] == STRATEGY_VECTOR
    assert len(plan["sub_steps"]) >= 3


def test_relational_two_entity_query_uses_graph():
    rag = make_agentic_rag()
    plan = rag.decompose_query("How are OpenAI and Microsoft related?")
    assert set(plan["entities"]) == {"OpenAI", "Microsoft"}
    assert plan["strategy"] == STRATEGY_GRAPH


def test_combined_strategy_when_both_cues_present():
    rag = make_agentic_rag()
    plan = rag.decompose_query(
        "What are the AI initiatives for Microsoft and Amazon? use both search types"
    )
    assert plan["strategy"] == STRATEGY_COMBINED
    assert len(plan["entities"]) >= 2


def test_graph_is_case_insensitive_for_entity_detection():
    g = KnowledgeGraph()
    g.add_node("Anthropic")
    assert g.find_entities("how does anthropic compare") == ["Anthropic"]


# ---------------------------------------------------------------------------
# Multi-hop knowledge-graph traversal
# ---------------------------------------------------------------------------


def test_shortest_path_multihop():
    # Amazon -> Anthropic -> AWS is a two-hop chain from the transcript demo.
    rag = make_agentic_rag()
    path = rag.traverse("Amazon", "AWS")
    assert [e["relation"] for e in path] == ["invested_in", "runs_on"]
    assert [e["source"] for e in path] == ["Amazon", "Anthropic"]


def test_shortest_path_microsoft_openai_azure():
    rag = make_agentic_rag()
    path = rag.traverse("Microsoft", "Azure")
    assert [e["target"] for e in path] == ["OpenAI", "Azure"]


def test_no_path_returns_empty():
    rag = make_agentic_rag()
    path = rag.traverse("Google", "Azure")
    assert path == []


def test_shortest_path_honors_max_hops():
    g = KnowledgeGraph()
    g.add_edge("a", "b", "rel")
    g.add_edge("b", "c", "rel")
    g.add_edge("c", "d", "rel")
    assert len(g.shortest_path("a", "d", max_hops=2)) == 0
    assert len(g.shortest_path("a", "d", max_hops=3)) == 3


def test_connected_edges_collects_reachable_subgraph():
    rag = make_agentic_rag()
    edges = rag.graph.connected_edges(["Microsoft"], max_hops=2)
    rels = {(e["source"], e["relation"], e["target"]) for e in edges}
    assert ("Microsoft", "partnered_with", "OpenAI") in rels
    assert ("OpenAI", "hosted_on", "Azure") in rels


# ---------------------------------------------------------------------------
# Retrieval + reranking
# ---------------------------------------------------------------------------


def test_retrieve_returns_relevant_chunks():
    rag = make_agentic_rag()
    results = rag.retrieve("Google AI initiatives", k=2)
    assert len(results) == 2
    assert results[0]["id"] == "c3"  # the Google chunk ranks first


def test_rerank_ranks_entity_coverage_higher():
    rag = make_agentic_rag()
    ranked = rag.rerank("OpenAI and Microsoft", top_k=4)
    # The chunk mentioning both relational entities should lead.
    assert ranked[0]["chunk"]["id"] == "c1"
    assert ranked[0]["entity_coverage"] > 0


def test_rerank_empty_detected_entities_falls_back_to_lexical():
    store = VectorStore()
    store.add(Chunk("a", "The cat sat on the mat", source="s"))
    store.add(Chunk("b", "A dog barked loudly at night", source="s"))
    ranked = rerank(store.chunks, "cat mat", entities=[], top_k=2)
    assert ranked[0]["chunk"]["id"] == "a"
    assert ranked[0]["score"] > ranked[1]["score"]


def test_rerank_returns_top_k_only():
    rag = make_agentic_rag()
    ranked = rag.rerank("Microsoft initiatives", top_k=2)
    assert len(ranked) == 2


# ---------------------------------------------------------------------------
# Full agentic answer pipeline
# ---------------------------------------------------------------------------


def test_answer_factual_strategy():
    rag = make_agentic_rag()
    result = rag.answer("What are Google's initiatives?")
    assert result["plan"]["strategy"] == STRATEGY_VECTOR
    assert result["evidence"] and "answer" in result


def test_answer_relational_strategy_uses_graph_path():
    rag = make_agentic_rag()
    result = rag.answer("How are OpenAI and Microsoft related?")
    assert result["plan"]["strategy"] == STRATEGY_GRAPH
    assert result["graph_path"], "expected a multi-hop graph path"
    assert "hosted_on" in {e["relation"] for e in result["graph_edges"]}


def test_answer_combined_strategy_has_evidence_and_path():
    rag = make_agentic_rag()
    result = rag.answer(
        "What are the initiatives for Microsoft and Anthropic? use both search types")
    assert result["plan"]["strategy"] == STRATEGY_COMBINED
    assert result["evidence"] and result["graph_edges"]


# ---------------------------------------------------------------------------
# Platform Module wrapper
# ---------------------------------------------------------------------------


async def test_module_initialize_health_shutdown():
    m = create_agentic_rag_module({})
    await m.initialize()
    assert m.engine is not None
    status = await m.health_check()
    assert status.value == "healthy"

    result = m.answer("How are OpenAI and Microsoft related?")
    assert result["graph_path"]

    info = m.graph_info()
    assert info["num_nodes"] == 8
    assert info["num_edges"] == 5

    await m.shutdown()
    assert (await m.health_check()).value == "unhealthy"


async def test_module_facade_returns_dicts():
    m = create_agentic_rag_module({})
    await m.initialize()
    plan = m.decompose("What are Google's AI initiatives?")
    assert plan["strategy"] == STRATEGY_VECTOR
    ranked = m.rerank("OpenAI and Microsoft", top_k=2)
    assert len(ranked) == 2
    await m.shutdown()


# ---------------------------------------------------------------------------
# tmp_path file IO (sanity: no network, works with a filesystem scratch dir)
# ---------------------------------------------------------------------------


async def test_engine_writes_and_reads_a_plan_to_tmp_path(tmp_path: Path):
    rag = make_agentic_rag()
    plan = rag.decompose_query("How are OpenAI and Microsoft related?")
    out = tmp_path / "plan.json"
    out.write_text(str(plan))
    assert out.exists()
    assert "knowledge_graph" in out.read_text()
