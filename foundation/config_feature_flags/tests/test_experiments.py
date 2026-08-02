"""
Tests for ExperimentManager.
"""

import math
import time

import pytest

import sys
from pathlib import Path

_project_root = Path(__file__).resolve().parents[5]
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from enterprise.foundation.config_feature_flags.experiments import (
    Experiment,
    ExperimentManager,
    ExperimentResult,
    ExperimentStatus,
    Variant,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

@pytest.fixture
def mgr():
    """Return a fresh ExperimentManager."""
    return ExperimentManager()


@pytest.fixture
def basic_exp(mgr):
    """Create a basic A/B experiment (control vs treatment)."""
    return mgr.create_experiment(
        name="test-exp",
        description="A test experiment",
        variants=[
            Variant(name="control", weight=50),
            Variant(name="treatment", weight=50),
        ],
        target_metric="conversion",
        min_sample_size=100,
    )


# ---------------------------------------------------------------------------
# Experiment CRUD tests
# ---------------------------------------------------------------------------

class TestCRUD:
    """Tests for experiment creation, retrieval, update, and deletion."""

    def test_create_experiment(self, mgr):
        exp = mgr.create_experiment(
            name="my-exp",
            description="Test",
            variants=[
                Variant(name="a", weight=1),
                Variant(name="b", weight=1),
            ],
        )
        assert exp.name == "my-exp"
        assert exp.status == ExperimentStatus.DRAFT
        assert len(exp.variants) == 2

    def test_duplicate_name_raises(self, mgr, basic_exp):
        with pytest.raises(ValueError, match="already exists"):
            mgr.create_experiment(name="test-exp")

    def test_default_variants_when_none_given(self, mgr):
        exp = mgr.create_experiment(name="default-vars")
        assert len(exp.variants) == 2
        assert exp.variants[0].name == "control"

    def test_get_experiment(self, mgr, basic_exp):
        assert mgr.get_experiment("test-exp") is not None
        assert mgr.get_experiment("nonexistent") is None

    def test_list_experiments(self, mgr):
        mgr.create_experiment(name="e1")
        mgr.create_experiment(name="e2")
        all_exps = mgr.list_experiments()
        assert len(all_exps) == 2

        mgr.start_experiment("e1")
        running = mgr.list_experiments(status=ExperimentStatus.RUNNING)
        assert len(running) == 1
        assert running[0].name == "e1"

    def test_update_experiment_draft(self, mgr, basic_exp):
        mgr.update_experiment("test-exp", description="Updated desc")
        assert mgr.get_experiment("test-exp").description == "Updated desc"

    def test_update_experiment_non_draft_raises(self, mgr, basic_exp):
        mgr.start_experiment("test-exp")
        with pytest.raises(ValueError):
            mgr.update_experiment("test-exp", description="Cannot update")

    def test_delete_experiment(self, mgr, basic_exp):
        mgr.delete_experiment("test-exp")
        assert mgr.get_experiment("test-exp") is None


# ---------------------------------------------------------------------------
# Experiment lifecycle tests
# ---------------------------------------------------------------------------

class TestLifecycle:
    """Tests for experiment lifecycle transitions."""

    def test_start_experiment(self, mgr, basic_exp):
        exp = mgr.start_experiment("test-exp")
        assert exp.status == ExperimentStatus.RUNNING
        assert exp.started_at is not None

    def test_start_non_draft_raises(self, mgr, basic_exp):
        mgr.start_experiment("test-exp")
        with pytest.raises(ValueError):
            mgr.start_experiment("test-exp")

    def test_pause_and_resume(self, mgr, basic_exp):
        mgr.start_experiment("test-exp")
        exp = mgr.pause_experiment("test-exp")
        assert exp.status == ExperimentStatus.PAUSED

        exp = mgr.resume_experiment("test-exp")
        assert exp.status == ExperimentStatus.RUNNING

    def test_pause_non_running_raises(self, mgr, basic_exp):
        with pytest.raises(ValueError):
            mgr.pause_experiment("test-exp")

    def test_complete_experiment(self, mgr, basic_exp):
        mgr.start_experiment("test-exp")
        exp = mgr.complete_experiment("test-exp")
        assert exp.status == ExperimentStatus.COMPLETED
        assert exp.ended_at is not None

    def test_complete_paused_experiment(self, mgr, basic_exp):
        mgr.start_experiment("test-exp")
        mgr.pause_experiment("test-exp")
        exp = mgr.complete_experiment("test-exp")
        assert exp.status == ExperimentStatus.COMPLETED

    def test_archive_experiment(self, mgr, basic_exp):
        mgr.start_experiment("test-exp")
        mgr.complete_experiment("test-exp")
        exp = mgr.archive_experiment("test-exp")
        assert exp.status == ExperimentStatus.ARCHIVED


# ---------------------------------------------------------------------------
# Variant assignment tests
# ---------------------------------------------------------------------------

class TestAssignment:
    """Tests for user-to-variant assignment."""

    def test_assign_user(self, mgr, basic_exp):
        mgr.start_experiment("test-exp")
        variant = mgr.assign("test-exp", "user-1")
        assert variant is not None
        assert variant.name in ("control", "treatment")

    def test_assignment_is_consistent(self, mgr, basic_exp):
        mgr.start_experiment("test-exp")
        v1 = mgr.assign("test-exp", "consistent-user")
        v2 = mgr.assign("test-exp", "consistent-user")
        assert v1.name == v2.name

    def test_assign_non_running_raises(self, mgr, basic_exp):
        with pytest.raises(ValueError):
            mgr.assign("test-exp", "user-1")

    def test_assign_paused_experiment_works(self, mgr, basic_exp):
        mgr.start_experiment("test-exp")
        mgr.pause_experiment("test-exp")
        variant = mgr.assign("test-exp", "user-paused")
        assert variant is not None

    def test_assignment_counts_samples(self, mgr, basic_exp):
        mgr.start_experiment("test-exp")
        for i in range(100):
            mgr.assign("test-exp", f"user-{i}")
        exp = mgr.get_experiment("test-exp")
        assert exp.total_samples == 100

    def test_get_assignment(self, mgr, basic_exp):
        mgr.start_experiment("test-exp")
        mgr.assign("test-exp", "user-42")
        variant_name = mgr.get_assignment("test-exp", "user-42")
        assert variant_name in ("control", "treatment")
        assert mgr.get_assignment("test-exp", "unassigned") is None

    def test_traffic_allocation(self, mgr):
        """Users outside traffic_allocation should get control variant."""
        mgr.create_experiment(
            name="partial",
            variants=[
                Variant(name="control", weight=50),
                Variant(name="treatment", weight=50),
            ],
            traffic_allocation=0.5,
        )
        mgr.start_experiment("partial")

        control_count = 0
        total = 200
        for i in range(total):
            v = mgr.assign("partial", f"user-{i}")
            if v.name == "control":
                control_count += 1
        # At least 50% should be control (the traffic check returns control for excluded)
        assert control_count >= total // 2


# ---------------------------------------------------------------------------
# Metrics tests
# ---------------------------------------------------------------------------

class TestMetrics:
    """Tests for metrics recording and retrieval."""

    def test_record_metric(self, mgr, basic_exp):
        mgr.start_experiment("test-exp")
        mgr.assign("test-exp", "user-1")
        mgr.record_metric("test-exp", "user-1", "conversion", 1.0)
        mgr.record_metric("test-exp", "user-1", "revenue", 9.99)

        # Metrics are per-variant, so we need to check which variant user-1 got
        variant_name = mgr.get_assignment("test-exp", "user-1")
        exp = mgr.get_experiment("test-exp")
        variant = exp.get_variant(variant_name)
        assert variant.metrics.get("conversion") == 1.0
        assert variant.metrics.get("revenue") == 9.99

    def test_record_metric_unassigned_user_noop(self, mgr, basic_exp):
        mgr.start_experiment("test-exp")
        # User not assigned, recording should be a no-op
        mgr.record_metric("test-exp", "never-assigned", "conversion", 1.0)

    def test_record_metric_nonexistent_experiment_noop(self, mgr):
        mgr.record_metric("ghost-exp", "user-1", "metric", 1.0)

    def test_get_metric(self, mgr, basic_exp):
        mgr.start_experiment("test-exp")
        for i in range(50):
            mgr.assign("test-exp", f"user-{i}")
            mgr.record_metric("test-exp", f"user-{i}", "conversion", 1.0)

        # At least one variant should have metrics
        exp = mgr.get_experiment("test-exp")
        total_conversions = sum(v.metrics.get("conversion", 0.0) for v in exp.variants)
        assert total_conversions == 50.0

    def test_variant_get_rate(self):
        v = Variant(name="test", sample_count=100)
        v.record_metric("conversion", 30.0)
        assert v.get_rate("conversion") == 0.3

    def test_variant_get_rate_zero_samples(self):
        v = Variant(name="empty", sample_count=0)
        v.record_metric("conversion", 10.0)
        assert v.get_rate("conversion") == 0.0


# ---------------------------------------------------------------------------
# Analysis tests
# ---------------------------------------------------------------------------

class TestAnalysis:
    """Tests for statistical analysis."""

    def test_analyze_with_sufficient_data(self, mgr):
        mgr.create_experiment(
            "stat-test",
            variants=[
                Variant(name="control", weight=1),
                Variant(name="treatment", weight=1),
            ],
            target_metric="conversion",
            min_sample_size=100,
        )
        mgr.start_experiment("stat-test")

        # Assign users and record conversions
        # Control: 10% conversion (100 conversions out of 1000)
        # Treatment: 12% conversion (120 conversions out of 1000)
        for i in range(2000):
            v = mgr.assign("stat-test", f"user-{i}")
            is_control = v.name == "control"
            should_convert = False
            if is_control:
                should_convert = i % 10 == 0  # 10%
            else:
                should_convert = i % 8 == 0   # 12.5%

            if should_convert:
                mgr.record_metric("stat-test", f"user-{i}", "conversion", 1.0)

        result = mgr.analyze("stat-test")
        assert result.total_samples == 2000
        assert result.target_metric == "conversion"
        assert "control" in result.variant_rates

    def test_analyze_insufficient_data(self, mgr, basic_exp):
        mgr.start_experiment("test-exp")
        mgr.assign("test-exp", "user-only")
        result = mgr.analyze("test-exp")
        assert result.is_significant is False
        assert result.p_value == 1.0

    def test_clear_winner_detection(self, mgr):
        """When treatment clearly outperforms control."""
        mgr.create_experiment(
            "clear-winner",
            variants=[
                Variant(name="control", weight=1),
                Variant(name="treatment", weight=1),
            ],
            target_metric="click",
            min_sample_size=100,
        )
        mgr.start_experiment("clear-winner")

        for i in range(2000):
            v = mgr.assign("clear-winner", f"user-{i}")
            # Control: 10% conversion, Treatment: 40% conversion
            if v.name == "control" and i % 10 == 0:
                mgr.record_metric("clear-winner", f"user-{i}", "click", 1.0)
            elif v.name == "treatment" and i % 2 == 0:
                mgr.record_metric("clear-winner", f"user-{i}", "click", 1.0)

        result = mgr.analyze("clear-winner")
        # With such a large difference, it should be significant
        assert result.is_significant is True
        assert result.winner == "treatment"
        assert result.lift > 0

    def test_get_winner_convenience(self, mgr):
        mgr.create_experiment(
            "win-test",
            variants=[
                Variant(name="control", weight=1),
                Variant(name="better", weight=1),
            ],
            target_metric="conv",
            min_sample_size=100,
        )
        mgr.start_experiment("win-test")
        for i in range(1000):
            v = mgr.assign("win-test", f"user-{i}")
            if v.name == "better" and i % 3 == 0:
                mgr.record_metric("win-test", f"user-{i}", "conv", 1.0)
            elif v.name == "control" and i % 10 == 0:
                mgr.record_metric("win-test", f"user-{i}", "conv", 1.0)

        winner = mgr.get_winner("win-test")
        # With enough data, treatment should win
        assert winner is not None


# ---------------------------------------------------------------------------
# Reset tests
# ---------------------------------------------------------------------------

class TestReset:
    """Tests for resetting metrics and assignments."""

    def test_reset_metrics(self, mgr, basic_exp):
        mgr.start_experiment("test-exp")
        mgr.assign("test-exp", "user-1")
        mgr.record_metric("test-exp", "user-1", "conversion", 1.0)
        mgr.reset_metrics("test-exp")

        exp = mgr.get_experiment("test-exp")
        for v in exp.variants:
            assert v.metrics == {}
            assert v.sample_count == 0

    def test_clear_assignments(self, mgr, basic_exp):
        mgr.start_experiment("test-exp")
        mgr.assign("test-exp", "user-1")
        assert mgr.get_assignment("test-exp", "user-1") is not None

        mgr.clear_assignments("test-exp")
        assert mgr.get_assignment("test-exp", "user-1") is None


# ---------------------------------------------------------------------------
# Variant model tests
# ---------------------------------------------------------------------------

class TestVariantModel:
    """Tests for Variant dataclass properties."""

    def test_record_multiple_metrics(self):
        v = Variant(name="test")
        v.record_metric("a", 1.0)
        v.record_metric("a", 2.0)
        v.record_metric("b", 5.0)
        assert v.metrics["a"] == 3.0
        assert v.metrics["b"] == 5.0

    def test_rate_with_sample_count(self):
        v = Variant(name="test", sample_count=200)
        v.record_metric("conv", 40.0)
        assert v.get_rate("conv") == 0.2


# ---------------------------------------------------------------------------
# Experiment model validation
# ---------------------------------------------------------------------------

class TestExperimentValidation:
    """Tests for Experiment parameter validation."""

    def test_too_few_variants_raises(self):
        with pytest.raises(ValueError, match="least 2"):
            Experiment(
                name="bad",
                variants=[Variant(name="only-one")],
            )

    def test_invalid_confidence_level(self):
        with pytest.raises(ValueError):
            Experiment(
                name="bad",
                variants=[Variant(name="a"), Variant(name="b")],
                confidence_level=1.5,
            )
        with pytest.raises(ValueError):
            Experiment(
                name="bad",
                variants=[Variant(name="a"), Variant(name="b")],
                confidence_level=0.0,
            )

    def test_invalid_traffic_allocation(self):
        with pytest.raises(ValueError):
            Experiment(
                name="bad",
                variants=[Variant(name="a"), Variant(name="b")],
                traffic_allocation=1.5,
            )
        with pytest.raises(ValueError):
            Experiment(
                name="bad",
                variants=[Variant(name="a"), Variant(name="b")],
                traffic_allocation=0.0,
            )


# ---------------------------------------------------------------------------
# Experiment model properties tests
# ---------------------------------------------------------------------------

class TestExperimentProperties:
    """Tests for Experiment model computed properties."""

    def test_total_weight(self, mgr, basic_exp):
        assert basic_exp.total_weight == 100.0

    def test_total_samples(self, mgr, basic_exp):
        mgr.start_experiment("test-exp")
        for i in range(50):
            mgr.assign("test-exp", f"user-{i}")
        assert basic_exp.total_samples == 50

    def test_get_variant(self, basic_exp):
        v = basic_exp.get_variant("control")
        assert v is not None
        assert v.name == "control"
        assert basic_exp.get_variant("nonexistent") is None

    def test_normalized_weights(self, basic_exp):
        nw = basic_exp.normalized_weights()
        assert len(nw) == 2
        assert math.isclose(nw[0], 0.5)
        assert math.isclose(nw[1], 0.5)

    def test_normalized_weights_zero_total(self):
        exp = Experiment(
            name="zero-weight",
            variants=[
                Variant(name="a", weight=0),
                Variant(name="b", weight=0),
            ],
        )
        nw = exp.normalized_weights()
        assert math.isclose(nw[0], 0.5)
        assert math.isclose(nw[1], 0.5)


# ---------------------------------------------------------------------------
# Statistical test edge cases
# ---------------------------------------------------------------------------

class TestStatisticalEdgeCases:
    """Tests for statistical calculation edge cases."""

    def test_z_test_zero_samples(self):
        p = ExperimentManager._z_test_proportions(0, 0, 0, 0)
        assert p == 1.0

    def test_z_test_pooled_zero(self):
        p = ExperimentManager._z_test_proportions(0, 100, 0, 100)
        assert p == 1.0

    def test_z_test_pooled_one(self):
        p = ExperimentManager._z_test_proportions(100, 100, 100, 100)
        assert p == 1.0

    def test_z_test_clear_difference(self):
        """Large sample, clear difference should give very small p-value."""
        p = ExperimentManager._z_test_proportions(
            success_a=100, n_a=1000,
            success_b=200, n_b=1000,
        )
        assert p < 0.001

    def test_z_test_no_difference(self):
        p = ExperimentManager._z_test_proportions(
            success_a=100, n_a=1000,
            success_b=100, n_b=1000,
        )
        assert p > 0.05


# ---------------------------------------------------------------------------
# Hash distribution tests
# ---------------------------------------------------------------------------

class TestHashDistribution:
    """Tests for hash-based assignment distribution."""

    def test_50_50_split(self, mgr):
        """With 50/50 weights, distribution should be roughly even."""
        mgr.create_experiment(
            "split-test",
            variants=[
                Variant(name="a", weight=1),
                Variant(name="b", weight=1),
            ],
        )
        mgr.start_experiment("split-test")

        counts = {"a": 0, "b": 0}
        n = 1000
        for i in range(n):
            v = mgr.assign("split-test", f"user-{i}")
            counts[v.name] += 1

        ratio = min(counts["a"], counts["b"]) / max(counts["a"], counts["b"])
        assert ratio > 0.8, f"Split ratio {ratio:.3f} too skewed"


# ---------------------------------------------------------------------------
# ExperimentResult
# ---------------------------------------------------------------------------

class TestExperimentResult:
    """Tests for ExperimentResult dataclass."""

    def test_default_values(self):
        result = ExperimentResult(experiment_name="test", target_metric="conv")
        assert result.experiment_name == "test"
        assert result.p_value == 1.0
        assert result.is_significant is False
        assert result.winner is None
        assert result.test_used == "z-test-proportions"