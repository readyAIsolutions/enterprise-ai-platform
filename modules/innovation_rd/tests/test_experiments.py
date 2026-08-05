"""
Tests for the master-class statistical experiment surface (experiments.py).

Covers: Welch's t-test p-value computation, significance decisions, bootstrap
determinism, registry lifecycle + persistence round-trip, and the guarded
ExperimentRunner.
"""

import contextlib
import os
import tempfile
import unittest
from typing import Never

import pytest

from enterprise.modules.innovation_rd.experiments import (
    AssessmentResult,
    Experiment,
    ExperimentRegistry,
    ExperimentRunner,
    HypothesisTest,
    assess,
    bootstrap_p_value,
    permutation_test,
    welch_t_test,
)

# ---------------------------------------------------------------------------
# HypothesisTest: p-values + significance.
# ---------------------------------------------------------------------------


class TestHypothesisTest(unittest.TestCase):
    def test_welch_p_value_significant(self) -> None:
        """Clear separation between groups should yield a tiny p-value."""
        ht = HypothesisTest([1, 2, 3, 4, 5], [10, 11, 12, 13, 14])
        p = ht.p_value()
        assert p < 0.05

    def test_welch_p_value_not_significant(self) -> None:
        """Overlapping groups should yield a large p-value."""
        ht = HypothesisTest([1, 2, 3, 4, 5], [1.1, 2.2, 3.1, 4.2, 5.1])
        p = ht.p_value()
        assert p > 0.05

    def test_is_significant_decision(self) -> None:
        ht = HypothesisTest([1, 2, 3, 4, 5], [10, 11, 12, 13, 14])
        assert ht.is_significant(alpha=0.05)
        assert not ht.is_significant(alpha=1e-09)

    def test_welch_function_returns_three_tuple(self) -> None:
        t, df, p = welch_t_test([1, 2, 3], [5, 6, 7])
        assert isinstance(t, float)
        assert isinstance(df, float)
        assert isinstance(p, float)
        assert p >= 0.0
        assert p <= 1.0

    def test_permutation_degenerate_constant_groups(self) -> None:
        """Zero variance in both groups -> no difference, p approaches 1."""
        _, _, p = welch_t_test([5, 5, 5], [5, 5, 5])
        assert p == 1.0


# ---------------------------------------------------------------------------
# Bootstrap / permutation determinism.
# ---------------------------------------------------------------------------


class TestDeterminism(unittest.TestCase):
    def test_permutation_deterministic_with_seed(self) -> None:
        p1 = permutation_test([1, 2, 3], [4, 5, 6], n_permutations=2000, seed=7)
        p2 = permutation_test([1, 2, 3], [4, 5, 6], n_permutations=2000, seed=7)
        assert p1 == p2

    def test_bootstrap_deterministic_with_seed(self) -> None:
        r1 = bootstrap_p_value([1, 2, 3, 4], [5, 6, 7, 8], n_bootstrap=2000, seed=99)
        r2 = bootstrap_p_value([1, 2, 3, 4], [5, 6, 7, 8], n_bootstrap=2000, seed=99)
        assert r1 == r2

    def test_assess_fallback_bootstrap_deterministic(self) -> None:
        a = assess([1, 2, 3], [4, 5, 6], fallback_to_bootstrap=True, seed=42)
        b = assess([1, 2, 3], [4, 5, 6], fallback_to_bootstrap=True, seed=42)
        assert a.p_value == b.p_value

    def test_assess_fallback_uses_permutation(self) -> None:
        res = assess([1, 2, 3], [4, 5, 6], fallback_to_bootstrap=True, seed=1)
        assert res.method == "permutation"

    def test_assess_default_uses_welch(self) -> None:
        res = assess([1, 2, 3, 4], [5, 6, 7, 8])
        assert res.method == "welch"

    def test_assess_returns_assessment_result(self) -> None:
        res = assess([1, 2, 3, 4], [5, 6, 7, 8])
        assert isinstance(res, AssessmentResult)
        assert res.effect_size is not None


# ---------------------------------------------------------------------------
# Registry lifecycle + persistence round-trip.
# ---------------------------------------------------------------------------


class TestExperimentRegistry(unittest.TestCase):
    def setUp(self) -> None:
        fd, self.path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self.reg = ExperimentRegistry(db_path=self.path)

    def tearDown(self) -> None:
        with contextlib.suppress(Exception):
            self.reg.close()
        if os.path.exists(self.path):
            os.remove(self.path)

    def test_register_and_get(self) -> None:
        exp = self.reg.register_experiment("Caching reduces latency")
        assert isinstance(exp, Experiment)
        assert exp.id is not None
        assert exp.status == "draft"
        fetched = self.reg.get(exp.id)
        assert fetched.hypothesis == "Caching reduces latency"

    def test_lifecycle_transitions(self) -> None:
        exp = self.reg.register_experiment("Test hypothesis")
        assert self.reg.start(exp.id)
        assert self.reg.get(exp.id).status == "running"
        assert self.reg.record_metric_before(exp.id, 1.0)
        assert self.reg.record_metric_before(exp.id, 2.0)
        assert self.reg.record_metric_after(exp.id, 10.0)
        assert self.reg.record_metric_after(exp.id, 11.0)
        fin = self.reg.finish(exp.id)
        assert fin.status == "finished"
        assert fin.p_value is not None

    def test_persistence_round_trip(self) -> None:
        """Close and reopen the registry on the same db — data survives."""
        exp = self.reg.register_experiment("Persisted hypothesis")
        self.reg.start(exp.id)
        self.reg.record_metric_before(exp.id, 1.0)
        self.reg.record_metric_after(exp.id, 10.0)
        self.reg.finish(exp.id)
        self.reg.close()

        reg2 = ExperimentRegistry(db_path=self.path)
        try:
            recovered = reg2.get(exp.id)
            assert recovered is not None
            assert recovered.hypothesis == "Persisted hypothesis"
            assert recovered.status == "finished"
            assert recovered.metrics_before == [1.0]
            assert recovered.metrics_after == [10.0]
            assert recovered.p_value is not None
        finally:
            reg2.close()

    def test_start_rejected_when_already_started(self) -> None:
        exp = self.reg.register_experiment("Once only")
        assert self.reg.start(exp.id)
        assert not self.reg.start(exp.id)

    def test_get_missing_returns_none(self) -> None:
        assert self.reg.get("does-not-exist") is None

    def test_conclude_records_significance_when_separated(self) -> None:
        exp = self.reg.register_experiment("Strong effect")
        self.reg.start(exp.id)
        for i in range(1, 6):
            self.reg.record_metric_before(exp.id, i)
            self.reg.record_metric_after(exp.id, i + 10)
        fin = self.reg.conclude(exp.id, alpha=0.05)
        assert fin.significance
        assert "Significant" in fin.conclusion

    def test_conclude_not_significant_when_overlapping(self) -> None:
        exp = self.reg.register_experiment("Weak effect")
        self.reg.start(exp.id)
        for i in range(1, 6):
            self.reg.record_metric_before(exp.id, i)
            self.reg.record_metric_after(exp.id, i + 0.1)
        fin = self.reg.conclude(exp.id, alpha=0.05)
        assert not fin.significance


# ---------------------------------------------------------------------------
# ExperimentRunner: guarded harness.
# ---------------------------------------------------------------------------


class TestExperimentRunner(unittest.TestCase):
    def setUp(self) -> None:
        fd, self.path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self.reg = ExperimentRegistry(db_path=self.path)
        self.runner = ExperimentRunner(self.reg, alpha=0.05, seed=42)

    def tearDown(self) -> None:
        with contextlib.suppress(Exception):
            self.reg.close()
        if os.path.exists(self.path):
            os.remove(self.path)

    def _control(self):
        return [1, 2, 3, 4, 5]

    def _treatment(self):
        return [10, 11, 12, 13, 14]

    def test_runner_records_before_and_after(self) -> None:
        exp = self.reg.register_experiment("Runner test")
        self.reg.start(exp.id)
        fin = self.runner.run(exp.id, self._control, self._treatment)
        assert fin.metrics_before == [1, 2, 3, 4, 5]
        assert fin.metrics_after == [10, 11, 12, 13, 14]
        assert fin.status == "finished"

    def test_runner_concludes_significance(self) -> None:
        exp = self.reg.register_experiment("Runner sig")
        self.reg.start(exp.id)
        fin = self.runner.run(exp.id, self._control, self._treatment)
        assert fin.significance
        assert fin.p_value < 0.05

    def test_run_new_registers_and_runs(self) -> None:
        fin = self.runner.run_new("Fresh experiment", self._control, self._treatment)
        assert fin.id is not None
        assert fin.status == "finished"
        assert self.reg.count() == 1

    def test_runner_guards_exception_marks_failed(self) -> None:
        exp = self.reg.register_experiment("Failing")
        self.reg.start(exp.id)

        def boom() -> Never:
            msg = "deliberate failure"
            raise RuntimeError(msg)

        with pytest.raises(RuntimeError):
            self.runner.run(exp.id, self._control, boom)
        failed = self.reg.get(exp.id)
        assert failed.status == "failed"
        assert "Runner error" in failed.conclusion

    def test_runner_rejects_unregistered(self) -> None:
        with pytest.raises(KeyError):
            self.runner.run("no-such-id", self._control, self._treatment)


if __name__ == "__main__":
    unittest.main()
