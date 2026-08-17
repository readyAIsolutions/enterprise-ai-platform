"""Second Brain module — a knowledge capture & resurfacing engine.

Grounded in three real pulled JE Van Clief transcripts:

  * "Your Second Brain Is Not a Notes App" (-CUsfao6m7E)  — a second brain
    links ideas and carries metadata; plain storage becomes a "graveyard".
  * "Van Squared: A Free Local AI Model Labeled a 26-Year Archive"
    (mme027WZhgo) — a labeled long-term archive stays searchable/compounds.
  * "AI Since 2011: The Ideas That Outlive Every Model" (lDXCkx3Nla8) — ideas
    and first principles outlive any single model or tool.

Export surface:
  * SecondBrain — the capture/link/resurface/query/compounding engine.
  * Entry       — a single captured node with metadata + review state.
  * SecondBrainModule — the ENI platform Module wrapper.
  * create_second_brain_module(config) — factory used by the platform.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from enterprise.platform_kernel import HealthStatus, Module, module

from .second_brain import Entry, SecondBrain, make_second_brain  # noqa: F401

logger = logging.getLogger("eni.second_brain")
__version__ = "1.0.0"


@module(
    name="second_brain",
    version="1.0.0",
    config_defaults={
        "default_tags": [],
        "global_source": "eni",
        "compound_score_enabled": True,
    },
)
class SecondBrainModule(Module):
    """ENI platform wrapper around the SecondBrain engine."""

    def __init__(self, config: Optional[dict[str, Any]] = None) -> None:
        super().__init__(config)
        self.brain: Optional[SecondBrain] = None

    async def initialize(self) -> None:
        self.brain = make_second_brain()
        self.status = HealthStatus.HEALTHY
        logger.info("second_brain module initialized")

    async def health_check(self) -> HealthStatus:
        return (HealthStatus.HEALTHY if self.brain is not None
                else HealthStatus.UNHEALTHY)

    async def shutdown(self) -> None:
        self.brain = None
        self.status = HealthStatus.UNKNOWN

    # ------------------------------------------------------------- facade
    def capture(self, note: str, tags: Optional[list] = None,
                source: str = "") -> Dict[str, Any]:
        """Capture a note; returns the entry as a dict."""
        src = source or str(self._config.get("global_source", "eni"))
        e = self.brain.capture(note, tags or self._config.get("default_tags"),
                               source=src)
        return _entry_to_dict(e)

    def link_ideas(self, a: str, b: str) -> bool:
        return self.brain.link_ideas(a, b)

    def resurface(self) -> List[Dict[str, Any]]:
        return [_entry_to_dict(e) for e in self.brain.resurface()]

    def query_concept(self, term: str) -> List[Dict[str, Any]]:
        return [_entry_to_dict(e) for e in self.brain.query_concept(term)]

    def build_compounding_report(self) -> Dict[str, Any]:
        return self.brain.build_compounding_report()


def _entry_to_dict(e: Entry) -> Dict[str, Any]:
    return {
        "id": e.id,
        "text": e.text,
        "tags": list(e.tags),
        "source": e.source,
        "created_at": e.created_at.isoformat(),
        "next_review": e.next_review.isoformat(),
        "links": sorted(e.links),
    }


def create_second_brain_module(config: Optional[dict[str, Any]] = None) -> SecondBrainModule:
    return SecondBrainModule(config=config or {})


__all__ = ["SecondBrain", "Entry", "SecondBrainModule",
           "create_second_brain_module", "make_second_brain", "__version__"]
