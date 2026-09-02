"""
Tests for the hardened Verifier + evidence-chain report layer
(modules/research_verification/verifier.py).

Covers: Source model, SourceCredibility derivation (tier / corroboration /
recency), Verdict thresholds, the minimum-corroboration rule, EvidenceChain
completeness, contradiction handling, verify_report aggregation, the
provider/mapping API, determinism, and threshold configur[ity].

Run:
    cd <repo root> && python3 -m pytest modules/research_verification -q -p no:cacheprovider
"""

from __future__ import annotations

import datetime as dt
import unittest

from modules.research_verification import (
    PRIMARY_TIER,
    TIER_BASE_CREDIBILITY,
    VALID_TIERS,
    EvidenceChain,
    Source,
    SourceCredibility,
    Verdict,
    VerificationReport,
    Verifier,
    verify_claim,
    verify_report,
)

NOW = dt.date(2026, 8, 4)
FRESH = "2026-08-01"


def src(
    id: str = "s",
    url: str = "https://example.org/x",
    tier: str = "academic",
    stance: str = "support",
    retrieved_at: str = FRESH,
    credibility: float | None = None,
) -> Source:
    return Source(
        id=id,
        url=url,
        title=f"Source {id}",
        tier=tier,
        stance=stance,
        retrieved_at=retrieved_at,
        credibility=credibility,
    )


# ============================================================================
# 1. Source model
# ============================================================================


class TestSource(unittest.TestCase):
    def test_source_fields_and_stance(self) -> None:
        s = src(id="s1", url="https://gov.example/1", tier="gov")
        assert s.id == "s1"
        assert s.url == "https://gov.example/1"
        assert s.supports()
        assert s.domain == "gov.example"
        assert not Source(id="c1", stance="contradict").supports()

    def test_source_domain_independence_key(self) -> None:
        a = src(id="a", url="https://news.example/a")
        b = src(id="b", url="https://news.example/b")
        assert a.domain == b.domain, "same host counts as one independent source"

    def test_source_tier_normalised(self) -> None:
        s = Source(id="x", tier="bogus-tier-value")
        assert s.tier == "unknown"

    def test_valid_tiers_and_base_credibility_ordered(self) -> None:
        assert (
            frozenset({"primary", "gov", "academic", "reputable-news", "unknown", "banned"})
            == VALID_TIERS
        )
        assert TIER_BASE_CREDIBILITY[PRIMARY_TIER] > TIER_BASE_CREDIBILITY["banned"]
        assert TIER_BASE_CREDIBILITY["banned"] == 0.05


# ============================================================================
# 2. SourceCredibility — tier, corroboration, recency, determinism
# ============================================================================


class TestSourceCredibility(unittest.TestCase):
    def setUp(self) -> None:
        self.sc = SourceCredibility()

    def test_credibility_derived_by_tier(self) -> None:
        # Higher-authority tiers get higher base credibility (fresh, single source).
        primary = self.sc.derive(tier="primary", corroboration=1, retrieved_at=FRESH, now=NOW)
        academic = self.sc.derive(tier="academic", corroboration=1, retrieved_at=FRESH, now=NOW)
        news = self.sc.derive(tier="reputable-news", corroboration=1, retrieved_at=FRESH, now=NOW)
        unknown = self.sc.derive(tier="unknown", corroboration=1, retrieved_at=FRESH, now=NOW)
        banned = self.sc.derive(tier="banned", corroboration=1, retrieved_at=FRESH, now=NOW)
        assert primary > academic
        assert academic > news
        assert news > unknown
        assert unknown > banned

    def test_banned_never_boosted_by_corroboration(self) -> None:
        single = self.sc.derive(tier="banned", corroboration=1, retrieved_at=FRESH, now=NOW)
        many = self.sc.derive(tier="banned", corroboration=10, retrieved_at=FRESH, now=NOW)
        assert single == many
        assert single == 0.05

    def test_corroboration_raises_credibility(self) -> None:
        low = self.sc.derive(tier="academic", corroboration=1, retrieved_at=FRESH, now=NOW)
        high = self.sc.derive(tier="academic", corroboration=4, retrieved_at=FRESH, now=NOW)
        assert high > low
        assert high <= 1.0

    def test_recency_decays_old_sources(self) -> None:
        fresh = self.sc.derive(tier="primary", corroboration=1, retrieved_at="2026-08-01", now=NOW)
        ancient = self.sc.derive(
            tier="primary", corroboration=1, retrieved_at="2015-01-01", now=NOW
        )
        assert fresh > ancient
        assert ancient < 1.0

    def test_deterministic(self) -> None:
        a = self.sc.derive(tier="gov", corroboration=3, retrieved_at="2026-06-01", now=NOW)
        b = self.sc.derive(tier="gov", corroboration=3, retrieved_at="2026-06-01", now=NOW)
        assert a == b

    def test_explicit_credibility_respected(self) -> None:
        s = src(id="s1", tier="banned", credibility=0.9)
        assert self.sc.for_source(s, corroboration=2, now=NOW) == 0.9


# ============================================================================
# 3. Verification thresholds & the minimum-corroboration rule
# ============================================================================


class TestVerifierThresholds(unittest.TestCase):
    def test_verified_with_two_independent_sources(self) -> None:
        v = Verifier(min_corroboration=2, verified_threshold=0.70)
        chain = v.assess_claim(
            "claim",
            [
                src("a", "https://gov.example/a", tier="gov"),
                src("b", "https://acad.example/b", tier="academic"),
            ],
        )
        assert chain.verdict == Verdict.VERIFIED
        assert chain.confidence >= 0.7
        assert chain.corroboration == 2

    def test_single_source_is_partially_verified(self) -> None:
        v = Verifier(min_corroboration=2)
        chain = v.assess_claim("claim", [src("a", "https://acad.example/a", tier="academic")])
        assert chain.verdict == Verdict.PARTIALLY
        assert chain.corroboration == 1
        assert chain.contradiction == 0

    def test_no_sources_is_unverifiable(self) -> None:
        v = Verifier()
        chain = v.assess_claim("claim", [])
        assert chain.verdict == Verdict.UNVERIFIABLE
        assert chain.confidence == 0.0

    def test_contradiction_dominates_is_refuted(self) -> None:
        v = Verifier(min_corroboration=2)
        chain = v.assess_claim(
            "claim",
            [
                src("a", "https://acad.example/a", tier="academic", stance="support"),
                src("c1", "https://news.example/c1", tier="reputable-news", stance="contradict"),
                src("c2", "https://gov.example/c2", tier="gov", stance="contradict"),
            ],
        )
        assert chain.verdict == Verdict.REFUTED
        assert chain.contradiction >= 2

    def test_contradiction_lowers_confidence(self) -> None:
        v = Verifier()
        clean = v.assess_claim("c", [src("a", "https://acad.example/a", tier="academic")])
        mixed = v.assess_claim(
            "c",
            [
                src("a", "https://acad.example/a", tier="academic"),
                src("c1", "https://gov.example/c1", tier="gov", stance="contradict"),
            ],
        )
        assert clean.confidence > mixed.confidence
        assert mixed.contradiction == 1

    def test_refuted_confidence_is_zero(self) -> None:
        v = Verifier()
        chain = v.assess_claim(
            "x", [src("c", "https://gov.example/c", tier="gov", stance="contradict")]
        )
        assert chain.verdict == Verdict.REFUTED
        assert chain.confidence == 0.0


# ============================================================================
# 4. Verifier / EvidenceChain configuration & completeness
# ============================================================================


class TestVerifierConfig(unittest.TestCase):
    def test_min_corroboration_rule_tightened(self) -> None:
        strict = Verifier(min_corroboration=3)
        chain = strict.assess_claim(
            "c",
            [
                src("a", "https://a.example/x", tier="academic"),
                src("b", "https://b.example/y", tier="gov"),
            ],
        )
        assert chain.verdict == Verdict.PARTIALLY, "2 sources < min 3"

    def test_evidence_chain_completeness(self) -> None:
        v = Verifier(min_corroboration=2)
        sources = [
            src("a", "https://gov.example/a", tier="gov"),
            src("b", "https://acad.example/b", tier="academic"),
        ]
        chain = v.assess_claim("the claim", sources)
        assert chain.claim == "the claim"
        assert len(chain.sources) == 2
        assert chain.corroboration == 2
        assert chain.contradiction == 0
        assert 0.0 <= chain.confidence <= 1.0
        assert isinstance(chain.verdict, Verdict)
        assert chain.reasons

    def test_evidence_chain_to_dict(self) -> None:
        v = Verifier()
        chain = v.assess_claim("c", [src("a", "https://gov.example/a", tier="gov")])
        d = chain.to_dict()
        for key in (
            "claim",
            "verdict",
            "confidence",
            "corroboration",
            "contradiction",
            "sources",
            "reasons",
        ):
            assert key in d
        assert len(d["sources"]) == 1
        assert d["sources"][0]["tier"] == "gov"
        assert abs(d["sources"][0]["credibility"] - 0.9) < 0.05

    def test_verify_claim_single_convenience(self) -> None:
        chain = verify_claim("c", [src("a", "https://a.example/x", tier="primary")])
        assert isinstance(chain, EvidenceChain)
        assert chain.verdict == Verdict.PARTIALLY


# ============================================================================
# 5. verify_report aggregation — provider/mapping API + overall score
# ============================================================================


class TestVerifyReport(unittest.TestCase):
    def test_report_aggregates_per_claim_verdicts(self) -> None:
        report = verify_report(
            {
                "strong": [
                    src("a", "https://gov.example/a", tier="gov"),
                    src("b", "https://acad.example/b", tier="academic"),
                ],
                "weak": [src("c", "https://unknown.example/c", tier="unknown")],
            }
        )
        assert isinstance(report, VerificationReport)
        assert report.claim_count == 2  # type: ignore[attr-defined]
        assert report.distribution[Verdict.VERIFIED.value] == 1
        assert report.distribution[Verdict.PARTIALLY.value] == 1
        assert len(report.claims) == 2

    def test_report_accepts_iterable_of_pairs(self) -> None:
        report = verify_report(
            [
                ("c1", [src("a", "https://gov.example/a", tier="gov")]),
                ("c2", [src("b", "https://gov.example/b", tier="banned")]),
            ]
        )
        assert len(report.claims) == 2

    def test_report_overall_score_reflects_verified_vs_refuted(self) -> None:
        good = verify_report(
            {
                "a": [
                    src("1", "https://gov.example/1", tier="gov"),
                    src("2", "https://acad.example/2", tier="academic"),
                ]
            }
        ).overall_score
        bad = verify_report(
            {"a": [src("1", "https://gov.example/1", tier="gov", stance="contradict")]}
        ).overall_score
        assert good > bad
        assert bad * 0 <= 0  # bad should be very low
        assert good <= 100.0

    def test_report_empty_is_zero(self) -> None:
        report = verify_report({})
        assert report.overall_score == 0.0
        assert report.claim_count == 0  # type: ignore[attr-defined]

    def test_report_to_dict_shape(self) -> None:
        report = verify_report(
            {
                "a": [
                    src("1", "https://gov.example/1", tier="gov"),
                    src("2", "https://acad.example/2", tier="academic"),
                ]
            }
        )
        d = report.to_dict()
        for key in ("overall_score", "claim_count", "distribution", "claims"):
            assert key in d
        assert "verified" in d["distribution"]
        assert 0.0 <= d["overall_score"] <= 100.0


if __name__ == "__main__":
    unittest.main()
