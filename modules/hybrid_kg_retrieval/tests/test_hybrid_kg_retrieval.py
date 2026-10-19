"""Tests for the hybrid_kg_retrieval module (agentic vector + KG, local)."""
from __future__ import annotations

from pathlib import Path

import pytest

# Ensure the enterprise package root (two levels above the repo) is importable.
import sys

_REPO = Path(__file__).resolve().parents[3]          # .../Enterprise Builder/enterprise
_PKG_PARENT = _REPO.parent                            # .../Enterprise Builder
for p in (str(_PKG_PARENT), str(_REPO)):
    if p not in sys.path:
        sys.path.insert(0, p)

from enterprise.modules.hybrid_kg_retrieval import (  # noqa: E402
    HybridKgRetrievalModule,
    HybridRetriever,
    KnowledgeGraph,
    VectorIndex,
    create_hybrid_kg_retrieval_module,
)
from enterprise.modules.hybrid_kg_retrieval.core import tokenize  # noqa: E402


# ── VectorIndex ──────────────────────────────────────────────────────────────
def test_vector_search_returns_most_overlapping_first():
    vi = VectorIndex()
    vi.add_document("d1", "the quick brown fox jumps over the lazy dog")
    vi.add_document("d2", "python programming language tutorial for beginners")
    vi.add_document("d3", "a fox and a dog playing in the quick morning")
    hits = vi.search("quick fox dog", top_k=3)
    assert hits, "expected at least one vector hit"
    # d1 and d3 both strongly overlap; whichever is first must beat d2.
    ids = [doc_id for doc_id, _ in hits]
    assert ids[0] in {"d1", "d3"}
    assert "d2" not in ids  # no token overlap -> filtered out
    # scores sorted descending
    scores = [s for _, s in hits]
    assert scores == sorted(scores, reverse=True)


def test_vector_no_overlap_returns_empty():
    vi = VectorIndex()
    vi.add_document("d1", "alpha beta gamma")
    assert vi.search("completely unrelated terms", top_k=5) == []


def test_tokenize():
    assert tokenize("Hello, World! 123") == ["hello", "world", "123"]


# ── KnowledgeGraph ───────────────────────────────────────────────────────────
def test_graph_neighbors_and_relations():
    g = KnowledgeGraph()
    g.add_entity("service_a", "service")
    g.add_entity("service_b", "service")
    g.add_relation("service_a", "depends_on", "service_b")
    assert g.neighbors("service_a") == ["service_b"]
    assert g.neighbors("service_a", rel="depends_on") == ["service_b"]
    assert g.neighbors("service_a", rel="other") == []
    triples = g.query_relations("service_b")
    assert ("service_a", "depends_on", "service_b") in triples


def test_graph_multi_hop_and_path():
    g = KnowledgeGraph()
    g.add_relation("a", "r", "b")
    g.add_relation("b", "r", "c")
    g.add_relation("c", "r", "d")
    dist = g.multi_hop("a", max_hops=2)
    assert dist == {"b": 1, "c": 2}  # d is 3 hops away, excluded
    dist3 = g.multi_hop("a", max_hops=3)
    assert dist3 == {"b": 1, "c": 2, "d": 3}
    path = g.find_path("a", "d", max_hops=5)
    assert path == ["a", "b", "c", "d"]
    assert g.find_path("d", "a") is None  # directed, no reverse path


# ── Router ───────────────────────────────────────────────────────────────────
def _make_retriever() -> HybridRetriever:
    r = HybridRetriever()
    r.vector_index.add_document("doc_payments", "payments billing invoice refunds")
    r.vector_index.add_document("doc_auth", "authentication login tokens sessions")
    r.graph.add_entity("payments", "service")
    r.graph.add_entity("ledger", "service")
    r.graph.add_entity("auth", "service")
    r.graph.add_relation("payments", "depends_on", "ledger")
    r.graph.add_relation("payments", "calls", "auth")
    return r


def test_router_picks_graph_for_relational_query():
    r = _make_retriever()
    assert r.classify("how does payments relate to ledger") == "graph"
    assert r.classify("what depends on payments") == "graph"


def test_router_picks_vector_for_plain_lookup():
    r = _make_retriever()
    assert r.classify("invoice refunds") == "vector"


def test_router_picks_hybrid():
    r = _make_retriever()
    # relational cue but no known entity mentioned -> need semantic seed -> hybrid
    assert r.classify("how does checkout relate to shipping") == "hybrid"
    # plain, broad lookup that names a known entity -> hybrid for recall
    assert r.classify("tell me about the payments billing flow") == "hybrid"


# ── Fusion / retrieve ────────────────────────────────────────────────────────
def test_graph_retrieve_returns_neighbors_with_provenance():
    r = _make_retriever()
    bundle = r.retrieve("what depends on payments", top_k=5)
    assert bundle["strategy"] == "graph"
    refs = {res.ref for res in bundle["results"]}
    assert {"ledger", "auth"} <= refs
    assert all(res.source == "graph" for res in bundle["results"])


def test_vector_retrieve_provenance():
    r = _make_retriever()
    bundle = r.retrieve("invoice refunds", top_k=5)
    assert bundle["strategy"] == "vector"
    assert bundle["results"]
    assert bundle["results"][0].ref == "doc_payments"
    assert all(res.source == "vector" for res in bundle["results"])


def test_hybrid_retrieve_fuses_and_tags_provenance():
    r = _make_retriever()
    bundle = r.retrieve("tell me about the payments billing flow", top_k=10)
    assert bundle["strategy"] == "hybrid"
    sources = {res.source for res in bundle["results"]}
    # Fusion should surface both a vector doc and graph entities.
    assert "vector" in sources
    assert "graph" in sources
    # scores are descending after RRF
    scores = [res.score for res in bundle["results"]]
    assert scores == sorted(scores, reverse=True)


# ── Module lifecycle + events ────────────────────────────────────────────────
class _FakeBus:
    def __init__(self):
        self.events = []

    def publish(self, event):
        self.events.append(event)


@pytest.mark.asyncio
async def test_module_initialize_health_shutdown():
    from enterprise.platform_kernel import HealthStatus

    mod = create_hybrid_kg_retrieval_module()
    assert isinstance(mod, HybridKgRetrievalModule)
    await mod.initialize()
    assert await mod.health_check() == HealthStatus.HEALTHY
    await mod.shutdown()
    assert await mod.health_check() == HealthStatus.STOPPING


@pytest.mark.asyncio
async def test_module_emits_events_when_bus_attached():
    mod = create_hybrid_kg_retrieval_module()
    await mod.initialize()
    bus = _FakeBus()
    mod.set_event_bus(bus)
    mod.index_document("d1", "payments billing invoice")
    mod.add_entity("payments", "service")
    mod.add_entity("ledger", "service")
    mod.add_relation("payments", "depends_on", "ledger")
    bundle = mod.retrieve("what depends on payments")
    assert bundle["strategy"] == "graph"
    topics = [e.topic for e in bus.events]
    assert "hybrid_kg_retrieval.document_indexed" in topics
    assert "hybrid_kg_retrieval.entity_added" in topics
    assert "hybrid_kg_retrieval.relation_added" in topics
    assert "hybrid_kg_retrieval.query_served" in topics


@pytest.mark.asyncio
async def test_module_no_events_without_bus():
    mod = create_hybrid_kg_retrieval_module()
    await mod.initialize()
    # Should not raise even though no bus is attached.
    mod.index_document("d1", "hello world")
    assert mod.retrieve("hello world")["strategy"] == "vector"
