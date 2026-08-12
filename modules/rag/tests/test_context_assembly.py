"""Tests for the RAG context assembly submodule."""

import math

from modules.rag.chunking import Chunk
from modules.rag.context_assembly import (
    ConcatenateAssembler,
    ContextAssembler,
    ContextResult,
    CrossDocumentFusionAssembler,
    SummarizationAssembler,
    create_assembler,
)
from modules.rag.retrieval import RetrievalResult


def _result(text, cid, source, score=0.9, **meta):
    chunk = Chunk(
        id=cid,
        text=text,
        start_char=0,
        end_char=len(text),
        chunk_index=0,
        metadata={"source": source, **meta},
    )
    return RetrievalResult(chunk=chunk, score=score, strategy="vector")


def test_create_assembler_factory_maps_strategies():
    assert isinstance(create_assembler("concatenate"), ConcatenateAssembler)
    assert isinstance(create_assembler("summarization"), SummarizationAssembler)
    assert isinstance(create_assembler("cross_document"), CrossDocumentFusionAssembler)
    # Default is concatenate.
    assert isinstance(create_assembler(), ConcatenateAssembler)


def test_create_assembler_raises_on_unknown_strategy():
    try:
        create_assembler("bogus")
    except ValueError:
        return
    raise AssertionError("expected ValueError for unknown strategy")


def test_context_result_metrics():
    res = ContextResult(context="abc def ghi jkl", sources=["a"])
    assert res.char_count == 15
    assert res.token_estimate == max(1, 15 // 4) == 3


def test_concatenate_orders_by_score_and_joins():
    a = _result("first doc evidence", "a1", "d1", score=1.0)
    b = _result("second doc evidence", "b1", "d2", score=0.5)
    out = ConcatenateAssembler().assemble([a, b], query="q")
    assert isinstance(out, ContextResult)
    assert out.context.startswith("first doc evidence")
    assert "second doc evidence" in out.context
    assert out.sources == ["d1", "d2"]
    assert out.chunks[0].id == "a1"


def test_summarization_extractive_selects_query_matching_sentences():
    results = [
        _result(
            "Apples are a fruit. Apples grow on trees. Weather is often cloudy.",
            "a1",
            "d1",
            score=1.0,
        )
    ]
    out = SummarizationAssembler(max_sentences=2, min_chars_per_sentence=1).assemble(
        results, query="apples fruit"
    )
    assert "Apples are a fruit" in out.context
    assert "cloudy" not in out.context  # least relevant sentence dropped
    assert out.strategy == "summarization"


def test_summarization_include_raw_appends_evidence():
    results = [ _result("Only sentence here is gold.", "a1", "d1", score=1.0) ]
    out = SummarizationAssembler(include_raw=True).assemble(results, query="gold")
    assert "Raw evidence" in out.context
    assert "Only sentence here is gold." in out.context


def test_cross_document_fusion_dedups_near_duplicates():
    a = _result("The capital of France is Paris and it is famous.", "a1", "d1", score=1.0)
    b = _result("Paris is the capital of France, quite famous indeed.", "b1", "d2", score=0.95)
    c = _result("Bread is made from flour and water yeast.", "c1", "d3", score=0.9)
    out = CrossDocumentFusionAssembler(similarity_threshold=0.5).assemble([a, b, c])
    assert out.metadata["kept_results"] == 2  # b dropped as duplicate of a
    assert out.metadata["removed_duplicates"] == 1


def test_assembler_is_deterministic_identical_inputs():
    results = [
        _result("alpha beta gamma", "x1", "d1", score=1.0),
        _result("delta epsilon zeta", "x2", "d2", score=0.5),
    ]
    one = ConcatenateAssembler().assemble(results)
    two = ConcatenateAssembler().assemble(results)
    assert one.context == two.context
    assert math.isclose(one.char_count, two.char_count)
