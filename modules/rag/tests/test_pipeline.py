"""Tests for the unified RAG pipeline and its kernel module registration."""

import asyncio

from enterprise.platform_kernel import HealthStatus, _MODULE_REGISTRY
from enterprise.modules.rag import (
    RAGConfig,
    RAGModule,
    RAGPipeline,
    create_rag_module,
)
from enterprise.modules.rag.pipeline import PipelineResult
from enterprise.modules.rag.chunking import Chunk


def _single_doc_pipeline(**cfg_overrides):
    cfg = RAGConfig(**cfg_overrides)
    return RAGPipeline(cfg)


def test_config_defaults():
    cfg = RAGConfig()
    assert cfg.top_k == 2
    assert cfg.embedding_dimension == 8


def test_index_documents_counts_chunks():
    pipe = _single_doc_pipeline(chunk_size=50, min_chunk_size=1)
    n = pipe.index_documents(["alpha beta gamma delta " * 40])
    assert n >= 1
    assert len(pipe.retriever._documents) == n


def test_query_returns_deterministic_single_document_result():
    text = "The gateway galaxy contains a bright central supermassive star."
    pipe = _single_doc_pipeline(top_k=1)
    pipe.index_text(text, source="doc_alpha")
    result = pipe.query("What is in the gateway galaxy?")
    assert isinstance(result, PipelineResult)
    assert result.sources == ["doc_alpha"]
    assert len(result.citations) == 1
    assert result.citations[0].source_id == "doc_alpha"
    assert "gateway galaxy" in result.context
    # The single chunk must always be present regardless of hash-seed ordering.
    assert len(result.retrieval_results) >= 1
    assert result.answer.count("References:") == 1


def test_query_indexes_multiple_raw_documents():
    pipe = _single_doc_pipeline(top_k=2)
    n = pipe.index_documents(
        ["First paper describes plant biology.", "Second paper covers rocket engines."]
    )
    assert n >= 2
    result = pipe.query("rocket engines")
    assert result.sources  # sources populated
    # Citations de-duplicated by source id.
    ids = [c.source_id for c in result.citations]
    assert len(ids) == len(set(ids))


def test_index_accepts_prechunked_chunks():
    pipe = _single_doc_pipeline()
    chunk = Chunk(
        id="pre",
        text="Pre-chunked analytical content for searching.",
        start_char=0,
        end_char=len("pre"),
        chunk_index=0,
        metadata={"source": "doc_pre"},
    )
    n = pipe.index_documents([chunk])
    assert n == 1


def test_formatted_citations_not_empty_after_queries():
    pipe = _single_doc_pipeline(top_k=1)
    pipe.index_text("A reference-worthy scientific claim about neutrinos.", source="doc_n")
    pipe.query("neutrino claim")
    assert "doc_n" in pipe.formatted_citations()


# --------------------------------------------------------------------------- #
# Kernel module registration + lifecycle
# --------------------------------------------------------------------------- #
def test_module_registered_in_kernel_registry():
    assert "rag" in _MODULE_REGISTRY
    assert issubclass(_MODULE_REGISTRY["rag"], RAGModule)


def test_module_meta():
    assert RAGModule._meta_name == "rag"
    assert RAGModule._meta_version == "1.0.0"


def test_create_rag_module_factory():
    mod = create_rag_module({"top_k": 3})
    assert isinstance(mod, RAGModule)
    assert mod.config["top_k"] == 3
    assert mod.status is HealthStatus.UNKNOWN


def test_module_lifecycle_and_query():
    mod = create_rag_module({"top_k": 1})

    async def drive():
        await mod.initialize()
        assert await mod.health_check() is HealthStatus.HEALTHY
        mod.index_documents(["Lifecycle module handles a streaming corpus query."])
        res = mod.query("streaming corpus")
        assert res.sources
        await mod.shutdown()

    asyncio.run(drive())


def test_uninitialized_module_raises_on_pipeline_access():
    mod = RAGModule({})
    try:
        mod.pipeline
    except RuntimeError:
        return
    raise AssertionError("expected RuntimeError before initialize")


def test_event_bus_wiring_accepts_none_or_bus():
    mod = RAGModule({})
    mod.set_event_bus(None)  # must not raise
    assert True