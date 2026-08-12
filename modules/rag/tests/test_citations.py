"""Tests for the RAG citations submodule."""

from modules.rag.citations import (
    Citation,
    CitationManager,
    CitationStyle,
    create_citation_manager,
)


def _cite(source_id="s1", **kw):
    defaults = dict(
        title="A Study",
        author="Alice",
        year="2021",
        publisher="PubCo",
        url="https://example.com/x",
    )
    defaults.update(kw)
    return Citation(source_id=source_id, **defaults)


def test_create_manager_default_style_and_empty():
    mgr = create_citation_manager()
    assert isinstance(mgr, CitationManager)
    assert mgr.default_style == CitationStyle.APA
    assert len(mgr) == 0
    assert mgr.citations == []


def test_add_and_dedupe():
    mgr = CitationManager()
    assert mgr.add_citation(_cite("s1")) is True
    added = mgr.add_citation(_cite("s1"))   # identical -> duplicate
    assert added is False
    assert len(mgr) == 1
    # Different source id adds.
    assert mgr.add_citation(_cite("s2")) is True
    assert len(mgr) == 2


def test_add_many_counts():
    mgr = CitationManager()
    assert mgr.add_many([_cite("s1"), _cite("s1"), _cite("s2")]) == 2
    assert len(mgr) == 2


def test_remove_and_clear():
    mgr = CitationManager(citations=[_cite("s1"), _cite("s2")])
    assert mgr.remove("s1") is True
    assert [c.source_id for c in mgr] == ["s2"]
    mgr.clear()
    assert len(mgr) == 0


def test_format_apa():
    mgr = CitationManager(default_style=CitationStyle.APA, citations=[_cite("s1")])
    formatted = mgr.format()
    assert "Alice" in formatted
    assert "(2021)" in formatted
    assert "https://example.com/x" in formatted


def test_ieee_brackets_source_id():
    mgr = CitationManager(default_style=CitationStyle.IEEE, citations=[_cite("s1")])
    assert "[s1]" in mgr.format()
    assert mgr.inline_marks() == "[s1]"


def test_all_styles_render_some_text():
    c = _cite("s1")
    for style in CitationStyle:
        rendered = CitationManager.format_citation(c, style)
        assert isinstance(rendered, str) and rendered.strip()


def test_none_style_returns_plain():
    rendered = CitationManager.format_citation(_cite("s1"), CitationStyle.NONE)
    assert "Alice" in rendered


def test_unknown_style_raises():
    mgr = CitationManager()
    try:
        mgr.format_citation(_cite("s1"), "not-a-style")
    except ValueError:
        return
    raise AssertionError("expected ValueError for unknown style")


def test_to_dict_json_friendly():
    mgr = CitationManager(citations=[_cite("s1")])
    data = mgr.to_dict()
    assert data[0]["source_id"] == "s1"
    assert data[0]["title"] == "A Study"
