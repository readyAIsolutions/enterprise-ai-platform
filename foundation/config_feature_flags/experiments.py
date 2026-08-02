"""
A/B testing and experimentation support.

Provides:
    - Experiment definition with multiple variants
    - Hash-based consistent variant assignment
    - Metrics tracking per variant
    - Statistical significance calculation (Z-test for proportions)
    - Experiment lifecycle management (draft, running, paused, completed)
"""

from __future__ import annotations

import hashlib
import math
import time
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Dict, List, Optional, Set, Tuple


# ---------------------------------------------------------------------------
# Data Models
# ---------------------------------------------------------------------------

class ExperimentStatus(Enum):
    """Lifecycle states of an experiment."""
    DRAFT = auto()
    RUNNING = auto()
    PAUSED = auto()
    COMPLETED = auto()
    ARCHIVED = auto()


@dataclass
class Variant:
    """A single variant within an experiment.

    Attributes:
        name: Variant identifier (e.g., 'control', 'treatment-a').
        description: Human-readable description.
        weight: Relative traffic allocation weight.  Weights are
                normalized across all variants.  E.g., if control=50
                and treatment=50, each gets 50%.
        config: Arbitrary configuration for this variant (e.g., feature
                flag values, UI settings).
        metrics: Accumulated metric values for this variant.
        sample_count: Number of assignments to this variant.
    """

    name: str
    description: str = ""
    weight: float = 1.0
    config: Dict[str, Any] = field(default_factory=dict)
    metrics: Dict[str, float] = field(default_factory=dict)
    sample_count: int = 0

    def record_metric(self, name: str, value: float) -> None:
        """Accumulate a metric value (e.g., sum of conversion indicators).

        The metric is stored as a running sum; the caller should divide
        by sample_count to get the average rate.
        """
        self.metrics[name] = self.metrics.get(name, 0.0) + value

    def get_rate(self, name: str) -> float:
        """Return the average rate for a metric (sum / sample_count)."""
        if self.sample_count == 0:
            return 0.0
        return self.metrics.get(name, 0.0) / self.sample_count


@dataclass
class Experiment:
    """An A/B test experiment definition.

    Attributes:
        name: Unique experiment identifier.
        description: Human-readable description.
        status: Current lifecycle status.
        variants: List of variant definitions.
        target_metric: The primary metric to optimize (e.g., 'conversion').
        min_sample_size: Minimum samples needed before drawing conclusions.
        confidence_level: Desired statistical confidence (0.0-1.0),
                          typically 0.95 for 95% confidence.
        traffic_allocation: Fraction of total traffic allocated to this
                            experiment (0.0-1.0).  Default 1.0 = 100%.
        created_at: Unix timestamp of creation.
        started_at: When the experiment started running.
        ended_at: When the experiment ended.
        metadata: Arbitrary key-value metadata.
    """

    name: str
    description: str = ""
    status: ExperimentStatus = ExperimentStatus.DRAFT
    variants: List[Variant] = field(default_factory=list)
    target_metric: str = "conversion"
    min_sample_size: int = 1000
    confidence_level: float = 0.95
    traffic_allocation: float = 1.0
    created_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    ended_at: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not 0.0 < self.confidence_level < 1.0:
            raise ValueError("confidence_level must be between 0.0 and 1.0")
        if not 0.0 < self.traffic_allocation <= 1.0:
            raise ValueError("traffic_allocation must be between 0.0 and 1.0")
        if len(self.variants) < 2:
            raise ValueError("At least 2 variants are required for an experiment")

    @property
    def total_weight(self) -> float:
        """Sum of all variant weights."""
        return sum(v.weight for v in self.variants)

    @property
    def total_samples(self) -> int:
        """Total number of assignments across all variants."""
        return sum(v.sample_count for v in self.variants)

    def get_variant(self, name: str) -> Optional[Variant]:
        """Return a variant by name."""
        for v in self.variants:
            if v.name == name:
                return v
        return None

    def normalized_weights(self) -> List[float]:
        """Return per-variant probability based on weights."""
        total = self.total_weight
        if total == 0:
            n = len(self.variants)
            return [1.0 / n] * n
        return [v.weight / total for v in self.variants]


@dataclass
class ExperimentResult:
    """Statistical analysis result for an experiment.

    Attributes:
        experiment_name: The experiment analyzed.
        target_metric: The metric analyzed.
        variant_rates: Mapping of variant_name -> observed rate.
        p_value: The p-value from the statistical test.
        is_significant: Whether the result is statistically significant
                        at the configured confidence level.
        winner: Name of the winning variant (highest rate), or None.
        lift: Relative lift of the winner over the control.
        control_name: Name of the control variant (first variant by default).
        total_samples: Total samples across all variants.
        test_used: Which statistical test was used.
    """

    experiment_name: str
    target_metric: str
    variant_rates: Dict[str, float] = field(default_factory=dict)
    p_value: float = 1.0
    is_significant: bool = False
    winner: Optional[str] = None
    lift: float = 0.0
    control_name: str = ""
    total_samples: int = 0
    test_used: str = "z-test-proportions"


# ---------------------------------------------------------------------------
# ExperimentManager
# ---------------------------------------------------------------------------


class ExperimentManager:
    """Manage A/B experiments and analyze results.

    Usage::

        mgr = ExperimentManager()

        # Create experiment
        exp = mgr.create_experiment(
            name="pricing-test",
            description="Test new pricing page layout",
            variants=[
                Variant(name="control", weight=50),
                Variant(name="treatment", weight=50),
            ],
            target_metric="conversion",
            min_sample_size=2000,
        )

        # Start experiment
        mgr.start_experiment("pricing-test")

        # Assign users
        variant = mgr.assign("pricing-test", user_id="user-123")

        # Record metrics
        mgr.record_metric("pricing-test", "user-123", "conversion", 1.0)

        # Analyze
        result = mgr.analyze("pricing-test")
        if result.is_significant:
            print(f"Winner: {result.winner}, lift: {result.lift:.2%}")
    """

    def __init__(self):
        self._experiments: Dict[str, Experiment] = {}
        # Cache user -> variant assignments to ensure consistency
        self._assignments: Dict[str, Dict[str, str]] = {}

    # ------------------------------------------------------------------
    # Experiment CRUD
    # ------------------------------------------------------------------

    def create_experiment(
        self,
        name: str,
        description: str = "",
        variants: Optional[List[Variant]] = None,
        **kwargs: Any,
    ) -> Experiment:
        """Create a new experiment in DRAFT status.

        Args:
            name: Unique experiment name.
            description: Human-readable description.
            variants: List of Variant objects (minimum 2).
            **kwargs: Additional Experiment fields.

        Returns:
            The created Experiment.

        Raises:
            ValueError if an experiment with the same name already exists.
        """
        if name in self._experiments:
            raise ValueError(f"Experiment '{name}' already exists")

        if variants is None:
            variants = [
                Variant(name="control", weight=50),
                Variant(name="treatment", weight=50),
            ]

        exp = Experiment(
            name=name,
            description=description,
            variants=variants,
            **kwargs,
        )
        self._experiments[name] = exp
        return exp

    def get_experiment(self, name: str) -> Optional[Experiment]:
        """Return an experiment by name, or None."""
        return self._experiments.get(name)

    def list_experiments(
        self, status: Optional[ExperimentStatus] = None
    ) -> List[Experiment]:
        """List experiments, optionally filtered by status."""
        if status is None:
            return list(self._experiments.values())
        return [e for e in self._experiments.values() if e.status == status]

    def update_experiment(self, name: str, **kwargs: Any) -> Experiment:
        """Update experiment fields.

        Only DRAFT experiments can be updated.
        """
        exp = self._get_experiment(name)
        if exp.status != ExperimentStatus.DRAFT:
            raise ValueError(
                f"Cannot update experiment '{name}': status is {exp.status.name}"
            )
        for key, value in kwargs.items():
            if hasattr(exp, key):
                setattr(exp, key, value)
        return exp

    def delete_experiment(self, name: str) -> None:
        """Delete an experiment (any status)."""
        self._experiments.pop(name, None)
        self._assignments.pop(name, None)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start_experiment(self, name: str) -> Experiment:
        """Start a DRAFT experiment (move to RUNNING)."""
        exp = self._get_experiment(name)
        if exp.status != ExperimentStatus.DRAFT:
            raise ValueError(
                f"Cannot start experiment '{name}': status is {exp.status.name}"
            )
        exp.status = ExperimentStatus.RUNNING
        exp.started_at = time.time()
        return exp

    def pause_experiment(self, name: str) -> Experiment:
        """Pause a RUNNING experiment."""
        exp = self._get_experiment(name)
        if exp.status != ExperimentStatus.RUNNING:
            raise ValueError(
                f"Cannot pause experiment '{name}': status is {exp.status.name}"
            )
        exp.status = ExperimentStatus.PAUSED
        return exp

    def resume_experiment(self, name: str) -> Experiment:
        """Resume a PAUSED experiment."""
        exp = self._get_experiment(name)
        if exp.status != ExperimentStatus.PAUSED:
            raise ValueError(
                f"Cannot resume experiment '{name}': status is {exp.status.name}"
            )
        exp.status = ExperimentStatus.RUNNING
        return exp

    def complete_experiment(self, name: str) -> Experiment:
        """Complete an experiment (move to COMPLETED)."""
        exp = self._get_experiment(name)
        if exp.status not in (ExperimentStatus.RUNNING, ExperimentStatus.PAUSED):
            raise ValueError(
                f"Cannot complete experiment '{name}': status is {exp.status.name}"
            )
        exp.status = ExperimentStatus.COMPLETED
        exp.ended_at = time.time()
        return exp

    def archive_experiment(self, name: str) -> Experiment:
        """Archive a completed experiment."""
        exp = self._get_experiment(name)
        exp.status = ExperimentStatus.ARCHIVED
        return exp

    # ------------------------------------------------------------------
    # Assignment
    # ------------------------------------------------------------------

    def assign(self, experiment_name: str, user_id: str) -> Variant:
        """Assign a user to a variant using consistent hashing.

        The same user_id will always receive the same variant as long
        as the experiment configuration (variants & weights) remains
        unchanged.

        Assignments respect the experiment's traffic_allocation: if the
        user falls outside the allocated fraction, the control variant
        is returned and no sample is counted.

        Returns:
            The assigned Variant.

        Raises:
            ValueError if the experiment is not RUNNING or PAUSED.
        """
        exp = self._get_experiment(experiment_name)

        if exp.status not in (ExperimentStatus.RUNNING, ExperimentStatus.PAUSED):
            raise ValueError(
                f"Cannot assign to experiment '{experiment_name}': "
                f"status is {exp.status.name}"
            )

        # Check cached assignment
        if experiment_name in self._assignments:
            cached = self._assignments[experiment_name].get(user_id)
            if cached is not None:
                variant = exp.get_variant(cached)
                if variant is not None:
                    return variant

        # Traffic allocation check: outside the allocated fraction -> control
        if exp.traffic_allocation < 1.0:
            in_experiment = self._hash_bucket(
                f"{experiment_name}:traffic", user_id
            ) < exp.traffic_allocation
            if not in_experiment:
                return exp.variants[0]  # return control, don't count

        # Hash-based variant selection
        variant = self._select_variant(exp, user_id)
        variant.sample_count += 1

        # Cache the assignment
        if experiment_name not in self._assignments:
            self._assignments[experiment_name] = {}
        self._assignments[experiment_name][user_id] = variant.name

        return variant

    def get_assignment(
        self, experiment_name: str, user_id: str
    ) -> Optional[str]:
        """Return the variant name a user was assigned to, or None."""
        return self._assignments.get(experiment_name, {}).get(user_id)

    # ------------------------------------------------------------------
    # Metrics
    # ------------------------------------------------------------------

    def record_metric(
        self,
        experiment_name: str,
        user_id: str,
        metric_name: str,
        value: float,
    ) -> None:
        """Record a metric value for a user in an experiment.

        The metric is attributed to the variant the user was assigned to.
        If the user hasn't been assigned yet, this is a no-op.
        """
        variant_name = self.get_assignment(experiment_name, user_id)
        if variant_name is None:
            return
        exp = self._experiments.get(experiment_name)
        if exp is None:
            return
        variant = exp.get_variant(variant_name)
        if variant is not None:
            variant.record_metric(metric_name, value)

    def get_metric(self, experiment_name: str, variant_name: str, metric_name: str) -> float:
        """Get the accumulated metric value for a variant."""
        exp = self._experiments.get(experiment_name)
        if exp is None:
            return 0.0
        variant = exp.get_variant(variant_name)
        if variant is None:
            return 0.0
        return variant.metrics.get(metric_name, 0.0)

    # ------------------------------------------------------------------
    # Analysis
    # ------------------------------------------------------------------

    def analyze(self, experiment_name: str) -> ExperimentResult:
        """Perform statistical analysis on an experiment.

        Uses a two-proportion Z-test to compare each variant against
        the control.  Returns an ExperimentResult with p-value,
        significance, winner, and lift.

        If fewer than min_sample_size total samples have been collected,
        returns a result with p_value=1.0 and is_significant=False.
        """
        exp = self._get_experiment(experiment_name)

        control = exp.variants[0]
        target_metric = exp.target_metric

        # Build rate map
        variant_rates: Dict[str, float] = {}
        for v in exp.variants:
            variant_rates[v.name] = v.get_rate(target_metric)

        total_samples = exp.total_samples

        result = ExperimentResult(
            experiment_name=experiment_name,
            target_metric=target_metric,
            variant_rates=variant_rates,
            control_name=control.name,
            total_samples=total_samples,
        )

        # Not enough data
        if total_samples < exp.min_sample_size:
            result.p_value = 1.0
            result.is_significant = False
            return result

        # Compare each non-control variant against control
        best_variant = control
        best_rate = variant_rates.get(control.name, 0.0)
        lowest_p_value = 1.0

        for variant in exp.variants[1:]:
            p_value = self._z_test_proportions(
                success_a=control.metrics.get(target_metric, 0.0),
                n_a=control.sample_count,
                success_b=variant.metrics.get(target_metric, 0.0),
                n_b=variant.sample_count,
                one_sided=True,
            )
            if p_value < lowest_p_value:
                lowest_p_value = p_value

            rate = variant_rates.get(variant.name, 0.0)
            if rate > best_rate:
                best_rate = rate
                best_variant = variant

        result.p_value = lowest_p_value
        result.is_significant = lowest_p_value < (1.0 - exp.confidence_level)

        if result.is_significant and best_variant.name != control.name:
            result.winner = best_variant.name
            control_rate = variant_rates.get(control.name, 0.0)
            if control_rate > 0:
                result.lift = (best_rate - control_rate) / control_rate
            else:
                result.lift = float("inf") if best_rate > 0 else 0.0

        return result

    def get_winner(self, experiment_name: str) -> Optional[str]:
        """Convenience: return the winning variant name, or None."""
        result = self.analyze(experiment_name)
        return result.winner

    # ------------------------------------------------------------------
    # Reset
    # ------------------------------------------------------------------

    def reset_metrics(self, experiment_name: str) -> None:
        """Reset all metrics and assignments for an experiment."""
        exp = self._get_experiment(experiment_name)
        for v in exp.variants:
            v.metrics.clear()
            v.sample_count = 0
        self._assignments.pop(experiment_name, None)

    def clear_assignments(self, experiment_name: str) -> None:
        """Clear cached assignments (does not reset metrics)."""
        self._assignments.pop(experiment_name, None)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _get_experiment(self, name: str) -> Experiment:
        """Get experiment by name, raising KeyError if not found."""
        exp = self._experiments.get(name)
        if exp is None:
            raise KeyError(f"Experiment not found: {name}")
        return exp

    def _select_variant(self, exp: Experiment, user_id: str) -> Variant:
        """Hash-based variant selection respecting weights.

        Uses a hash ring approach: maps the user to a bucket in [0, 1)
        and selects based on cumulative normalized weights.
        """
        bucket = self._hash_bucket(exp.name, user_id)
        cumulative = 0.0
        for variant in exp.variants:
            norm_weight = variant.weight / exp.total_weight
            cumulative += norm_weight
            if bucket < cumulative:
                return variant
        # Fallback (should not happen due to floating point)
        return exp.variants[-1]

    @staticmethod
    def _hash_bucket(seed: str, user_id: str) -> float:
        """Hash seed + user_id to a float in [0, 1)."""
        payload = f"{seed}:{user_id}".encode("utf-8")
        digest = hashlib.sha256(payload).digest()
        # Use first 8 bytes as integer, divide by 2^64
        num = int.from_bytes(digest[:8], "big")
        return num / (2 ** 64)

    @staticmethod
    def _z_test_proportions(
        success_a: float,
        n_a: int,
        success_b: float,
        n_b: int,
        one_sided: bool = True,
    ) -> float:
        """Compute p-value for a two-proportion Z-test.

        Args:
            success_a: Number of successes in group A (control).
            n_a: Sample size of group A.
            success_b: Number of successes in group B (treatment).
            n_b: Sample size of group B.
            one_sided: If True, compute one-sided p-value (B > A).
                       If False, compute two-sided.

        Returns:
            p-value between 0 and 1.
        """
        if n_a == 0 or n_b == 0:
            return 1.0

        p_a = success_a / n_a
        p_b = success_b / n_b
        p_pool = (success_a + success_b) / (n_a + n_b)

        if p_pool == 0.0 or p_pool == 1.0:
            return 1.0

        se = math.sqrt(p_pool * (1.0 - p_pool) * (1.0 / n_a + 1.0 / n_b))
        if se == 0.0:
            return 0.0 if p_b > p_a else 1.0

        z = (p_b - p_a) / se

        # Standard normal CDF approximation (Abramowitz & Stegun 7.1.26)
        p_value = ExperimentManager._normal_cdf(-abs(z))
        if one_sided:
            p_value = p_value
        else:
            p_value = 2 * p_value

        # Clamp
        return max(0.0, min(1.0, p_value))

    @staticmethod
    def _normal_cdf(x: float) -> float:
        """Approximate the standard normal CDF using Abramowitz & Stegun formula."""
        # Constants for approximation
        a1 = 0.254829592
        a2 = -0.284496736
        a3 = 1.421413741
        a4 = -1.453152027
        a5 = 1.061405429
        p = 0.3275911

        sign = 1.0 if x >= 0 else -1.0
        x = abs(x) / math.sqrt(2.0)
        t = 1.0 / (1.0 + p * x)
        y = 1.0 - (((((a5 * t + a4) * t) + a3) * t + a2) * t + a1) * t * math.exp(-x * x)
        return 0.5 * (1.0 + sign * y)