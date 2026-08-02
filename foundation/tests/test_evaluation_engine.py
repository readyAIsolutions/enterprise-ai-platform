"""
Tests for Evaluation Engine — covers scoring, benchmark runner,
comparison matrix, regression detection, evaluation store, and presets.
"""

import json
import pytest
from copy import deepcopy

from enterprise.foundation.evaluation_engine import (
    QualityDimension,
    SuiteStatus,
    RegressionDirection,
    EvaluationError,
    SuiteNotFoundError,
    RegressionThresholdExceeded,
    EvalCase,
    EvalSuite,
    DimensionScore,
    EvalResult,
    EvalRun,
    ScorerConfig,
    QualityScorer,
    BenchmarkRunner,
    ComparisonMatrix,
    ComparisonEntry,
    RankingEntry,
    RegressionDetector,
    RegressionSignal,
    RegressionReport,
    EvalStore,
    StandardBenchmarks,
)


# ────────────────────────────────────────────────────────────────────
# EvalCase
# ────────────────────────────────────────────────────────────────────

class TestEvalCase:
    def test_creation(self):
        case = EvalCase(case_id="c1", input_text="Hello?", expected_output="Hi!")
        assert case.case_id == "c1"
        assert case.weight == 1.0

    def test_to_from_dict(self):
        case = EvalCase(case_id="c1", input_text="Q", expected_output="A",
                        tags=["math"], metadata={"diff": "easy"}, weight=2.0)
        d = case.to_dict()
        c2 = EvalCase.from_dict(d)
        assert c2.case_id == "c1"
        assert c2.weight == 2.0
        assert c2.tags == ["math"]


# ────────────────────────────────────────────────────────────────────
# EvalSuite
# ────────────────────────────────────────────────────────────────────

class TestEvalSuite:
    def test_creation(self):
        suite = EvalSuite(name="Test Suite", description="A test")
        assert suite.suite_id != ""
        assert suite.status == SuiteStatus.DRAFT

    def test_add_remove_case(self):
        suite = EvalSuite(name="S")
        case = EvalCase(case_id="c1", input_text="Q")
        suite.add_case(case)
        assert len(suite.cases) == 1
        assert suite.remove_case("c1") is True
        assert suite.remove_case("c1") is False

    def test_total_weight(self):
        suite = EvalSuite(name="S")
        suite.add_case(EvalCase(case_id="c1", input_text="Q", weight=2.0))
        suite.add_case(EvalCase(case_id="c2", input_text="Q", weight=3.0))
        assert suite.total_weight == 5.0

    def test_to_from_json(self):
        suite = EvalSuite(name="JSON Suite", version="2.0.0")
        suite.add_case(EvalCase(case_id="c1", input_text="Q", expected_output="A"))
        s = suite.to_json()
        s2 = EvalSuite.from_json(s)
        assert s2.name == "JSON Suite"
        assert s2.version == "2.0.0"
        assert len(s2.cases) == 1

    def test_dimensions(self):
        suite = EvalSuite(name="S", dimensions=[QualityDimension.ACCURACY, QualityDimension.SAFETY])
        assert len(suite.dimensions) == 2
        assert QualityDimension.ACCURACY in suite.dimensions


# ────────────────────────────────────────────────────────────────────
# QualityScorer
# ────────────────────────────────────────────────────────────────────

class TestQualityScorer:
    @pytest.fixture
    def scorer(self):
        return QualityScorer()

    def test_exact_match_perfect(self, scorer):
        case = EvalCase(case_id="c1", input_text="What is 2+2?",
                        expected_output="4")
        result = scorer.score_case(case, "4")
        # The accuracy dimension should be 1.0, but composite is weighted
        assert result.dimensions["accuracy"].score == 1.0
        assert result.dimensions["accuracy"].passed
        assert result.overall_score > 0.7  # weighted composite above threshold

    def test_partial_match(self, scorer):
        case = EvalCase(case_id="c1", input_text="What is 2+2?",
                        expected_output="The answer is 4")
        result = scorer.score_case(case, "The answer is 5")
        assert 0.0 < result.overall_score < 1.0

    def test_empty_output(self, scorer):
        case = EvalCase(case_id="c1", input_text="Q", expected_output="A")
        result = scorer.score_case(case, "")
        assert result.overall_score <= 0.5

    def test_safety_clean_output(self, scorer):
        case = EvalCase(case_id="c1", input_text="Q", expected_output="A")
        result = scorer.score_case(case, "This is a safe and friendly response.")
        dim = result.dimensions.get("safety")
        assert dim is not None
        assert dim.score == 1.0

    def test_safety_unsafe_output(self, scorer):
        case = EvalCase(case_id="c1", input_text="Q", expected_output="A")
        result = scorer.score_case(case, "You should kill and hack to steal data.")
        dim = result.dimensions.get("safety")
        assert dim is not None
        assert dim.score < 1.0

    def test_custom_scorer(self):
        def custom_acc(inp, exp, act):
            return 0.5

        config = ScorerConfig(
            dimensions=(QualityDimension.ACCURACY,),
            weights={QualityDimension.ACCURACY: 1.0},
            thresholds={QualityDimension.ACCURACY: 0.5},
            custom_scorers={QualityDimension.ACCURACY: custom_acc},
        )
        scorer = QualityScorer(config)
        case = EvalCase(case_id="c1", input_text="Q", expected_output="A")
        result = scorer.score_case(case, "Anything")
        assert result.overall_score == 0.5

    def test_fluency_dimension(self, scorer):
        case = EvalCase(case_id="c1", input_text="Q", expected_output="A")
        result = scorer.score_case(case, "The quick brown fox jumps over the lazy dog.")
        dim = result.dimensions.get("fluency")
        # fluence isn't in default dimensions, so it won't be scored
        # unless we configure it explicitly
        assert dim is None  # fluency not in default config

    def test_toxicity_inverse(self, scorer):
        config = ScorerConfig(
            dimensions=(QualityDimension.TOXICITY,),
            weights={QualityDimension.TOXICITY: 1.0},
            thresholds={QualityDimension.TOXICITY: 0.5},  # high threshold = must be non-toxic
        )
        scorer2 = QualityScorer(config)
        case = EvalCase(case_id="c1", input_text="Q", expected_output="")
        result = scorer2.score_case(case, "I will help you kill people.")
        dim = result.dimensions.get("toxicity")
        assert dim is not None
        # Toxicity inverses safety — high toxicity = high toxicity score (bad)
        assert dim.score > 0.0

    def test_scorer_config_validation(self):
        # Weights must sum to ~1
        with pytest.raises(EvaluationError):
            ScorerConfig(
                dimensions=(QualityDimension.ACCURACY, QualityDimension.SAFETY),
                weights={QualityDimension.ACCURACY: 0.5, QualityDimension.SAFETY: 0.2},
                thresholds={QualityDimension.ACCURACY: 0.7, QualityDimension.SAFETY: 0.8},
            )

    def test_scorer_config_missing_threshold(self):
        with pytest.raises(EvaluationError):
            ScorerConfig(
                dimensions=(QualityDimension.ACCURACY,),
                weights={QualityDimension.ACCURACY: 1.0},
                thresholds={},  # missing
            )


# ────────────────────────────────────────────────────────────────────
# BenchmarkRunner
# ────────────────────────────────────────────────────────────────────

class TestBenchmarkRunner:
    @pytest.fixture
    def runner(self):
        r = BenchmarkRunner()
        suite = EvalSuite(name="Mini", suite_id="mini_suite",
                          dimensions=[QualityDimension.ACCURACY])
        suite.add_case(EvalCase(case_id="c1", input_text="2+2", expected_output="4"))
        suite.add_case(EvalCase(case_id="c2", input_text="Capital of France",
                                expected_output="Paris"))
        r.register_suite(suite)
        return r

    def test_run_single_suite(self, runner):
        def model(prompt: str) -> str:
            if "2+2" in prompt:
                return "4"
            return "Paris"

        run = runner.run("mini_suite", model, model_name="test_model", model_version="1.0")
        assert run.run_id != ""
        assert run.total_cases == 2
        assert run.pass_rate == 1.0
        assert run.overall_score > 0.7  # weighted composite
        assert run.model_name == "test_model"

    def test_run_partial_failure(self, runner):
        def model(prompt: str) -> str:
            return "Wrong answer"

        run = runner.run("mini_suite", model, model_name="bad_model")
        assert run.pass_rate == 0.0
        assert run.overall_score < 1.0

    def test_suite_not_found(self, runner):
        with pytest.raises(SuiteNotFoundError):
            runner.run("nonexistent", lambda p: "x")

    def test_get_suite(self, runner):
        assert runner.get_suite("mini_suite") is not None
        assert runner.get_suite("nonexistent") is None

    def test_run_all_suites(self, runner):
        suite2 = EvalSuite(name="Mini2", suite_id="mini2",
                           dimensions=[QualityDimension.ACCURACY])
        suite2.add_case(EvalCase(case_id="c3", input_text="Q", expected_output="A"))
        runner.register_suite(suite2)
        runs = runner.run_all_suites(lambda p: p, model_name="echo")
        assert len(runs) == 2


# ────────────────────────────────────────────────────────────────────
# EvalStore
# ────────────────────────────────────────────────────────────────────

class TestEvalStore:
    @pytest.fixture
    def store(self):
        s = EvalStore()
        r1 = EvalRun(run_id="r1", suite_id="s1", suite_name="Suite 1",
                     model_name="model_a", model_version="1.0",
                     overall_score=0.85, overall_passed=True,
                     passed_cases=8, failed_cases=2, total_cases=10,
                     aggregated={"accuracy": 0.9, "safety": 0.8},
                     completed_at="2024-01-01T00:00:00")
        r2 = EvalRun(run_id="r2", suite_id="s1", suite_name="Suite 1",
                     model_name="model_a", model_version="2.0",
                     overall_score=0.92, overall_passed=True,
                     passed_cases=9, failed_cases=1, total_cases=10,
                     aggregated={"accuracy": 0.95, "safety": 0.89},
                     completed_at="2024-02-01T00:00:00")
        r3 = EvalRun(run_id="r3", suite_id="s2", suite_name="Suite 2",
                     model_name="model_b", model_version="1.0",
                     overall_score=0.70, overall_passed=False,
                     passed_cases=5, failed_cases=5, total_cases=10,
                     aggregated={"accuracy": 0.65, "safety": 0.75},
                     completed_at="2024-01-15T00:00:00")
        s.save(r1)
        s.save(r2)
        s.save(r3)
        return s

    def test_get(self, store):
        assert store.get("r1") is not None
        assert store.get("nonexistent") is None

    def test_query_by_model(self, store):
        results = store.query(model_name="model_a")
        assert len(results) == 2

    def test_query_by_suite(self, store):
        results = store.query(suite_id="s2")
        assert len(results) == 1
        assert results[0].model_name == "model_b"

    def test_query_by_score_range(self, store):
        results = store.query(min_score=0.9)
        assert len(results) == 1
        assert results[0].run_id == "r2"

    def test_query_by_passed(self, store):
        results = store.query(passed=True)
        assert len(results) == 2

    def test_latest_for_model(self, store):
        latest = store.latest_for_model("model_a")
        # For s1, the latest run is r2
        assert "s1" in latest
        assert latest["s1"].run_id == "r2"

    def test_history_for_suite(self, store):
        history = store.history_for_suite("s1")
        assert len(history) == 2
        assert history[0].run_id == "r1"  # oldest first

    def test_serialization(self, store):
        data = store.to_dict()
        store2 = EvalStore.from_dict(data)
        assert store2.get("r1") is not None
        assert store2.get("r1").overall_score == 0.85

    def test_to_from_json(self, store):
        s = store.to_json()
        store2 = EvalStore.from_json(s)
        assert store2.get("r2").overall_score == 0.92


# ────────────────────────────────────────────────────────────────────
# ComparisonMatrix
# ────────────────────────────────────────────────────────────────────

class TestComparisonMatrix:
    @pytest.fixture
    def matrix(self):
        m = ComparisonMatrix()
        r1 = EvalRun(run_id="r1", suite_id="s1", suite_name="Accuracy",
                     model_name="gpt4", model_version="1",
                     overall_score=0.92, overall_passed=True,
                     passed_cases=9, failed_cases=1, total_cases=10,
                     aggregated={"accuracy": 0.92})
        r2 = EvalRun(run_id="r2", suite_id="s1", suite_name="Accuracy",
                     model_name="claude", model_version="1",
                     overall_score=0.88, overall_passed=True,
                     passed_cases=8, failed_cases=2, total_cases=10,
                     aggregated={"accuracy": 0.88})
        r3 = EvalRun(run_id="r3", suite_id="s2", suite_name="Safety",
                     model_name="gpt4", model_version="1",
                     overall_score=0.85, overall_passed=True,
                     passed_cases=8, failed_cases=2, total_cases=10,
                     aggregated={"safety": 0.85})
        r4 = EvalRun(run_id="r4", suite_id="s2", suite_name="Safety",
                     model_name="claude", model_version="1",
                     overall_score=0.91, overall_passed=True,
                     passed_cases=9, failed_cases=1, total_cases=10,
                     aggregated={"safety": 0.91})
        m.add_run(r1)
        m.add_run(r2)
        m.add_run(r3)
        m.add_run(r4)
        return m

    def test_models(self, matrix):
        models = matrix.models()
        assert "gpt4" in models
        assert "claude" in models

    def test_suites(self, matrix):
        suites = matrix.suites()
        assert "Accuracy" in suites
        assert "Safety" in suites

    def test_rank_models(self, matrix):
        ranking = matrix.rank_models()
        assert len(ranking) == 2
        assert ranking[0].rank == 1  # best
        # gpt4: (0.92 + 0.85)/2 = 0.885, claude: (0.88 + 0.91)/2 = 0.895
        assert ranking[0].model_name == "claude"

    def test_head_to_head(self, matrix):
        h2h = matrix.head_to_head("gpt4", "claude")
        assert h2h["model_a"]["name"] == "gpt4"
        assert h2h["model_b"]["name"] == "claude"
        assert "delta" in h2h
        assert "per_suite" in h2h

    def test_to_table_list(self, matrix):
        table = matrix.to_table(fmt="list")
        assert isinstance(table, list)
        assert len(table) >= 4  # 2 models × 2 suites


# ────────────────────────────────────────────────────────────────────
# RegressionDetector
# ────────────────────────────────────────────────────────────────────

class TestRegressionDetector:
    @pytest.fixture
    def detector(self):
        return RegressionDetector(absolute_threshold=0.05, relative_threshold=5.0)

    def test_no_regression(self, detector):
        baseline = EvalRun(
            run_id="b1", suite_id="s1", suite_name="S1",
            model_name="m1", overall_score=0.85,
            passed_cases=8, failed_cases=2, total_cases=10,
            aggregated={"accuracy": 0.90, "safety": 0.80},
        )
        current = EvalRun(
            run_id="c1", suite_id="s1", suite_name="S1",
            model_name="m1", overall_score=0.86,
            passed_cases=8, failed_cases=2, total_cases=10,
            aggregated={"accuracy": 0.91, "safety": 0.81},
        )
        report = detector.detect(baseline, current)
        assert not report.has_regression

    def test_regression_detected(self, detector):
        baseline = EvalRun(
            run_id="b1", suite_id="s1", suite_name="S1",
            model_name="m1", overall_score=0.85,
            passed_cases=8, failed_cases=2, total_cases=10,
            aggregated={"accuracy": 0.90, "safety": 0.80},
        )
        current = EvalRun(
            run_id="c1", suite_id="s1", suite_name="S1",
            model_name="m1", overall_score=0.70,
            passed_cases=5, failed_cases=5, total_cases=10,
            aggregated={"accuracy": 0.70, "safety": 0.60},
        )
        report = detector.detect(baseline, current)
        assert report.has_regression
        assert report.overall_delta < 0

    def test_signals_have_directions(self, detector):
        baseline = EvalRun(
            run_id="b1", suite_id="s1", suite_name="S1",
            model_name="m1", overall_score=0.80,
            passed_cases=8, failed_cases=2, total_cases=10,
            aggregated={"accuracy": 0.85, "safety": 0.75},
        )
        current = EvalRun(
            run_id="c1", suite_id="s1", suite_name="S1",
            model_name="m1", overall_score=0.75,
            passed_cases=7, failed_cases=3, total_cases=10,
            aggregated={"accuracy": 0.65, "safety": 0.85},
        )
        report = detector.detect(baseline, current)
        acc_signal = next(s for s in report.signals if s.dimension == "accuracy")
        safety_signal = next(s for s in report.signals if s.dimension == "safety")
        assert acc_signal.direction == RegressionDirection.REGRESSED
        assert safety_signal.direction == RegressionDirection.IMPROVED

    def test_new_dimension(self, detector):
        baseline = EvalRun(
            run_id="b1", suite_id="s1", suite_name="S1",
            model_name="m1", overall_score=0.80,
            passed_cases=8, failed_cases=2, total_cases=10,
            aggregated={"accuracy": 0.85},
        )
        current = EvalRun(
            run_id="c1", suite_id="s1", suite_name="S1",
            model_name="m1", overall_score=0.80,
            passed_cases=8, failed_cases=2, total_cases=10,
            aggregated={"accuracy": 0.85, "coherence": 0.70},
        )
        report = detector.detect(baseline, current)
        new_signal = next((s for s in report.signals if s.dimension == "coherence"), None)
        assert new_signal is not None
        assert new_signal.direction == RegressionDirection.NEW

    def test_detect_all(self, detector):
        baseline = EvalRun(
            run_id="b1", suite_id="s1", suite_name="S1",
            model_name="m1", overall_score=0.85,
            passed_cases=8, failed_cases=2, total_cases=10,
            aggregated={"accuracy": 0.90},
        )
        current = EvalRun(
            run_id="c1", suite_id="s1", suite_name="S1",
            model_name="m1", overall_score=0.80,
            passed_cases=7, failed_cases=3, total_cases=10,
            aggregated={"accuracy": 0.70},
        )
        reports = detector.detect_all([baseline], current)
        assert len(reports) == 1
        assert reports[0].has_regression


# ────────────────────────────────────────────────────────────────────
# Standard Benchmarks
# ────────────────────────────────────────────────────────────────────

class TestStandardBenchmarks:
    def test_accuracy_suite(self):
        suite = StandardBenchmarks.accuracy_suite()
        assert suite.name == "Standard Accuracy"
        assert len(suite.cases) == 5
        assert suite.status == SuiteStatus.ACTIVE
        assert QualityDimension.ACCURACY in suite.dimensions
        assert QualityDimension.FACTUALITY in suite.dimensions

    def test_safety_suite(self):
        suite = StandardBenchmarks.safety_suite()
        assert suite.name == "Standard Safety"
        assert len(suite.cases) == 3
        # Danger-related cases have higher weight
        assert suite.cases[0].weight == 2.0
        assert QualityDimension.SAFETY in suite.dimensions

    def test_coherence_suite(self):
        suite = StandardBenchmarks.coherence_suite()
        assert suite.name == "Standard Coherence"
        assert len(suite.cases) == 2
        assert QualityDimension.COHERENCE in suite.dimensions


# ────────────────────────────────────────────────────────────────────
# EvalResult roundtrip
# ────────────────────────────────────────────────────────────────────

class TestEvalResultRoundtrip:
    def test_to_from_dict(self):
        scorer = QualityScorer()
        case = EvalCase(case_id="c1", input_text="Q", expected_output="A")
        result = scorer.score_case(case, "A")
        d = result.to_dict()
        r2 = EvalResult.from_dict(d)
        assert r2.case_id == "c1"
        assert r2.overall_score == result.overall_score

    def test_evalrun_to_from_dict(self):
        scorer = QualityScorer()
        case = EvalCase(case_id="c1", input_text="Q", expected_output="A")
        result = scorer.score_case(case, "A")
        run = EvalRun(
            run_id="test_run", suite_id="s1", suite_name="S",
            model_name="m1", results=[result],
            overall_score=1.0, overall_passed=True,
            passed_cases=1, failed_cases=0, total_cases=1,
            aggregated={"accuracy": 1.0},
        )
        d = run.to_dict()
        r2 = EvalRun.from_dict(d)
        assert r2.run_id == "test_run"
        assert r2.overall_score == 1.0
        assert len(r2.results) == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])