"""
Source Ranker — Standalone source ranking utility.

Provides the SourcePriorities configuration and rank_source() function
for use outside the full ResearchVerificationModule context.

Per Research OS spec source priority order:
  1. Internal project documentation
  2. Official vendor documentation
  3. Standards organizations
  4. Academic literature
  5. High-quality technical publications
  6. Established community resources
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class SourcePriorities:
    """Configuration for source priority tiers with weights."""

    INTERNAL: float = 1.0
    VENDOR: float = 0.92
    STANDARDS: float = 0.85
    ACADEMIC: float = 0.72
    TECH_PUBLICATION: float = 0.58
    COMMUNITY: float = 0.35
    UNVERIFIED: float = 0.1

    def validate(self) -> bool:
        """Validate that priorities are monotonically decreasing."""
        values = [
            self.INTERNAL, self.VENDOR, self.STANDARDS,
            self.ACADEMIC, self.TECH_PUBLICATION, self.COMMUNITY,
            self.UNVERIFIED,
        ]
        for i in range(len(values) - 1):
            if values[i] < values[i + 1]:
                return False
        return True


class SourceRanker:
    """Standalone source ranker with configurable priority weights.

    Ranks sources by authority, relevance, and credibility.
    """

    def __init__(self, priorities: SourcePriorities | None = None) -> None:
        self._priorities = priorities or SourcePriorities()

    def rank(self, sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Rank sources by computed score.

        Each source dict should have:
          - name: str
          - tier: str (one of: internal, vendor, standards, academic,
                   tech_publication, community, unverified)
          - relevance: float (0.0-1.0, optional, default 0.8)

        Returns sources sorted by score descending with 'score' key added.
        """
        tier_map = {
            "internal": self._priorities.INTERNAL,
            "vendor": self._priorities.VENDOR,
            "standards": self._priorities.STANDARDS,
            "academic": self._priorities.ACADEMIC,
            "tech_publication": self._priorities.TECH_PUBLICATION,
            "community": self._priorities.COMMUNITY,
            "unverified": self._priorities.UNVERIFIED,
        }

        ranked: list[dict[str, Any]] = []
        for src in sources:
            tier_weight = tier_map.get(src.get("tier", "unverified"), self._priorities.UNVERIFIED)
            relevance = src.get("relevance", 0.8)
            credibility = src.get("credibility", tier_weight * 0.9)
            score = (tier_weight * 0.5) + (relevance * 0.3) + (credibility * 0.2)
            entry = {**src, "score": round(score, 3)}
            ranked.append(entry)

        ranked.sort(key=lambda s: s["score"], reverse=True)
        return ranked


def rank_source(name: str, tier: str = "unverified", relevance: float = 0.8, credibility: float | None = None) -> float:
    """Quickly compute a single source's rank score.

    Args:
        name: Source name/URL.
        tier: Authority tier string.
        relevance: Relevance to the research question (0.0-1.0).
        credibility: Estimated credibility (auto-computed if None).

    Returns:
        Rank score between 0.0 and 1.0.
    """
    priorities = SourcePriorities()
    tier_map = {
        "internal": priorities.INTERNAL,
        "vendor": priorities.VENDOR,
        "standards": priorities.STANDARDS,
        "academic": priorities.ACADEMIC,
        "tech_publication": priorities.TECH_PUBLICATION,
        "community": priorities.COMMUNITY,
        "unverified": priorities.UNVERIFIED,
    }
    tier_weight = tier_map.get(tier, priorities.UNVERIFIED)
    if credibility is None:
        credibility = tier_weight * 0.9
    score = (tier_weight * 0.5) + (relevance * 0.3) + (credibility * 0.2)
    return round(score, 3)