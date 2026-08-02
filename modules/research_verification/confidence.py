"""
Confidence Assigner — Standalone confidence computation.

Assigns confidence scores to claims based on:
  - Claim type (facts > assumptions > opinions > speculation)
  - Source credibility
  - Supporting evidence count
  - Contradicting evidence penalty
  - Corroboration (multiple sources agreeing)
"""

from __future__ import annotations

import uuid
from enum import Enum
from typing import Any


class ConfidenceTier(Enum):
    """Confidence tiers."""
    HIGH = "high"           # ≥ 0.80
    MODERATE = "moderate"   # ≥ 0.60
    LOW = "low"             # ≥ 0.40
    UNCERTAIN = "uncertain" # ≥ 0.20
    SPECULATIVE = "speculative"  # < 0.20


class ConfidenceAssigner:
    """Standalone confidence assigner.

    Computes confidence scores for claims using multi-factor analysis.
    """

    # Base confidence by claim type
    TYPE_BASES: dict[str, float] = {
        "fact": 0.85,
        "assumption": 0.50,
        "opinion": 0.40,
        "speculation": 0.25,
        "conflicting": 0.20,
    }

    # Source credibility by tier
    TIER_CREDIBILITY: dict[str, float] = {
        "internal": 0.90,
        "vendor": 0.95,
        "standards": 0.90,
        "academic": 0.75,
        "tech_publication": 0.60,
        "community": 0.35,
        "unverified": 0.10,
    }

    def assess(self, claims: list[dict[str, Any]], sources: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        """Assess confidence for a list of claims.

        Args:
            claims: List of claim dicts with keys: id, kind, supporting (list), contradicting (list).
            sources: List of source dicts with keys: id, credibility (optional).

        Returns:
            Assessment dict with per-claim scores, aggregate, tier, and reasoning.
        """
        src_map: dict[str, float] = {}
        if sources:
            for s in sources:
                cred = s.get("credibility", self.TIER_CREDIBILITY.get(s.get("tier", "unverified"), 0.1))
                src_map[s.get("id", "")] = cred

        scores: dict[str, float] = {}
        risks: list[str] = []

        for claim in claims:
            score = self._compute(claim, src_map)
            scores[claim["id"]] = round(score, 2)
            if score < 0.4:
                risks.append(f"Low confidence on claim {claim['id'][:8]}: {claim.get('text', '')[:60]}...")
            if claim.get("kind") == "conflicting":
                risks.append(f"Conflicting claim {claim['id'][:8]}")

        if scores:
            aggregate = sum(scores.values()) / len(scores)
        else:
            aggregate = 0.0

        tier = self._to_tier(aggregate)

        return {
            "assessment_id": str(uuid.uuid4()),
            "scores": scores,
            "aggregate": round(aggregate, 2),
            "tier": tier.value,
            "reasoning": self._reason(aggregate, tier, len(scores), len(risks)),
            "risk_factors": risks,
        }

    def _compute(self, claim: dict[str, Any], src_map: dict[str, float]) -> float:
        """Compute confidence score for a single claim."""
        kind = claim.get("kind", "assumption")
        base = self.TYPE_BASES.get(kind, 0.3)

        # Supporting evidence bonus
        support = len(claim.get("supporting", []) or claim.get("supporting_evidence", []))
        support_bonus = min(support * 0.05, 0.3)

        # Contradicting evidence penalty
        contradict = len(claim.get("contradicting", []) or claim.get("contradicting_evidence", []))
        contradict_penalty = contradict * 0.1

        # Source credibility boost
        source_id = claim.get("source_id", "")
        source_cred = src_map.get(source_id, 0.15)
        source_bonus = source_cred * 0.15

        score = base + support_bonus + source_bonus - contradict_penalty
        return max(0.0, min(1.0, score))

    @staticmethod
    def _to_tier(score: float) -> ConfidenceTier:
        if score >= 0.8:
            return ConfidenceTier.HIGH
        elif score >= 0.6:
            return ConfidenceTier.MODERATE
        elif score >= 0.4:
            return ConfidenceTier.LOW
        elif score >= 0.2:
            return ConfidenceTier.UNCERTAIN
        return ConfidenceTier.SPECULATIVE

    @staticmethod
    def _reason(aggregate: float, tier: ConfidenceTier, claim_count: int, risk_count: int) -> str:
        parts = [f"Aggregate: {aggregate:.2f} ({tier.value}). {claim_count} claims."]
        if risk_count:
            parts.append(f"{risk_count} risk factor(s).")
        return " ".join(parts)


# ── Convenience functions ──────────────────────────────────────────────────


def compute_confidence(claim: dict[str, Any], source_credibility: float = 0.5) -> float:
    """Compute confidence for a single claim.

    Args:
        claim: Claim dict with 'kind' key.
        source_credibility: Source credibility score (0.0-1.0).

    Returns:
        Confidence score (0.0-1.0).
    """
    ca = ConfidenceAssigner()
    return ca._compute(claim, {"default": source_credibility})


def aggregate_confidence(scores: list[float]) -> dict[str, Any]:
    """Aggregate a list of confidence scores into a summary.

    Returns dict with min, max, mean, median, and tier.
    """
    if not scores:
        return {"min": 0.0, "max": 0.0, "mean": 0.0, "median": 0.0, "tier": "speculative"}
    sorted_scores = sorted(scores)
    n = len(sorted_scores)
    median = sorted_scores[n // 2] if n % 2 == 1 else (sorted_scores[n // 2 - 1] + sorted_scores[n // 2]) / 2
    mean = sum(scores) / n
    tier = ConfidenceAssigner._to_tier(mean)
    return {
        "min": min(scores),
        "max": max(scores),
        "mean": round(mean, 3),
        "median": round(median, 3),
        "tier": tier.value,
    }