"""Paper-feed puller — daily AI papers from arXiv / HuggingFace / PaperswithCode /
AlphaXiv, WiFi-safe.

Each source is a single lightweight page fetch (no video floods). We save a
clean daily digest markdown per feed under data/papers/<date>/<feed>.md so you
can cite current research in client-facing docs.

Feeds
-----
* arxiv    : https://arxiv.org/list/cs.AI/recent   (raw arXiv daily list)
* hf       : https://huggingface.co/papers          (trending/most-discussed)
* pwc      : https://paperswithcode.com/latest      (papers paired with code)
* alphaxiv : https://alphaxiv.org                   (papers + discussion threads)

The hugginface feed is the fastest daily-scan (clean interface, shows what's
actually getting attention) — mark as preferred in docs.
"""
from __future__ import annotations

import html
import json
import re
import time
import urllib.request
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Dict, List, Optional

FEEDS = {
    "arxiv": "https://arxiv.org/list/cs.AI/recent",
    "hf": "https://huggingface.co/papers",
    "pwc": "https://paperswithcode.com/latest",
    "alphaxiv": "https://alphaxiv.org",
}


def _fetch(url: str, headers: Optional[dict] = None, timeout: float = 25) -> Optional[str]:
    h = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) ENIResearch/1.0"}
    if headers:
        h.update(headers)
    try:
        req = urllib.request.Request(url, headers=h)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8", "replace")
    except Exception:
        return None


def _clean(t: str) -> str:
    return html.unescape(t)


def parse_arxiv(html_text: str) -> List[str]:
    """Extract paper titles from arXiv cs.AI recent listing."""
    items = []
    # each entry: <div class="list-title mathjax"> <span class="descriptor">Title:</span> ...
    for m in re.finditer(
        r'class="list-title[^"]*">.*?Title:</span>\s*(.*?)</div>',
        html_text, re.S):
        title = _clean(re.sub(r"<[^>]+>", "", m.group(1))).strip()
        if title:
            items.append(title)
    return items


def parse_generic_links(html_text: str, domains: List[str]) -> List[str]:
    """Best-effort extraction: pull <a> titles/text near links to paper pages."""
    out = []
    pat = re.compile(r'<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', re.S)
    for href, text in pat.findall(html_text):
        t = _clean(re.sub(r"<[^>]+>", "", text)).strip()
        if not t or len(t) < 12:
            continue
        if any(d in href for d in domains):
            out.append(t)
    # de-dup preserving order
    seen = set(); uniq = []
    for t in out:
        if t not in seen:
            seen.add(t); uniq.append(t)
    return uniq[:50]


def pull_feed(name: str, out_dir: str | Path, date_str: Optional[str] = None) -> Dict[str, object]:
    """Pull one feed into a markdown digest. Returns {feed, got, file}."""
    url = FEEDS.get(name)
    if not url:
        return {"feed": name, "got": 0, "error": "unknown feed"}
    html_text = _fetch(url)
    ds = date_str or date.today().isoformat()
    feed_dir = Path(out_dir) / ds
    feed_dir.mkdir(parents=True, exist_ok=True)
    out_file = feed_dir / f"{name}.md"

    items: List[str] = []
    if name == "arxiv" and html_text:
        items = parse_arxiv(html_text)
    elif name == "pwc" and html_text:
        items = parse_generic_links(html_text, ["paperswithcode.com"])
    elif name in ("hf", "alphaxiv") and html_text:
        domains = ["huggingface.co"] if name == "hf" else ["alphaxiv.org"]
        items = parse_generic_links(html_text, domains)

    header = (f"# Paper feed: {name} ({ds})\n"
              f"- source: {url}\n\n")
    body = "\n".join(f"- {t}" for t in items) if items else "(no items parsed)"
    out_file.write_text(header + body, encoding="utf-8")
    return {"feed": name, "got": len(items), "file": str(out_file)}


def pull_all_feeds(out_dir: str | Path, feeds: Optional[List[str]] = None) -> Dict[str, object]:
    feeds = feeds or list(FEEDS)
    results = []
    for name in feeds:
        results.append(pull_feed(name, out_dir))
        time.sleep(1.5)  # gentle, WiFi-safe
    return {"results": results, "total": sum(r.get("got", 0) for r in results)}


if __name__ == "__main__":
    import sys
    print(json.dumps(pull_all_feeds(sys.argv[1] if len(sys.argv) > 1 else "data/papers"), indent=2))

__all__ = ["pull_feed", "pull_all_feeds", "parse_arxiv", "FEEDS", "__version__"]
__version__ = "1.0.0"