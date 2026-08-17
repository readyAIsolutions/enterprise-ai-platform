"""Paper-feeds module — daily AI research digests (arXiv/HF/PwC/AlphaXiv).

Rebuilt v2.0: structured ``Paper`` model, primary arXiv Atom API ingestion with
HTML fallback, change detection (only *new* papers surface in daily digests),
relevance tagging for the enterprise, and machine-readable JSON/CSV exports —
WiFi-safe, retry/backoff, gentle pacing.

Writes markdown + JSON + CSV under ``data/papers/<date>/<feed>.*`` plus a
persistent ``data/papers/index.json`` for change detection.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from enterprise.platform_kernel import HealthStatus, Module, module

from .papers import (  # noqa: F401
    RSS_FEEDS,
    FEEDS,
    Paper,
    load_index,
    mark_new,
    parse_arxiv_atom,
    parse_arxiv_html,
    parse_rss,
    pull_all_feeds,
    pull_feed,
    save_index,
    tag_paper,
)

logger = logging.getLogger("eni.papers")
__version__ = "2.0.0"


@module(
    name="paper_feeds",
    version="2.0.0",
    config_defaults={"out_dir": "data/papers", "enable_dedup": True},
)
class PaperFeedsModule(Module):
    def __init__(self, config: Optional[dict[str, Any]] = None) -> None:
        super().__init__(config)
        self.status = HealthStatus.UNKNOWN
        self._out_dir: Optional[Path] = None

    async def initialize(self) -> None:
        out = self.config.get("out_dir", "data/papers")
        if isinstance(out, str) and not out.startswith("/"):
            out = Path(__file__).resolve().parent.parent.parent / out
        self._out_dir = Path(out)
        self._out_dir.mkdir(parents=True, exist_ok=True)
        self.status = HealthStatus.HEALTHY

    async def health_check(self) -> HealthStatus:
        return HealthStatus.HEALTHY if self._out_dir is not None else HealthStatus.UNHEALTHY

    async def shutdown(self) -> None:
        self.status = HealthStatus.UNKNOWN

    def pull_today(self) -> Dict[str, Any]:
        return pull_all_feeds(self._out_dir or "data/papers",
                              enable_dedup=bool(self.config.get("enable_dedup", True)))

    def pull_one(self, name: str) -> Dict[str, Any]:
        return pull_feed(name, self._out_dir or "data/papers",
                         enable_dedup=bool(self.config.get("enable_dedup", True)))

    def seen_count(self) -> int:
        index = Path(self._out_dir or "data/papers") / "index.json"
        return len(load_index(index))


def create_paper_feeds_module(config: Optional[dict[str, Any]] = None) -> PaperFeedsModule:
    return PaperFeedsModule(config=config or {})


__all__ = ["PaperFeedsModule", "create_paper_feeds_module", "Paper",
           "pull_feed", "pull_all_feeds", "parse_arxiv_atom", "parse_arxiv_html",
           "tag_paper", "mark_new", "load_index", "save_index", "FEEDS",
           "__version__"]
