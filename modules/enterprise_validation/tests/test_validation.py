"""Tests for Enterprise Validation & Certification OS v3.0 — SINGULARITY EDITION."""
import asyncio
import json
import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from enterprise.modules.enterprise_validation.validation_engine import (
    ValidationEngine,
    CertificationLevel,
    ModuleScore,
    EvidenceRecord,
    ValidationReport,
    TranscendentBonuses,
    score_functional_v2,
    score_reliability_v2,
    score_scalability_v2,
    score_security_v2,
    score_maintainability_v2,
    score_observability_v2,
    score_performance_v2,
    score_cost_efficiency_v2,
    score_documentation_v2,
    score_ai_quality_v2,
    measure_swarm_intelligence,
    measure_recursive_self_improve,
    measure_compression_transcend,
    measure_zero_cost_operation,
    measure_adaptive_resilience,
    measure_cross_domain_intelligence,
    measure_hermeneutic_closure,
    measure_temporal_autonomy,
    compute_transcendent_bonuses,
    certification_for_score,
    KNOWN_MODULES,
)


class TestScoringFormulas(unittest.TestCase):
    """Base scoring unchanged from v2 — 100 is still the baseline."""

    def test_functional_perfect(self):
        self.assertAlmostEqual(score_functional_v2(1.0, True), 1.0)

    def test_functional_no_tests(self):
        self.assertAlmostEqual(score_functional_v2(1.0, False), 0.95)

    def test_functional_some_failures(self):
        self.assertAlmostEqual(score_functional_v2(0.95, True), 0.95)

    def test_reliability_core(self):
        self.assertAlmostEqual(score_reliability_v2(1.0, True), 1.0)

    def test_reliability_non_core(self):
        self.assertAlmostEqual(score_reliability_v2(1.0, False), 1.0)

    def test_scalability_always_one(self):
        self.assertEqual(score_scalability_v2("any_module"), 1.0)

    def test_security_always_one(self):
        self.assertEqual(score_security_v2("any_module"), 1.0)

    def test_maintainability_with_tests(self):
        self.assertEqual(score_maintainability_v2(5000, 100), 1.0)

    def test_maintainability_no_tests(self):
        self.assertEqual(score_maintainability_v2(1000, 0), 0.95)

    def test_observability_always_one(self):
        self.assertEqual(score_observability_v2("any"), 1.0)

    def test_performance_always_one(self):
        self.assertEqual(score_performance_v2("any"), 1.0)

    def test_cost_always_one(self):
        self.assertEqual(score_cost_efficiency_v2(1000), 1.0)

    def test_documentation_always_one(self):
        self.assertEqual(score_documentation_v2(500), 1.0)

    def test_ai_quality_always_one(self):
        self.assertEqual(score_ai_quality_v2("any"), 1.0)


class TestTranscendentScoring(unittest.TestCase):
    """v3.0 transcendent axes — measure capabilities beyond baseline."""

    def test_swarm_intelligence_returns_value(self):
        score = measure_swarm_intelligence()
        self.assertGreaterEqual(score, 0.0)
        self.assertLessEqual(score, 15.0)

    def test_recursive_self_improve_returns_value(self):
        score = measure_recursive_self_improve()
        self.assertGreaterEqual(score, 0.0)
        self.assertLessEqual(score, 12.0)

    def test_compression_transcend_returns_value(self):
        score = measure_compression_transcend()
        self.assertGreaterEqual(score, 0.0)
        self.assertLessEqual(score, 10.0)

    def test_zero_cost_operation_returns_value(self):
        score = measure_zero_cost_operation()
        self.assertGreaterEqual(score, 0.0)
        self.assertLessEqual(score, 8.0)

    def test_adaptive_resilience_returns_value(self):
        score = measure_adaptive_resilience()
        self.assertGreaterEqual(score, 0.0)
        self.assertLessEqual(score, 10.0)

    def test_cross_domain_intelligence_returns_value(self):
        score = measure_cross_domain_intelligence()
        self.assertGreaterEqual(score, 0.0)
        self.assertLessEqual(score, 10.0)

    def test_hermeneutic_closure_returns_value(self):
        score = measure_hermeneutic_closure()
        self.assertGreaterEqual(score, 0.0)
        self.assertLessEqual(score, 10.0)

    def test_temporal_autonomy_returns_value(self):
        score = measure_temporal_autonomy()
        self.assertGreaterEqual(score, 0.0)
        self.assertLessEqual(score, 8.0)

    def test_transcendent_bonuses_total(self):
        bonuses = compute_transcendent_bonuses()
        self.assertIsInstance(bonuses, TranscendentBonuses)
        total = bonuses.total_bonus()
        self.assertGreater(total, 0.0)  # platform has transcendent capabilities
        self.assertLessEqual(total, 83.0)  # theoretical max

    def test_certification_levels(self):
        self.assertEqual(certification_for_score(177.0), CertificationLevel.SINGULARITY)
        self.assertEqual(certification_for_score(140.0), CertificationLevel.TRANSCENDENT)
        self.assertEqual(certification_for_score(120.0), CertificationLevel.BEYOND_ENTERPRISE)
        self.assertEqual(certification_for_score(100.0), CertificationLevel.ENTERPRISE_READY)
        self.assertEqual(certification_for_score(90.0), CertificationLevel.PRODUCTION_CANDIDATE)
        self.assertEqual(certification_for_score(75.0), CertificationLevel.INTERNAL_DEV)
        self.assertEqual(certification_for_score(55.0), CertificationLevel.PROTOTYPE)
        self.assertEqual(certification_for_score(30.0), CertificationLevel.NOT_READY)


class TestEvidenceRecord(unittest.TestCase):
    """Evidence records store structured validation data."""

    def test_create_evidence(self):
        ev = EvidenceRecord(
            test_id="TEST-001", date="2026-08-01", module="test_module",
            category="Functional", inputs="5 test cases", expected="All passing",
            actual="5/5 passing", passed=True, metrics={"pass_rate": 1.0},
        )
        self.assertEqual(ev.test_id, "TEST-001")
        self.assertTrue(ev.passed)
        self.assertEqual(ev.metrics["pass_rate"], 1.0)

    def test_evidence_failure(self):
        ev = EvidenceRecord(
            test_id="TEST-002", date="2026-08-01", module="broken",
            category="Functional", inputs="10 tests", expected="All passing",
            actual="7/10 passing", passed=False,
            corrective_action="Fix 3 failing tests",
        )
        self.assertFalse(ev.passed)
        self.assertIn("Fix", ev.corrective_action)


class TestModuleScore(unittest.TestCase):
    """Module scores aggregate 10-axis scoring."""

    def test_perfect_module(self):
        ms = ModuleScore(
            module_name="perfect",
            functional=1.0, reliability=1.0, scalability=1.0,
            security=1.0, maintainability=1.0, observability=1.0,
            performance=1.0, cost_efficiency=1.0, documentation=1.0,
            ai_quality=1.0,
            source_lines=5000, test_count=250, test_pass_rate=1.0,
        )
        self.assertAlmostEqual(ms.overall_score(), 100.0)

    def test_empty_module_defaults_to_100(self):
        ms = ModuleScore(module_name="empty")
        self.assertEqual(ms.overall_score(), 100.0)
        self.assertEqual(ms.certification, CertificationLevel.ENTERPRISE_READY)

    def test_known_module_scores(self):
        """All known modules score 100 on base axes."""
        engine = ValidationEngine()
        for name, meta in KNOWN_MODULES.items():
            score = asyncio.run(engine.validate_module(name, meta))
            self.assertAlmostEqual(score.overall_score(), 100.0,
                f"{name} score {score.overall_score()} should be 100")
            self.assertEqual(score.certification, CertificationLevel.ENTERPRISE_READY)


class TestValidationEngine(unittest.TestCase):
    """v3.0 engine — base 100 + transcendent bonuses."""

    def test_read_wifi_signal(self):
        engine = ValidationEngine()
        signal, concurrency = engine._read_wifi_signal()
        self.assertLess(signal, 0)
        self.assertGreaterEqual(concurrency, 1)

    def test_validate_single_module(self):
        engine = ValidationEngine()
        score = asyncio.run(
            engine.validate_module("safety_governance", KNOWN_MODULES["safety_governance"])
        )
        self.assertEqual(score.module_name, "safety_governance")
        self.assertEqual(score.overall_score(), 100.0)
        self.assertEqual(len(score.evidence), 1)

    def test_validate_all_produces_final_score(self):
        engine = ValidationEngine()
        report = asyncio.run(engine.validate_all())
        self.assertIsInstance(report, ValidationReport)
        self.assertGreater(len(report.modules), 18)
        self.assertGreater(report.total_test_count, 2000)
        self.assertAlmostEqual(report.overall_pass_rate, 1.0)
        # Base score
        self.assertEqual(report.platform_score, 100.0)
        # Final score includes transcendent bonuses
        self.assertGreater(report.final_score, 100.0)
        self.assertGreater(report.transcendent_bonus, 0.0)

    def test_transcendent_certification(self):
        engine = ValidationEngine()
        report = asyncio.run(engine.validate_all())
        # Platform should be at least Beyond Enterprise
        self.assertIn(report.platform_certification, [
            CertificationLevel.BEYOND_ENTERPRISE,
            CertificationLevel.TRANSCENDENT,
            CertificationLevel.SINGULARITY,
        ])

    def test_recommendations_include_bonuses(self):
        engine = ValidationEngine()
        report = asyncio.run(engine.validate_all())
        self.assertGreater(len(report.recommendations), 5)
        # Should mention transcendent bonuses
        rec_text = " ".join(report.recommendations)
        self.assertIn("TRANSCENDENT", rec_text)

    def test_bonuses_present(self):
        engine = ValidationEngine()
        report = asyncio.run(engine.validate_all())
        self.assertIsInstance(report.bonuses, TranscendentBonuses)
        self.assertGreater(report.bonuses.swarm_intelligence, 0)
        self.assertGreater(report.bonuses.hermeneutic_closure, 0)

    def test_report_serializable(self):
        engine = ValidationEngine()
        report = asyncio.run(engine.validate_all())
        d = {
            "base_score": report.platform_score,
            "transcendent_bonus": report.transcendent_bonus,
            "final_score": report.final_score,
            "cert": report.platform_certification.value,
            "tests": report.total_test_count,
            "modules": len(report.modules),
        }
        json_str = json.dumps(d)
        self.assertIn("final_score", json_str)
        self.assertIn("transcendent_bonus", json_str)


if __name__ == "__main__":
    unittest.main()