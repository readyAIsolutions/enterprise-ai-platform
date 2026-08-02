"""
Comprehensive tests for the Innovation R&D OS module.

Covers all modules: pipeline, research, experiment, integrity,
isolation, scouting, and IP management.
"""

import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from ..research import (
    ResearchDomain,
    ResearchEntry,
    ResearchLibrary,
    MaturityLevel,
)
from ..experiment import (
    Experiment,
    ExperimentStatus,
    ExperimentTracker,
)
from ..integrity import IntegrityCheck, IntegrityReport
from ..isolation import (
    IsolationConfig,
    IsolationManager,
    Environment,
    EnvironmentType,
    EnvironmentStatus,
    PolicyReport,
    MonitoringSnapshot,
)
from ..scouting import (
    ScoutTarget,
    ScoutEntry,
    ScoutEngine,
    ScoutStatus,
    RiskLevel,
)
from ..ip import (
    IPCategory,
    IPEntry,
    IPManager,
    IPStatus,
)
from ..pipeline import (
    InnovationPipeline,
    Opportunity,
    Hypothesis,
    ResearchResult,
    Assessment,
    ExperimentDesign,
    Prototype,
    MetricsSnapshot,
    Comparison,
    Decision,
    Documentation,
    TransferPackage,
)


# ---------------------------------------------------------------------------
# TestInnovationPipeline
# ---------------------------------------------------------------------------


class TestInnovationPipeline(unittest.TestCase):
    """Tests for the full innovation pipeline workflow."""

    def setUp(self) -> None:
        self.pipeline = InnovationPipeline(name="test-pipeline")

    def test_identify_opportunity(self) -> None:
        """Test opportunity identification."""
        opp = self.pipeline.identify_opportunity(
            problem_statement="Reduce model inference latency by 50%",
            context="Enterprise AI serving",
            urgency="high",
        )
        self.assertIsInstance(opp, Opportunity)
        self.assertEqual(opp.urgency, "high")
        self.assertIn("latency", opp.problem_statement)
        self.assertTrue(opp.opportunity_id.startswith("opp-"))

    def test_define_hypothesis(self) -> None:
        """Test hypothesis definition from an opportunity."""
        opp = self.pipeline.identify_opportunity("Test problem")
        hyp = self.pipeline.define_hypothesis(
            opp,
            statement="Caching layer reduces latency by 40%",
            assumptions=["Cache hit rate > 80%"],
            null_hypothesis="Caching has no effect",
        )
        self.assertIsInstance(hyp, Hypothesis)
        self.assertIn("Caching", hyp.statement)
        self.assertEqual(len(hyp.assumptions), 1)
        self.assertTrue(hyp.hypothesis_id.startswith("hyp-"))

    def test_research(self) -> None:
        """Test research stage."""
        opp = self.pipeline.identify_opportunity("Test")
        hyp = self.pipeline.define_hypothesis(opp, "Test hypothesis")
        result = self.pipeline.research(
            hyp,
            findings=["Finding A", "Finding B"],
            references=["ref-1", "ref-2"],
            confidence=0.85,
        )
        self.assertIsInstance(result, ResearchResult)
        self.assertEqual(len(result.findings), 2)
        self.assertEqual(result.confidence, 0.85)

    def test_assess_value_feasibility_risk(self) -> None:
        """Test assessment stage including go/no-go logic."""
        opp = self.pipeline.identify_opportunity("Test")
        hyp = self.pipeline.define_hypothesis(opp, "Test")
        research = self.pipeline.research(hyp)

        # Strong scores should produce go
        assessment = self.pipeline.assess_value_feasibility_risk(
            research,
            value_score=0.9,
            feasibility_score=0.8,
            risk_score=0.2,
            summary="High potential",
        )
        self.assertTrue(assessment.go_no_go)

        # Weak value should produce no-go
        assessment2 = self.pipeline.assess_value_feasibility_risk(
            research,
            value_score=0.3,
            feasibility_score=0.8,
            risk_score=0.2,
        )
        self.assertFalse(assessment2.go_no_go)

        # High risk should produce no-go
        assessment3 = self.pipeline.assess_value_feasibility_risk(
            research,
            value_score=0.9,
            feasibility_score=0.8,
            risk_score=0.9,
        )
        self.assertFalse(assessment3.go_no_go)

    def test_design_experiment(self) -> None:
        """Test experiment design."""
        opp = self.pipeline.identify_opportunity("Test")
        hyp = self.pipeline.define_hypothesis(opp, "Test")
        research = self.pipeline.research(hyp)
        assessment = self.pipeline.assess_value_feasibility_risk(research)

        design = self.pipeline.design_experiment(
            assessment,
            methodology="A/B test with control group",
            metrics=["latency", "throughput"],
            success_criteria=["latency < 100ms"],
            failure_criteria=["latency > 200ms"],
            required_resources=["GPU x2"],
        )
        self.assertIsInstance(design, ExperimentDesign)
        self.assertEqual(len(design.metrics), 2)
        self.assertEqual(design.methodology, "A/B test with control group")

    def test_build_prototype(self) -> None:
        """Test prototype building."""
        opp = self.pipeline.identify_opportunity("Test")
        hyp = self.pipeline.define_hypothesis(opp, "Test")
        research = self.pipeline.research(hyp)
        assessment = self.pipeline.assess_value_feasibility_risk(research)
        design = self.pipeline.design_experiment(assessment)

        proto = self.pipeline.build_prototype(
            design,
            version="0.2.0",
            description="Caching proxy prototype",
            artifacts=["cache.py", "config.yaml"],
            build_log="Build successful",
        )
        self.assertIsInstance(proto, Prototype)
        self.assertEqual(proto.version, "0.2.0")
        self.assertEqual(len(proto.artifacts), 2)

    def test_measure(self) -> None:
        """Test measurement stage."""
        opp = self.pipeline.identify_opportunity("Test")
        hyp = self.pipeline.define_hypothesis(opp, "Test")
        research = self.pipeline.research(hyp)
        assessment = self.pipeline.assess_value_feasibility_risk(research)
        design = self.pipeline.design_experiment(assessment)
        proto = self.pipeline.build_prototype(design)

        snapshot = self.pipeline.measure(
            proto,
            metrics={"latency": 95, "throughput": 1200},
            environment="sandbox",
        )
        self.assertIsInstance(snapshot, MetricsSnapshot)
        self.assertEqual(snapshot.metrics["latency"], 95)
        self.assertEqual(snapshot.environment, "sandbox")

    def test_compare(self) -> None:
        """Test comparison against baseline."""
        snapshot = MetricsSnapshot(
            prototype_id="test-snap",
            metrics={"latency": 80, "throughput": 1500},
        )
        baseline = MetricsSnapshot(
            prototype_id="baseline",
            metrics={"latency": 120, "throughput": 1000},
        )
        comp = self.pipeline.compare(snapshot, baseline)
        self.assertIsInstance(comp, Comparison)
        self.assertEqual(comp.winner, "prototype")
        self.assertIn("latency", comp.deltas)
        self.assertTrue(comp.deltas["latency"] < 0)  # lower latency is better
        self.assertTrue(comp.deltas["throughput"] > 0)

    def test_compare_baseline_wins(self) -> None:
        """Test comparison where baseline wins."""
        snapshot = MetricsSnapshot(
            prototype_id="test-snap",
            metrics={"latency": 200, "throughput": 800},
        )
        baseline = MetricsSnapshot(
            prototype_id="baseline",
            metrics={"latency": 120, "throughput": 1000},
        )
        comp = self.pipeline.compare(snapshot, baseline)
        self.assertEqual(comp.winner, "baseline")

    def test_decide(self) -> None:
        """Test decision stage."""
        snapshot = MetricsSnapshot(prototype_id="test", metrics={"acc": 0.9})
        baseline = MetricsSnapshot(prototype_id="baseline", metrics={"acc": 0.8})
        comp = self.pipeline.compare(snapshot, baseline)

        decision = self.pipeline.decide(
            comp,
            decision="proceed",
            rationale="Clear improvement observed",
            next_steps=["Deploy to staging", "Monitor for 2 weeks"],
            approver="CTO",
        )
        self.assertIsInstance(decision, Decision)
        self.assertEqual(decision.decision, "proceed")
        self.assertEqual(decision.approver, "CTO")
        self.assertEqual(len(decision.next_steps), 2)

    def test_document(self) -> None:
        """Test documentation stage."""
        snapshot = MetricsSnapshot(prototype_id="test", metrics={"acc": 0.9})
        baseline = MetricsSnapshot(prototype_id="baseline", metrics={"acc": 0.8})
        comp = self.pipeline.compare(snapshot, baseline)
        decision = self.pipeline.decide(comp)

        doc = self.pipeline.document(
            decision,
            title="Latency Optimization Report",
            abstract="Reduced latency by 33% via caching layer",
            sections={"methodology": "A/B test", "results": "latency: 80ms"},
        )
        self.assertIsInstance(doc, Documentation)
        self.assertIn("Latency", doc.title)
        self.assertIn("methodology", doc.sections)

    def test_transfer(self) -> None:
        """Test transfer package creation."""
        snapshot = MetricsSnapshot(prototype_id="test", metrics={"acc": 0.9})
        baseline = MetricsSnapshot(prototype_id="baseline", metrics={"acc": 0.8})
        comp = self.pipeline.compare(snapshot, baseline)
        decision = self.pipeline.decide(comp)
        doc = self.pipeline.document(decision)

        package = self.pipeline.transfer(
            doc,
            target_team="Platform Engineering",
            assets=["cache.py", "config.yaml"],
            integration_plan="Phase 1: staging rollout",
            rollback_plan="Revert to direct DB queries",
            sla_requirements={"uptime": "99.9%"},
        )
        self.assertIsInstance(package, TransferPackage)
        self.assertEqual(package.target_team, "Platform Engineering")
        self.assertEqual(len(package.assets), 2)
        self.assertIn("uptime", package.sla_requirements)

    def test_full_workflow(self) -> None:
        """Test the complete end-to-end workflow."""
        package = self.pipeline.run_full_workflow(
            problem_statement="Reduce model inference latency by 50%",
            hypothesis_statement="Caching layer reduces latency by 40%",
            context="Enterprise AI serving",
            urgency="high",
            assumptions=["Cache hit rate > 80%"],
            null_hypothesis="Caching has no effect",
            research_findings=["Redis caching reduces p95 by 35%"],
            research_references=["paper-01"],
            research_confidence=0.85,
            value_score=0.9,
            feasibility_score=0.8,
            risk_score=0.2,
            methodology="A/B test",
            experiment_metrics=["latency", "throughput"],
            measured_metrics={"latency": 80, "throughput": 1500},
            baseline_metrics={"latency": 120, "throughput": 1000},
            decision_value="proceed",
            decision_rationale="Strong improvement",
            target_team="Platform Engineering",
            integration_plan="Deploy to production",
        )
        self.assertIsInstance(package, TransferPackage)
        self.assertEqual(package.target_team, "Platform Engineering")
        self.assertEqual(len(self.pipeline.opportunities), 1)
        self.assertEqual(len(self.pipeline.hypotheses), 1)
        self.assertEqual(len(self.pipeline.research_results), 1)
        self.assertEqual(len(self.pipeline.assessments), 1)
        self.assertEqual(len(self.pipeline.experiment_designs), 1)
        self.assertEqual(len(self.pipeline.prototypes), 1)
        self.assertEqual(len(self.pipeline.decisions), 1)
        self.assertEqual(len(self.pipeline.documents), 1)
        self.assertEqual(len(self.pipeline.transfer_packages), 1)


# ---------------------------------------------------------------------------
# TestResearchLibrary
# ---------------------------------------------------------------------------


class TestResearchLibrary(unittest.TestCase):
    """Tests for the ResearchLibrary."""

    def setUp(self) -> None:
        self.library = ResearchLibrary(name="test-library")
        self.entry1 = ResearchEntry(
            domain=ResearchDomain.AI_MODELS,
            title="Scaling Laws for Neural Language Models",
            source="arxiv:2001.08361",
            summary="Power-law scaling relationships",
            findings="Model performance scales predictably with compute, data, and parameters.",
            maturity=MaturityLevel.PROVEN,
            relevance=0.95,
            tags=["scaling", "LLM", "transformer"],
            authors=["Kaplan et al."],
        )
        self.entry2 = ResearchEntry(
            domain=ResearchDomain.RAG,
            title="Retrieval-Augmented Generation for Knowledge-Intensive Tasks",
            source="arxiv:2005.11401",
            summary="RAG architecture combining retrieval with generation",
            findings="RAG improves factual accuracy on knowledge-intensive benchmarks.",
            maturity=MaturityLevel.PROVEN,
            relevance=0.90,
            tags=["RAG", "retrieval", "generation"],
            authors=["Lewis et al."],
        )
        self.entry3 = ResearchEntry(
            domain=ResearchDomain.AGENT_ARCHITECTURES,
            title="ReAct: Synergizing Reasoning and Acting",
            source="arxiv:2210.03629",
            summary="Interleaved reasoning and action for agents",
            findings="ReAct outperforms reasoning-only and acting-only approaches.",
            maturity=MaturityLevel.EMERGING,
            relevance=0.80,
            tags=["agents", "reasoning", "tool-use"],
            authors=["Yao et al."],
        )

    def _populate_library(self) -> None:
        self.library.add_entry(self.entry1)
        self.library.add_entry(self.entry2)
        self.library.add_entry(self.entry3)

    def test_add_entry(self) -> None:
        """Test adding entries to the library."""
        entry_id = self.library.add_entry(self.entry1)
        self.assertEqual(entry_id, self.entry1.entry_id)
        self.assertEqual(len(self.library), 1)

    def test_remove_entry(self) -> None:
        """Test removing entries."""
        self.library.add_entry(self.entry1)
        self.assertTrue(self.library.remove_entry(self.entry1.entry_id))
        self.assertEqual(len(self.library), 0)
        self.assertFalse(self.library.remove_entry("nonexistent"))

    def test_get_entry(self) -> None:
        """Test entry retrieval."""
        self.library.add_entry(self.entry1)
        entry = self.library.get_entry(self.entry1.entry_id)
        self.assertIsNotNone(entry)
        self.assertEqual(entry.title, self.entry1.title)
        self.assertIsNone(self.library.get_entry("nonexistent"))

    def test_search_by_domain(self) -> None:
        """Test domain-based search."""
        self._populate_library()
        results = self.library.search_by_domain(ResearchDomain.AI_MODELS)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].title, self.entry1.title)

    def test_search_by_domain_empty(self) -> None:
        """Test domain search with no results."""
        self._populate_library()
        results = self.library.search_by_domain(ResearchDomain.SECURITY)
        self.assertEqual(len(results), 0)

    def test_search_by_keyword(self) -> None:
        """Test keyword search across fields."""
        self._populate_library()
        results = self.library.search_by_keyword("scaling")
        self.assertEqual(len(results), 1)
        self.assertIn("Scaling", results[0].title)

        results = self.library.search_by_keyword("retrieval")
        self.assertEqual(len(results), 1)

        results = self.library.search_by_keyword("nonexistent")
        self.assertEqual(len(results), 0)

    def test_search_by_keyword_in_tags(self) -> None:
        """Test that keyword search works on tags."""
        self._populate_library()
        results = self.library.search_by_keyword("LLM")
        self.assertEqual(len(results), 1)

    def test_get_trends(self) -> None:
        """Test trend analysis."""
        self._populate_library()
        trends = self.library.get_trends()
        self.assertIsInstance(trends, dict)
        self.assertIn(MaturityLevel.PROVEN, trends)
        self.assertIn(MaturityLevel.EMERGING, trends)
        self.assertEqual(trends[MaturityLevel.PROVEN], 2)
        self.assertEqual(trends[MaturityLevel.EMERGING], 1)

    def test_get_trends_by_domain(self) -> None:
        """Test trend analysis filtered by domain."""
        self._populate_library()
        trends = self.library.get_trends(domain=ResearchDomain.AI_MODELS)
        self.assertEqual(trends[MaturityLevel.PROVEN], 1)

    def test_assess_maturity(self) -> None:
        """Test maturity assessment."""
        self.library.add_entry(self.entry1)
        level = self.library.assess_maturity(self.entry1.entry_id)
        self.assertEqual(level, MaturityLevel.PROVEN)

        level = self.library.assess_maturity("nonexistent")
        self.assertEqual(level, MaturityLevel.UNKNOWN)

    def test_get_recent_entries(self) -> None:
        """Test retrieving recent entries."""
        self._populate_library()
        recent = self.library.get_recent_entries(days=30)
        self.assertEqual(len(recent), 3)

    def test_stats(self) -> None:
        """Test library statistics."""
        self._populate_library()
        stats = self.library.stats()
        self.assertEqual(stats["total_entries"], 3)
        self.assertIn("ai_models", stats["domains"])
        self.assertAlmostEqual(stats["avg_relevance"], (0.95 + 0.90 + 0.80) / 3)


# ---------------------------------------------------------------------------
# TestExperimentTracker
# ---------------------------------------------------------------------------


class TestExperimentTracker(unittest.TestCase):
    """Tests for the ExperimentTracker."""

    def setUp(self) -> None:
        self.tracker = ExperimentTracker()

    def test_create_experiment(self) -> None:
        """Test creating a new experiment."""
        exp = self.tracker.create_experiment(
            hypothesis="Caching reduces latency by 40%",
            baseline=120.0,
            variables={"cache_size": "1GB", "eviction_policy": "LRU"},
            dataset="production-traffic-sample",
            metrics=["latency", "throughput"],
            success_threshold=100.0,
            failure_threshold=150.0,
            budget=5000.0,
            security_requirements=["no-egress"],
            privacy_requirements=["pii-removed"],
            timeline="2 weeks",
            owner="ml-team",
            reproducibility_checklist=["seed fixed", "env documented", "data versioned"],
        )
        self.assertIsInstance(exp, Experiment)
        self.assertEqual(exp.status, ExperimentStatus.DRAFT)
        self.assertEqual(len(exp.metrics), 2)
        self.assertEqual(exp.owner, "ml-team")
        self.assertTrue(exp.experiment_id.startswith("exp-"))

    def test_start_experiment(self) -> None:
        """Test starting an experiment."""
        exp = self.tracker.create_experiment(hypothesis="Test")
        self.assertTrue(self.tracker.start(exp.experiment_id))
        self.assertEqual(exp.status, ExperimentStatus.RUNNING)
        self.assertIsNotNone(exp.start_time)

    def test_start_nonexistent_experiment(self) -> None:
        """Test starting a nonexistent experiment fails."""
        self.assertFalse(self.tracker.start("nonexistent"))

    def test_start_already_running(self) -> None:
        """Test starting an already-running experiment fails."""
        exp = self.tracker.create_experiment(hypothesis="Test")
        self.tracker.start(exp.experiment_id)
        self.assertFalse(self.tracker.start(exp.experiment_id))

    def test_record_result(self) -> None:
        """Test recording results."""
        exp = self.tracker.create_experiment(
            hypothesis="Test",
            metrics=["latency", "throughput"],
        )
        self.tracker.start(exp.experiment_id)
        self.assertTrue(self.tracker.record_result(exp.experiment_id, "latency", 85.0))
        self.assertTrue(
            self.tracker.record_result(exp.experiment_id, "throughput", 1500.0)
        )
        self.assertEqual(exp.results["latency"], 85.0)
        self.assertEqual(len(exp.results), 2)

    def test_record_result_not_running(self) -> None:
        """Test recording results on a non-running experiment fails."""
        exp = self.tracker.create_experiment(hypothesis="Test")
        self.assertFalse(self.tracker.record_result(exp.experiment_id, "latency", 85.0))

    def test_record_result_nonexistent(self) -> None:
        """Test recording on nonexistent experiment fails."""
        self.assertFalse(self.tracker.record_result("nonexistent", "latency", 85.0))

    def test_check_thresholds_success(self) -> None:
        """Test threshold check where experiment succeeds."""
        exp = self.tracker.create_experiment(
            hypothesis="Test",
            success_threshold=0.8,
            failure_threshold=0.5,
            metrics=["accuracy"],
        )
        self.tracker.start(exp.experiment_id)
        self.tracker.record_result(exp.experiment_id, "accuracy", 0.95)
        status = self.tracker.check_thresholds(exp.experiment_id)
        self.assertEqual(status, ExperimentStatus.COMPLETED)

    def test_check_thresholds_failure(self) -> None:
        """Test threshold check where experiment fails."""
        exp = self.tracker.create_experiment(
            hypothesis="Test",
            success_threshold=0.8,
            failure_threshold=0.5,
            metrics=["accuracy"],
        )
        self.tracker.start(exp.experiment_id)
        self.tracker.record_result(exp.experiment_id, "accuracy", 0.3)
        status = self.tracker.check_thresholds(exp.experiment_id)
        self.assertEqual(status, ExperimentStatus.FAILED)

    def test_check_thresholds_no_results(self) -> None:
        """Test threshold check with no results recorded."""
        exp = self.tracker.create_experiment(hypothesis="Test")
        self.tracker.start(exp.experiment_id)
        status = self.tracker.check_thresholds(exp.experiment_id)
        self.assertEqual(status, ExperimentStatus.RUNNING)  # stays running

    def test_verify_reproducibility(self) -> None:
        """Test reproducibility verification."""
        exp = self.tracker.create_experiment(
            hypothesis="Test",
            reproducibility_checklist=["seed fixed", "env documented", "data versioned"],
        )
        self.assertTrue(self.tracker.verify_reproducibility(exp.experiment_id))
        self.assertEqual(exp.status, ExperimentStatus.REPRODUCING)

    def test_verify_reproducibility_empty_checklist(self) -> None:
        """Test that empty checklist fails reproducibility check."""
        exp = self.tracker.create_experiment(hypothesis="Test")
        self.assertFalse(self.tracker.verify_reproducibility(exp.experiment_id))

    def test_verify_reproducibility_nonexistent(self) -> None:
        """Test reproducibility on nonexistent experiment."""
        self.assertFalse(self.tracker.verify_reproducibility("nonexistent"))

    def test_list_by_status(self) -> None:
        """Test filtering experiments by status."""
        exp1 = self.tracker.create_experiment(hypothesis="Test 1")
        exp2 = self.tracker.create_experiment(hypothesis="Test 2")
        self.tracker.start(exp1.experiment_id)

        drafts = self.tracker.list_by_status(ExperimentStatus.DRAFT)
        running = self.tracker.list_by_status(ExperimentStatus.RUNNING)
        self.assertEqual(len(drafts), 1)
        self.assertEqual(len(running), 1)

    def test_get_summary(self) -> None:
        """Test experiment summary."""
        exp = self.tracker.create_experiment(
            hypothesis="Caching reduces latency",
            metrics=["latency"],
        )
        self.tracker.start(exp.experiment_id)
        self.tracker.record_result(exp.experiment_id, "latency", 80.0)
        self.tracker.check_thresholds(exp.experiment_id)
        summary = self.tracker.get_summary(exp.experiment_id)
        self.assertIsNotNone(summary)
        # Default thresholds are 0.0, so any positive result completes successfully
        self.assertEqual(summary["status"], "completed")

    def test_get_summary_nonexistent(self) -> None:
        """Test summary for nonexistent experiment."""
        self.assertIsNone(self.tracker.get_summary("nonexistent"))


# ---------------------------------------------------------------------------
# TestIntegrityCheck
# ---------------------------------------------------------------------------


class TestIntegrityCheck(unittest.TestCase):
    """Tests for the IntegrityCheck system."""

    def setUp(self) -> None:
        self.integrity = IntegrityCheck()
        self.research_entry = ResearchEntry(
            domain=ResearchDomain.AI_MODELS,
            title="Test Paper",
            source="arxiv:test-001",
            summary="Test summary",
            findings="Detailed findings from the research study with sufficient length.",
            authors=["Author One"],
            tags=["AI"],
        )
        self.experiment = Experiment(
            hypothesis="Test hypothesis",
            dataset="CIFAR-10 with 60k labeled images",
            metrics=["accuracy"],
            success_threshold=0.9,
            failure_threshold=0.5,
            baseline=0.85,
            reproducibility_checklist=["seed fixed", "env documented", "data versioned"],
            notes=[],
        )

    def test_verify_source_attribution_pass(self) -> None:
        """Test source attribution verification passes with valid data."""
        self.assertTrue(self.integrity.verify_source_attribution(self.research_entry))

    def test_verify_source_attribution_empty_source(self) -> None:
        """Test source attribution fails with empty source."""
        entry = ResearchEntry(
            domain=ResearchDomain.AI_MODELS,
            title="Test",
            source="",
            summary="",
            findings="",
        )
        self.assertFalse(self.integrity.verify_source_attribution(entry))

    def test_verify_source_attribution_placeholder(self) -> None:
        """Test source attribution fails with placeholder source."""
        entry = ResearchEntry(
            domain=ResearchDomain.AI_MODELS,
            title="Test",
            source="TBD",
            summary="",
            findings="",
        )
        self.assertFalse(self.integrity.verify_source_attribution(entry))

    def test_verify_source_attribution_missing_title(self) -> None:
        """Test source attribution fails with missing title."""
        entry = ResearchEntry(
            domain=ResearchDomain.AI_MODELS,
            title="",
            source="arxiv:test",
            summary="",
            findings="",
        )
        self.assertFalse(self.integrity.verify_source_attribution(entry))

    def test_check_reproducibility_pass(self) -> None:
        """Test reproducibility check passes with valid checklist."""
        self.assertTrue(self.integrity.check_reproducibility(self.experiment))

    def test_check_reproducibility_empty_checklist(self) -> None:
        """Test reproducibility check fails with empty checklist."""
        exp = Experiment(
            hypothesis="Test",
            reproducibility_checklist=[],
        )
        self.assertFalse(self.integrity.check_reproducibility(exp))

    def test_validate_negative_results_failed_without_notes(self) -> None:
        """Test negative result validation fails without failure notes."""
        exp = Experiment(
            hypothesis="Test",
            status=ExperimentStatus.FAILED,
            baseline=1.0,
            results={"metric": 0.5},
            notes=[],
        )
        self.assertFalse(self.integrity.validate_negative_results(exp))

    def test_validate_negative_results_failed_with_notes(self) -> None:
        """Test negative result validation passes with failure notes."""
        exp = Experiment(
            hypothesis="Test",
            status=ExperimentStatus.FAILED,
            baseline=1.0,
            results={"metric": 0.5},
            notes=["Failed: metric below threshold and below baseline; negative result"],
        )
        self.assertTrue(self.integrity.validate_negative_results(exp))

    def test_validate_negative_results_below_baseline_undocumented(self) -> None:
        """Test negative result validation when result is below baseline without documentation."""
        exp = Experiment(
            hypothesis="Test",
            status=ExperimentStatus.COMPLETED,
            baseline=1.0,
            results={"metric": 0.5},
            notes=[],
        )
        self.assertFalse(self.integrity.validate_negative_results(exp))

    def test_verify_dataset_documentation_pass(self) -> None:
        """Test dataset documentation verification passes."""
        self.assertTrue(self.integrity.verify_dataset_documentation(self.experiment))

    def test_verify_dataset_documentation_missing(self) -> None:
        """Test dataset documentation fails when missing."""
        exp = Experiment(hypothesis="Test", dataset="")
        self.assertFalse(self.integrity.verify_dataset_documentation(exp))

    def test_verify_dataset_documentation_too_short(self) -> None:
        """Test dataset documentation fails when too short."""
        exp = Experiment(hypothesis="Test", dataset="CIFAR")
        self.assertFalse(self.integrity.verify_dataset_documentation(exp))

    def test_document_limitations(self) -> None:
        """Test limitation documentation."""
        limitations = self.integrity.document_limitations(self.research_entry)
        self.assertIsInstance(limitations, list)

    def test_document_limitations_short_findings(self) -> None:
        """Test that short findings produce a limitation."""
        entry = ResearchEntry(
            domain=ResearchDomain.AI_MODELS,
            title="Test",
            source="arxiv:test",
            summary="",
            findings="Short.",
            maturity=MaturityLevel.EMERGING,
        )
        limitations = self.integrity.document_limitations(entry)
        self.assertTrue(any("short" in lim.lower() for lim in limitations))

    def test_statistical_care_check_pass(self) -> None:
        """Test statistical care check passes."""
        self.assertTrue(self.integrity.statistical_care_check(self.experiment))

    def test_statistical_care_check_no_metrics(self) -> None:
        """Test statistical care fails without metrics."""
        exp = Experiment(
            hypothesis="Test",
            metrics=[],
        )
        self.assertFalse(self.integrity.statistical_care_check(exp))

    def test_statistical_care_check_bad_thresholds(self) -> None:
        """Test statistical care fails when success <= failure threshold."""
        exp = Experiment(
            hypothesis="Test",
            metrics=["accuracy"],
            success_threshold=0.5,
            failure_threshold=0.9,
        )
        self.assertFalse(self.integrity.statistical_care_check(exp))

    def test_run_full_check(self) -> None:
        """Test running full integrity check."""
        report = self.integrity.run_full_check(
            self.experiment,
            research_entry=self.research_entry,
        )
        self.assertIsInstance(report, IntegrityReport)
        self.assertEqual(report.target_id, self.experiment.experiment_id)
        self.assertIn("reproducibility", report.checks)
        self.assertIn("source_attribution", report.checks)

    def test_integrity_report_summary(self) -> None:
        """Test integrity report summary string."""
        report = IntegrityReport(target_id="test-id")
        report.add_check("check_a", True, "passed a")
        report.add_check("check_b", True, "passed b")
        self.assertTrue(report.overall_pass)
        self.assertIn("PASSED", report.summary())

        report.add_check("check_c", False, "failed c")
        self.assertFalse(report.overall_pass)
        self.assertIn("FAILED", report.summary())


# ---------------------------------------------------------------------------
# TestIsolationManager
# ---------------------------------------------------------------------------


class TestIsolationManager(unittest.TestCase):
    """Tests for the IsolationManager."""

    def setUp(self) -> None:
        self.manager = IsolationManager()
        self.config = IsolationConfig(
            environment_type=EnvironmentType.CONTAINER,
            credentials_policy="ephemeral_only",
            access_policy="owner_only",
            data_sanitization="synthetic_only",
            spending_limit=500.0,
            network_restrictions=["no_egress"],
            expiration=timedelta(hours=24),
            monitoring_enabled=True,
            removable=True,
        )

    def test_create_environment(self) -> None:
        """Test creating an isolated environment."""
        env = self.manager.create_environment(self.config)
        self.assertIsInstance(env, Environment)
        self.assertEqual(env.status, EnvironmentStatus.ACTIVE)
        self.assertTrue(env.env_id.startswith("env-"))
        self.assertIsNotNone(env.expires_at)

    def test_create_environment_default_config(self) -> None:
        """Test creating environment with default config."""
        env = self.manager.create_environment()
        self.assertEqual(env.config.credentials_policy, "ephemeral_only")

    def test_enforce_policies_compliant(self) -> None:
        """Test policy enforcement on compliant environment."""
        env = self.manager.create_environment(self.config)
        report = self.manager.enforce_policies(env)
        self.assertIsInstance(report, PolicyReport)
        self.assertTrue(report.compliant)
        self.assertEqual(len(report.violations), 0)

    def test_enforce_policies_spending_exceeded(self) -> None:
        """Test policy enforcement with spending violation."""
        env = self.manager.create_environment(self.config)
        env.current_spend = 1000.0  # exceeds 500 limit
        report = self.manager.enforce_policies(env)
        self.assertFalse(report.compliant)
        self.assertTrue(any("spending" in v.lower() for v in report.violations))

    def test_enforce_policies_bad_sanitization(self) -> None:
        """Test policy enforcement with unknown sanitization level."""
        config = IsolationConfig(data_sanitization="custom_unknown")
        env = self.manager.create_environment(config)
        report = self.manager.enforce_policies(env)
        self.assertFalse(report.compliant)

    def test_validate_credentials_ephemeral(self) -> None:
        """Test credential validation with ephemeral policy."""
        env = self.manager.create_environment(self.config)
        self.assertTrue(self.manager.validate_credentials(env))
        self.assertTrue(env.credentials_validated)

    def test_validate_credentials_no_persistent(self) -> None:
        """Test credential validation with no-persistent policy."""
        config = IsolationConfig(credentials_policy="no_persistent")
        env = self.manager.create_environment(config)
        self.assertTrue(self.manager.validate_credentials(env))

    def test_validate_credentials_read_only_vault(self) -> None:
        """Test credential validation with read-only vault policy."""
        config = IsolationConfig(credentials_policy="read_only_vault")
        env = self.manager.create_environment(config)
        self.assertTrue(self.manager.validate_credentials(env))

    def test_validate_credentials_unknown_policy(self) -> None:
        """Test credential validation with unknown policy."""
        config = IsolationConfig(credentials_policy="unknown")
        env = self.manager.create_environment(config)
        self.assertFalse(self.manager.validate_credentials(env))
        self.assertFalse(env.credentials_validated)

    def test_monitor_environment(self) -> None:
        """Test environment monitoring."""
        env = self.manager.create_environment(self.config)
        snapshot = self.manager.monitor_environment(env)
        self.assertIsInstance(snapshot, MonitoringSnapshot)
        self.assertTrue(snapshot.is_healthy)

    def test_monitor_environment_not_healthy(self) -> None:
        """Test monitoring with policy violations."""
        env = self.manager.create_environment(self.config)
        env.policy_violations = ["spending exceeded"]
        snapshot = self.manager.monitor_environment(env)
        self.assertFalse(snapshot.is_healthy)

    def test_monitor_environment_disabled(self) -> None:
        """Test monitoring when disabled."""
        config = IsolationConfig(monitoring_enabled=False)
        env = self.manager.create_environment(config)
        snapshot = self.manager.monitor_environment(env)
        self.assertIn("monitoring_disabled", snapshot.anomalies)

    def test_cleanup_environment(self) -> None:
        """Test environment cleanup."""
        env = self.manager.create_environment(self.config)
        self.assertTrue(self.manager.cleanup_environment(env))
        self.assertEqual(env.status, EnvironmentStatus.CLEANED_UP)
        self.assertNotIn(env.env_id, self.manager.environments)

    def test_cleanup_non_removable(self) -> None:
        """Test cleanup fails for non-removable environment."""
        config = IsolationConfig(removable=False)
        env = self.manager.create_environment(config)
        self.assertFalse(self.manager.cleanup_environment(env))

    def test_has_expired(self) -> None:
        """Test expiration check."""
        config = IsolationConfig(expiration=timedelta(hours=-1))  # expired 1 hour ago
        env = self.manager.create_environment(config)
        self.assertTrue(self.manager.has_expired(env))
        self.assertEqual(env.status, EnvironmentStatus.EXPIRED)

    def test_has_expired_not_expired(self) -> None:
        """Test expiration check on active environment."""
        env = self.manager.create_environment(self.config)
        self.assertFalse(self.manager.has_expired(env))

    def test_get_active_environments(self) -> None:
        """Test retrieving active environments."""
        env1 = self.manager.create_environment(self.config)
        env2 = self.manager.create_environment(self.config)
        active = self.manager.get_active_environments()
        self.assertEqual(len(active), 2)

    def test_expire_all_overdue(self) -> None:
        """Test bulk expiration of overdue environments."""
        expired_config = IsolationConfig(expiration=timedelta(hours=-1))
        self.manager.create_environment(expired_config)
        self.manager.create_environment(self.config)  # active
        expired = self.manager.expire_all_overdue()
        self.assertEqual(len(expired), 1)


# ---------------------------------------------------------------------------
# TestScoutEngine
# ---------------------------------------------------------------------------


class TestScoutEngine(unittest.TestCase):
    """Tests for the ScoutEngine."""

    def setUp(self) -> None:
        self.engine = ScoutEngine(name="test-engine")
        self.entry1 = ScoutEntry(
            target=ScoutTarget.PAPERS,
            name="Tree of Thoughts",
            description="Deliberate problem solving with LLMs via tree search",
            source_url="arxiv:2305.10601",
            relevance_score=0.95,
            risk_level=RiskLevel.LOW,
            tags=["reasoning", "LLM"],
        )
        self.entry2 = ScoutEntry(
            target=ScoutTarget.MODELS,
            name="Llama 4",
            description="Next-generation open LLM",
            source_url="https://meta.com/llama4",
            relevance_score=0.88,
            risk_level=RiskLevel.MEDIUM,
            tags=["LLM", "open-source"],
        )
        self.entry3 = ScoutEntry(
            target=ScoutTarget.SECURITY,
            name="Prompt Injection CVE",
            description="Critical vulnerability in agent frameworks",
            source_url="https://cve.example/2024-0001",
            relevance_score=0.92,
            risk_level=RiskLevel.CRITICAL,
            tags=["CVE", "security", "agents"],
        )

    def _populate_engine(self) -> None:
        self.engine.add_finding(self.entry1)
        self.engine.add_finding(self.entry2)
        self.engine.add_finding(self.entry3)

    def test_add_finding(self) -> None:
        """Test adding a scouting finding."""
        entry_id = self.engine.add_finding(self.entry1)
        self.assertEqual(entry_id, self.entry1.entry_id)
        self.assertEqual(len(self.engine.entries), 1)

    def test_scan_by_target(self) -> None:
        """Test scanning by target category."""
        self._populate_engine()
        results = self.engine.scan(target=ScoutTarget.PAPERS)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].name, "Tree of Thoughts")

    def test_scan_by_query(self) -> None:
        """Test scanning with query filter."""
        self._populate_engine()
        results = self.engine.scan(target=ScoutTarget.MODELS, query="llama")
        self.assertEqual(len(results), 1)

    def test_scan_no_results(self) -> None:
        """Test scan with no matching results."""
        self._populate_engine()
        results = self.engine.scan(target=ScoutTarget.PATENTS)
        self.assertEqual(len(results), 0)

    def test_rank_by_relevance(self) -> None:
        """Test ranking by relevance."""
        self._populate_engine()
        ranked = self.engine.rank_by_relevance()
        self.assertEqual(len(ranked), 3)
        self.assertEqual(ranked[0].name, "Tree of Thoughts")  # highest relevance

    def test_rank_by_relevance_filtered(self) -> None:
        """Test ranking filtered by target."""
        self._populate_engine()
        ranked = self.engine.rank_by_relevance(target=ScoutTarget.SECURITY)
        self.assertEqual(len(ranked), 1)

    def test_assess_risk(self) -> None:
        """Test risk assessment."""
        self._populate_engine()
        risk = self.engine.assess_risk(self.entry1.entry_id)
        self.assertEqual(risk, RiskLevel.LOW)

    def test_assess_risk_security_target(self) -> None:
        """Test risk assessment elevates security risks."""
        entry = ScoutEntry(
            target=ScoutTarget.SECURITY,
            name="Test CVE",
            description="Test",
            risk_level=RiskLevel.LOW,
        )
        self.engine.add_finding(entry)
        risk = self.engine.assess_risk(entry.entry_id)
        self.assertEqual(risk, RiskLevel.MEDIUM)  # elevated from low

    def test_assess_risk_nonexistent(self) -> None:
        """Test risk assessment on nonexistent entry."""
        self.assertEqual(self.engine.assess_risk("nonexistent"), RiskLevel.NONE)

    def test_generate_report(self) -> None:
        """Test report generation."""
        self._populate_engine()
        report = self.engine.generate_report()
        self.assertEqual(report["total_findings"], 3)
        self.assertIn("risk_distribution", report)
        self.assertIn("top_findings", report)
        self.assertEqual(len(report["top_findings"]), 3)

    def test_generate_report_filtered(self) -> None:
        """Test report generation filtered by target."""
        self._populate_engine()
        report = self.engine.generate_report(target=ScoutTarget.PAPERS)
        self.assertEqual(report["total_findings"], 1)

    def test_track_emerging(self) -> None:
        """Test tracking emerging technologies."""
        self._populate_engine()
        emerging = self.engine.track_emerging(days=90)
        self.assertEqual(len(emerging), 3)  # all are recent

    def test_update_status(self) -> None:
        """Test updating entry status."""
        self.engine.add_finding(self.entry1)
        self.assertTrue(
            self.engine.update_status(self.entry1.entry_id, ScoutStatus.EVALUATING)
        )
        self.assertEqual(self.entry1.status, ScoutStatus.EVALUATING)

    def test_update_status_nonexistent(self) -> None:
        """Test status update on nonexistent entry."""
        self.assertFalse(
            self.engine.update_status("nonexistent", ScoutStatus.ADOPTED)
        )

    def test_get_stats(self) -> None:
        """Test scouting engine statistics."""
        self._populate_engine()
        stats = self.engine.get_stats()
        self.assertEqual(stats["total_entries"], 3)
        self.assertEqual(stats["high_risk_count"], 1)  # only critical


# ---------------------------------------------------------------------------
# TestIPManager
# ---------------------------------------------------------------------------


class TestIPManager(unittest.TestCase):
    """Tests for the IPManager."""

    def setUp(self) -> None:
        self.manager = IPManager()

    def test_register_invention(self) -> None:
        """Test registering a new invention."""
        entry = self.manager.register_invention(
            category=IPCategory.PATENTABLE_INVENTION,
            title="Novel Caching Algorithm",
            description="A new algorithm for distributed cache invalidation "
            "that reduces stale reads by 80% compared to TTL-based approaches. "
            "The algorithm uses a gossip protocol with vector clocks to track "
            "causal dependencies between cached items.",
            inventors=["Alice Smith", "Bob Jones"],
            related_modules=["cache", "distributed"],
        )
        self.assertIsInstance(entry, IPEntry)
        self.assertEqual(entry.status, IPStatus.DRAFT)
        self.assertEqual(len(entry.inventors), 2)
        self.assertTrue(entry.ip_id.startswith("ip-"))

    def test_check_patentability_patentable(self) -> None:
        """Test patentability check returns patentable."""
        entry = self.manager.register_invention(
            category=IPCategory.PATENTABLE_INVENTION,
            title="Test Invention",
            description="A novel method for reducing latency in distributed systems "
            "through predictive prefetching. This method uses a lightweight neural "
            "network to predict access patterns and preload data before requests arrive. "
            "Extensive testing shows 40% latency reduction.",
            inventors=["Alice Smith"],
        )
        result = self.manager.check_patentability(entry.ip_id)
        self.assertTrue(result["patentable"])
        self.assertEqual(len(result["issues"]), 0)

    def test_check_patentability_not_patentable_category(self) -> None:
        """Test patentability check fails for non-patentable category."""
        entry = self.manager.register_invention(
            category=IPCategory.PROPRIETARY_DATASET,
            title="Dataset X",
            description="A large dataset of labeled images for training.",
            inventors=["Alice Smith"],
        )
        result = self.manager.check_patentability(entry.ip_id)
        self.assertFalse(result["patentable"])
        self.assertTrue(any("category" in i.lower() for i in result["issues"]))

    def test_check_patentability_short_description(self) -> None:
        """Test patentability fails for short description."""
        entry = self.manager.register_invention(
            category=IPCategory.PATENTABLE_INVENTION,
            title="Short Invention",
            description="Too short.",
            inventors=["Alice Smith"],
        )
        result = self.manager.check_patentability(entry.ip_id)
        self.assertFalse(result["patentable"])

    def test_check_patentability_nonexistent(self) -> None:
        """Test patentability check on nonexistent IP."""
        result = self.manager.check_patentability("nonexistent")
        self.assertFalse(result["patentable"])
        self.assertEqual(result["reason"], "not_found")

    def test_track_licensing(self) -> None:
        """Test licensing tracking."""
        entry = self.manager.register_invention(
            category=IPCategory.LICENSING_OBLIGATION,
            title="Apache-licensed Component",
            description="Component under Apache 2.0 license.",
            license_terms="Apache 2.0",
        )
        tracking = self.manager.track_licensing(entry.ip_id)
        self.assertTrue(tracking["found"])
        self.assertTrue(tracking["has_license_terms"])
        self.assertIn("warning", tracking)

    def test_track_licensing_nonexistent(self) -> None:
        """Test licensing tracking on nonexistent IP."""
        tracking = self.manager.track_licensing("nonexistent")
        self.assertFalse(tracking["found"])

    def test_assess_novelty(self) -> None:
        """Test novelty assessment."""
        entry = self.manager.register_invention(
            category=IPCategory.NOVEL_ARCHITECTURE,
            title="Unique Architecture",
            description="A completely novel distributed architecture using "
            "conflict-free replicated data types with sharded consensus. "
            "This architecture eliminates the need for a central coordinator.",
        )
        result = self.manager.assess_novelty(entry.ip_id)
        self.assertTrue(result["is_novel"])
        self.assertGreaterEqual(result["novelty_score"], 0.6)

    def test_assess_novelty_short_description(self) -> None:
        """Test novelty assessment with short description."""
        entry = self.manager.register_invention(
            category=IPCategory.NOVEL_ARCHITECTURE,
            title="Short",
            description="Brief.",
        )
        result = self.manager.assess_novelty(entry.ip_id)
        self.assertFalse(result["is_novel"])

    def test_assess_novelty_nonexistent(self) -> None:
        """Test novelty assessment on nonexistent IP."""
        result = self.manager.assess_novelty("nonexistent")
        self.assertFalse(result["novel"])
        self.assertEqual(result["reason"], "not_found")

    def test_generate_disclosure(self) -> None:
        """Test generating an invention disclosure."""
        entry = self.manager.register_invention(
            category=IPCategory.PATENTABLE_INVENTION,
            title="Disclosed Invention",
            description="A detailed description of a novel method for real-time "
            "data processing using stream processing with adaptive batching. "
            "This method dynamically adjusts batch sizes based on throughput "
            "and latency requirements, achieving optimal resource utilization.",
            inventors=["Alice Smith", "Bob Jones"],
        )
        disclosure = self.manager.generate_disclosure(entry.ip_id)
        self.assertIsNotNone(disclosure)
        self.assertIn("disclosure_id", disclosure)
        self.assertIn("novelty_assessment", disclosure)
        self.assertIn("patentability", disclosure)
        self.assertEqual(entry.status, IPStatus.DISCLOSED)

    def test_generate_disclosure_nonexistent(self) -> None:
        """Test disclosure generation on nonexistent IP."""
        disclosure = self.manager.generate_disclosure("nonexistent")
        self.assertIsNone(disclosure)

    def test_maintain_trade_secret(self) -> None:
        """Test trade secret maintenance."""
        entry = self.manager.register_invention(
            category=IPCategory.TRADE_SECRET,
            title="Secret Sauce",
            description="Proprietary training recipe for foundation models.",
            inventors=["Alice Smith"],
        )
        result = self.manager.maintain_trade_secret(entry.ip_id)
        self.assertTrue(result["maintained"])
        self.assertEqual(entry.status, IPStatus.TRADE_SECRET)

    def test_maintain_trade_secret_disclosed(self) -> None:
        """Test trade secret maintenance on disclosed asset."""
        entry = self.manager.register_invention(
            category=IPCategory.TRADE_SECRET,
            title="Leaked Secret",
            description="Formerly secret.",
            status=IPStatus.DISCLOSED,
            disclosure_date=datetime.now(timezone.utc),
        )
        result = self.manager.maintain_trade_secret(entry.ip_id)
        self.assertFalse(result["maintained"])

    def test_maintain_trade_secret_nonexistent(self) -> None:
        """Test trade secret maintenance on nonexistent IP."""
        result = self.manager.maintain_trade_secret("nonexistent")
        self.assertFalse(result["maintained"])
        self.assertEqual(result["reason"], "not_found")

    def test_list_by_category(self) -> None:
        """Test listing IP by category."""
        self.manager.register_invention(
            IPCategory.PATENTABLE_INVENTION,
            "Test A",
            "Description A with enough detail.",
        )
        self.manager.register_invention(
            IPCategory.TRADE_SECRET,
            "Test B",
            "Description B with enough detail.",
        )
        patents = self.manager.list_by_category(IPCategory.PATENTABLE_INVENTION)
        self.assertEqual(len(patents), 1)

    def test_list_by_status(self) -> None:
        """Test listing IP by status."""
        self.manager.register_invention(
            IPCategory.PATENTABLE_INVENTION,
            "Test A",
            "Description A with enough detail.",
        )
        drafts = self.manager.list_by_status(IPStatus.DRAFT)
        self.assertEqual(len(drafts), 1)

    def test_get_stats(self) -> None:
        """Test IP portfolio statistics."""
        self.manager.register_invention(
            IPCategory.PATENTABLE_INVENTION,
            "Test A",
            "Description A with sufficient detail for testing.",
        )
        self.manager.register_invention(
            IPCategory.TRADE_SECRET,
            "Test B",
            "Description B with sufficient detail for testing.",
        )
        stats = self.manager.get_stats()
        self.assertEqual(stats["total_assets"], 2)
        self.assertIn("patentable_invention", stats["by_category"])
        self.assertIn("trade_secret", stats["by_category"])


if __name__ == "__main__":
    unittest.main()