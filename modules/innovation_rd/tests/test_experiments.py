"""
Tests for the master-class statistical experiment surface (experiments.py).

Covers: Welch's t-test p-value computation, significance decisions, bootstrap
determinism, registry lifecycle + persistence round-trip, and the guarded
ExperimentRunner.
"""

import os
import tempfile
import unittest

from ..experiments import (
    Experiment,
    ExperimentRegistry,
    ExperimentRunner,
    HypothesisTest,
    AssessmentResult,
    assess,
    welch_t_test,
    permutation_test,
    bootstrap_p_value,
)


# ---------------------------------------------------------------------------
# HypothesisTest: p-values + significance.
# ---------------------------------------------------------------------------


class TestHypothesisTest(unittest.TestCase):
    def test_welch_p_value_significant(self):
        """Clear separation between groups should yield a tiny p-value."""
        ht = HypothesisTest([1, 2, 3, 4, 5], [10, 11, 12, 13, 14])
        p = ht.p_value()
        self.assertLess(p, 0.05)

    def test_welch_p_value_not_significant(self):
        """Overlapping groups should yield a large p-value."""
        ht = HypothesisTest([1, 2, 3, 4, 5], [1.1, 2.2, 3.1, 4.2, 5.1])
        p = ht.p_value()
        self.assertGreater(p, 0.05)

    def test_is_significant_decision(self):
        ht = HypothesisTest([1, 2, 3, 4, 5], [10, 11, 12, 13, 14])
        self.assertTrue(ht.is_significant(alpha=0.05))
        self.assertFalse(ht.is_significant(alpha=0.000000001))

    def test_welch_function_returns_three_tuple(self):
        t, df, p = welch_t_test([1, 2, 3], [5, 6, 7])
        self.assertIsInstance(t, float)
        self.assertIsInstance(df, float)
        self.assertIsInstance(p, float)
        self.assertGreaterEqual(p, 0.0)
        self.assertLessEqual(p, 1.0)

    def test_permutation_degenerate_constant_groups(self):
        """Zero variance in both groups -> no difference, p approaches 1."""
        _, _, p = welch_t_test([5, 5, 5], [5, 5, 5])
        self.assertEqual(p, 1.0)


# ---------------------------------------------------------------------------
# Bootstrap / permutation determinism.
# ---------------------------------------------------------------------------


class TestDeterminism(unittest.TestCase):
    def test_permutation_deterministic_with_seed(self):
        p1 = permutation_test([1, 2, 3], [4, 5, 6], n_permutations=2000, seed=7)
        p2 = permutation_test([1, 2, 3], [4, 5, 6], n_permutations=2000, seed=7)
        self.assertEqual(p1, p2)

    def test_bootstrap_deterministic_with_seed(self):
        r1 = bootstrap_p_value([1, 2, 3, 4], [5, 6, 7, 8], n_bootstrap=2000, seed=99)
        r2 = bootstrap_p_value([1, 2, 3, 4], [5, 6, 7, 8], n_bootstrap=2000, seed=99)
        self.assertEqual(r1, r2)

    def test_assess_fallback_bootstrap_deterministic(self):
        a = assess([1, 2, 3], [4, 5, 6], fallback_to_bootstrap=True, seed=42)
        b = assess([1, 2, 3], [4, 5, 6], fallback_to_bootstrap=True, seed=42)
        self.assertEqual(a.p_value, b.p_value)

    def test_assess_fallback_uses_permutation(self):
        res = assess([1, 2, 3], [4, 5, 6], fallback_to_bootstrap=True, seed=1)
        self.assertEqual(res.method, "permutation")

    def test_assess_default_uses_welch(self):
        res = assess([1, 2, 3, 4], [5, 6, 7, 8])
        self.assertEqual(res.method, "welch")

    def test_assess_returns_assessment_result(self):
        res = assess([1, 2, 3, 4], [5, 6, 7, 8])
        self.assertIsInstance(res, AssessmentResult)
        self.assertIsNotNone(res.effect_size)


# ---------------------------------------------------------------------------
# Registry lifecycle + persistence round-trip.
# ---------------------------------------------------------------------------


class TestExperimentRegistry(unittest.TestCase):
    def setUp(self):
        fd, self.path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self.reg = ExperimentRegistry(db_path=self.path)

    def tearDown(self):
        try:
            self.reg.close()
        except Exception:
            pass
        if os.path.exists(self.path):
            os.remove(self.path)

    def test_register_and_get(self):
        exp = self.reg.register_experiment("Caching reduces latency")
        self.assertIsInstance(exp, Experiment)
        self.assertIsNotNone(exp.id)
        self.assertEqual(exp.status, "draft")
        fetched = self.reg.get(exp.id)
        self.assertEqual(fetched.hypothesis, "Caching reduces latency")

    def test_lifecycle_transitions(self):
        exp = self.reg.register_experiment("Test hypothesis")
        self.assertTrue(self.reg.start(exp.id))
        self.assertEqual(self.reg.get(exp.id).status, "running")
        self.assertTrue(self.reg.record_metric_before(exp.id, 1.0))
        self.assertTrue(self.reg.record_metric_before(exp.id, 2.0))
        self.assertTrue(self.reg.record_metric_after(exp.id, 10.0))
        self.assertTrue(self.reg.record_metric_after(exp.id, 11.0))
        fin = self.reg.finish(exp.id)
        self.assertEqual(fin.status, "finished")
        self.assertIsNotNone(fin.p_value)

    def test_persistence_round_trip(self):
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
            self.assertIsNotNone(recovered)
            self.assertEqual(recovered.hypothesis, "Persisted hypothesis")
            self.assertEqual(recovered.status, "finished")
            self.assertEqual(recovered.metrics_before, [1.0])
            self.assertEqual(recovered.metrics_after, [10.0])
            self.assertIsNotNone(recovered.p_value)
        finally:
            reg2.close()

    def test_start_rejected_when_already_started(self):
        exp = self.reg.register_experiment("Once only")
        self.assertTrue(self.reg.start(exp.id))
        self.assertFalse(self.reg.start(exp.id))

    def test_get_missing_returns_none(self):
        self.assertIsNone(self.reg.get("does-not-exist"))

    def test_conclude_records_significance_when_separated(self):
        exp = self.reg.register_experiment("Strong effect")
        self.reg.start(exp.id)
        for i in range(1, 6):
            self.reg.record_metric_before(exp.id, i)
            self.reg.record_metric_after(exp.id, i + 10)
        fin = self.reg.conclude(exp.id, alpha=0.05)
        self.assertTrue(fin.significance)
        self.assertIn("Significant", fin.conclusion)

    def test_conclude_not_significant_when_overlapping(self):
        exp = self.reg.register_experiment("Weak effect")
        self.reg.start(exp.id)
        for i in range(1, 6):
            self.reg.record_metric_before(exp.id, i)
            self.reg.record_metric_after(exp.id, i + 0.1)
        fin = self.reg.conclude(exp.id, alpha=0.05)
        self.assertFalse(fin.significance)


# ---------------------------------------------------------------------------
# ExperimentRunner: guarded harness.
# ---------------------------------------------------------------------------


class TestExperimentRunner(unittest.TestCase):
    def setUp(self):
        fd, self.path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self.reg = ExperimentRegistry(db_path=self.path)
        self.runner = ExperimentRunner(self.reg, alpha=0.05, seed=42)

    def tearDown(self):
        try:
            self.reg.close()
        except Exception:
            pass
        if os.path.exists(self.path):
            os.remove(self.path)

    def _control(self):
        return [1, 2, 3, 4, 5]

    def _treatment(self):
        return [10, 11, 12, 13, 14]

    def test_runner_records_before_and_after(self):
        exp = self.reg.register_experiment("Runner test")
        self.reg.start(exp.id)
        fin = self.runner.run(exp.id, self._control, self._treatment)
        self.assertEqual(fin.metrics_before, [1, 2, 3, 4, 5])
        self.assertEqual(fin.metrics_after, [10, 11, 12, 13, 14])
        self.assertEqual(fin.status, "finished")

    def test_runner_concludes_significance(self):
        exp = self.reg.register_experiment("Runner sig")
        self.reg.start(exp.id)
        fin = self.runner.run(exp.id, self._control, self._treatment)
        self.assertTrue(fin.significance)
        self.assertLess(fin.p_value, 0.05)

    def test_run_new_registers_and_runs(self):
        fin = self.runner.run_new(
            "Fresh experiment", self._control, self._treatment
        )
        self.assertIsNotNone(fin.id)
        self.assertEqual(fin.status, "finished")
        self.assertEqual(self.reg.count(), 1)

    def test_runner_guards_exception_marks_failed(self):
        exp = self.reg.register_experiment("Failing")
        self.reg.start(exp.id)

        def boom():
            raise RuntimeError("deliberate failure")

        with self.assertRaises(RuntimeError):
            self.runner.run(exp.id, self._control, boom)
        failed = self.reg.get(exp.id)
        self.assertEqual(failed.status, "failed")
        self.assertIn("Runner error", failed.conclusion)

    def test_runner_rejects_unregistered(self):
        with self.assertRaises(KeyError):
            self.runner.run("no-such-id", self._control, self._treatment)


if __name__ == "__main__":
    unittest.main()
