#!/usr/bin/env python3
"""
Comprehensive test suite for Research & Verification OS enterprise module (26 tests).

Covers: ResearchVerificationModule lifecycle, ResearchPlanner, SourceRanker,
ClaimDetector, ConfidenceAssigner, EvidenceSynthesizer, ProvenanceTracker,
standalone components, edge cases, and full pipeline execution.

Usage:
    python3 -m pytest enterprise/modules/research_verification/tests/tests_research.py -v -p no:anyio
"""

import sys
import os
import unittest

# Ensure the module is importable
_MODULE_PARENT = os.path.join(os.path.dirname(__file__), "..", "..")
if _MODULE_PARENT not in sys.path:
    sys.path.insert(0, os.path.abspath(_MODULE_PARENT))

# Ensure Eni Builder root is on path
_BUILDER_ROOT = os.path.abspath(os.path.join(_MODULE_PARENT, ".."))
if _BUILDER_ROOT not in sys.path:
    sys.path.insert(0, _BUILDER_ROOT)

from enterprise.platform_kernel import HealthStatus
from enterprise.modules.research_verification import (
    ResearchVerificationModule,
    ResearchPlanner,
    SourceRanker,
    ClaimDetector,
    ConfidenceAssigner,
    EvidenceSynthesizer,
    ProvenanceTracker,
    ResearchPlan,
    RankedSource,
    DetectedClaim,
    ConfidenceAssessment,
    SynthesizedEvidence,
    ProvenanceRecord,
    ResearchFindings,
    ResearchDomain,
    SourceTier,
    ClaimType,
    ConfidenceLevel,
)


# ============================================================================
# Test helpers
# ============================================================================

def _run(coro):
    """Run coroutine synchronously."""
    import asyncio
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                return pool.submit(asyncio.run, coro).result()
        return loop.run_until_complete(coro)
    except RuntimeError:
        return asyncio.run(coro)


# ============================================================================
# Test 1-3: Module Lifecycle
# ============================================================================

class TestModuleLifecycle(unittest.TestCase):
    """Tests for ResearchVerificationModule lifecycle."""

    def setUp(self):
        self.module = ResearchVerificationModule(config={"planner": {}, "ranker": {}})

    def test_01_module_creation(self):
        """Module is created with correct metadata."""
        self.assertEqual(self.module.name, "research_verification")
        self.assertEqual(self.module.version, "1.0.0")
        self.assertIsNotNone(self.module.module_id)

    def test_02_initialize_creates_all_engines(self):
        """initialize() creates all six research engines."""
        _run(self.module.initialize())
        self.assertIsNotNone(self.module.planner)
        self.assertIsNotNone(self.module.ranker)
        self.assertIsNotNone(self.module.detector)
        self.assertIsNotNone(self.module.confidence)
        self.assertIsNotNone(self.module.synthesizer)
        self.assertIsNotNone(self.module.tracker)
        self.assertEqual(self.module.status, HealthStatus.HEALTHY)

    def test_03_shutdown_clears_all_engines(self):
        """shutdown() nullifies all engines."""
        _run(self.module.initialize())
        _run(self.module.shutdown())
        self.assertIsNone(self.module.planner)
        self.assertIsNone(self.module.ranker)
        self.assertIsNone(self.module.detector)
        self.assertIsNone(self.module.confidence)
        self.assertIsNone(self.module.synthesizer)
        self.assertIsNone(self.module.tracker)


# ============================================================================
# Test 4-6: Health Check
# ============================================================================

class TestHealthCheck(unittest.TestCase):
    """Tests for health check behavior."""

    def test_04_health_check_healthy(self):
        """Health check returns HEALTHY when all engines initialized."""
        module = ResearchVerificationModule()
        _run(module.initialize())
        status = _run(module.health_check())
        self.assertEqual(status, HealthStatus.HEALTHY)

    def test_05_health_check_unhealthy_before_init(self):
        """Health check returns UNHEALTHY when not initialized."""
        module = ResearchVerificationModule()
        status = _run(module.health_check())
        self.assertEqual(status, HealthStatus.UNHEALTHY)


# ============================================================================
# Test 7-10: ResearchPlanner
# ============================================================================

class TestResearchPlanner(unittest.TestCase):
    """Tests for ResearchPlanner."""

    def test_06_create_plan_basic(self):
        """create_plan generates a valid ResearchPlan."""
        planner = ResearchPlanner()
        plan = planner.create_plan("What is the best Python async pattern?")
        self.assertIsInstance(plan, ResearchPlan)
        self.assertTrue(len(plan.plan_id) > 0)
        self.assertIn("Python", plan.objective)
        self.assertIsInstance(plan.domain, ResearchDomain)
        self.assertGreater(len(plan.questions), 0)

    def test_07_domain_classification_engineering(self):
        """Objective with 'code'/'implement' → ENGINEERING domain."""
        planner = ResearchPlanner()
        plan = planner.create_plan("Implement a REST API with FastAPI")
        self.assertEqual(plan.domain, ResearchDomain.ENGINEERING)

    def test_08_domain_classification_security(self):
        """Objective with 'vulnerability' → SECURITY domain."""
        planner = ResearchPlanner()
        plan = planner.create_plan("What are the security vulnerabilities in JWT?")
        self.assertEqual(plan.domain, ResearchDomain.SECURITY)

    def test_09_domain_hint_override(self):
        """Domain hint overrides auto-classification."""
        planner = ResearchPlanner()
        plan = planner.create_plan("Build something", domain_hint="performance")
        self.assertEqual(plan.domain, ResearchDomain.PERFORMANCE)

    def test_10_add_source_to_plan(self):
        """add_source appends to plan sources."""
        planner = ResearchPlanner()
        plan = planner.create_plan("Test")
        result = planner.add_source(plan.plan_id, "https://docs.python.org")
        self.assertTrue(result)
        self.assertIn("https://docs.python.org", plan.sources)


# ============================================================================
# Test 11-14: SourceRanker
# ============================================================================

class TestSourceRanker(unittest.TestCase):
    """Tests for SourceRanker."""

    def test_11_rank_sources_by_tier(self):
        """Sources are ranked by authority tier (vendor > community)."""
        ranker = SourceRanker()
        sources = [
            "https://docs.python.org/3/library/asyncio.html",
            "https://github.com/some-random/repo",
        ]
        ranked = ranker.rank(sources)
        self.assertEqual(len(ranked), 2)
        # vendor docs should outrank github
        self.assertGreater(ranked[0].score, ranked[1].score)
        self.assertEqual(ranked[0].tier, SourceTier.VENDOR_OFFICIAL)

    def test_12_rank_standards_org(self):
        """IETF/W3C sources classified as STANDARDS_ORG."""
        ranker = SourceRanker()
        ranked = ranker.rank(["https://www.ietf.org/rfc/rfc2616.txt"])
        self.assertEqual(ranked[0].tier, SourceTier.STANDARDS_ORG)

    def test_13_rank_academic_source(self):
        """.edu / arxiv classified as ACADEMIC."""
        ranker = SourceRanker()
        ranked = ranker.rank(["https://arxiv.org/abs/2301.00001"])
        self.assertEqual(ranked[0].tier, SourceTier.ACADEMIC)

    def test_14_rank_empty_list(self):
        """Ranking empty list returns empty list."""
        ranker = SourceRanker()
        ranked = ranker.rank([])
        self.assertEqual(ranked, [])


# ============================================================================
# Test 15-18: ClaimDetector
# ============================================================================

class TestClaimDetector(unittest.TestCase):
    """Tests for ClaimDetector."""

    def test_15_classify_fact(self):
        """Factual statement classified as FACT."""
        detector = ClaimDetector()
        claim_type = detector.classify("The Earth is round and has been confirmed by observation.")
        self.assertEqual(claim_type, ClaimType.FACT)

    def test_16_classify_assumption(self):
        """Statement with 'probably' classified as ASSUMPTION."""
        detector = ClaimDetector()
        claim_type = detector.classify("This feature probably works for all edge cases.")
        self.assertEqual(claim_type, ClaimType.ASSUMPTION)

    def test_17_classify_speculation(self):
        """Statement with 'might be' classified as SPECULATION."""
        detector = ClaimDetector()
        claim_type = detector.classify("The bug might be related to memory corruption.")
        self.assertEqual(claim_type, ClaimType.SPECULATION)

    def test_18_detect_conflicting_claims(self):
        """Conflicting claims are detected and marked."""
        detector = ClaimDetector()
        claims = detector.detect(
            ["Python is fast. Python is not fast for CPU-bound tasks."],
            ResearchDomain.ENGINEERING,
        )
        conflict_count = sum(1 for c in claims if c.claim_type == ClaimType.CONFLICTING)
        self.assertGreater(conflict_count, 0)


# ============================================================================
# Test 19-22: ConfidenceAssigner
# ============================================================================

class TestConfidenceAssigner(unittest.TestCase):
    """Tests for ConfidenceAssigner."""

    def test_19_high_confidence_on_facts(self):
        """Facts with credible sources get HIGH confidence."""
        assigner = ConfidenceAssigner()
        claims = [
            DetectedClaim(
                claim_id="c1", text="Python 3.12 is released.",
                claim_type=ClaimType.FACT, source_id="s1",
            ),
        ]
        sources = [
            RankedSource(
                source_id="s1", name="python.org", url="https://python.org",
                tier=SourceTier.VENDOR_OFFICIAL, score=0.95, relevance=1.0,
                credibility=0.95,
            ),
        ]
        assessment = assigner.assess(claims, sources)
        self.assertGreater(assessment.aggregate_confidence, 0.7)
        self.assertEqual(assessment.level, ConfidenceLevel.HIGH)

    def test_20_low_confidence_on_speculation(self):
        """Speculative claims get LOW or lower confidence."""
        assigner = ConfidenceAssigner()
        claims = [
            DetectedClaim(
                claim_id="c1", text="Maybe this will work someday.",
                claim_type=ClaimType.SPECULATION, source_id="s1",
            ),
        ]
        sources = [
            RankedSource(
                source_id="s1", name="random", url="",
                tier=SourceTier.UNVERIFIED, score=0.1, relevance=0.5,
                credibility=0.1,
            ),
        ]
        assessment = assigner.assess(claims, sources)
        self.assertLess(assessment.aggregate_confidence, 0.5)

    def test_21_contradictory_evidence_penalty(self):
        """Contradictory evidence reduces confidence."""
        assigner = ConfidenceAssigner()
        claims = [
            DetectedClaim(
                claim_id="c1", text="X is true.",
                claim_type=ClaimType.FACT, source_id="s1",
                contradicting_evidence=["X is false", "X is not true"],
            ),
        ]
        sources = [
            RankedSource(
                source_id="s1", name="python.org", url="",
                tier=SourceTier.VENDOR_OFFICIAL, score=0.9, relevance=1.0,
                credibility=0.9,
            ),
        ]
        assessment = assigner.assess(claims, sources)
        # With 2 contradicting pieces, confidence should be lower
        score = assessment.findings["c1"]
        self.assertLess(score, 0.9)  # penalized from base

    def test_22_risk_factors_generated(self):
        """Low-confidence findings generate risk factors."""
        assigner = ConfidenceAssigner()
        claims = [
            DetectedClaim(
                claim_id="c1", text="Uncertain claim here.",
                claim_type=ClaimType.SPECULATION, source_id="s1",
            ),
        ]
        sources = [
            RankedSource(
                source_id="s1", name="unknown", url="",
                tier=SourceTier.UNVERIFIED, score=0.1, relevance=0.5,
                credibility=0.1,
            ),
        ]
        assessment = assigner.assess(claims, sources)
        self.assertGreater(len(assessment.risk_factors), 0)


# ============================================================================
# Test 23-24: EvidenceSynthesizer
# ============================================================================

class TestEvidenceSynthesizer(unittest.TestCase):
    """Tests for EvidenceSynthesizer."""

    def test_23_synthesize_creates_report(self):
        """Synthesize produces a full report with all sections."""
        synthesizer = EvidenceSynthesizer()
        plan = ResearchPlan(
            plan_id="p1", objective="Test async patterns",
            domain=ResearchDomain.ENGINEERING,
        )
        sources = [
            RankedSource(
                source_id="s1", name="python.org", url="https://python.org",
                tier=SourceTier.VENDOR_OFFICIAL, score=0.95, relevance=1.0,
                credibility=0.95,
            ),
        ]
        claims = [
            DetectedClaim(
                claim_id="c1", text="asyncio is the recommended async library.",
                claim_type=ClaimType.FACT, source_id="s1",
            ),
        ]
        confidence = ConfidenceAssessment(
            assessment_id="a1",
            findings={"c1": 0.95},
            aggregate_confidence=0.95,
            level=ConfidenceLevel.HIGH,
        )
        evidence = synthesizer.synthesize(plan, sources, claims, confidence)
        self.assertIsInstance(evidence, SynthesizedEvidence)
        self.assertGreater(len(evidence.summary), 0)
        self.assertGreater(len(evidence.key_findings), 0)
        # Should generate recommendations
        self.assertGreater(len(evidence.recommendations), 0)

    def test_24_synthesize_security_recommendation(self):
        """Security domain gets security-specific recommendation."""
        synthesizer = EvidenceSynthesizer()
        plan = ResearchPlan(
            plan_id="p2", objective="Security audit",
            domain=ResearchDomain.SECURITY,
        )
        sources: list[RankedSource] = []
        claims: list[DetectedClaim] = []
        confidence = ConfidenceAssessment(
            assessment_id="a2",
            findings={},
            aggregate_confidence=0.9,
            level=ConfidenceLevel.HIGH,
        )
        evidence = synthesizer.synthesize(plan, sources, claims, confidence)
        self.assertTrue(
            any("security" in r.lower() for r in evidence.recommendations),
            "Security domain should get security-specific recommendation",
        )


# ============================================================================
# Test 25: ProvenanceTracker
# ============================================================================

class TestProvenanceTracker(unittest.TestCase):
    """Tests for ProvenanceTracker."""

    def test_25_record_and_retrieve(self):
        """Provenance records can be created and retrieved."""
        tracker = ProvenanceTracker()
        plan = ResearchPlan(
            plan_id="p1", objective="Test provenance",
            domain=ResearchDomain.GENERAL,
        )
        sources = [
            RankedSource(
                source_id="s1", name="source1", url="https://example.com",
                tier=SourceTier.VENDOR_OFFICIAL, score=0.9, relevance=1.0,
                credibility=0.9,
            ),
        ]
        claims = [
            DetectedClaim(
                claim_id="c1", text="This is a test claim.",
                claim_type=ClaimType.FACT, source_id="s1",
            ),
        ]
        confidence = ConfidenceAssessment(
            assessment_id="a1",
            findings={"c1": 0.9},
            aggregate_confidence=0.9,
            level=ConfidenceLevel.HIGH,
        )
        evidence = SynthesizedEvidence(
            synthesis_id="e1", summary="Test synthesis.",
        )
        record = tracker.record(plan, sources, claims, confidence, evidence)
        self.assertEqual(record.version, 1)
        self.assertGreater(len(record.source_chain), 0)
        self.assertGreater(len(record.transformation_log), 0)

        # Retrieve
        retrieved = tracker.get_record(record.record_id)
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved.plan_id, "p1")

    def test_26_version_history(self):
        """Multiple recordings for same plan create version history."""
        tracker = ProvenanceTracker()
        plan = ResearchPlan(
            plan_id="p2", objective="Version test",
            domain=ResearchDomain.GENERAL,
        )
        sources: list[RankedSource] = []
        claims: list[DetectedClaim] = []
        confidence = ConfidenceAssessment(assessment_id="a1")
        evidence = SynthesizedEvidence(synthesis_id="e1", summary="v1")

        # Record twice
        r1 = tracker.record(plan, sources, claims, confidence, evidence)
        r2 = tracker.record(plan, sources, claims, confidence, evidence)

        self.assertEqual(r1.version, 1)
        self.assertEqual(r2.version, 2)
        self.assertIn(r1.record_id, r2.predecessors)

        history = tracker.get_version_history("p2")
        self.assertEqual(len(history), 2)

    def test_27_audit_trail(self):
        """Audit trail provides full transformation log."""
        tracker = ProvenanceTracker()
        plan = ResearchPlan(
            plan_id="p3", objective="Audit test",
            domain=ResearchDomain.GENERAL,
        )
        sources: list[RankedSource] = []
        claims: list[DetectedClaim] = []
        confidence = ConfidenceAssessment(assessment_id="a1")
        evidence = SynthesizedEvidence(synthesis_id="e1", summary="audit")

        tracker.record(plan, sources, claims, confidence, evidence)
        trail = tracker.audit_trail("p3")
        self.assertEqual(len(trail), 1)
        self.assertIn("transformations", trail[0])


# ============================================================================
# Test 28-29: Full Pipeline
# ============================================================================

class TestFullPipeline(unittest.TestCase):
    """End-to-end pipeline tests."""

    def test_28_full_pipeline_execution(self):
        """execute_pipeline runs the complete Research OS workflow."""
        module = ResearchVerificationModule()
        _run(module.initialize())

        findings = _run(module.execute_pipeline(
            objective="What is the best async Python library?",
            domain_hint="engineering",
        ))
        self.assertIsInstance(findings, ResearchFindings)
        self.assertIsNotNone(findings.plan)
        self.assertIsNotNone(findings.confidence)
        self.assertIsNotNone(findings.evidence)
        self.assertIsNotNone(findings.provenance)
        self.assertIsNotNone(findings.completed_at)

    def test_29_pipeline_without_init_raises(self):
        """Pipeline raises RuntimeError if module not initialized."""
        module = ResearchVerificationModule()
        with self.assertRaises(RuntimeError):
            _run(module.execute_pipeline("Test"))


# ============================================================================
# Test 30-32: Standalone components
# ============================================================================

class TestStandaloneComponents(unittest.TestCase):
    """Tests for standalone source_ranker, claim_detector, confidence, evidence_synthesizer."""

    def test_30_rank_source_function(self):
        """rank_source() standalone function works."""
        from enterprise.modules.research_verification import rank_source
        score = rank_source("https://docs.python.org", tier="vendor", relevance=1.0)
        self.assertGreater(score, 0.5)

    def test_31_classify_claim_function(self):
        """classify_claim() standalone function works."""
        from enterprise.modules.research_verification import classify_claim, extract_claims
        kind = classify_claim("This is a confirmed fact documented by research.")
        self.assertEqual(kind, "fact")

        claims = extract_claims(
            "The system is operational. We assume it will continue. "
            "However, this might be wrong."
        )
        self.assertEqual(len(claims), 3)

    def test_32_compute_confidence_function(self):
        """compute_confidence() and aggregate_confidence() work."""
        from enterprise.modules.research_verification import compute_confidence, aggregate_confidence
        score = compute_confidence({"kind": "fact"}, source_credibility=0.9)
        self.assertGreater(score, 0.7)

        agg = aggregate_confidence([0.9, 0.8, 0.7, 0.6, 0.5])
        self.assertAlmostEqual(agg["mean"], 0.7, places=1)
        self.assertEqual(agg["tier"], "moderate")

    def test_33_synthesize_evidence_function(self):
        """synthesize_evidence() standalone function works."""
        from enterprise.modules.research_verification import synthesize_evidence, generate_recommendations
        result = synthesize_evidence({
            "objective": "Test synthesis",
            "domain": "performance",
            "sources": [],
            "claims": [],
            "confidence": {"aggregate": 0.85, "tier": "high", "scores": {}},
        })
        self.assertIn("summary", result)
        self.assertIn("recommendations", result)

        recs = generate_recommendations(0.85, conflicts=2, gaps=3, domain="security")
        self.assertGreater(len(recs), 1)


# ============================================================================
# Run
# ============================================================================

if __name__ == "__main__":
    unittest.main()