"""
Drift Detector — statistical monitoring for feature / prediction / label
distribution shift between a reference dataset and a current (production)
dataset.

Pure-stdlib implementation using :mod:`statistics` and :mod:`math`. Supports
two robust, widely-used methods:

* **KS test** -- two-sample Kolmogorov-Smirnov statistic with a large-sample
  p-value approximation (the two-sample test with the combined-sample
  effective size).
* **PSI** -- Population Stability Index, bucketed into deciles derived from
  the reference distribution.

Both return a per-feature :class:`DriftMetric` whose ``drifted`` flag is set
when the p-value falls below ``alpha`` (KS) or PSI exceeds ``psi_threshold``.
"""

from __future__ import annotations

import logging
import math
import statistics
import threading
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Sequence

logger = logging.getLogger("enterprise.mlops_lifecycle.drift_detector")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class DriftType(Enum):
    FEATURE = "feature"
    PREDICTION = "prediction"
    LABEL = "label"
    DATA = "data"


class DetectionMethod(Enum):
    KS_TEST = "ks_test"
    PSI = "psi"


@dataclass
class DriftMetric:
    """Drift measurement for a single feature/bucket."""

    feature_name: str
    method: DetectionMethod
    value: float
    threshold: float
    drifted: bool
    p_value: Optional[float] = None
    drift_type: DriftType = DriftType.FEATURE
    reference_size: int = 0
    current_size: int = 0

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["method"] = self.method.value
        data["drift_type"] = self.drift_type.value
        return data


@dataclass
class DriftAlert:
    """A user-facing alert raised when a feature is flagged as drifted."""

    feature_name: str
    method: DetectionMethod
    value: float
    severity: str = "warning"
    alert_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: str = field(default_factory=_now_iso)
    message: str = ""


class _DriftAlgorithms:
    """Pure-python statistical building blocks."""

    @staticmethod
    def _ecdf(sorted_data: List[float]) -> List[float]:
        n = len(sorted_data)
        return [(i + 1) / n for i in range(n)]

    @classmethod
    def kolmogorov_smirnov(
        cls, reference: Sequence[float], current: Sequence[float]
    ) -> tuple[float, float]:
        """Return (D, p_value) for the two-sample KS test.

        D is the largest absolute gap between the two empirical CDFs.
        p-value uses the standard large-sample asymptotic approximation:
            lambda = (sqrt(n_eff) + 0.12 + 0.11 / sqrt(n_eff)) * D
            p ~= 2 * sum_{k=1..inf} (-1)^(k-1) * exp(-2 * k^2 * lambda^2)
        which saturates near 2 * exp(-2 * lambda^2) for large lambda.
        """
        ref = sorted(float(x) for x in reference)
        cur = sorted(float(x) for x in current)
        n1, n2 = len(ref), len(cur)
        if n1 == 0 or n2 == 0:
            # Degenerate: treat as maximal drift.
            return 1.0, 0.0

        # Two-sample KS statistic D = sup_x |F1(x) - F2(x)|.
        i = j = 0
        d = 0.0
        while i < n1 and j < n2:
            if ref[i] <= cur[j]:
                f1 = (i + 1) / n1
                f2 = j / n2
                i += 1
            else:
                f1 = i / n1
                f2 = (j + 1) / n2
                j += 1
            d = max(d, abs(f1 - f2))
        # Remaining tail (one distribution exhausted -> its CDF is 1.0).
        while i < n1:
            d = max(d, abs((i + 1) / n1 - 1.0))
            i += 1
        while j < n2:
            d = max(d, abs(1.0 - (j + 1) / n2))
            j += 1

        n_eff = (n1 * n2) / (n1 + n2)
        sqrt_neff = math.sqrt(n_eff)
        # Standard small-sample correction factor for the two-sample KS test.
        lambda_ = (sqrt_neff + 0.12 + 0.11 / sqrt_neff) * d
        p = cls._ks_pvalue(lambda_)
        return d, p

    @staticmethod
    def _ks_pvalue(lambda_: float) -> float:
        """Kolmogorov distribution survival function (two-sided)."""
        if lambda_ <= 0.0:
            return 1.0
        if lambda_ > 4.0:
            return 2.0 * math.exp(-2.0 * lambda_ * lambda_)
        total = 0.0
        sign = 1.0
        for k in range(1, 200):
            term = math.exp(-2.0 * k * k * lambda_ * lambda_)
            total += sign * term
            sign = -sign
            if term < 1e-14:
                break
        return min(1.0, max(0.0, 2.0 * total))

    @staticmethod
    def psi(reference: Sequence[float], current: Sequence[float], buckets: int = 10) -> float:
        """Population Stability Index.

        Deciles are derived from the reference distribution; each sample is
        bucketed and PSI = sum((actual - expected) * ln(actual / expected)).
        """
        ref = list(float(x) for x in reference)
        cur = list(float(x) for x in current)
        if not ref or not cur:
            return 0.0
        lo, hi = min(ref), max(ref)
        if math.isclose(lo, hi):
            # Degenerate reference -> fall back to simple proportion.
            e = sum(1 for x in ref if math.isclose(x, lo))
            a = sum(1 for x in cur if math.isclose(x, lo))
            return _psi_component(a, e, len(cur), len(ref))

        edges = [lo + (hi - lo) * (i / buckets) for i in range(buckets + 1)]
        psi_val = 0.0
        for i in range(buckets):
            left = edges[i]
            right = edges[i + 1]
            expected = sum(1 for x in ref if left <= x < right or (i == buckets - 1 and x == hi))
            actual = sum(1 for x in cur if left <= x < right or (i == buckets - 1 and x == hi))
            psi_val += _psi_component(actual, expected, len(cur), len(ref))
        return psi_val


def _psi_component(actual: int, expected: int, total_actual: int, total_expected: int) -> float:
    """Contribution of one bucket to PSI, with small-cell smoothing."""
    ratio_a = (actual + 0.5) / total_actual
    ratio_e = (expected + 0.5) / total_expected
    if ratio_a <= 0 or ratio_e <= 0:
        return 0.0
    return (ratio_a - ratio_e) * math.log(ratio_a / ratio_e)


class DriftDetector:
    """Detects statistical drift between reference and current datasets.

    Args:
        alpha: p-value significance threshold for the KS test (default 0.05).
        psi_threshold: PSI value above which a feature is flagged (default 0.25).
    """

    def __init__(self, alpha: float = 0.05, psi_threshold: float = 0.25) -> None:
        self._alpha = alpha
        self._psi_threshold = psi_threshold
        self._alerts: List[DriftAlert] = []
        self._lock = threading.RLock()

    def compute_drift(
        self,
        reference: Sequence[float],
        current: Sequence[float],
        feature_name: str = "feature",
        method: DetectionMethod = DetectionMethod.KS_TEST,
        drift_type: DriftType = DriftType.FEATURE,
    ) -> DriftMetric:
        """Compute a single drift metric on one feature's values."""
        ref = list(float(x) for x in reference)
        cur = list(float(x) for x in current)
        if method is DetectionMethod.PSI:
            value = _DriftAlgorithms.psi(ref, cur)
            return DriftMetric(
                feature_name=feature_name,
                method=method,
                value=value,
                threshold=self._psi_threshold,
                drifted=value > self._psi_threshold,
                drift_type=drift_type,
                reference_size=len(ref),
                current_size=len(cur),
            )

        _, p_value = _DriftAlgorithms.kolmogorov_smirnov(ref, cur)
        drifted = p_value < self._alpha
        return DriftMetric(
            feature_name=feature_name,
            method=method,
            value=p_value,
            threshold=self._alpha,
            drifted=drifted,
            p_value=p_value,
            drift_type=drift_type,
            reference_size=len(ref),
            current_size=len(cur),
        )

    def detect(
        self,
        reference: Dict[str, Sequence[float]],
        current: Dict[str, Sequence[float]],
        method: DetectionMethod = DetectionMethod.KS_TEST,
        drift_type: DriftType = DriftType.FEATURE,
        raise_alerts: bool = False,
    ) -> List[DriftMetric]:
        """Run drift detection across every feature present in both dicts."""
        common = set(reference.keys()) & set(current.keys())
        metrics: List[DriftMetric] = []
        for name in common:
            metric = self.compute_drift(
                reference[name], current[name], feature_name=name,
                method=method, drift_type=drift_type,
            )
            metrics.append(metric)
            if raise_alerts and metric.drifted:
                self._alerts.append(
                    DriftAlert(
                        feature_name=name,
                        method=method,
                        value=metric.value,
                        message=(
                            f"{name} drifted via {method.value} "
                            f"(value={metric.value:.4f}, threshold={metric.threshold:.4f})"
                        ),
                    )
                )
        return metrics

    def summarize(self, metrics: Sequence[DriftMetric]) -> Dict[str, Any]:
        return {
            "total_features": len(metrics),
            "drifted": sum(1 for m in metrics if m.drifted),
            "stable": sum(1 for m in metrics if not m.drifted),
            "any_drift": any(m.drifted for m in metrics),
        }

    def alerts(self) -> List[DriftAlert]:
        with self._lock:
            return list(self._alerts)

    def clear_alerts(self) -> None:
        with self._lock:
            self._alerts.clear()


def create_drift_detector(config: Optional[Dict[str, Any]] = None) -> DriftDetector:
    """Create a default :class:`DriftDetector`.

    Args:
        config: Optional dict. Supported keys:
            - ``alpha`` (float): KS significance threshold (default 0.05).
            - ``psi_threshold`` (float): PSI drift threshold (default 0.25).
    """
    config = config or {}
    return DriftDetector(
        alpha=float(config.get("alpha", 0.05)),
        psi_threshold=float(config.get("psi_threshold", 0.25)),
    )
