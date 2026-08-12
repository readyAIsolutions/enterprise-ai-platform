"""Tests for statistical drift detection (KS test and PSI)."""

from modules.mlops_lifecycle.drift_detector import (
    DetectionMethod,
    DriftDetector,
    DriftMetric,
    create_drift_detector,
)


def test_create_drift_detector_returns_default_instance():
    d = create_drift_detector()
    assert isinstance(d, DriftDetector)


def test_identical_distributions_are_not_drifted():
    d = DriftDetector(alpha=0.05)
    data = [float(i) for i in range(100)]
    metric = d.compute_drift(data, data[:], method=DetectionMethod.KS_TEST)
    assert isinstance(metric, DriftMetric)
    assert metric.p_value >= 0.05
    assert metric.drifted is False


def test_shifted_distributions_are_drifted():
    d = DriftDetector(alpha=0.05)
    ref = [float(i) for i in range(100)]
    cur = [float(i) + 50 for i in range(100)]
    metric = d.compute_drift(ref, cur, method=DetectionMethod.KS_TEST)
    assert metric.p_value < 0.05
    assert metric.drifted is True


def test_psi_zero_for_identical_distributions():
    d = DriftDetector(psi_threshold=0.25)
    data = [float(i) for i in range(100)]
    metric = d.compute_drift(data, data[:], method=DetectionMethod.PSI)
    assert metric.value < 0.25
    assert metric.drifted is False


def test_psi_flags_drift_on_shift():
    d = DriftDetector(psi_threshold=0.25)
    ref = [float(i) for i in range(100)]
    cur = [float(i) + 50 for i in range(100)]
    metric = d.compute_drift(ref, cur, method=DetectionMethod.PSI)
    assert metric.value > 0.25
    assert metric.drifted is True


def test_detect_over_multiple_features_and_raise_alerts():
    d = DriftDetector(alpha=0.05)
    ref = {"a": [float(i) for i in range(100)], "b": [float(i) for i in range(100)]}
    cur = {"a": [float(i) + 60 for i in range(100)], "b": [float(i) for i in range(100)]}
    metrics = d.detect(ref, cur, raise_alerts=True)
    assert len(metrics) == 2
    by_name = {m.feature_name: m for m in metrics}
    assert by_name["a"].drifted is True
    assert by_name["b"].drifted is False
    summary = d.summarize(metrics)
    assert summary["drifted"] == 1
    assert summary["stable"] == 1
    assert summary["any_drift"] is True
    assert len(d.alerts()) == 1
