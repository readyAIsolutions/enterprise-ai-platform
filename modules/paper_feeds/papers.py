"""Paper-feeds research intel engine — daily AI papers, rebuilt v2.0.

Rebuilt from the original v1 plain title-scraper into a structured research
intel engine. Changes that make it *better* than before:

* Structured data model  -> each item is a ``Paper`` (id, title, abstract,
  authors, url, source, published, tags, relevance), not a bare title string.
* Robust arXiv ingestion  -> uses the official arXiv Atom API
  (``export.arxiv.org``) parsed with ElementTree instead of regex-scraping the
  human HTML listing. Falls back to HTML parsing if the API is unreachable.
* Change detection       -> persists every seen paper id in an index; each daily
  digest marks/separates "NEW today" so client docs only surface fresh research
  instead of re-listing yesterday.
* Relevance tagging      -> classifies each paper into enterprise-relevant
  buckets (agents, multiplayer, rag, finetune, local, security, video, robotics,
  eval, embed) so LO can cite the right research fast.
* Machine-readable out   -> markdown digest *plus* JSON + CSV exports so
  downstream modules (context_routing, docs synthesizer) can consume it.
* WiFi-safe              -> gentle per-feed pacing, timeout + retry/backoff,
  no video floods — safe for our connection.

Feeds (all lightweight page/API fetches):
  arxiv    https://arxiv.org/list/cs.AI/recent   + Atom API (primary)
  hf       https://huggingface.co/papers          (trending / most-discussed)
  pwc      https://paperswithcode.com/latest      (papers paired with code)
  alphaxiv https://alphaxiv.org                   (papers + discussion threads)
"""
from __future__ import annotations

import csv
import html
import json
import re
import time
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

FEEDS: Dict[str, str] = {
    "arxiv": "http://export.arxiv.org/api/query?search_query=cat:cs.AI+OR+cat:cs.LG+OR+cat:cs.MA+OR+cat:cs.CL+OR+cat:cs.CY+OR+cat:cs.RO+OR+cat:cs.CV+OR+cat:q-fin.TR&sortBy=submittedDate&sortOrder=descending&start=0&max_results=60",
    "hf": "https://huggingface.co/papers",
    "pwc": "https://paperswithcode.com/latest",
    "alphaxiv": "https://alphaxiv.org",
    "deepmind": "https://deepmind.google/blog/rss.xml",
    "openai": "https://openai.com/news/rss.xml",
    "googleai": "https://blog.google/technology/ai/rss/",
}
# feeds parsed as RSS XML (title extraction)
RSS_FEEDS = {"deepmind", "openai", "googleai"}
# HTML fallback for arXiv in case the API is down
ARXIV_HTML = "https://arxiv.org/list/cs.AI/recent"

_ATOM_NS = {"a": "http://www.w3.org/2005/Atom"}

# relevance tags: each maps to a set of case-insensitive keywords
RELEVANCE_RULES: Dict[str, List[str]] = {
    "agents": ["agent", "multi-agent", "autonomous", "tool use", "tool-use", "act"],
    "multiplayer": ["multiplayer", "multi-player", "collaborat", "multi-agent", "multi agent", "cooperative", "coordination"],
    "rag": ["retrieval", "rag", "retrieval-augmented", "embedding", "vector", "knowledge base"],
    "finetune": ["fine-tun", "finetun", "instruction tun", "supervis", "sft"],
    "local": ["efficien", "quantiz", "prun", "small model", "resource-constrained", "on-device", "edge"],
    "security": ["secur", "privacy", "jailbreak", "red-team", "red team", "opsec", "poison", "inject"],
    "video": ["video", "diffusion", "generation", "image gen", "text-to-image", "world model"],
    "robotics": ["robot", "embodied", "manipulation", "control", "policy"],
    "eval": ["benchmark", "eval", "evaluation", "safety eval", "reasoning"],
    "embed": ["embedding", "retrieval", "vector", "sentence embed"],
}


@dataclass
class Paper:
    """A single research paper pulled from a feed."""
    id: str                      # stable identity (arxiv id / url)
    title: str
    source: str                  # feed name
    url: str = ""
    authors: List[str] = field(default_factory=list)
    abstract: str = ""
    published: str = ""
    tags: List[str] = field(default_factory=list)
    relevance: int = 0
    is_new: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _fetch(url: str, headers: Optional[dict] = None, timeout: float = 25,
           retries: int = 2, backoff: float = 1.0) -> Optional[str]:
    """Fetch a URL with retry/backoff. Returns decoded text or None."""
    h = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) ENIResearch/2.0"}
    if headers:
        h.update(headers)
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers=h)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read().decode("utf-8", "replace")
        except Exception:
            if attempt < retries:
                time.sleep(backoff * (attempt + 1))
                continue
            return None
    return None


def _clean(t: Optional[str]) -> str:
    if not t:
        return ""
    return html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", t))).strip()


def tag_paper(paper: Paper) -> Paper:
    """Classify a paper into enterprise-relevant buckets by keyword rules."""
    blob = f"{paper.title} {paper.abstract}".lower()
    tags: List[str] = []
    for tag, kws in RELEVANCE_RULES.items():
        if any(k in blob for k in kws):
            tags.append(tag)
    paper.tags = tags
    # relevance = number of matched high-value buckets (agents/multiplayer/rag/etc)
    paper.relevance = len(tags)
    return paper


# ---------------------------------------------------------------- arXiv Atom
def parse_arxiv_atom(xml_text: str) -> List[Paper]:
    """Parse the arXiv Atom API response into Papers (primary path)."""
    papers: List[Paper] = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return papers
    for entry in root.findall("a:entry", _ATOM_NS):
        title = _clean(entry.findtext("a:title", default="", namespaces=_ATOM_NS))
        if not title:
            continue
        eid = entry.findtext("a:id", default="", namespaces=_ATOM_NS).strip()
        summary = _clean(entry.findtext("a:summary", default="", namespaces=_ATOM_NS))
        published = entry.findtext("a:published", default="", namespaces=_ATOM_NS)[:10]
        _links = entry.findall("a:link", _ATOM_NS)
        link = _links[0].get("href") if _links else ""
        authors = [a.findtext("a:name", default="", namespaces=_ATOM_NS).strip()
                   for a in entry.findall("a:author", _ATOM_NS)]
        authors = [a for a in authors if a]
        if not link:
            link = eid
        papers.append(Paper(
            id=eid or link,
            title=title,
            source="arxiv",
            url=link,
            authors=authors[:6],
            abstract=summary[:600],
            published=published,
        ))
    return papers


def parse_arxiv_html(html_text: str) -> List[Paper]:
    """Fallback: extract titles/urls from the arXiv HTML listing."""
    papers: List[Paper] = []
    for m in re.finditer(
        r'<a href="(/abs/[^"]+)"[^>]*>\s*(.*?)\s*</a>', html_text, re.S):
        href, title = m.group(1), _clean(m.group(2))
        if not title or len(title) < 12:
            continue
        papers.append(Paper(id=href, title=title, source="arxiv",
                            url="https://arxiv.org" + href))
    # de-dup
    seen: set = set(); uniq: List[Paper] = []
    for p in papers:
        if p.id not in seen:
            seen.add(p.id); uniq.append(p)
    return uniq[:50]


# ----------------------------------------------------------- generic sources
def parse_generic_links(html_text: str, domains: List[str], source: str) -> List[Paper]:
    """Best-effort extraction of paper links/titles from HTML feeds."""
    out: List[Paper] = []
    pat = re.compile(r'<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', re.S)
    seen: set = set()
    for href, text in pat.findall(html_text):
        t = _clean(text)
        if not t or len(t) < 12:
            continue
        if not any(d in href for d in domains):
            continue
        pid = href.split("?")[0]
        if pid in seen:
            continue
        seen.add(pid)
        out.append(Paper(id=pid, title=t, source=source, url=href if href.startswith("http") else domains[0].split("//")[-1].split("/")[0] + href))
        if len(out) >= 50:
            break
    return out


# ---------------------------------------------------------------- dedup/index
def load_index(index_file: Path) -> set:
    """Load the set of paper ids already seen across prior runs."""
    if not index_file.exists():
        return set()
    try:
        data = json.loads(index_file.read_text(encoding="utf-8"))
        return set(data.get("seen", []))
    except Exception:
        return set()


def save_index(index_file: Path, seen_ids: set, meta: Optional[dict] = None) -> None:
    index_file.parent.mkdir(parents=True, exist_ok=True)
    index_file.write_text(json.dumps({
        "seen": sorted(seen_ids),
        "count": len(seen_ids),
        **(meta or {}),
    }, indent=2), encoding="utf-8")


def mark_new(papers: List[Paper], seen: set) -> List[Paper]:
    """Tag each paper as new based on whether its id was already seen."""
    for p in papers:
        p.is_new = p.id not in seen
    return papers


# -------------------------------------------------------------- RSS feeds
def parse_rss(xml_text: str, source: str) -> List[Paper]:
    """Best-effort parse of an RSS feed into Papers (title + link)."""
    papers: List[Paper] = []
    if not xml_text:
        return papers
    for m in re.finditer(r"<item>.*?</item>", xml_text, re.S):
        item = m.group(0)
        tm = re.search(r"<title>(.*?)</title>", item, re.S)
        title = tm.group(1) if tm else ""
        title = _clean(re.sub(r"<!\[CDATA\[(.*?)\]\]>", r"\1", title))
        link = ""
        lm = re.search(r"<link>(.*?)</link>", item, re.S)
        if lm:
            link = lm.group(1).strip()
        if not title:
            continue
        papers.append(Paper(id=link or title, title=title, source=source, url=link))
    return papers[:60]


# ------------------------------------------------------------------- digest
def _digest_md(papers: List[Paper], source: str, ds: str, url: str) -> str:
    new_papers = [p for p in papers if p.is_new]
    lines = [f"# Paper feed: {source} ({ds})", f"- source: {url}", ""]
    if not papers:
        lines.append("(no items parsed)")
        return "\n".join(lines)
    lines.append(f"- **{len(new_papers)} new** / {len(papers)} total today")
    lines.append("")
    for i, p in enumerate(papers, 1):
        marker = "🆕" if p.is_new else "•"
        tag_str = (" [{}]".format(", ".join(p.tags)) if p.tags else "")
        lines.append(f"{marker} **{p.title}**{tag_str}")
        if p.url:
            lines.append(f"  {p.url}")
        if p.authors:
            lines.append("  " + ", ".join(p.authors[:4]))
        if p.abstract:
            lines.append(f"  {p.abstract[:180]}…")
        lines.append("")
    return "\n".join(lines)


def _export_json(papers: List[Paper], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps([p.to_dict() for p in papers], indent=2,
                               ensure_ascii=False), encoding="utf-8")


def _export_csv(papers: List[Paper], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ["id", "title", "source", "url", "published", "tags",
                  "relevance", "is_new", "authors", "abstract"]
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for p in papers:
            row = p.to_dict()
            row["tags"] = ",".join(row["tags"])
            row["authors"] = ", ".join(row["authors"])
            writer.writerow(row)


# ------------------------------------------------------------------- runner
def pull_feed(name: str, out_dir: str | Path, date_str: Optional[str] = None,
              enable_dedup: bool = True) -> Dict[str, Any]:
    """Pull one feed. Returns {feed, got, new, file, json, csv, index, error}."""
    url = FEEDS.get(name)
    if not url:
        return {"feed": name, "got": 0, "new": 0, "error": "unknown feed"}
    ds = date_str or date.today().isoformat()
    feed_dir = Path(out_dir) / ds
    feed_dir.mkdir(parents=True, exist_ok=True)

    # seen index (for change detection)
    index_file = Path(out_dir) / "index.json"
    seen = load_index(index_file) if enable_dedup else set()
    newly_seen = seen

    papers: List[Paper] = []
    err = None
    if name == "arxiv":
        xml_text = _fetch(url, headers={"Accept": "application/atom+xml"})
        papers = parse_arxiv_atom(xml_text) if xml_text else []
        if not papers:  # API failed -> HTML fallback
            html_text = _fetch(ARXIV_HTML)
            papers = parse_arxiv_html(html_text or "")
            if not papers:
                err = "arxiv api + html both returned nothing"
    elif name == "pwc":
        html_text = _fetch(url)
        papers = parse_generic_links(html_text or "", ["paperswithcode.com"], "pwc")
    elif name in ("hf", "alphaxiv"):
        html_text = _fetch(url)
        domain = "huggingface.co" if name == "hf" else "alphaxiv.org"
        papers = parse_generic_links(html_text or "", [domain], name)
    elif name in RSS_FEEDS:
        xml_text = _fetch(url, headers={"Accept": "application/rss+xml, application/xml"})
        papers = parse_rss(xml_text or "", name)

    for p in papers:
        tag_paper(p)
    papers = mark_new(papers, seen)

    if enable_dedup:
        for p in papers:
            newly_seen.add(p.id)
        save_index(index_file, newly_seen, meta={"last_run": datetime.utcnow().isoformat()})

    out_file = feed_dir / f"{name}.md"
    out_file.write_text(_digest_md(papers, name, ds, url), encoding="utf-8")
    js = feed_dir / f"{name}.json"; _export_json(papers, js)
    cs = feed_dir / f"{name}.csv"; _export_csv(papers, cs)

    return {
        "feed": name,
        "got": len(papers),
        "new": sum(1 for p in papers if p.is_new),
        "file": str(out_file), "json": str(js), "csv": str(cs),
        "index": str(index_file),
        "error": err,
    }


def pull_all_feeds(out_dir: str | Path, feeds: Optional[List[str]] = None,
                   enable_dedup: bool = True) -> Dict[str, Any]:
    """Pull all configured feeds, WiFi-safe paced."""
    feeds = feeds or list(FEEDS)
    results = []
    for name in feeds:
        results.append(pull_feed(name, out_dir, enable_dedup=enable_dedup))
        time.sleep(1.5)  # gentle, WiFi-safe pacing
    return {"results": results,
            "total": sum(r.get("got", 0) for r in results),
            "new": sum(r.get("new", 0) for r in results)}


if __name__ == "__main__":
    import sys
    print(json.dumps(pull_all_feeds(sys.argv[1] if len(sys.argv) > 1 else "data/papers"),
                     indent=2))

__version__ = "2.0.0"
__all__ = ["Paper", "pull_feed", "pull_all_feeds", "parse_arxiv_atom",
           "parse_arxiv_html", "parse_generic_links", "tag_paper",
           "mark_new", "load_index", "save_index", "RELEVANCE_RULES",
           "FEEDS", "__version__", "parse_rss", "RSS_FEEDS"]
