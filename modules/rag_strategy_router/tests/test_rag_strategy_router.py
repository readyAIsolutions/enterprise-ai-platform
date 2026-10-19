"""Tests for the ``rag_strategy_router`` module.

Network-free, stdlib-only, deterministic. Async tests use plain ``async def``
(project pytest ``asyncio_mode = "auto"``). Every assertion is grounded in the
real transcript ``ColeMedin/p0FERNkpyHE.md`` decision rules:
  * single-entity / broad semantic fact lookup -> VECTOR
  * relationship / multi-entity -> GRAPH
  * explicit "use both" or balanced dual-intent -> HYBRID
"""
from __future__ import annotations

import pytest

from enterprise.platform_kernel import HealthStatus, _MODULE_REGISTRY
from enterprise.modules.rag_strategy_router import (
    QueryClassifier,
    RagStrategyRouterModule,
    RouteDecision,
    Signal,
    Strategy,
    StrategyRouter,
    all_strategies,
    create_rag_strategy_router_module,
    create_router,
    default_signals,
)


# =============================================================================
# Strategy enum
# =============================================================================


def test_strategy_members():
    assert {s.value for s in Strategy} == {"vector", "graph", "hybrid"}


def test_all_strategies_helper():
    assert all_strategies() == [Strategy.VECTOR, Strategy.GRAPH, Strategy.HYBRID]


def test_strategy_from_value_string():
    assert Strategy.from_value("graph") is Strategy.GRAPH
    assert Strategy.from_value("VECTOR") is Strategy.VECTOR
    assert Strategy.from_value(Strategy.HYBRID) is Strategy.HYBRID


def test_strategy_from_value_invalid():
    with pytest.raises(ValueError):
        Strategy.from_value("semantic-graph-quantum")


def test_strategy_str():
    assert str(Strategy.GRAPH) == "graph"


# =============================================================================
# Signals
# =============================================================================


def test_default_signals_nonempty_and_cover_all_strategies():
    sigs = default_signals()
    assert len(sigs) >= 10
    covered = {s.strategy for s in sigs}
    assert covered == {Strategy.VECTOR, Strategy.GRAPH, Strategy.HYBRID}


def test_default_signals_returns_fresh_list():
    assert default_signals() is not default_signals()


def test_signal_search_and_count():
    sig = next(s for s in default_signals() if s.name == "relationship_term")
    assert sig.search("what is the relationship here")
    assert not sig.search("tell me about google")
    assert sig.count("relationship and relationship") == 2


# =============================================================================
# Classifier — core routing decisions (transcript-grounded)
# =============================================================================


@pytest.fixture()
def clf():
    return QueryClassifier()


def test_relationship_query_routes_graph(clf):
    # transcript: "how are OpenAI and Microsoft related" -> knowledge graph
    d = clf.classify("How are OpenAI and Microsoft related?")
    assert d.strategy is Strategy.GRAPH


def test_relationship_between_two_companies_graph(clf):
    d = clf.classify("What is the relationship between Amazon and Anthropic?")
    assert d.strategy is Strategy.GRAPH


def test_how_connected_query_graph(clf):
    d = clf.classify("How are these companies connected together?")
    assert d.strategy is Strategy.GRAPH


def test_broad_semantic_single_entity_routes_vector(clf):
    # transcript: "what are the AI initiatives for Google" -> vector search
    d = clf.classify("What are the AI initiatives for Google?")
    assert d.strategy is Strategy.VECTOR


def test_tell_me_about_routes_vector(clf):
    d = clf.classify("Tell me about OpenAI's products.")
    assert d.strategy is Strategy.VECTOR


def test_lookup_info_routes_vector(clf):
    d = clf.classify("Find information on Microsoft.")
    assert d.strategy is Strategy.VECTOR


def test_explicit_use_both_routes_hybrid(clf):
    # transcript: "use both search types"
    d = clf.classify(
        "What are the initiatives for Microsoft? How does that relate to "
        "Anthropic? Use both search types."
    )
    assert d.strategy is Strategy.HYBRID


def test_both_sources_mentioned_hybrid(clf):
    d = clf.classify("Query both the vector database and the knowledge graph.")
    assert d.strategy is Strategy.HYBRID


def test_balanced_dual_intent_hybrid():
    # relationship term + fact-lookup term, balanced weights -> hybrid
    clf = QueryClassifier(hybrid_margin=0.5)
    d = clf.classify("What are the initiatives for Microsoft and how do they relate?")
    assert d.strategy is Strategy.HYBRID


# =============================================================================
# RouteDecision fields populated
# =============================================================================


def test_decision_confidence_in_range(clf):
    d = clf.classify("How are OpenAI and Microsoft related?")
    assert 0.0 <= d.confidence <= 1.0


def test_decision_matched_signals_populated(clf):
    d = clf.classify("How are OpenAI and Microsoft related?")
    assert d.matched_signals
    assert all(isinstance(n, str) for n in d.matched_signals)


def test_decision_rationale_populated(clf):
    d = clf.classify("Tell me about Google.")
    assert d.rationale
    assert "VECTOR" in d.rationale or "vector" in d.rationale


def test_decision_scores_has_all_strategies(clf):
    d = clf.classify("How are OpenAI and Microsoft related?")
    assert set(d.scores.keys()) == {Strategy.VECTOR, Strategy.GRAPH, Strategy.HYBRID}


def test_decision_query_preserved(clf):
    q = "How are OpenAI and Microsoft related?"
    assert clf.classify(q).query == q


def test_decision_as_dict(clf):
    d = clf.classify("How are OpenAI and Microsoft related?")
    dd = d.as_dict()
    assert dd["strategy"] == "graph"
    assert "confidence" in dd and "scores" in dd and "rationale" in dd
    assert set(dd["scores"].keys()) == {"vector", "graph", "hybrid"}


# =============================================================================
# Fallback + determinism
# =============================================================================


def test_no_signal_falls_back_to_default_vector(clf):
    d = clf.classify("xyzzy plugh frobnicate")
    assert d.strategy is Strategy.VECTOR
    assert d.confidence == 0.0
    assert d.matched_signals == []


def test_configurable_default_strategy():
    clf = QueryClassifier(default_strategy=Strategy.GRAPH)
    d = clf.classify("qwerty zxcv")
    assert d.strategy is Strategy.GRAPH


def test_classify_is_deterministic(clf):
    q = "How are OpenAI and Microsoft related?"
    a = clf.classify(q)
    b = clf.classify(q)
    assert a.strategy is b.strategy
    assert a.confidence == b.confidence
    assert a.matched_signals == b.matched_signals


def test_classify_rejects_nonstring(clf):
    with pytest.raises(TypeError):
        clf.classify(123)  # type: ignore[arg-type]


def test_signal_weight_override_shifts_decision():
    # Boost the generic vector fact-lookup words so a relationship-ish query
    # instead leans hybrid/vector; verify weights are actually applied.
    base = QueryClassifier()
    sig = next(s for s in base.signals if s.name == "single_fact_wh")
    assert base.effective_weight(sig) == sig.weight
    boosted = QueryClassifier(weights={"single_fact_wh": 5.0})
    assert boosted.effective_weight(
        next(s for s in boosted.signals if s.name == "single_fact_wh")
    ) == sig.weight * 5.0


# =============================================================================
# StrategyRouter route / route_batch
# =============================================================================


@pytest.fixture()
def router():
    return StrategyRouter()


def test_router_route_returns_decision(router):
    d = router.route("Tell me about Google.")
    assert isinstance(d, RouteDecision)
    assert d.strategy is Strategy.VECTOR


def test_router_route_batch(router):
    queries = [
        "What are the AI initiatives for Google?",          # vector
        "How are OpenAI and Microsoft related?",            # graph
        "Use both search types for Microsoft and Anthropic.",  # hybrid
    ]
    out = router.route_batch(queries)
    assert [d.strategy for d in out] == [
        Strategy.VECTOR,
        Strategy.GRAPH,
        Strategy.HYBRID,
    ]


def test_router_route_batch_preserves_length(router):
    assert len(router.route_batch(["a", "b", "c", "d"])) == 4


def test_create_router_factory():
    r = create_router()
    assert isinstance(r, StrategyRouter)


def test_router_weight_merge_into_existing_classifier():
    clf = QueryClassifier()
    r = StrategyRouter(classifier=clf, weights={"relationship_term": 2.0})
    sig = next(s for s in r.classifier.signals if s.name == "relationship_term")
    assert r.classifier.effective_weight(sig) == sig.weight * 2.0


# =============================================================================
# Dispatch — injected retriever called for chosen strategy
# =============================================================================


def test_dispatch_calls_injected_retriever_for_vector(router):
    calls = {}

    def vector_retriever(q):
        calls["vector"] = q
        return ["chunk-1", "chunk-2"]

    out = router.dispatch(
        "What are the AI initiatives for Google?",
        retrievers={Strategy.VECTOR: vector_retriever},
    )
    assert out["strategy"] == "vector"
    assert calls["vector"].startswith("What are the AI initiatives")
    assert out["result"] == ["chunk-1", "chunk-2"]


def test_dispatch_calls_graph_retriever(router):
    seen = []

    def graph_retriever(q):
        seen.append(q)
        return {"path": "OpenAI --partnered_with--> Microsoft"}

    out = router.dispatch(
        "How are OpenAI and Microsoft related?",
        retrievers={Strategy.GRAPH: graph_retriever},
    )
    assert out["strategy"] == "graph"
    assert seen and "result" in out
    assert out["result"]["path"].startswith("OpenAI")


def test_dispatch_selects_correct_retriever_among_many(router):
    def vec(q):
        return "V"

    def gra(q):
        return "G"

    def hyb(q):
        return "H"

    retrievers = {
        Strategy.VECTOR: vec,
        Strategy.GRAPH: gra,
        Strategy.HYBRID: hyb,
    }
    assert router.dispatch("Tell me about Google.", retrievers=retrievers)["result"] == "V"
    assert router.dispatch(
        "How are A and B related?", retrievers=retrievers
    )["result"] == "G"
    assert router.dispatch(
        "Use both search types.", retrievers=retrievers
    )["result"] == "H"


def test_dispatch_uses_registered_retriever(router):
    router.register_retriever(Strategy.VECTOR, lambda q: "registered")
    out = router.dispatch("Tell me about Google.")
    assert out["result"] == "registered"


def test_dispatch_inline_overrides_registered(router):
    router.register_retriever(Strategy.VECTOR, lambda q: "registered")
    out = router.dispatch(
        "Tell me about Google.", retrievers={Strategy.VECTOR: lambda q: "inline"}
    )
    assert out["result"] == "inline"


def test_dispatch_missing_retriever_raises(router):
    with pytest.raises(KeyError):
        router.dispatch("Tell me about Google.")


def test_dispatch_result_includes_decision_fields(router):
    out = router.dispatch(
        "How are OpenAI and Microsoft related?",
        retrievers={Strategy.GRAPH: lambda q: 1},
    )
    for key in ("query", "strategy", "confidence", "matched_signals", "rationale", "result"):
        assert key in out


def test_register_retriever_string_key(router):
    router.register_retriever("vector", lambda q: "ok")
    assert Strategy.VECTOR in router.registered_strategies()


def test_register_retriever_rejects_noncallable(router):
    with pytest.raises(TypeError):
        router.register_retriever(Strategy.VECTOR, "not-callable")


def test_unregister_retriever(router):
    router.register_retriever(Strategy.VECTOR, lambda q: "ok")
    router.unregister_retriever(Strategy.VECTOR)
    assert Strategy.VECTOR not in router.registered_strategies()


# =============================================================================
# Module lifecycle (async -> asyncio_mode="auto")
# =============================================================================


def test_module_registered_in_registry():
    assert "rag_strategy_router" in _MODULE_REGISTRY


def test_factory_creates_module():
    m = create_rag_strategy_router_module()
    assert isinstance(m, RagStrategyRouterModule)
    assert m.name == "rag_strategy_router"
    assert m.version == "1.0.0"


async def test_health_check_unhealthy_before_initialize():
    m = create_rag_strategy_router_module()
    assert await m.health_check() is HealthStatus.UNHEALTHY


async def test_initialize_sets_healthy():
    m = create_rag_strategy_router_module()
    await m.initialize()
    assert m.status is HealthStatus.HEALTHY
    assert await m.health_check() is HealthStatus.HEALTHY


async def test_module_route_facade():
    m = create_rag_strategy_router_module()
    await m.initialize()
    d = m.route("How are OpenAI and Microsoft related?")
    assert d.strategy is Strategy.GRAPH


async def test_module_route_batch_facade():
    m = create_rag_strategy_router_module()
    await m.initialize()
    out = m.route_batch(["Tell me about Google.", "How are A and B related?"])
    assert [d.strategy for d in out] == [Strategy.VECTOR, Strategy.GRAPH]


async def test_module_dispatch_facade():
    m = create_rag_strategy_router_module()
    await m.initialize()
    out = m.dispatch(
        "Tell me about Google.", retrievers={Strategy.VECTOR: lambda q: "r"}
    )
    assert out["result"] == "r"


async def test_module_register_retriever_facade():
    m = create_rag_strategy_router_module()
    await m.initialize()
    m.register_retriever(Strategy.GRAPH, lambda q: "graph-result")
    out = m.dispatch("How are A and B related?")
    assert out["result"] == "graph-result"


async def test_module_config_default_strategy():
    m = create_rag_strategy_router_module({"default_strategy": "graph"})
    await m.initialize()
    d = m.route("qwerty zxcv nonsense")
    assert d.strategy is Strategy.GRAPH


async def test_module_set_event_bus():
    m = create_rag_strategy_router_module()
    sentinel = object()
    m.set_event_bus(sentinel)
    assert m._event_bus is sentinel


async def test_module_shutdown():
    m = create_rag_strategy_router_module()
    await m.initialize()
    await m.shutdown()
    assert m.router is None
    assert await m.health_check() is HealthStatus.UNHEALTHY


async def test_module_strategies_facade():
    m = create_rag_strategy_router_module()
    await m.initialize()
    assert m.strategies() == [Strategy.VECTOR, Strategy.GRAPH, Strategy.HYBRID]
