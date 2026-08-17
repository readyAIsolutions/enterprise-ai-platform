"""Paper-feeds module — daily AI research digests (arXiv/HF/PwC/AlphaXiv).

WiFi-safe daily paper puller. Each feed is a single lightweight page fetch; we
persist clean markdown digests under data/papers/<date>/<feed>.md for use as
citable research in client-facing docs.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from enterprise.platform_kernel import HealthStatus, Module, module

from .papers import FEEDS, pull_all_feeds, pull_feed  # noqa: F401

logger = logging.getLogger("eni.papers")
__version__ = "1.0.0"


@module(
    name="paper_feeds",
    version="1.0.0",
    config_defaults={"out_dir": "data/papers"},
)
class PaperFeedsModule(Module):
    def __init__(self, config: Optional[dict[str, Any]] = None) -> None:
        super().__init__(config)
        self.status = HealthStatus.UNKNOWN

    async def initialize(self) -> None:
        self.status = HealthStatus.HEALTHY

    async def health_check(self) -> HealthStatus:
        return HealthStatus.HEALTHY

    async def shutdown(self) -> None:
        self.status = HealthStatus.UNKNOWN

    # facade
    def pull_today(self) -> Dict[str, Any]:
        out = self.config.get("out_dir", "data/papers")
        return pull_all_feeds(out)

    def pull_one(self, name: str) -> Dict[str, Any]:
        out = self.config.get("out_dir", "data/papers")
        return pull_feed(name, out)


def create_paper_feeds_module(config: Optional[dict[str, Any]] = None) -> PaperFeedsModule:
    return PaperFeedsModule(config=config or {})


__all__ = ["PaperFeedsModule", "create_paper_feeds_module", "pull_feed",
           "pull_all_feeds", "FEEDS", "__version__"]