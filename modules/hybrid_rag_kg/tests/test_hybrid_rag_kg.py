"""Tests for hybrid_rag_kg module."""

import asyncio
import tempfile
from pathlib import Path

import pytest

from enterprise.modules.hybrid_rag_kg import (
    AgenticRouter,
    HybridRagKgModule,
    KnowledgeGraph,
    RELATIONAL_CUES,
    RetrievalResult,
    VectorStore,
    create_hybrid_rag_kg_module,
    tokenize,
)
from enterprise.platform_kernel import HealthStatus


class TestTokenize:
    def test_tokenize_basic(self):
        assert tokenize("Hello World") == ["hello", "world"]
        assert tokenize("AI & ML: RAG 2.0") == ["ai", "ml", "rag", "2", "0"]
        assert tokenize("") == []
        assert tokenize("   ") == []


class TestVectorStore:
    def test_add_chunk_and_search(self):
        vs = VectorStore()
        vs.add_chunk("c1", "The quick brown fox jumps over the lazy dog")
        vs.add_chunk("c2", "Machine learning and artificial intelligence")
        vs.add_chunk("c3", "Vector databases store embeddings for semantic search")

        # Search for fox-related content - only c1 matches
        results = vs.search("fox dog", top_k=2)
        assert len(results) == 1
        assert results[0][0] == "c1"

        # Search for ML content
        results = vs.search("machine learning", top_k=2)
        assert len(results) >= 1
        assert results[0][0] == "c2"

    def test_add_document_splits_into_chunks(self):
        vs = VectorStore()
        text = " ".join([f"word{i}" for i in range(1000)])  # long text
        chunk_ids = vs.add_document("doc1", text, chunk_size=100, chunk_overlap=20)
        assert len(chunk_ids) > 1
        assert all(cid.startswith("doc1#chunk") for cid in chunk_ids)
        assert len(vs) == len(chunk_ids)

    def test_search_empty_returns_empty(self):
        vs = VectorStore()
        results = vs.search("anything", top_k=5)
        assert results == []

    def test_cosine_similarity_deterministic(self):
        vs = VectorStore()
        vs.add_chunk("a", "apple banana cherry")
        vs.add_chunk("b", "apple banana")
        vs.add_chunk("c", "durian elderberry")

        results = vs.search("apple banana", top_k=3)
        # a and b both match apple banana, c has no overlap (score 0, filtered out)
        assert len(results) == 2
        assert results[0][0] in ("a", "b")
        assert results[1][0] in ("a", "b")


class TestKnowledgeGraph:
    def test_add_entity_and_get(self):
        kg = KnowledgeGraph()
        kg.add_entity("Amazon", "Company", {"industry": "Tech"})
        kg.add_entity("Anthropic", "Company", {"industry": "AI"})

        assert kg.has_entity("Amazon")
        assert kg.has_entity("Anthropic")
        assert not kg.has_entity("Google")

        ent = kg.get_entity("Amazon")
        assert ent is not None
        assert ent.type == "Company"
        assert ent.props["industry"] == "Tech"

    def test_add_relation_auto_creates_entities(self):
        kg = KnowledgeGraph()
        kg.add_relation("Amazon", "invested_in", "Anthropic", {"amount": "4B"})

        assert kg.has_entity("Amazon")
        assert kg.has_entity("Anthropic")

        rels = kg.query_relations("Amazon")
        assert ("Amazon", "invested_in", "Anthropic", {"amount": "4B"}) in rels

    def test_neighbors(self):
        kg = KnowledgeGraph()
        kg.add_relation("A", "rel1", "B")
        kg.add_relation("A", "rel2", "C")
        kg.add_relation("D", "rel1", "A")

        assert set(kg.neighbors("A")) == {"B", "C"}
        assert kg.neighbors("A", rel="rel1") == ["B"]
        assert kg.neighbors("D") == ["A"]

    def test_query_relations_both_directions(self):
        kg = KnowledgeGraph()
        kg.add_relation("X", "connects", "Y")
        kg.add_relation("Z", "connects", "X")

        rels = kg.query_relations("X")
        assert len(rels) == 2
        assert ("X", "connects", "Y", {}) in rels
        assert ("Z", "connects", "X", {}) in rels

    def test_multi_hop_bfs(self):
        kg = KnowledgeGraph()
        kg.add_relation("A", "next", "B")
        kg.add_relation("B", "next", "C")
        kg.add_relation("C", "next", "D")
        kg.add_relation("B", "other", "E")

        # 2 hops from A
        dist = kg.multi_hop("A", max_hops=2)
        # B at 1 hop, C and E at 2 hops
        assert dist["B"] == 1
        assert dist["C"] == 2
        assert dist["E"] == 2

        # filtered by rel
        dist = kg.multi_hop("A", max_hops=2, rel="next")
        assert dist == {"B": 1, "C": 2}

    def test_find_path(self):
        kg = KnowledgeGraph()
        kg.add_relation("Start", "step", "Mid")
        kg.add_relation("Mid", "step", "End")
        kg.add_relation("Start", "direct", "End")

        # BFS finds shortest path - direct edge is 1 hop, step->step is 2 hops
        path = kg.find_path("Start", "End", max_hops=3)
        assert path == ["Start", "End"]  # shortest path (direct edge)

        # Path with 1 hop limit finds direct
        path = kg.find_path("Start", "End", max_hops=1)
        assert path == ["Start", "End"]

        # No path in reverse direction
        assert kg.find_path("End", "Start") is None

    def test_temporal_query(self):
        kg = KnowledgeGraph()
        kg.add_relation("CompanyA", "partnered_with", "CompanyB", valid_at="2020-01-01")
        kg.add_relation("CompanyA", "partnered_with", "CompanyC", valid_at="2024-01-01")
        kg.add_relation("CompanyA", "acquired", "CompanyD", valid_at="2022-06-15")

        # Query at 2021 - should only see 2020 partnership
        rels = kg.temporal_query("CompanyA", "2021-01-01")
        partners = [(r[1], r[2]) for r in rels]
        assert ("partnered_with", "CompanyB") in partners
        assert ("partnered_with", "CompanyC") not in partners
        assert ("acquired", "CompanyD") not in partners

        # Query at 2025 - should see all
        rels = kg.temporal_query("CompanyA", "2025-01-01")
        assert len(rels) == 3


class TestAgenticRouter:
    def test_classify_vector_for_semantic_lookup(self):
        router = AgenticRouter()
        # Add some chunks to vector store
        router.vector_store.add_chunk("c1", "Google AI initiatives include Bard and DeepMind")
        router.vector_store.add_chunk("c2", "Microsoft Azure OpenAI partnership")

        # No relational cues, no known entities -> vector
        strategy = router.classify("What are Google's AI initiatives?")
        assert strategy == "vector"

    def test_classify_graph_for_relational_query(self):
        router = AgenticRouter()
        # Add entities to graph
        router.graph.add_entity("Amazon", "Company")
        router.graph.add_entity("Anthropic", "Company")
        router.graph.add_relation("Amazon", "invested_in", "Anthropic")

        # Relational cue + known entities -> graph
        strategy = router.classify("How are Amazon and Anthropic related?")
        assert strategy == "graph"

        strategy = router.classify("What is the relationship between Amazon and Anthropic?")
        assert strategy == "graph"

        strategy = router.classify("Amazon depends on Anthropic")
        assert strategy == "graph"

    def test_classify_hybrid_when_relational_but_no_known_entities(self):
        router = AgenticRouter()
        # Relational cue but no entities in graph yet -> hybrid
        strategy = router.classify("How does CompanyX relate to CompanyY?")
        assert strategy == "hybrid"

    def test_classify_hybrid_when_known_entity_broad_query(self):
        router = AgenticRouter()
        router.graph.add_entity("Google", "Company")
        router.vector_store.add_chunk("c1", "Google AI initiatives include Bard and DeepMind")

        # Known entity + broad query (>=4 tokens) -> hybrid
        strategy = router.classify("Tell me about Google AI projects")
        assert strategy == "hybrid"

    def test_retrieve_vector_strategy(self):
        router = AgenticRouter()
        router.vector_store.add_chunk("c1", "Google AI initiatives Bard DeepMind")
        router.vector_store.add_chunk("c2", "Microsoft Azure OpenAI")

        bundle = router.retrieve("Google AI", top_k=2)
        assert bundle["strategy"] == "vector"
        assert len(bundle["results"]) > 0
        assert all(r.source == "vector" for r in bundle["results"])

    def test_retrieve_graph_strategy(self):
        router = AgenticRouter()
        router.graph.add_entity("Amazon", "Company")
        router.graph.add_entity("Anthropic", "Company")
        router.graph.add_relation("Amazon", "invested_in", "Anthropic")

        bundle = router.retrieve("How are Amazon and Anthropic related?", top_k=2)
        assert bundle["strategy"] == "graph"
        assert len(bundle["results"]) > 0
        assert all(r.source == "graph" for r in bundle["results"])

    def test_retrieve_hybrid_strategy_fuses_results(self):
        router = AgenticRouter()
        router.vector_store.add_chunk("c1", "Google AI initiatives Bard")
        router.graph.add_entity("Google", "Company")
        router.graph.add_entity("DeepMind", "Company")
        router.graph.add_relation("Google", "owns", "DeepMind")

        bundle = router.retrieve("Tell me about Google AI projects", top_k=3)
        assert bundle["strategy"] == "hybrid"
        assert len(bundle["results"]) > 0
        sources = {r.source for r in bundle["results"]}
        assert "vector" in sources
        assert "graph" in sources


class TestModuleLifecycle:
    @pytest.mark.asyncio
    async def test_initialize_health_check_shutdown(self):
        module = create_hybrid_rag_kg_module({"default_top_k": 3, "max_hops": 2})

        # Initialize
        await module.initialize()
        assert module.status == HealthStatus.HEALTHY

        # Health check
        status = await module.health_check()
        assert status == HealthStatus.HEALTHY

        # Shutdown
        await module.shutdown()
        assert module.status == HealthStatus.HEALTHY  # goes to HEALTHY after STOPPING

    @pytest.mark.asyncio
    async def test_module_facade_methods(self):
        module = create_hybrid_rag_kg_module()
        await module.initialize()

        # add_chunk
        module.add_chunk("test:chunk1", "Hybrid RAG combines vector and graph search")
        # add_document
        chunk_ids = module.add_document("doc1", "Agentic RAG lets the agent choose tools. " * 10)
        assert len(chunk_ids) > 0

        # add_entity
        module.add_entity("Amazon", "Company", {"sector": "Tech"})
        module.add_entity("Anthropic", "Company", {"sector": "AI"})

        # add_relation
        module.add_relation("Amazon", "invested_in", "Anthropic", {"amount": "4B"}, "2024-01-01")

        # classify
        assert module.classify("What are AI initiatives?") == "vector"
        assert module.classify("How are Amazon and Anthropic related?") == "graph"

        # retrieve
        bundle = module.retrieve("Google AI projects", top_k=2)
        assert "strategy" in bundle
        assert "results" in bundle

        await module.shutdown()


class TestRELATIONAL_CUES:
    def test_cues_include_expected_keywords(self):
        cues = RELATIONAL_CUES
        assert "related to" in cues
        assert "how are" in cues
        assert "depends on" in cues
        assert "temporal" in cues
        assert "when did" in cues
        assert "path between" in cues


class TestRetrievalResult:
    def test_dataclass_fields(self):
        r = RetrievalResult(
            ref="test_id",
            source="vector",
            score=0.95,
            detail={"rank": 0, "similarity": 0.95},
        )
        assert r.ref == "test_id"
        assert r.source == "vector"
        assert r.score == 0.95
        assert r.detail["rank"] == 0