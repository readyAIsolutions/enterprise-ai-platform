"""
Statistical experiment management for the Innovation R&D OS.

Adds a MASTER-CLASS experiment surface to innovation_rd:

  * ``Experiment``           — a first-class, serializable record of a hypothesis
                               test with before/after metric samples, a p-value,
                               a significance verdict and a human conclusion.
  * ``HypothesisTest``       — Welch's t-test (stdlib ``statistics``) plus a
                               deterministic bootstrap / permutation fallback.
  * ``ExperimentRegistry``   — a durable SQLite store that tracks the full
                               experiment lifecycle and persists every record.
  * ``ExperimentRunner``     — a guarded harness that executes the control and
                               treatment callables, records their outputs and
                               reaches a statistical conclusion.
  * ``assess``               — module-level helper that reduces before/after
                               samples to a p-value + significance decision.

Only the Python standard library is used (``statistics``, ``math``, ``sqlite3``,
``random``, ``json``, ``datetime``). No numpy/scipy required.
"""

from __future__ import annotations

import json
import logging
import math
import os
import random
import sqlite3
import statistics
import tempfile
import threading
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from uuid import uuid4

if TYPE_CHECKING:
    import builtins
    from collections.abc import Callable, Sequence

logger = logging.getLogger("enterprise.innovation_rd.experiments")

# ---------------------------------------------------------------------------
# Numerical helpers (regularized incomplete beta + Student-t survival).
# ---------------------------------------------------------------------------


def _log_gamma(x: float) -> float:
    """Natural logarithm of the gamma function (Lanczos approximation)."""
    coeff = [
        0.99999999999980993,
        676.5203681218851,
        -1259.1392167224028,
        771.32342877765313,
        -176.61502916214059,
        12.507343278686905,
        -0.13857109526572012,
        9.9843695780195716e-6,
        1.5056327351493116e-7,
    ]
    g = 7
    if x < 0.5:
        return math.log(math.pi) - math.log(math.sin(math.pi * x)) - _log_gamma(1.0 - x)
    x -= 1.0
    a = coeff[0]
    t = x + g + 0.5
    for i in range(1, len(coeff)):
        a += coeff[i] / (x + i)
    return 0.5 * math.log(2.0 * math.pi) + (x + 0.5) * math.log(t) - t + math.log(a)


def _betacf(a: float, b: float, x: float) -> float:
    """Continued-fraction evaluation of the incomplete beta function."""
    MAXIT = 200
    EPS = 3.0e-12
    FPMIN = 1.0e-300

    qab = a + b
    qap = a + 1.0
    qam = a - 1.0
    c = 1.0
    d = 1.0 - qab * x / qap
    if abs(d) < FPMIN:
        d = FPMIN
    d = 1.0 / d
    h = d
    for m in range(1, MAXIT + 1):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        if abs(d) < FPMIN:
            d = FPMIN
        c = 1.0 + aa / c
        if abs(c) < FPMIN:
            c = FPMIN
        d = 1.0 / d
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        if abs(d) < FPMIN:
            d = FPMIN
        c = 1.0 + aa / c
        if abs(c) < FPMIN:
            c = FPMIN
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < EPS:
            break
    return h


def _betainc(a: float, b: float, x: float) -> float:
    """Regularized incomplete beta function I_x(a, b)."""
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    bt = math.exp(
        _log_gamma(a + b) - _log_gamma(a) - _log_gamma(b) + a * math.log(x) + b * math.log(1.0 - x)
    )
    if x < (a + 1.0) / (a + b + 2.0):
        return bt * _betacf(a, b, x) / a
    return 1.0 - bt * _betacf(b, a, 1.0 - x) / b


def student_t_two_sided_p(t: float, df: float) -> float:
    """Two-sided p-value for a Student-t statistic with ``df`` degrees of freedom.

    Uses the identity  p = I_{df/(df+t^2)}(df/2, 1/2).  This is the exact result
    for the t-distribution; the approximation caveat is that Welch's degrees-of-
    freedom correction is itself a continuous approximation.
    """
    if df <= 0:
        return float("nan")
    if not math.isfinite(t):
        return 0.0
    x = df / (df + t * t)
    return _betainc(df / 2.0, 0.5, x)


# ---------------------------------------------------------------------------
# Welch's t-test.
# ---------------------------------------------------------------------------


def welch_t_test(before: Sequence[float], after: Sequence[float]) -> tuple[float, float, float]:
    """Welch's unequal-variance t-test over two independent samples.

    Returns ``(t_statistic, degrees_of_freedom, two_sided_p_value)``.

    NOTE: Uses the stdlib ``statistics`` module only. The Welch-Satterthwaite
    degrees-of-freedom is a continuous approximation of the true (unknown) df,
    and the p-value is computed from that approximate df — hence "approximate".
    """
    n1 = len(before)
    n2 = len(after)
    if n1 < 2 or n2 < 2:
        msg = "Welch's t-test requires at least 2 samples per group"
        raise ValueError(msg)
    m1 = statistics.fmean(before)
    m2 = statistics.fmean(after)
    v1 = statistics.variance(before)
    v2 = statistics.variance(after)
    if v1 == 0.0 and v2 == 0.0:
        # Degenerate: identical constant groups. No evidence of a difference.
        return (0.0, float("inf"), 1.0)
    se = math.sqrt(v1 / n1 + v2 / n2)
    if se == 0.0:
        return (0.0, float("inf"), 1.0)
    t = (m2 - m1) / se
    df = (v1 / n1 + v2 / n2) ** 2 / ((v1 / n1) ** 2 / (n1 - 1) + (v2 / n2) ** 2 / (n2 - 1))
    if not math.isfinite(df) or df <= 0:
        df = float(n1 + n2 - 2)
    p = student_t_two_sided_p(t, df)
    return (t, df, p)


# ---------------------------------------------------------------------------
# Deterministic bootstrap / permutation test.
# ---------------------------------------------------------------------------


def permutation_test(
    before: Sequence[float],
    after: Sequence[float],
    n_permutations: int = 10_000,
    seed: int | None = None,
) -> float:
    """Two-sided permutation p-value comparing group means.

    Pool both samples, repeatedly shuffle the labels, and measure how often the
    permuted mean-difference is at least as extreme as the observed one.
    Deterministic for a fixed ``seed``.
    """
    before = list(before)
    after = list(after)
    n1 = len(before)
    if n1 == 0 or len(after) == 0:
        return float("nan")
    rng = random.Random(seed)
    pooled = before + after
    obs = statistics.fmean(after) - statistics.fmean(before)
    if obs == 0.0:
        return 1.0
    count = 0
    obs_abs = abs(obs)
    for _ in range(max(1, n_permutations)):
        rng.shuffle(pooled)
        group_a = pooled[:n1]
        group_b = pooled[n1:]
        diff = statistics.fmean(group_b) - statistics.fmean(group_a)
        if abs(diff) >= obs_abs:
            count += 1
    return (count + 1) / (n_permutations + 1)


def bootstrap_p_value(
    before: Sequence[float],
    after: Sequence[float],
    n_bootstrap: int = 10_000,
    seed: int | None = None,
) -> float:
    """Bootstrap p-value (difference-of-means resampling).

    Approximates the null distribution by centering the two samples and
    resampling with replacement. Deterministic for a fixed ``seed``.
    """
    before = list(before)
    after = list(after)
    n1 = len(before)
    n2 = len(after)
    if n1 == 0 or n2 == 0:
        return float("nan")
    rng = random.Random(seed)

    m1 = statistics.fmean(before)
    m2 = statistics.fmean(after)
    obs = m2 - m1
    if obs == 0.0:
        return 1.0

    # Center both groups around their pooled mean so the resampled null is
    # mean-zero. This is the "resampling under the null" bootstrap.
    pooled = before + after
    pooled_mean = statistics.fmean(pooled)
    centered1 = [v - statistics.fmean(before) + pooled_mean for v in before]
    centered2 = [v - statistics.fmean(after) + pooled_mean for v in after]

    obs_abs = abs(obs)
    count = 0
    for _ in range(max(1, n_bootstrap)):
        b1 = [centered1[rng.randrange(n1)] for _ in range(n1)]
        b2 = [centered2[rng.randrange(n2)] for _ in range(n2)]
        diff = statistics.fmean(b2) - statistics.fmean(b1)
        if abs(diff) >= obs_abs:
            count += 1
    return (count + 1) / (n_bootstrap + 1)


# ---------------------------------------------------------------------------
# Assessment result + top-level assess().
# ---------------------------------------------------------------------------


@dataclass
class AssessmentResult:
    """Result of a statistical hypothesis test."""

    p_value: float
    significant: bool
    method: str
    alpha: float = 0.05
    t_statistic: float | None = None
    degrees_of_freedom: float | None = None
    effect_size: float | None = None

    def conclusion(self) -> str:
        """Human-readable one-line conclusion."""
        if not math.isfinite(self.p_value):
            return "Insufficient data to reach a statistical conclusion"
        if self.significant:
            return (
                f"Significant ({self.method}): p={self.p_value:.4f} <= "
                f"alpha={self.alpha:.3f}; reject the null hypothesis"
            )
        return (
            f"Not significant ({self.method}): p={self.p_value:.4f} > "
            f"alpha={self.alpha:.3f}; fail to reject the null hypothesis"
        )


def assess(
    before: Sequence[float],
    after: Sequence[float],
    alpha: float = 0.05,
    fallback_to_bootstrap: bool = False,
    seed: int | None = None,
    method: str = "auto",
) -> AssessmentResult:
    """Reduce before/after samples to a p-value and significance decision.

    Args:
        before: Control / baseline sample.
        after: Treatment / experiment sample.
        alpha: Significance level.
        fallback_to_bootstrap: If True, always use the deterministic bootstrap
            / permutation test instead of Welch's t-test.
        seed: Random seed for the (deterministic) resampling fallback.
        method: "auto" (prefer Welch, fall back to bootstrap for tiny samples),
            "welch", or "bootstrap"/"permutation".

    Returns:
        An ``AssessmentResult`` with the p-value and significance verdict.
    """
    before = list(before)
    after = list(after)

    # Default auto: prefer the exact Welch t-test when we have enough samples;
    # fall back to the permutation test for degenerate / tiny inputs.
    method_lc = method.lower()
    use_perm = (
        fallback_to_bootstrap
        or method_lc in ("bootstrap", "permutation")
        or (method_lc == "auto" and (len(before) < 2 or len(after) < 2))
    )

    if use_perm:
        p = permutation_test(before, after, n_permutations=10_000, seed=seed)
        used = "permutation"
        t_stat = df = None
        eff = _effect_size(before, after)
    else:
        t_stat, df, p = welch_t_test(before, after)
        used = "welch"
        eff = _effect_size(before, after)

    significant = bool(p <= alpha) if math.isfinite(p) else False
    return AssessmentResult(
        p_value=float(p),
        significant=significant,
        method=used,
        alpha=alpha,
        t_statistic=t_stat,
        degrees_of_freedom=df,
        effect_size=eff,
    )


def _effect_size(before: Sequence[float], after: Sequence[float]) -> float | None:
    """Cohen's d (pooled) effect size, or None when incalculable."""
    n1 = len(before)
    n2 = len(after)
    if n1 < 2 or n2 < 2:
        return None
    try:
        m1 = statistics.fmean(before)
        m2 = statistics.fmean(after)
        v1 = statistics.variance(before)
        v2 = statistics.variance(after)
    except statistics.StatisticsError:
        return None
    pooled_var = ((n1 - 1) * v1 + (n2 - 1) * v2) / (n1 + n2 - 2)
    if pooled_var <= 0:
        return None
    return (m2 - m1) / math.sqrt(pooled_var)


# ---------------------------------------------------------------------------
# Experiment record.
# ---------------------------------------------------------------------------


@dataclass
class Experiment:
    """A first-class, serializable record of a hypothesis test."""

    id: str
    hypothesis: str
    status: str = "draft"
    metrics_before: list[float] = field(default_factory=list)
    metrics_after: list[float] = field(default_factory=list)
    p_value: float | None = None
    significance: bool | None = None
    conclusion: str = ""
    method: str = ""
    alpha: float = 0.05
    created_at: str = field(default_factory=lambda: _now_iso())
    updated_at: str = field(default_factory=lambda: _now_iso())

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain dictionary (JSON-friendly)."""
        return {
            "id": self.id,
            "hypothesis": self.hypothesis,
            "status": self.status,
            "metrics_before": list(self.metrics_before),
            "metrics_after": list(self.metrics_after),
            "p_value": self.p_value,
            "significance": self.significance,
            "conclusion": self.conclusion,
            "method": self.method,
            "alpha": self.alpha,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Experiment:
        """Reconstruct from a dictionary produced by ``to_dict``."""
        return cls(
            id=str(data.get("id", "")),
            hypothesis=str(data.get("hypothesis", "")),
            status=str(data.get("status", "draft")),
            metrics_before=[float(x) for x in data.get("metrics_before", [])],
            metrics_after=[float(x) for x in data.get("metrics_after", [])],
            p_value=data.get("p_value"),
            significance=data.get("significance"),
            conclusion=str(data.get("conclusion", "")),
            method=str(data.get("method", "")),
            alpha=float(data.get("alpha", 0.05)),
            created_at=str(data.get("created_at", _now_iso())),
            updated_at=str(data.get("updated_at", _now_iso())),
        )


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


# ---------------------------------------------------------------------------
# SQLite-backed experiment registry.
# ---------------------------------------------------------------------------


class ExperimentRegistry:
    """Durable SQLite-backed store for experiments and their lifecycle.

    The registry owns the full lifecycle: register -> start -> record before ->
    record after -> finish -> conclude. Every transition is persisted, so a
    registry reopened against the same database path recovers all experiments.
    """

    def __init__(
        self,
        db_path: str | os.PathLike | None = None,
        *,
        autocommit: bool = True,
    ) -> None:
        if db_path is None:
            db_path = os.path.join(
                tempfile.gettempdir(),
                f"eni_innovation_rd_{os.getpid()}_{uuid4().hex[:8]}.db",
            )
        self._db_path = str(db_path)
        self._autocommit = autocommit
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(self._db_path)
        self._conn.row_factory = sqlite3.Row
        self._create_schema()

    @property
    def db_path(self) -> str:
        return self._db_path

    # -- schema -------------------------------------------------------------
    def _create_schema(self) -> None:
        with self._lock:
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS experiments (
                    id            TEXT PRIMARY KEY,
                    hypothesis    TEXT NOT NULL,
                    status        TEXT NOT NULL,
                    metrics_before TEXT NOT NULL,
                    metrics_after  TEXT NOT NULL,
                    p_value       REAL,
                    significance  INTEGER,
                    conclusion    TEXT,
                    method        TEXT,
                    alpha         REAL,
                    created_at    TEXT,
                    updated_at    TEXT
                )
                """
            )
            self._conn.commit()

    # -- lifecycle ----------------------------------------------------------
    def register_experiment(self, hypothesis: str, experiment_id: str | None = None) -> Experiment:
        """Create and persist a new experiment in DRAFT status."""
        eid = experiment_id or f"exp-{uuid4().hex[:12]}"
        exp = Experiment(id=eid, hypothesis=hypothesis, status="draft")
        with self._lock:
            self._conn.execute(
                """
                INSERT OR REPLACE INTO experiments
                (id, hypothesis, status, metrics_before, metrics_after,
                 p_value, significance, conclusion, method, alpha,
                 created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    exp.id,
                    exp.hypothesis,
                    exp.status,
                    json.dumps(exp.metrics_before),
                    json.dumps(exp.metrics_after),
                    exp.p_value,
                    None if exp.significance is None else int(exp.significance),
                    exp.conclusion,
                    exp.method,
                    exp.alpha,
                    exp.created_at,
                    exp.updated_at,
                ),
            )
            self._commit()
        logger.info("Registered experiment %s: %s", eid, hypothesis[:60])
        return exp

    def start(self, experiment_id: str) -> bool:
        """Transition an experiment from draft -> running."""
        exp = self.get(experiment_id)
        if exp is None:
            return False
        if exp.status != "draft":
            return False
        return self._update(
            experiment_id,
            status="running",
            updated_at=_now_iso(),
        )

    def record_metric_before(self, experiment_id: str, value: float) -> bool:
        """Append a control/baseline metric to the experiment."""
        exp = self.get(experiment_id)
        if exp is None:
            return False
        if exp.status not in ("running", "draft"):
            return False
        metrics = list(exp.metrics_before) + [float(value)]
        return self._update(
            experiment_id,
            metrics_before=json.dumps(metrics),
            updated_at=_now_iso(),
        )

    def record_metric_after(self, experiment_id: str, value: float) -> bool:
        """Append a treatment/experiment metric to the experiment."""
        exp = self.get(experiment_id)
        if exp is None:
            return False
        if exp.status not in ("running", "draft"):
            return False
        metrics = list(exp.metrics_after) + [float(value)]
        return self._update(
            experiment_id,
            metrics_after=json.dumps(metrics),
            updated_at=_now_iso(),
        )

    def finish(
        self,
        experiment_id: str,
        *,
        alpha: float = 0.05,
        fallback_to_bootstrap: bool = False,
        seed: int | None = None,
    ) -> Experiment:
        """Run the statistical test and conclude the experiment.

        Computes the p-value from the recorded before/after metrics, sets the
        significance verdict and conclusion, and marks the experiment finished.
        """
        exp = self.get(experiment_id)
        if exp is None:
            msg = f"No experiment registered with id {experiment_id!r}"
            raise KeyError(msg)
        result = assess(
            exp.metrics_before,
            exp.metrics_after,
            alpha=alpha,
            fallback_to_bootstrap=fallback_to_bootstrap,
            seed=seed,
        )
        self._update(
            experiment_id,
            status="finished",
            p_value=float(result.p_value),
            significance=1 if result.significant else 0,
            conclusion=result.conclusion(),
            method=result.method,
            alpha=alpha,
            updated_at=_now_iso(),
        )
        return self.get(experiment_id)  # type: ignore[return-value]

    def conclude(
        self,
        experiment_id: str,
        *,
        alpha: float = 0.05,
        fallback_to_bootstrap: bool = False,
        seed: int | None = None,
    ) -> Experiment:
        """Alias for ``finish`` — compute stats and reach a conclusion."""
        return self.finish(
            experiment_id,
            alpha=alpha,
            fallback_to_bootstrap=fallback_to_bootstrap,
            seed=seed,
        )

    def fail(self, experiment_id: str, message: str = "") -> bool:
        """Mark an experiment as failed (e.g. runner raised)."""
        exp = self.get(experiment_id)
        if exp is None:
            return False
        return self._update(
            experiment_id,
            status="failed",
            conclusion=message or "Experiment failed",
            updated_at=_now_iso(),
        )

    # -- query --------------------------------------------------------------
    def get(self, experiment_id: str) -> Experiment | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM experiments WHERE id = ?", (experiment_id,)
            ).fetchone()
        if row is None:
            return None
        return self._row_to_experiment(row)

    def list(self) -> builtins.list[Experiment]:
        with self._lock:
            rows = self._conn.execute("SELECT * FROM experiments ORDER BY created_at").fetchall()
        return [self._row_to_experiment(r) for r in rows]

    def count(self) -> int:
        with self._lock:
            row = self._conn.execute("SELECT COUNT(*) AS n FROM experiments").fetchone()
        return int(row["n"]) if row else 0

    # -- internals ----------------------------------------------------------
    def _update(self, experiment_id: str, **fields: Any) -> bool:
        cols = [k for k in fields if k not in ("id",)]
        if not cols:
            return False
        assignments = ", ".join(f"{c} = ?" for c in cols)
        params = [fields[c] for c in cols]
        params.append(experiment_id)
        with self._lock:
            cur = self._conn.execute(f"UPDATE experiments SET {assignments} WHERE id = ?", params)
            self._commit()
        return cur.rowcount > 0

    def _commit(self) -> None:
        if self._autocommit:
            self._conn.commit()

    @staticmethod
    def _row_to_experiment(row: sqlite3.Row) -> Experiment:
        return Experiment(
            id=str(row["id"]),
            hypothesis=str(row["hypothesis"]),
            status=str(row["status"]),
            metrics_before=[float(x) for x in json.loads(row["metrics_before"] or "[]")],
            metrics_after=[float(x) for x in json.loads(row["metrics_after"] or "[]")],
            p_value=row["p_value"],
            significance=(bool(row["significance"]) if row["significance"] is not None else None),
            conclusion=str(row["conclusion"] or ""),
            method=str(row["method"] or ""),
            alpha=float(row["alpha"] or 0.05),
            created_at=str(row["created_at"] or ""),
            updated_at=str(row["updated_at"] or ""),
        )

    def close(self) -> None:
        with self._lock:
            try:
                self._conn.commit()
            finally:
                self._conn.close()

    def __enter__(self) -> ExperimentRegistry:
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()


# ---------------------------------------------------------------------------
# HypothesisTest: object-oriented statistical test.
# ---------------------------------------------------------------------------


class HypothesisTest:
    """Wraps the statistics surface of a before/after comparison.

    Accepts raw sample arrays and exposes ``p_value`` and ``is_significant``
    using either the exact Welch t-test or a deterministic permutation test.
    """

    def __init__(
        self,
        before: Sequence[float],
        after: Sequence[float],
        alpha: float = 0.05,
        *,
        seed: int | None = None,
    ) -> None:
        self.before = list(before)
        self.after = list(after)
        self.alpha = alpha
        self.seed = seed

    def p_value(self, fallback_to_bootstrap: bool = False) -> float:
        """Compute the two-sided p-value.

        Uses Welch's t-test by default; falls back to a deterministic
        permutation test when ``fallback_to_bootstrap`` is True or when the
        sample sizes are too small for the t-test.
        """
        return assess(
            self.before,
            self.after,
            alpha=self.alpha,
            fallback_to_bootstrap=fallback_to_bootstrap,
            seed=self.seed,
        ).p_value

    def is_significant(self, alpha: float | None = None) -> bool:
        """Return True if the difference is significant at ``alpha``."""
        threshold = self.alpha if alpha is None else alpha
        return assess(
            self.before,
            self.after,
            alpha=threshold,
            fallback_to_bootstrap=False,
            seed=self.seed,
        ).significant

    def result(self, fallback_to_bootstrap: bool = False) -> AssessmentResult:
        """Full assessment result (p-value, significance, effect size, etc.)."""
        return assess(
            self.before,
            self.after,
            alpha=self.alpha,
            fallback_to_bootstrap=fallback_to_bootstrap,
            seed=self.seed,
        )


# ---------------------------------------------------------------------------
# ExperimentRunner: guarded harness.
# ---------------------------------------------------------------------------


class ExperimentRunner:
    """Guarded harness that runs control and treatment and records results.

    ``fn_before`` is the control/baseline callable and ``fn_after`` is the
    treatment callable. Both may return either a single float or a sequence of
    floats. Results are recorded into an ``ExperimentRegistry`` and the runner
    concludes the experiment statistically.

    The runner is *guarded*: if either callable raises, the experiment is
    marked failed and no partial conclusion is written.
    """

    def __init__(
        self,
        registry: ExperimentRegistry,
        alpha: float = 0.05,
        *,
        seed: int | None = None,
        fallback_to_bootstrap: bool = False,
    ) -> None:
        self.registry = registry
        self.alpha = alpha
        self.seed = seed
        self.fallback_to_bootstrap = fallback_to_bootstrap

    @staticmethod
    def _coerce_samples(value: Any) -> list[float]:
        if isinstance(value, (int, float)):
            return [float(value)]
        try:
            return [float(v) for v in value]
        except (TypeError, ValueError):
            msg = (
                f"Runner callables must return a number or sequence of numbers, "
                f"got {type(value).__name__}"
            )
            raise ValueError(msg)

    def run(
        self,
        experiment_id: str,
        fn_before: Callable[[], Any],
        fn_after: Callable[[], Any],
    ) -> Experiment:
        """Execute the control and treatment, record metrics, and conclude.

        Args:
            experiment_id: Registered experiment to run against.
            fn_before: Control callable -> float or sequence of floats.
            fn_after: Treatment callable -> float or sequence of floats.

        Returns:
            The concluded ``Experiment`` record (status ``finished``).
        """
        exp = self.registry.get(experiment_id)
        if exp is None:
            msg = f"Experiment {experiment_id!r} not registered — call register_experiment() first"
            raise KeyError(msg)

        if exp.status != "running":
            self.registry.start(experiment_id)

        try:
            before = self._coerce_samples(fn_before())
            after = self._coerce_samples(fn_after())
        except Exception as exc:  # guarded
            self.registry.fail(experiment_id, message=f"Runner error: {exc}")
            raise

        # Record all sampled metrics.
        for v in before:
            self.registry.record_metric_before(experiment_id, v)
        for v in after:
            self.registry.record_metric_after(experiment_id, v)

        return self.registry.finish(
            experiment_id,
            alpha=self.alpha,
            fallback_to_bootstrap=self.fallback_to_bootstrap,
            seed=self.seed,
        )

    def run_new(
        self,
        hypothesis: str,
        fn_before: Callable[[], Any],
        fn_after: Callable[[], Any],
        experiment_id: str | None = None,
    ) -> Experiment:
        """Register a fresh experiment, run it, and return the conclusion."""
        exp = self.registry.register_experiment(hypothesis, experiment_id)
        return self.run(exp.id, fn_before, fn_after)
