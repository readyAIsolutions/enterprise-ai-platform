"""
Evidence Synthesizer — Standalone evidence synthesis.

Synthesizes evidence, claims, and confidence assessments into
coherent findings, recommendations, and risk assessments.

Per Research OS spec deliverables:
  - Research plan
  - Evidence summary
  - Source inventory
  - Confidence assessment
  - Risk assessment
  - Recommendations
  - Knowledge update proposal
"""

from __future__ import annotations

import uuid
from typing import Any


class EvidenceSynthesizer:
    """Standalone evidence synthesizer.

    Produces narrative findings from structured research inputs.
    """

    def synthesize(self, inputs: dict[str, Any]) -> dict[str, Any]:
        """Synthesize research inputs into a structured report.

        Args:
            inputs: Dict with keys:
                - objective: str
                - domain: str (optional)
                - sources: list of source dicts
                - claims: list of claim dicts
                - confidence: dict with scores, aggregate, tier

        Returns:
            Synthesized report dict with summary, findings, recommendations,
            conflicts, gaps, and risk_assessment.
        """
        objective = inputs.get("objective", "Unknown objective")
        domain = inputs.get("domain", "general")
        sources = inputs.get("sources", [])
        claims = inputs.get("claims", [])
        confidence = inputs.get("confidence", {})

        claim_scores = confidence.get("scores", {})
        aggregate = confidence.get("aggregate", 0.0)
        tier = confidence.get("tier", "uncertain")

        # Key findings from high-confidence claims
        key_findings: list[str] = []
        for claim in claims:
            score = claim_scores.get(claim.get("id", ""), 0.0)
            if score >= 0.6:
                key_findings.append(
                    f"[{claim.get('kind', 'unknown').upper()}] {claim.get('text', '')} "
                    f"(confidence: {score:.2f})"
                )

        # Conflicts
        conflicts = [
            c.get("text", "") for c in claims
            if c.get("kind") == "conflicting"
        ]

        # Gaps (low-confidence claims)
        gaps = [
            f"Low confidence: {c.get('text', '')[:120]}..."
            for c in claims
            if claim_scores.get(c.get("id", ""), 0.0) < 0.4
        ]

        # Summary
        fact_count = sum(1 for c in claims if c.get("kind") == "fact")
        assumption_count = sum(1 for c in claims if c.get("kind") == "assumption")
        summary = (
            f"Research on '{objective}' ({domain}) synthesized {len(claims)} claims "
            f"from {len(sources)} sources. Found {fact_count} facts, {assumption_count} "
            f"assumptions, {len(conflicts)} conflicts. "
            f"Aggregate confidence: {aggregate:.2f} ({tier})."
        )

        # Recommendations
        recommendations = self._make_recommendations(aggregate, conflicts, gaps, domain)

        # Risk assessment
        risk = self._assess_risk(aggregate, conflicts, gaps)

        return {
            "synthesis_id": str(uuid.uuid4()),
            "summary": summary,
            "key_findings": key_findings,
            "recommendations": recommendations,
            "conflicts": conflicts,
            "gaps": gaps,
            "risk_assessment": risk,
        }

    @staticmethod
    def _make_recommendations(
        aggregate: float,
        conflicts: list[str],
        gaps: list[str],
        domain: str,
    ) -> list[str]:
        """Generate actionable recommendations."""
        recs: list[str] = []

        if aggregate >= 0.8:
            recs.append("Proceed with implementation based on high-confidence findings.")
        elif aggregate >= 0.6:
            recs.append("Proceed with caution — verify key claims before committing.")
        else:
            recs.append("Delay decision — conduct additional research to raise confidence.")

        if conflicts:
            recs.append(f"Resolve {len(conflicts)} conflicting claims before finalizing.")
        if gaps:
            recs.append(f"Investigate {len(gaps)} low-confidence areas with additional evidence.")
        if domain == "security":
            recs.append("Prioritize security review before deployment.")

        return recs

    @staticmethod
    def _assess_risk(
        aggregate: float,
        conflicts: list[str],
        gaps: list[str],
    ) -> str:
        """Assess overall risk level."""
        level = "LOW"
        reasons: list[str] = []

        if aggregate < 0.5:
            level = "HIGH"
            reasons.append("low aggregate confidence")
        elif aggregate < 0.7:
            level = "MEDIUM"
            reasons.append("moderate aggregate confidence")

        if conflicts:
            if level == "MEDIUM":
                level = "HIGH"
            reasons.append(f"{len(conflicts)} unresolved conflicts")

        if len(gaps) > 3:
            level = "HIGH"
            reasons.append(f"{len(gaps)} knowledge gaps")

        if not reasons:
            reasons.append("No significant risk factors")

        return f"Risk Level: {level} — {'; '.join(reasons)}."


# ── Convenience functions ──────────────────────────────────────────────────


def synthesize_evidence(inputs: dict[str, Any]) -> dict[str, Any]:
    """Synthesize evidence from a structured inputs dict.

    Args:
        inputs: Dict with objective, domain, sources, claims, confidence.

    Returns:
        Synthesized report dict.
    """
    return EvidenceSynthesizer().synthesize(inputs)


def generate_recommendations(
    aggregate: float,
    conflicts: int = 0,
    gaps: int = 0,
    domain: str = "general",
) -> list[str]:
    """Generate recommendations from summary metrics.

    Args:
        aggregate: Aggregate confidence score.
        conflicts: Number of conflicting claims.
        gaps: Number of knowledge gaps.
        domain: Research domain.

    Returns:
        List of recommendation strings.
    """
    fake_conflicts = [f"conflict_{i}" for i in range(conflicts)]
    fake_gaps = [f"gap_{i}" for i in range(gaps)]
    return EvidenceSynthesizer._make_recommendations(
        aggregate, fake_conflicts, fake_gaps, domain
    )