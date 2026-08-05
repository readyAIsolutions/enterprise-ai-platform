"""
Verifier — Hardened source-credibility verifier + evidence-chain report.

MASTER-CLASS verification layer for the Research & Verification OS. Adds a
real, evidence-anchored verification pipeline on top of the existing
Research OS engines:

  - Source              — immutable record of a single cited source
  - SourceCredibility   — derives a 0-1 credibility score from source tier
                          (primary/gov/academic/reputable-news/unknown/banned),
                          corroboration count (more independent sources -> higher),
                          and recency.
  - Verdict             — verified / partially / refuted / unverifiable
  - EvidenceChain       — evidence trail for one claim: {claim, sources,
                          corroboration, contradiction, confidence, verdict}
  - Verifier            — assess_claim(claim, sources) -> EvidenceChain with a
                          minimum-corroboration rule
  - verify_report       — aggregate a set of claims into a report with per-claim
                          verdicts and an overall verification score 0-100

Everything is stdlib-only and fully deterministic — no stubs, no randomness.
"""

from __future__ import annotations

import datetime as _dt
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

# ── Configuration constants ────────────────────────────────────────────────

# Canonical tiers for the verifier's credibility model.
PRIMARY_TIER = "primary"  # direct observation, original data
GOV_TIER = "gov"  # government / official records
ACADEMIC_TIER = "academic"  # peer-reviewed literature
NEWS_TIER = "reputable-news"  # established, fact-checked journalism
UNKNOWN_TIER = "unknown"  # no provenance signal
BANNED_TIER = "banned"  # known-low-integrity / disinformation

VALID_TIERS = frozenset(
    {PRIMARY_TIER, GOV_TIER, ACADEMIC_TIER, NEWS_TIER, UNKNOWN_TIER, BANNED_TIER}
)

# Base credibility by tier (0-1). Banned is held far below everything else.
TIER_BASE_CREDIBILITY: dict[str, float] = {
    PRIMARY_TIER: 0.95,
    GOV_TIER: 0.90,
    ACADEMIC_TIER: 0.85,
    NEWS_TIER: 0.70,
    UNKNOWN_TIER: 0.40,
    BANNED_TIER: 0.05,
}


# Recency windows (in days) with multiplicative freshness factors.
_RECENCY_BANDS: tuple[tuple[int, float], ...] = (
    (30, 1.00),  # ≤ 30 days old  — fully current
    (180, 0.98),  # ≤ 6 months
    (365, 0.95),  # ≤ 1 year
    (730, 0.90),  # ≤ 2 years
    (1825, 0.85),  # ≤ 5 years
)


def _parse_date(value: Any, now: _dt.date | None = None) -> _dt.date:
    """Parse an ISO-8601 date/datetime into a date (never returns None)."""
    if value is None:
        return now or _dt.date.today()
    if isinstance(value, _dt.datetime):
        return value.date()
    if isinstance(value, _dt.date):
        return value
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return now or _dt.date.today()
        # Accept trailing time components by truncating at the first space/T.
        head = text.split("T")[0].split(" ")[0]
        try:
            return _dt.date.fromisoformat(head)
        except ValueError:
            return now or _dt.date.today()
    return now or _dt.date.today()


def _clamp01(value: float) -> float:
    """Clamp a value into the inclusive [0, 1] range."""
    return max(0.0, min(1.0, value))


# ── Source ─────────────────────────────────────────────────────────────────


@dataclass
class Source:
    """An immutable record of a single cited source.

    Attributes:
        id: Unique identifier for the source.
        url: Where the source lives.
        title: Human-readable title.
        credibility: Pre-computed credibility in [0, 1]. If ``None`` the
            credibility is derived via :class:`SourceCredibility` at intake.
        tier: One of :data:`VALID_TIERS`.
        retrieved_at: ISO-8601 date or datetime when the source was retrieved.
        stance: ``"support"`` or ``"contradict"`` — which side of the claim
            this source sits on.
    """

    id: str
    url: str = ""
    title: str = ""
    credibility: float | None = None
    tier: str = UNKNOWN_TIER
    retrieved_at: str | None = None
    stance: str = "support"

    def __post_init__(self) -> None:
        if self.tier not in VALID_TIERS:
            # Tolerate unknown tier labels by normalising to 'unknown' rather
            # than crashing — provenance is weak but never fabricated.
            self.tier = UNKNOWN_TIER
        if self.stance not in ("support", "contradict"):
            self.stance = "support"

    @property
    def domain(self) -> str:
        """A lightweight independence key (host of the URL)."""
        if not self.url:
            return f"id-{self.id}"
        try:
            from urllib.parse import urlparse

            host = urlparse(self.url).netloc.lower()
            return host or f"id-{self.id}"
        except Exception:  # pragma: no cover - defensive
            return f"id-{self.id}"

    def supports(self, claim: str | None = None) -> bool:
        """True when this source supports (rather than contradicts) a claim."""
        return self.stance == "support"


# ── SourceCredibility ──────────────────────────────────────────────────────


class SourceCredibility:
    """Derives a 0-1 credibility score for a source.

    Credibility combines three independent signals:

    * **Tier** — the intrinsic authority of the source class.
    * **Corroboration** — more independent sources agreeing on the same claim
      raises credibility (diminishing returns, capped).
    * **Recency** — fresher sources score higher; very old material decays.

    The model is fully deterministic so identical inputs always yield
    identical credibility.
    """

    # Corroboration boost: each additional independent corroborating source
    # beyond the first adds this much, up to a cap.
    CORROBORATION_STEP = 0.04
    CORROBORATION_CAP = 0.20

    # Contradiction penalty scales with the number of contradicting sources.
    CONTRADICTION_STEP = 0.12
    CONTRADICTION_CAP = 0.55

    def __init__(self, base_credibility: Mapping[str, float] | None = None) -> None:
        self._base = dict(
            base_credibility if base_credibility is not None else TIER_BASE_CREDIBILITY
        )

    def derive(
        self,
        *,
        tier: str = UNKNOWN_TIER,
        corroboration: int = 1,
        retrieved_at: Any = None,
        now: _dt.date | None = None,
    ) -> float:
        """Compute credibility in [0, 1] from tier, corroboration, and recency.

        Args:
            tier: Source tier (see :data:`VALID_TIERS`).
            corroboration: Number of independent sources agreeing (≥ 1).
            retrieved_at: Retrieval timestamp for the recency adjustment.
            now: Reference "today" for recency (defaults to real today).

        Returns:
            A credibility score clamped to [0, 1] and rounded to 3 decimals.
        """
        tier = tier if tier in self._base else UNKNOWN_TIER
        base = self._base[tier]

        # Banned sources never benefit from corroboration.
        if tier == BANNED_TIER:
            return round(_clamp01(base), 3)

        # Corroboration: extra independent confirmations raise credibility.
        extra = max(0, int(corroboration) - 1)
        corr_boost = min(extra * self.CORROBORATION_STEP, self.CORROBORATION_CAP)
        credibility = base + corr_boost

        # Recency: multiplicative decay for older material.
        retrieved = _parse_date(retrieved_at, now=now)
        today = now or _dt.date.today()
        age_days = max(0, (today - retrieved).days)
        # Default to the oldest band's decay; override when a band matches.
        factor = _RECENCY_BANDS[-1][1]
        for band_days, band_factor in _RECENCY_BANDS:
            if age_days <= band_days:
                factor = band_factor
                break
        credibility *= factor

        return round(_clamp01(credibility), 3)

    def for_source(
        self, source: Source, corroboration: int = 1, now: _dt.date | None = None
    ) -> float:
        """Derive credibility for a :class:`Source`, honouring any pre-set value."""
        if source.credibility is not None:
            return round(_clamp01(source.credibility), 3)
        return self.derive(
            tier=source.tier,
            corroboration=corroboration,
            retrieved_at=source.retrieved_at,
            now=now,
        )


# ── Verdict ────────────────────────────────────────────────────────────────


class Verdict(StrEnum):
    """Possible verification outcomes for a claim."""

    VERIFIED = "verified"
    PARTIALLY = "partially"
    REFUTED = "refuted"
    UNVERIFIABLE = "unverifiable"

    # Base weight used when aggregating the overall report score.
    @property
    def report_weight(self) -> float:
        return {
            Verdict.VERIFIED: 1.0,
            Verdict.PARTIALLY: 0.5,
            Verdict.UNVERIFIABLE: 0.2,
            Verdict.REFUTED: 0.0,
        }[self]


# ── EvidenceChain ──────────────────────────────────────────────────────────


@dataclass
class EvidenceChain:
    """The complete evidence trail assembled for a single claim.

    Attributes:
        claim: The claim text being verified.
        sources: All sources considered (supporting and contradicting).
        corroboration: Number of independent supporting sources.
        contradiction: Number of independent contradicting sources.
        confidence: Final confidence in [0, 1].
        verdict: Derived :class:`Verdict`.
        reasons: Human-readable reasons behind the verdict.
    """

    claim: str
    sources: list[Source] = field(default_factory=list)
    corroboration: int = 0
    contradiction: int = 0
    confidence: float = 0.0
    verdict: Verdict = Verdict.UNVERIFIABLE
    reasons: list[str] = field(default_factory=list)

    @property
    def supporting(self) -> list[Source]:
        return [s for s in self.sources if s.supports()]

    @property
    def contradicting(self) -> list[Source]:
        return [s for s in self.sources if not s.supports()]

    @property
    def score(self) -> float:
        """Per-claim verification score in [0, 100]."""
        return round(100.0 * self.confidence * self.verdict.report_weight, 2)

    def to_dict(self) -> dict[str, Any]:
        return {
            "claim": self.claim,
            "verdict": self.verdict.value,
            "confidence": self.confidence,
            "corroboration": self.corroboration,
            "contradiction": self.contradiction,
            "score": self.score,
            "reasons": list(self.reasons),
            "sources": [
                {
                    "id": s.id,
                    "url": s.url,
                    "title": s.title,
                    "tier": s.tier,
                    "credibility": s.credibility
                    if s.credibility is not None
                    else SourceCredibility().for_source(s),
                    "stance": s.stance,
                }
                for s in self.sources
            ],
        }


# ── Verifier ───────────────────────────────────────────────────────────────


class Verifier:
    """Assesses individual claims against an evidence chain.

    Enforces a **minimum-corroboration rule**: a claim may only be marked
    VERIFIED when it is backed by at least ``min_corroboration`` independent
    supporting sources and sees no genuine contradiction.
    """

    def __init__(
        self,
        min_corroboration: int = 2,
        verified_threshold: float = 0.70,
        credibility: SourceCredibility | None = None,
    ) -> None:
        self.min_corroboration = max(1, int(min_corroboration))
        self.verified_threshold = _clamp01(verified_threshold)
        self.credibility = credibility or SourceCredibility()

    # ── Public API ─────────────────────────────────────────────────────────

    def assess_claim(self, claim: str, sources: Iterable[Source]) -> EvidenceChain:
        """Verify a single claim against its evidence chain.

        Args:
            claim: The claim text.
            sources: The sources gathered for this claim.

        Returns:
            A fully-populated :class:`EvidenceChain` including verdict and
            confidence.
        """
        source_list = list(sources)
        supporting: list[Source] = [s for s in source_list if s.supports()]
        contradicting: list[Source] = [s for s in source_list if not s.supports()]

        corroboration = self._independent_count(supporting)
        contradiction = self._independent_count(contradicting)

        # Assign a concrete credibility to each source (derive if unset).
        for src in source_list:
            if src.credibility is None:
                src.credibility = self.credibility.for_source(
                    src, corroboration=max(corroboration, 1)
                )

        confidence = self._compute_confidence(
            supporting, contradicting, corroboration, contradiction
        )
        verdict, reasons = self._judge(claim, corroboration, contradiction, confidence)

        return EvidenceChain(
            claim=claim,
            sources=source_list,
            corroboration=corroboration,
            contradiction=contradiction,
            confidence=round(_clamp01(confidence), 3),
            verdict=verdict,
            reasons=reasons,
        )

    # ── Internals ──────────────────────────────────────────────────────────

    @staticmethod
    def _independent_count(sources: list[Source]) -> int:
        """Count independent sources by distinct host / id."""
        keys: set[str] = set()
        for s in sources:
            keys.add(s.domain)
        return len(keys)

    def _compute_confidence(
        self,
        supporting: list[Source],
        contradicting: list[Source],
        corroboration: int,
        contradiction: int,
    ) -> float:
        """Combine corroboration, credibility, and contradiction into confidence."""
        if not supporting and not contradicting:
            return 0.0

        # Averaged credibility of independent supporting sources.
        support_creds = [s.credibility or 0.0 for s in supporting]
        base = sum(support_creds) / len(support_creds) if support_creds else 0.0

        # Corroboration raises confidence toward verified territory.
        if corroboration >= 1:
            base += min(corroboration * 0.05, 0.30)

        # Contradiction pushes confidence down.
        if contradiction:
            base -= min(
                contradiction * self.credibility.CONTRADICTION_STEP,
                self.credibility.CONTRADICTION_CAP,
            )

        return _clamp01(base)

    def _judge(
        self,
        claim: str,
        corroboration: int,
        contradiction: int,
        confidence: float,
    ) -> tuple[Verdict, list[str]]:
        reasons: list[str] = []

        # 1) No evidence at all -> unverifiable.
        if corroboration == 0 and contradiction == 0:
            return Verdict.UNVERIFIABLE, ["no evidence found for claim"]

        # 2) Genuine contradiction that dominates support -> refuted.
        if contradiction >= corroboration and corroboration > 0:
            reasons.append(
                f"contradicting sources ({contradiction}) >= supporting ({corroboration})"
            )
            return Verdict.REFUTED, reasons

        # Contradiction with zero support -> refuted.
        if contradiction > 0 and corroboration == 0:
            return Verdict.REFUTED, ["only contradicting evidence present"]

        # 3) Minimum-corroboration rule: need enough independent support,
        #    no contradiction, and high enough confidence -> verified.
        if (
            corroboration >= self.min_corroboration
            and contradiction == 0
            and confidence >= self.verified_threshold
        ):
            reasons.append(
                f"{corroboration} independent sources corroborate; "
                f"confidence {confidence:.2f} >= {self.verified_threshold:.2f}"
            )
            return Verdict.VERIFIED, reasons

        # 4) Anything with real support that falls short of verified -> partially.
        if corroboration > 0:
            reasons.append(
                f"insufficient corroboration ({corroboration} < "
                f"{self.min_corroboration}) or below confidence threshold"
            )
            return Verdict.PARTIALLY, reasons

        # Fallback safety net.
        return Verdict.UNVERIFIABLE, ["unable to determine verdict"]


# ── Report ─────────────────────────────────────────────────────────────────


@dataclass
class VerificationReport:
    """Aggregate report over many claims with an overall 0-100 score."""

    claims: list[EvidenceChain] = field(default_factory=list)

    @property
    def claim_count(self) -> int:
        """Number of claims in the report."""
        return len(self.claims)

    @property
    def overall_score(self) -> float:
        """Overall verification score in [0, 100] — mean of per-claim scores."""
        if not self.claims:
            return 0.0
        return round(sum(c.score for c in self.claims) / len(self.claims), 2)

    @property
    def distribution(self) -> dict[str, int]:
        counts: dict[str, int] = {v.value: 0 for v in Verdict}
        for c in self.claims:
            counts[c.verdict.value] += 1
        return counts

    def to_dict(self) -> dict[str, Any]:
        return {
            "overall_score": self.overall_score,
            "claim_count": len(self.claims),
            "distribution": self.distribution,
            "claims": [c.to_dict() for c in self.claims],
        }


def verify_report(
    claims: Mapping[str, Iterable[Source]] | Iterable[tuple[str, Iterable[Source]]],
    verifier: Verifier | None = None,
) -> VerificationReport:
    """Aggregate a set of claims into a :class:`VerificationReport`.

    Args:
        claims: Either a mapping ``{claim_text: [sources]}`` or an iterable of
            ``(claim_text, [sources])`` pairs.
        verifier: The :class:`Verifier` to use (a default is created if None).

    Returns:
        A :class:`VerificationReport` with per-claim verdicts and an overall
        0-100 score.
    """
    v = verifier or Verifier()

    if isinstance(claims, Mapping):
        pairs: list[Any] = list(claims.items())
    else:
        pairs = list(claims)

    chains: list[EvidenceChain] = [v.assess_claim(claim, sources) for claim, sources in pairs]
    return VerificationReport(claims=chains)


# Standalone convenience wrapper.
def verify_claim(
    claim: str, sources: Iterable[Source], verifier: Verifier | None = None
) -> EvidenceChain:
    """Verify a single claim, returning its :class:`EvidenceChain`."""
    return (verifier or Verifier()).assess_claim(claim, sources)


__all__ = [
    "Source",
    "SourceCredibility",
    "Verdict",
    "EvidenceChain",
    "Verifier",
    "VerificationReport",
    "verify_report",
    "verify_claim",
    "VALID_TIERS",
    "TIER_BASE_CREDIBILITY",
    "PRIMARY_TIER",
    "GOV_TIER",
    "ACADEMIC_TIER",
    "NEWS_TIER",
    "UNKNOWN_TIER",
    "BANNED_TIER",
]
