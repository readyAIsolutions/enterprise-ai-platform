"""Unit tests for the enterprise RAG module.

Covers the real, existing submodules: chunking, embeddings, retrieval and
reranking. All logic exercised is pure Python -- no network or external
embedding API calls are required. The deterministic ``HashEmbedder`` is used
for vector retrieval instead of the network-dependent ``PretrainedEmbedder``.
"""

import math

import pytest

from modules.rag.chunking import (
    Chunk,
    ChunkingStrategy,
    FixedChunker,
    SemanticChunker,
    create_chunker,
)
from modules.rag.embeddings import (
    BaseEmbedder,
    EmbeddingConfig,
    EmbeddingProvider,
    HashEmbedder,
    create_embedder,
)
from modules.rag.retrieval import (
    HybridRetriever,
    KeywordRetriever,
    RetrievalResult,
    RetrievalStrategy,
    VectorRetriever,
    create_retriever,
)
from modules.rag.reranking import (
    GradualReranker,
    IncrementalReranker,
    NoReranker,
    RerankResult,
    RerankingStrategy,
    UserInteraction,
    create_reranker,
)


def _chunk(text, cid, **meta):
    return Chunk(
        id=cid,
        text=text,
        start_char=0,
        end_char=len(text),
        chunk_index=0,
        metadata=meta,
    )


# --------------------------------------------------------------------------- #
# Chunking
# --------------------------------------------------------------------------- #

def test_fixed_chunker_splits_long_text_into_multiple_chunks():
    text = "word " * 200  # 1000 chars
    chunker = FixedChunker(chunk_size=200, chunk_overlap=20, min_chunk_size=1)
    chunks = chunker.chunk(text)
    assert len(chunks) > 1
    for c in chunks:
        assert len(c.text) <= chunker.chunk_size
        assert c.metadata["strategy"] == "fixed"


def test_fixed_chunker_overlap_is_shared_between_adjacent_chunks():
    text = "alpha beta gamma delta epsilon zeta eta theta iota kappa lambda"
    chunker = FixedChunker(chunk_size=20, chunk_overlap=8, min_chunk_size=1)
    chunks = chunker.chunk(text)
    assert len(chunks) >= 2
    # The tail of chunk[0] should appear at the head of chunk[1] (approx).
    overlap = chunks[0].text[-8:]
    assert chunks[1].text.startswith(overlap[:1]) or overlap.split()[0] in chunks[1].text


def test_fixed_chunker_returns_empty_for_blank_text():
    chunker = FixedChunker()
    assert chunker.chunk("") == []
    assert chunker.chunk("   \n  ") == []


def test_chunk_token_estimate_and_length():
    c = Chunk(id="x", text="hello world", start_char=0, end_char=11, chunk_index=0)
    assert c.length == 11
    assert c.token_estimate == max(1, 11 // 4)


def test_create_chunker_factory_and_unknown_strategy():
    assert isinstance(create_chunker("fixed"), FixedChunker)
    assert isinstance(create_chunker(ChunkingStrategy.SEMANTIC), SemanticChunker)
    with pytest.raises(ValueError):
        create_chunker("bogus")


def test_semantic_chunker_uses_fallback_hash_embedding():
    chunker = SemanticChunker(chunk_size=200, min_chunk_size=1, embedder=None)
    text = "First sentence here. Second sentence here. Third sentence here. "
    chunks = chunker.chunk(text)
    assert len(chunks) >= 1
    for c in chunks:
        assert c.metadata.get("strategy") == "semantic" or c.metadata.get("strategy") == "fixed"


# --------------------------------------------------------------------------- #
# Embeddings
# --------------------------------------------------------------------------- #

def test_hash_embedder_produces_deterministic_normalized_vectors():
    cfg = EmbeddingConfig(provider=EmbeddingProvider.HASH, dimension=32, normalize=True)
    emb = HashEmbedder(cfg)
    v1 = emb.embed("the quick brown fox")
    v2 = emb.embed("the quick brown fox")
    assert v1 == v2  # deterministic
    assert emb.dimension == 32
    assert len(v1[0]) == 32
    norm = math.sqrt(sum(x * x for x in v1[0]))
    assert math.isclose(norm, 1.0, abs_tol=1e-6)


def test_hash_embedder_similarity_ties_identical_text():
    cfg = EmbeddingConfig(provider=EmbeddingProvider.HASH, dimension=32, normalize=True)
    emb = HashEmbedder(cfg)
    sim = emb.similarity(emb.embed_single("same words"), emb.embed_single("same words"))
    assert math.isclose(sim, 1.0, abs_tol=1e-6)


def test_create_embedder_hash_provider():
    cfg = EmbeddingConfig(provider=EmbeddingProvider.HASH)
    embedder = create_embedder(cfg)
    assert isinstance(embedder, HashEmbedder)
    assert isinstance(embedder, BaseEmbedder)


# --------------------------------------------------------------------------- #
# Retrieval
# --------------------------------------------------------------------------- #

def test_keyword_retriever_bm25_ranks_matching_doc_first():
    kr = KeywordRetriever()
    kr.add_documents([
        _chunk("the quick brown fox jumps over the lazy dog", "c1", source="a"),
        _chunk("apples and oranges about nothing relevant here", "c2", source="b"),
    ])
    results = kr.retrieve("fox dog", k=2)
    assert len(results) == 2
    assert results[0].chunk.id == "c1"
    assert results[0].strategy == "keyword"
    # Sorted descending.
    assert all(results[i].score >= results[i + 1].score for i in range(len(results) - 1))


def test_keyword_retriever_metadata_filter():
    kr = KeywordRetriever()
    kr.add_documents([
        _chunk("the quick brown fox jumps", "c1", source="a"),
        _chunk("the lazy dog sleeps all day", "c2", source="b"),
    ])
    results = kr.retrieve("fox", filter_metadata={"source": "a"})
    assert [r.chunk.id for r in results] == ["c1"]


def test_vector_retriever_retrieves_similar_chunk():
    vec = VectorRetriever(embedding_config=EmbeddingConfig(
        provider=EmbeddingProvider.HASH, dimension=32))
    vec.add_documents([
        _chunk("machine learning models train on data", "v1"),
        _chunk("cooking recipes for pasta and sauces", "v2"),
    ])
    results = vec.retrieve("training neural network models", k=1)
    assert results[0].chunk.id == "v1"
    assert results[0].strategy == "vector"


def test_vector_retriever_empty_returns_empty():
    vec = VectorRetriever(embedding_config=EmbeddingConfig(
        provider=EmbeddingProvider.HASH, dimension=32))
    assert vec.retrieve("anything") == []


def test_hybrid_retriever_rrf_fusion():
    hybrid = HybridRetriever(vector_config=EmbeddingConfig(
        provider=EmbeddingProvider.HASH, dimension=32), fusion_method="rrf")
    hybrid.add_documents([
        _chunk("the quick brown fox jumps over the lazy dog", "h1"),
        _chunk("entirely unrelated textile manufacturing", "h2"),
        _chunk("foxes and dogs in the wild", "h3"),
    ])
    results = hybrid.retrieve("fox dog", k=3)
    assert len(results) > 0
    assert all(r.strategy == "hybrid_rrf" for r in results)
    assert all(r.score > 0 for r in results)


def test_retrieval_result_sorts_by_score_descending():
    a = RetrievalResult(chunk=_chunk("x", "a"), score=0.9, strategy="k")
    b = RetrievalResult(chunk=_chunk("x", "b"), score=0.2, strategy="k")
    c = RetrievalResult(chunk=_chunk("x", "c"), score=0.5, strategy="k")
    s = sorted([a, b, c])
    assert [r.chunk.id for r in s] == ["a", "c", "b"]


def test_create_retriever_factory():
    assert isinstance(create_retriever("keyword"), KeywordRetriever)
    assert isinstance(create_retriever(RetrievalStrategy.VECTOR), VectorRetriever)
    with pytest.raises(ValueError):
        create_retriever("nope")


# --------------------------------------------------------------------------- #
# Re-ranking
# --------------------------------------------------------------------------- #

def test_no_reranker_passes_through_scores():
    nr = NoReranker()
    results = [
        RetrievalResult(chunk=_chunk("x", "a"), score=0.8, strategy="k"),
        RetrievalResult(chunk=_chunk("x", "b"), score=0.3, strategy="k"),
    ]
    out = nr.rerank(results, "q")
    assert len(out) == 2
    assert all(r.strategy == "none" for r in out)
    assert all(r.reranked_score == r.original_score for r in out)
    assert all(isinstance(r, RerankResult) for r in out)


def test_gradual_reranker_boosts_interacted_chunks():
    gr = GradualReranker(alpha=0.1, beta=0.0, max_boost=0.5)
    results = [
        RetrievalResult(chunk=_chunk("x", "a"), score=0.5, strategy="k"),
        RetrievalResult(chunk=_chunk("x", "b"), score=0.7, strategy="k"),
    ]
    gr.record_interaction(UserInteraction(
        chunk_id="a", interaction_type="thumbs_up", timestamp=0.0))
    out = gr.rerank(results, "q")
    by_id = {r.chunk_id: r for r in out}
    assert by_id["a"].reranked_score > by_id["a"].original_score  # boosted
    assert by_id["a"].strategy == "gradual"
    # Boost is bounded by max_boost.
    assert by_id["a"].reranked_score - by_id["a"].original_score <= gr.max_boost


def test_gradual_reranker_persists_accumulated_relevance():
    import tempfile
    import os
    gr = GradualReranker(alpha=0.1, beta=0.0, max_boost=0.5)
    results = [
        RetrievalResult(chunk=_chunk("x", "p1"), score=0.4, strategy="k"),
    ]
    gr.record_interaction(UserInteraction(
        chunk_id="p1", interaction_type="copy", timestamp=0.0, duration=None))
    gr.rerank(results, "q")
    # Second rerank should reflect the accumulated relevance (no decay since beta=0).
    out2 = gr.rerank(results, "q")
    assert out2[0].metadata["accumulated_relevance"] > 0


def test_incremental_reranker_clamps_and_updates():
    ir = IncrementalReranker(gamma=0.1, base_weight=0.7, interaction_weight=0.3,
                             min_score=0.0, max_score=1.0)
    results = [
        RetrievalResult(chunk=_chunk("x", "inc1"), score=0.9, strategy="k"),
    ]
    ir.record_interaction(UserInteraction(
        chunk_id="inc1", interaction_type="thumbs_down", timestamp=0.0))
    out = ir.rerank(results, "q")
    assert 0.0 <= out[0].reranked_score <= 1.0
    assert out[0].strategy == "incremental"
    # The incremental score was stored.
    assert "inc1" in ir._incremental_scores


def test_create_reranker_factory():
    assert isinstance(create_reranker("gradual"), GradualReranker)
    assert isinstance(create_reranker(RerankingStrategy.INCREMENTAL), IncrementalReranker)
    assert isinstance(create_reranker("none"), NoReranker)
    with pytest.raises(ValueError):
        create_reranker("mystery")
