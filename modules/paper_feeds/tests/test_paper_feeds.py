"""Tests for paper_feeds v2.0 (structured Paper model, arXiv Atom, dedup,
relevance tagging, machine-readable export, module contract). Network-free:
all parsers are fed fixture XML/HTML strings.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

from enterprise.modules.paper_feeds import (
    Paper,
    create_paper_feeds_module,
    load_index,
    mark_new,
    parse_arxiv_atom,
    parse_arxiv_html,
    save_index,
    tag_paper,
)

ATOM_FIXTURE = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>ArXiv Query</title>
  <entry>
    <id>http://arxiv.org/abs/2301.00001v1</id>
    <title>Multi-Agent Collaboration for Autonomous Task Solving</title>
    <summary>We introduce a framework where multiple LLM agents cooperate on complex retrieval-augmented reasoning tasks, with fine-tuning to improve coordination.</summary>
    <published>2023-01-01T00:00:00Z</published>
    <author><name>Alice Lane</name></author>
    <author><name>Bob Coder</name></author>
    <link href="http://arxiv.org/abs/2301.00001v1" rel="alternate" type="text/html"/>
  </entry>
  <entry>
    <id>http://arxiv.org/abs/2301.00002v1</id>
    <title>Efficient Quantized Small Models for On-Device Inference</title>
    <summary>Methods to prune and quantize language models for edge deployment with minimal accuracy loss.</summary>
    <published>2023-01-02T00:00:00Z</published>
    <author><name>Carol Em</name></author>
    <link href="http://arxiv.org/abs/2301.00002v1" rel="alternate" type="text/html"/>
  </entry>
</feed>
"""

HTML_FIXTURE = """<html><body>
  <a href="/abs/2201.11111">A Robust Agent Benchmark for Tool Use</a>
  <a href="/abs/2201.22222">Video Diffusion World Models for Planning</a>
  <a href="/list/cs.AI">recent listing</a>
</body></html>"""

HF_FIXTURE = """<html><body>
  <a href="https://huggingface.co/papers/1234">RAG over Enterprise Knowledge Bases</a>
  <a href="https://huggingface.co/papers/5678">Jailbreak Defenses for Open Models</a>
</body></html>"""


def test_parse_arxiv_atom_structured():
    papers = parse_arxiv_atom(ATOM_FIXTURE)
    assert len(papers) == 2
    p = papers[0]
    assert isinstance(p, Paper)
    assert "Multi-Agent" in p.title
    assert p.source == "arxiv"
    assert p.authors == ["Alice Lane", "Bob Coder"]
    assert p.url.startswith("http")
    assert p.published == "2023-01-01"
    assert len(p.abstract) > 0


def test_parse_arxiv_html_fallback():
    papers = parse_arxiv_html(HTML_FIXTURE)
    # the "recent listing" link has short/ignorable text -> excluded
    assert len(papers) == 2
    assert all(p.source == "arxiv" for p in papers)


def test_tag_paper_relevance():
    papers = parse_arxiv_atom(ATOM_FIXTURE)
    p = papers[0]
    tag_paper(p)
    assert "agents" in p.tags
    assert "multiplayer" in p.tags      # "Multi-Agent Collaboration"
    assert "rag" in p.tags              # "retrieval-augmented"
    assert "finetune" in p.tags         # "fine-tuning"
    assert p.relevance == len(p.tags)
    # second is a local/efficiency paper
    p2 = papers[1]
    tag_paper(p2)
    assert "local" in p2.tags


def test_mark_new_dedup():
    papers = parse_arxiv_atom(ATOM_FIXTURE)
    seen = {papers[0].id}
    marked = mark_new(papers, seen)
    assert marked[0].is_new is False
    assert marked[1].is_new is True


def test_index_roundtrip(tmp_path):
    idx = tmp_path / "index.json"
    save_index(idx, {"a", "b", "c"})
    assert load_index(idx) == {"a", "b", "c"}
    assert json.loads(idx.read_text())["count"] == 3


def test_pull_feed_arxiv_uses_api(tmp_path):
    """pull_feed for arxiv should hit the Atom API; simulate with mocks."""
    import enterprise.modules.paper_feeds.papers as papers_mod
    original = papers_mod._fetch
    papers_mod._fetch = lambda url, **kw: ATOM_FIXTURE  # no network
    try:
        res = papers_mod.pull_feed("arxiv", tmp_path, date_str="2023-01-05")
    finally:
        papers_mod._fetch = original
    assert res["got"] == 2
    assert res["new"] <= 2
    md = Path(res["file"]).read_text()
    assert "Multi-Agent Collaboration" in md
    js = json.loads(Path(res["json"]).read_text())
    assert len(js) == 2 and js[0]["source"] == "arxiv"
    assert Path(res["csv"]).exists()


def test_pull_feed_unknown_feed(tmp_path):
    from enterprise.modules.paper_feeds.papers import pull_feed
    res = pull_feed("nope", tmp_path)
    assert res["error"] == "unknown feed"


def test_module_initializes(tmp_path):
    m = create_paper_feeds_module({"out_dir": str(tmp_path)})
    asyncio.run(m.initialize())
    assert asyncio.run(m.health_check()).value in ("healthy", "HEALTHY") or "HEALTHY" in str(asyncio.run(m.health_check()))
    assert (tmp_path / "index.json").parent.exists()
    asyncio.run(m.shutdown())


def test_imports_exposed():
    from enterprise.modules.paper_feeds import FEEDS, Paper, parse_arxiv_atom
    assert "arxiv" in FEEDS and "hf" in FEEDS
    assert callable(parse_arxiv_atom)
