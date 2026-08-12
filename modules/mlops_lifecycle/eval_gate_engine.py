"""
Evaluation Gate Engine — automated quality gates that block or promote a
model/agent version based on evaluation metrics against configurable policies.

Pure-stdlib implementation (dataclasses + enums). A pipeline produces an
:class:`EvaluationReport` from raw metrics; policies are then evaluated
against the report to produce a list of :class:`GateResult` objects.
"""

from __future__ import annotations

import logging
import threading
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Sequence

logger = logging.getLogger("enterprise.mlops_lifecycle.eval_gate_engine")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class Comparison(Enum):
    """Supported metric -> threshold comparison operators."""

    GE = ">="
    LE = "<="
    GT = ">"
    LT = "<"
    EQ = "=="


@dataclass
class GatePolicy:
    """A single quality gate: ``metric`` compared to ``threshold``."""

    name: str
    metric: str
    operator: Comparison | str = Comparison.GE
    threshold: float = 0.9
    description: str = ""

    def __post_init__(self) -> None:
        if isinstance(self.operator, str):
            try:
                self.operator = Comparison(self.operator)
            except ValueError:
                raise ValueError(f"unsupported comparison operator: {self.operator!r}")

    def evaluate(self, report: "EvaluationReport") -> "GateResult":
        value = report.metrics.get(self.metric)
        if value is None:
            return GateResult(
                policy_name=self.name,
                metric=self.metric,
                operator=self.operator,
                threshold=self.threshold,
                value=None,
                passed=False,
                reason=f"metric {self.metric!r} not present in report",
            )
        passed, reason = self._compare(float(value), float(self.threshold))
        return GateResult(
            policy_name=self.name,
            metric=self.metric,
            operator=self.operator,
            threshold=self.threshold,
            value=float(value),
            passed=passed,
            reason=reason,
        )

    def _compare(self, value: float, threshold: float) -> tuple[bool, str]:
        op = self.operator
        if op is Comparison.GE:
            ok = value >= threshold
        elif op is Comparison.LE:
            ok = value <= threshold
        elif op is Comparison.GT:
            ok = value > threshold
        elif op is Comparison.LT:
            ok = value < threshold
        elif op is Comparison.EQ:
            ok = abs(value - threshold) < 1e-9
        else:  # pragma: no cover - defensive
            ok = False
        return ok, f"{value:.4f} {op.value} {threshold:.4f}"


@dataclass
class GateResult:
    """Outcome of evaluating one policy against a report."""

    policy_name: str
    metric: str
    operator: Comparison
    threshold: float
    value: Optional[float]
    passed: bool
    reason: str = ""
    evaluated_at: str = field(default_factory=_now_iso)


@dataclass
class EvaluationReport:
    """A scored evaluation of a candidate version."""

    version: str
    metrics: Dict[str, float] = field(default_factory=dict)
    report_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: str = field(default_factory=_now_iso)
    extra: Dict[str, Any] = field(default_factory=dict)


@dataclass
class EvaluationPipeline:
    """A named evaluation with a deterministic set of policies."""

    name: str
    policies: List[GatePolicy] = field(default_factory=list)
    pipeline_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    description: str = ""

    def add_policy(self, policy: GatePolicy) -> None:
        self.policies.append(policy)


class EvalGateEngine:
    """Runs evaluation pipelines and enforces quality gates."""

    def __init__(self) -> None:
        self._pipelines: Dict[str, EvaluationPipeline] = {}
        self._history: List[tuple[EvaluationReport, List[GateResult]]] = []
        self._lock = threading.RLock()

    def register_pipeline(self, pipeline: EvaluationPipeline) -> str:
        with self._lock:
            self._pipelines[pipeline.pipeline_id] = pipeline
        return pipeline.pipeline_id

    def get_pipeline(self, pipeline_id: str) -> Optional[EvaluationPipeline]:
        with self._lock:
            return self._pipelines.get(pipeline_id)

    def run_pipeline(
        self,
        pipeline: EvaluationPipeline | str,
        metrics: Dict[str, float],
        version: str = "latest",
    ) -> list[GateResult]:
        """Run a pipeline's policies against raw metrics."""
        if isinstance(pipeline, str):
            resolved = self.get_pipeline(pipeline)
            if resolved is None:
                raise KeyError(f"unknown pipeline: {pipeline!r}")
            pipeline = resolved
        report = EvaluationReport(version=version, metrics=metrics)
        results = [policy.evaluate(report) for policy in pipeline.policies]
        with self._lock:
            self._history.append((report, results))
        return results

    def evaluate(
        self,
        pipeline: EvaluationPipeline | str,
        metrics: Dict[str, float],
        version: str = "latest",
    ) -> tuple[EvaluationReport, List[GateResult]]:
        """Convenience wrapper returning both the report and gate results."""
        results = self.run_pipeline(pipeline, metrics, version=version)
        report = self._history[-1][0]
        return report, results

    @staticmethod
    def passed(results: Sequence[GateResult]) -> bool:
        """True only if every gate in the sequence passed."""
        return all(r.passed for r in results)

    def gate_summary(self, results: Sequence[GateResult]) -> Dict[str, Any]:
        return {
            "total": len(results),
            "passed": sum(1 for r in results if r.passed),
            "failed": sum(1 for r in results if not r.passed),
            "all_passed": self.passed(results),
        }

    def history(self) -> List[tuple[EvaluationReport, List[GateResult]]]:
        with self._lock:
            return list(self._history)


def create_eval_gate_engine(config: Optional[Dict[str, Any]] = None) -> EvalGateEngine:
    """Create a default :class:`EvalGateEngine`.

    Args:
        config: Optional dict (currently unused; kept for interface parity).
    """
    return EvalGateEngine()
