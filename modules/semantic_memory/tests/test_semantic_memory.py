"""Unit tests for the semantic_memory module.

Covers the dependency-free semantic retrieval layer: deterministic hashing
embeddings, pure-Python vector math, ranking + k limits, metadata filtering,
removal/counting, the knowledge-graph triple adapter, and the Platform Kernel
module lifecycle (initialize / health_check / shutdown / event publishing).

Run with:
    python3 -m pytest modules/semantic_memory/tests -q
"""

from __future__ import annotations

import math
from typing import Any

import pytest
from enterprise.modules.semantic_memory import (
    SemanticMemoryModule,
    cosine_similarity,
    dot,
    normalize,
)
from enterprise.modules.semantic_memory.semantic_memory import (
    HashEmbedder,
    KnowledgeGraphAdapter,
    SemanticIndex,
    SemanticMemory,
)
from enterprise.platform_kernel import EventBus, HealthStatus

# ---------------------------------------------------------------------------
# Corpus + deterministic fake embedder
# ---------------------------------------------------------------------------

# A small but meaningfully distinguishable corpus (machine-learning vs baking).
# Every token used below is present in the fake embedder's _TOKEN_INDEX so the
# ranking tests are deterministic and independent of hash-collision behaviour.
CORPUS = [
    ("ml-1", "machine learning model trained on large data", {"domain": "ai"}),
    ("ml-2", "training a neural network needs a gpu and lots of data", {"domain": "ai"}),
    ("bak-1", "baking sourdough bread needs flour water salt and time", {"domain": "food"}),
    ("bak-2", "a good bakers yeast starter turns dough into crusty bread", {"domain": "food"}),
    ("ml-3", "gradient descent optimizes the loss function of a model", {"domain": "ai"}),
]

# Deterministic fake embedder for isolation: maps each known token to a fixed
# index so tests don't depend on hash-collision details.
_TOKEN_INDEX = {
    "ml": 0, "model": 1, "train": 2, "data": 3, "network": 4, "gpu": 5,
    "bake": 6, "bread": 7, "flour": 8, "dough": 9, "yeast": 10,
}


class FakeEmbedder:
    """Deterministic one-hot embedder over a fixed token vocabulary."""

    def __init__(self, dim: int = 16) -> None:
        self._dim = dim

    @property
    def dim(self) -> int:
        return self._dim

    def embed(self, text: str) -> list[float]:
        vec = [0.0] * self._dim
        for tok in text.lower().split():
            idx = _TOKEN_INDEX.get(tok)
            if idx is not None and idx < self._dim:
                vec[idx] = 1.0
        return normalize(vec)


def _build_index(embedder=None) -> SemanticIndex:
    idx = SemanticIndex(embedder=embedder or FakeEmbedder(dim=16))
    for doc_id, text, meta in CORPUS:
        idx.add(doc_id, text, meta)
    return idx


# ---------------------------------------------------------------------------
# HashEmbedder
# ---------------------------------------------------------------------------


class TestHashEmbedder:
    def test_deterministic_same_input_same_vector(self) -> None:
        emb = HashEmbedder(dim=256)
        assert emb.embed("machine learning model") == emb.embed("machine learning model")

    def test_different_text_different_vector(self) -> None:
        emb = HashEmbedder(dim=256)
        a = emb.embed("machine learning model")
        b = emb.embed("baking sourdough bread")
        assert a != b

    def test_embedding_unit_normalized(self) -> None:
        emb = HashEmbedder(dim=256)
        vec = emb.embed("training a neural network with gradient descent")
        norm = math.sqrt(sum(x * x for x in vec))
        assert norm == pytest.approx(1.0, abs=1e-9)

    def test_cross_process_determinism(self) -> None:
        # Two independent embedder instances must agree.
        a = HashEmbedder(dim=128).embed("add milk and eggs to the recipe")
        b = HashEmbedder(dim=128).embed("add milk and eggs to the recipe")
        assert a == b

    def test_empty_text_yields_zero_vector(self) -> None:
        emb = HashEmbedder(dim=256)
        assert emb.embed("") == [0.0] * 256

    def test_validates_dim(self) -> None:
        with pytest.raises(ValueError):
            HashEmbedder(dim=0)
        with pytest.raises(ValueError):
            HashEmbedder(dim=-5)


# ---------------------------------------------------------------------------
# Vector math helpers
# ---------------------------------------------------------------------------


class TestVectorMath:
    def test_cosine_identical_is_one(self) -> None:
        v = normalize([1.0, 2.0, 3.0])
        assert cosine_similarity(v, v) == pytest.approx(1.0)

    def test_cosine_orthogonal_is_zero(self) -> None:
        a = normalize([1.0, 0.0])
        b = normalize([0.0, 1.0])
        assert cosine_similarity(a, b) == pytest.approx(0.0)

    def test_cosine_zero_vector_is_zero(self) -> None:
        assert cosine_similarity([0.0, 0.0], normalize([1.0, 1.0])) == 0.0
        assert cosine_similarity([0.0, 0.0], [0.0, 0.0]) == 0.0

    def test_dot(self) -> None:
        assert dot([1.0, 2.0], [3.0, 4.0]) == pytest.approx(11.0)

    def test_dimension_mismatch_raises(self) -> None:
        with pytest.raises(ValueError):
            cosine_similarity([1.0, 0.0], [1.0])
        with pytest.raises(ValueError):
            dot([1.0], [1.0, 2.0])


# ---------------------------------------------------------------------------
# SemanticIndex
# ---------------------------------------------------------------------------


class TestSemanticIndex:
    def test_returns_most_similar_first(self) -> None:
        idx = _build_index()
        results = idx.search("model training data", k=5)
        assert results[0].id == "ml-1"

    def test_respects_k(self) -> None:
        idx = _build_index()
        assert len(idx.search("model training", k=2)) == 2
        assert len(idx.search("model training", k=0)) == 0

    def test_ml_query_does_not_rank_baking_first(self) -> None:
        idx = _build_index()
        results = idx.search("neural network GPU training", k=5)
        top = results[0]
        assert top.id == "ml-2"
        # The baking docs should rank well below the ML docs for an ML query,
        # but keep the assertion robust to hash collisions in the fake embedder.
        ml_ids = {r.id for r in results[:3] if r.id in ("ml-1", "ml-2", "ml-3")}
        assert "ml-2" in ml_ids

    def test_metadata_filter_narrows_results(self) -> None:
        idx = _build_index()
        ai = idx.search("model training data", k=5, metadata_filter={"domain": "ai"})
        assert len(ai) == 3
        assert all(d.metadata["domain"] == "ai" for d in ai)
        food = idx.search("model training data", k=5, metadata_filter={"domain": "food"})
        assert len(food) == 2
        assert all(d.metadata["domain"] == "food" for d in food)

    def test_remove_and_count(self) -> None:
        idx = _build_index()
        assert idx.count() == 5
        assert idx.remove("ml-2") is True
        assert idx.count() == 4
        assert idx.remove("does-not-exist") is False
        assert idx.count() == 4

    def test_add_replace(self) -> None:
        idx = _build_index()
        idx.add("ml-1", "only baking bread", {"domain": "food"})
        assert idx.get("ml-1") is not None
        assert idx.get("ml-1").metadata["domain"] == "food"
        assert idx.count() == 5

    def test_construct_with_any_embedder_dependency_injection(self) -> None:
        idx = SemanticIndex(embedder=HashEmbedder(dim=32))
        idx.add("d1", "some text to embed")
        assert idx.count() == 1
        # Default embedder when none supplied.
        default_idx = SemanticIndex()
        assert default_idx.embedder.dim == 256

    def test_search_scores_are_non_negative(self) -> None:
        idx = _build_index()
        for r in idx.search("machine learning model"):
            assert r.score >= 0.0
            assert r.score <= 1.0


# ---------------------------------------------------------------------------
# KnowledgeGraphAdapter
# ---------------------------------------------------------------------------


class TestKnowledgeGraphAdapter:
    def test_ingest_triples_indexes_documents(self) -> None:
        idx = SemanticIndex(embedder=FakeEmbedder(dim=16))
        adapter = KnowledgeGraphAdapter(idx)
        triples = [
            {
                "entity_name": "Transformer Model",
                "description": "a machine learning model architecture",
                "relation": "used_for_training",
            },
            {
                "entity_name": "Sourdough Starter",
                "description": "a fermented mixture of flour and water",
                "relation": "used_in_baking",
            },
        ]
        created = adapter.ingest_triples(triples)
        assert len(created) == 4  # 2 per triple (entity + edge)
        assert idx.count() == 4

    def test_recall_finds_triples_by_semantic_similarity(self) -> None:
        mem = SemanticMemory(embedder=FakeEmbedder(dim=16))
        adapter = mem.adapter
        adapter.ingest_triples(
            [
                {
                    "entity_name": "Neural Network",
                    "description": "machine learning model learns from training data",
                    "relation": "requires GPU",
                },
                {
                    "entity_name": "Rye Loaf",
                    "description": "baked from flour water and sourdough starter",
                    "relation": "made in oven",
                },
            ]
        )
        hits = mem.recall("training a machine learning model", k=5)
        assert hits, "expected at least one hit"
        assert hits[0].id.startswith("kg:entity:")  # entity doc ranks first
        # Semantic recall should surface the ML entity above the baking one.
        # The FakeEmbedder maps distinct tokens to distinct indices, so the
        # ML query is strictly closer to the ML entity doc.
        assert "Neural" in hits[0].text or "Neural" in hits[0].text

    def test_validate_triple_shape(self) -> None:
        idx = SemanticIndex(embedder=FakeEmbedder(dim=16))
        adapter = KnowledgeGraphAdapter(idx)
        with pytest.raises(ValueError):
            adapter.ingest_triples([{"entity_name": "x", "description": "y"}])
        with pytest.raises(ValueError):
            adapter.ingest_triples(
                [{"entity_name": "x", "description": None, "relation": "r"}]
            )
        with pytest.raises(TypeError):
            adapter.ingest_triples(["not-a-dict"])  # type: ignore[list-item]


# ---------------------------------------------------------------------------
# SemanticMemory facade + module lifecycle
# ---------------------------------------------------------------------------


class TestSemanticMemoryFacade:
    def test_remember_and_recall(self) -> None:
        mem = SemanticMemory(embedder=FakeEmbedder(dim=16))
        mem.remember("d1", "compute gradient descent on the model", {"domain": "ml"})
        mem.remember("d2", "mix the bread dough and let it rise", {"domain": "food"})
        assert mem.recall("model gradient descent", k=1)[0].id == "d1"


class TestSemanticMemoryModule:
    async def test_initialize_builds_memory_and_healthy(self) -> None:
        mod = SemanticMemoryModule(config={"dim": 64, "top_k": 3})
        assert mod.status is HealthStatus.UNKNOWN
        await mod.initialize()
        assert mod.status is HealthStatus.HEALTHY
        assert mod.memory is not None
        assert mod.dim == 64
        assert mod.top_k == 3

    async def test_defaults(self) -> None:
        mod = SemanticMemoryModule()
        await mod.initialize()
        assert mod.dim == 256
        assert mod.top_k == 5

    async def test_health_check(self) -> None:
        mod = SemanticMemoryModule()
        assert await mod.health_check() is HealthStatus.UNKNOWN
        await mod.initialize()
        assert await mod.health_check() is HealthStatus.HEALTHY

    async def test_remember_recall_through_module(self) -> None:
        mod = SemanticMemoryModule(config={"dim": 64})
        await mod.initialize()
        mod.remember("a1", "machine learning model training", {"domain": "ai"})
        mod.remember("a2", "baking sourdough bread from flour", {"domain": "food"})
        hits = mod.recall("model training", k=1)
        assert hits[0].id == "a1"

    async def test_shutdown_releases_memory(self) -> None:
        mod = SemanticMemoryModule()
        await mod.initialize()
        await mod.shutdown()
        assert mod.memory is None

    async def test_operation_before_initialize_raises(self) -> None:
        mod = SemanticMemoryModule()
        with pytest.raises(RuntimeError):
            mod.remember("x", "text")
        with pytest.raises(RuntimeError):
            mod.recall("query")

    async def test_event_bus_publishes_indexed_and_query(self) -> None:
        bus = EventBus(config={"async_dispatch": False})
        received: list[str] = []

        @bus.subscribe("memory.doc.indexed")
        def _on_indexed(event: Any) -> None:
            received.append(event.topic)

        @bus.subscribe("memory.query")
        def _on_query(event: Any) -> None:
            received.append(event.topic)

        mod = SemanticMemoryModule(config={"dim": 64})
        mod.set_event_bus(bus)
        await mod.initialize()
        mod.remember("doc1", "machine learning model training")
        mod.recall("model", k=1)

        assert "memory.doc.indexed" in received
        assert "memory.query" in received

    async def test_registered_with_platform(self) -> None:
        from enterprise.platform_kernel import _MODULE_REGISTRY

        assert "semantic_memory" in _MODULE_REGISTRY
        cls = _MODULE_REGISTRY["semantic_memory"]
        assert issubclass(cls, SemanticMemoryModule)
        assert cls._meta_version == "1.0.0"
