"""ENI Eval Gate OS Module — automated LLM evaluation gates (local & offline).

Local, stdlib-only automated evaluation of model output quality using fully
deterministic lexical/heuristic metrics (no external model or service calls).
Mirrors the ``model_security`` philosophy: every metric is a regex- and
term-overlap-based function that can be unit tested offline.

Metrics implemented (computed from text alone):
  - AnswerRelevancy    — relevance proxy via answer/question token overlap.
  - Faithfulness       — groundedness of the answer relative to a source.
  - ToxicityDetector   — banned-word lexicon scan for profane content.
  - HallucinationProxy — fact-consistency proxy (unsupported-claim fraction).
  - RefusalDetector    — refusal / evasion phrasing detection.
  - JailbreakGuard     — jailbreak / prompt-injection attempt detection.

An :class:`EvalGate` enforces thresholds + policy (fail if any required metric
is below its minimum), :class:`EvalRunner` aggregates over sample dicts, and
:class:`EvalGateFacade` exposes the public surface behind the @module-decorated
:class:`EvalGateModule`.

All components are stdlib-only, zero external dependencies.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from enterprise.platform_kernel import (
    EventBus,
    HealthStatus,
    Module,
    module,
)

from .eval_gate import (
    AnswerRelevancy,
    EvalGate,
    EvalGateFacade,
    EvalGateModule,
    EvalMetric,
    EvalRunner,
    EvaluationReport,
    Faithfulness,
    HallucinationProxy,
    JailbreakGuard,
    MetricResult,
    RefusalDetector,
    SuiteReport,
    ToxicityDetector,
    default_metrics,
)

__version__ = "1.0.0"
__module__ = "eval_gate"

__all__ = [
    "__version__",
    "EvalGateModule",
    # Core framework
    "EvalMetric",
    "EvalGate",
    "EvalRunner",
    "EvalGateFacade",
    "default_metrics",
    # Metrics
    "AnswerRelevancy",
    "Faithfulness",
    "ToxicityDetector",
    "HallucinationProxy",
    "RefusalDetector",
    "JailbreakGuard",
    # Types
    "MetricResult",
    "EvaluationReport",
    "SuiteReport",
]

_logger = logging.getLogger("enterprise.eval_gate")


def create_eval_gate(
    config: Optional[Dict[str, Any]] = None,
) -> EvalGate:
    """Create an :class:`EvalGate` with default metrics and optional overrides.

    Args:
        config: Optional dict with ``thresholds`` ({metric: min_score}) and/or
            ``required`` (list of metric names enforced by the policy).
    """
    cfg = config or {}
    return EvalGate(
        thresholds=dict(cfg.get("thresholds") or {}),
        required=(
            list(cfg["required"]) if cfg.get("required") is not None else None
        ),
    )
