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
    Source,
    SourceCredibility,
    Verdict,
    EvidenceChain,
    Verifier,
    VerificationReport,
    verify_report,
    verify_claim,
    VALID_TIERS,
    TIER_BASE_CREDIBILITY,
    PRIMARY_TIER,
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
    def test_source_fields_and_stance(self):
        s = src(id="s1", url="https://gov.example/1", tier="gov")
        self.assertEqual(s.id, "s1")
        self.assertEqual(s.url, "https://gov.example/1")
        self.assertTrue(s.supports())
        self.assertEqual(s.domain, "gov.example")
        self.assertFalse(Source(id="c1", stance="contradict").supports())

    def test_source_domain_independence_key(self):
        a = src(id="a", url="https://news.example/a")
        b = src(id="b", url="https://news.example/b")
        self.assertEqual(a.domain, b.domain, "same host counts as one independent source")

    def test_source_tier_normalised(self):
        s = Source(id="x", tier="bogus-tier-value")
        self.assertEqual(s.tier, "unknown")

    def test_valid_tiers_and_base_credibility_ordered(self):
        self.assertEqual(
            VALID_TIERS, frozenset({"primary", "gov", "academic", "reputable-news", "unknown", "banned"})
        )
        self.assertGreater(TIER_BASE_CREDIBILITY[PRIMARY_TIER], TIER_BASE_CREDIBILITY["banned"])
        self.assertEqual(TIER_BASE_CREDIBILITY["banned"], 0.05)


# ============================================================================
# 2. SourceCredibility — tier, corroboration, recency, determinism
# ============================================================================


class TestSourceCredibility(unittest.TestCase):
    def setUp(self):
        self.sc = SourceCredibility()

    def test_credibility_derived_by_tier(self):
        # Higher-authority tiers get higher base credibility (fresh, single source).
        primary = self.sc.derive(tier="primary", corroboration=1, retrieved_at=FRESH, now=NOW)
        academic = self.sc.derive(tier="academic", corroboration=1, retrieved_at=FRESH, now=NOW)
        news = self.sc.derive(tier="reputable-news", corroboration=1, retrieved_at=FRESH, now=NOW)
        unknown = self.sc.derive(tier="unknown", corroboration=1, retrieved_at=FRESH, now=NOW)
        banned = self.sc.derive(tier="banned", corroboration=1, retrieved_at=FRESH, now=NOW)
        self.assertGreater(primary, academic)
        self.assertGreater(academic, news)
        self.assertGreater(news, unknown)
        self.assertGreater(unknown, banned)

    def test_banned_never_boosted_by_corroboration(self):
        single = self.sc.derive(tier="banned", corroboration=1, retrieved_at=FRESH, now=NOW)
        many = self.sc.derive(tier="banned", corroboration=10, retrieved_at=FRESH, now=NOW)
        self.assertEqual(single, many)
        self.assertEqual(single, 0.05)

    def test_corroboration_raises_credibility(self):
        low = self.sc.derive(tier="academic", corroboration=1, retrieved_at=FRESH, now=NOW)
        high = self.sc.derive(tier="academic", corroboration=4, retrieved_at=FRESH, now=NOW)
        self.assertGreater(high, low)
        self.assertLessEqual(high, 1.0)

    def test_recency_decays_old_sources(self):
        fresh = self.sc.derive(tier="primary", corroboration=1, retrieved_at="2026-08-01", now=NOW)
        ancient = self.sc.derive(tier="primary", corroboration=1, retrieved_at="2015-01-01", now=NOW)
        self.assertGreater(fresh, ancient)
        self.assertLess(ancient, 1.0)

    def test_deterministic(self):
        a = self.sc.derive(tier="gov", corroboration=3, retrieved_at="2026-06-01", now=NOW)
        b = self.sc.derive(tier="gov", corroboration=3, retrieved_at="2026-06-01", now=NOW)
        self.assertEqual(a, b)

    def test_explicit_credibility_respected(self):
        s = src(id="s1", tier="banned", credibility=0.9)
        self.assertEqual(self.sc.for_source(s, corroboration=2, now=NOW), 0.9)


# ============================================================================
# 3. Verification thresholds & the minimum-corroboration rule
# ============================================================================


class TestVerifierThresholds(unittest.TestCase):
    def test_verified_with_two_independent_sources(self):
        v = Verifier(min_corroboration=2, verified_threshold=0.70)
        chain = v.assess_claim(
            "claim",
            [
                src("a", "https://gov.example/a", tier="gov"),
                src("b", "https://acad.example/b", tier="academic"),
            ],
        )
        self.assertEqual(chain.verdict, Verdict.VERIFIED)
        self.assertGreaterEqual(chain.confidence, 0.70)
        self.assertEqual(chain.corroboration, 2)

    def test_single_source_is_partially_verified(self):
        v = Verifier(min_corroboration=2)
        chain = v.assess_claim("claim", [src("a", "https://acad.example/a", tier="academic")])
        self.assertEqual(chain.verdict, Verdict.PARTIALLY)
        self.assertEqual(chain.corroboration, 1)
        self.assertEqual(chain.contradiction, 0)

    def test_no_sources_is_unverifiable(self):
        v = Verifier()
        chain = v.assess_claim("claim", [])
        self.assertEqual(chain.verdict, Verdict.UNVERIFIABLE)
        self.assertEqual(chain.confidence, 0.0)

    def test_contradiction_dominates_is_refuted(self):
        v = Verifier(min_corroboration=2)
        chain = v.assess_claim(
            "claim",
            [
                src("a", "https://acad.example/a", tier="academic", stance="support"),
                src("c1", "https://news.example/c1", tier="reputable-news", stance="contradict"),
                src("c2", "https://gov.example/c2", tier="gov", stance="contradict"),
            ],
        )
        self.assertEqual(chain.verdict, Verdict.REFUTED)
        self.assertGreaterEqual(chain.contradiction, 2)

    def test_contradiction_lowers_confidence(self):
        v = Verifier()
        clean = v.assess_claim("c", [src("a", "https://acad.example/a", tier="academic")])
        mixed = v.assess_claim(
            "c",
            [
                src("a", "https://acad.example/a", tier="academic"),
                src("c1", "https://gov.example/c1", tier="gov", stance="contradict"),
            ],
        )
        self.assertGreater(clean.confidence, mixed.confidence)
        self.assertEqual(mixed.contradiction, 1)

    def test_refuted_confidence_is_zero(self):
        v = Verifier()
        chain = v.assess_claim("x", [src("c", "https://gov.example/c", tier="gov", stance="contradict")])
        self.assertEqual(chain.verdict, Verdict.REFUTED)
        self.assertEqual(chain.confidence, 0.0)


# ============================================================================
# 4. Verifier / EvidenceChain configuration & completeness
# ============================================================================


class TestVerifierConfig(unittest.TestCase):
    def test_min_corroboration_rule_tightened(self):
        strict = Verifier(min_corroboration=3)
        chain = strict.assess_claim(
            "c",
            [
                src("a", "https://a.example/x", tier="academic"),
                src("b", "https://b.example/y", tier="gov"),
            ],
        )
        self.assertEqual(chain.verdict, Verdict.PARTIALLY, "2 sources < min 3")

    def test_evidence_chain_completeness(self):
        v = Verifier(min_corroboration=2)
        sources = [
            src("a", "https://gov.example/a", tier="gov"),
            src("b", "https://acad.example/b", tier="academic"),
        ]
        chain = v.assess_claim("the claim", sources)
        self.assertEqual(chain.claim, "the claim")
        self.assertEqual(len(chain.sources), 2)
        self.assertEqual(chain.corroboration, 2)
        self.assertEqual(chain.contradiction, 0)
        self.assertTrue(0.0 <= chain.confidence <= 1.0)
        self.assertIsInstance(chain.verdict, Verdict)
        self.assertTrue(chain.reasons)

    def test_evidence_chain_to_dict(self):
        v = Verifier()
        chain = v.assess_claim("c", [src("a", "https://gov.example/a", tier="gov")])
        d = chain.to_dict()
        for key in ("claim", "verdict", "confidence", "corroboration", "contradiction", "sources", "reasons"):
            self.assertIn(key, d)
        self.assertEqual(len(d["sources"]), 1)
        self.assertEqual(d["sources"][0]["tier"], "gov")
        self.assertEqual(d["sources"][0]["credibility"], 0.9)

    def test_verify_claim_single_convenience(self):
        chain = verify_claim("c", [src("a", "https://a.example/x", tier="primary")])
        self.assertIsInstance(chain, EvidenceChain)
        self.assertEqual(chain.verdict, Verdict.PARTIALLY)


# ============================================================================
# 5. verify_report aggregation — provider/mapping API + overall score
# ============================================================================


class TestVerifyReport(unittest.TestCase):
    def test_report_aggregates_per_claim_verdicts(self):
        report = verify_report(
            {
                "strong": [
                    src("a", "https://gov.example/a", tier="gov"),
                    src("b", "https://acad.example/b", tier="academic"),
                ],
                "weak": [src("c", "https://unknown.example/c", tier="unknown")],
            }
        )
        self.assertIsInstance(report, VerificationReport)
        self.assertEqual(report.claim_count, 2)  # type: ignore[attr-defined]
        self.assertEqual(report.distribution[Verdict.VERIFIED.value], 1)
        self.assertEqual(report.distribution[Verdict.PARTIALLY.value], 1)
        self.assertEqual(len(report.claims), 2)

    def test_report_accepts_iterable_of_pairs(self):
        report = verify_report(
            [
                ("c1", [src("a", "https://gov.example/a", tier="gov")]),
                ("c2", [src("b", "https://gov.example/b", tier="banned")]),
            ]
        )
        self.assertEqual(len(report.claims), 2)

    def test_report_overall_score_reflects_verified_vs_refuted(self):
        good = verify_report(
            {
                "a": [
                    src("1", "https://gov.example/1", tier="gov"),
                    src("2", "https://acad.example/2", tier="academic"),
                ]
            }
        ).overall_score
        bad = verify_report({"a": [src("1", "https://gov.example/1", tier="gov", stance="contradict")]}).overall_score
        self.assertGreater(good, bad)
        self.assertGreaterEqual(0, bad * 0)  # bad should be very low
        self.assertLessEqual(good, 100.0)

    def test_report_empty_is_zero(self):
        report = verify_report({})
        self.assertEqual(report.overall_score, 0.0)
        self.assertEqual(report.claim_count, 0)  # type: ignore[attr-defined]

    def test_report_to_dict_shape(self):
        report = verify_report(
            {"a": [src("1", "https://gov.example/1", tier="gov"), src("2", "https://acad.example/2", tier="academic")]}
        )
        d = report.to_dict()
        for key in ("overall_score", "claim_count", "distribution", "claims"):
            self.assertIn(key, d)
        self.assertIn("verified", d["distribution"])
        self.assertTrue(0.0 <= d["overall_score"] <= 100.0)


if __name__ == "__main__":
    unittest.main()
