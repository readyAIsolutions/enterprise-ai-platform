"""Production Hardening module — production-readiness for ML / agent systems.

Grounded in the real pulled JE Van Clief transcript
"data/transcripts/JEVanClief/ezRtp6K6zwE.md" — "Two Engineers on Why Your
Agent Demo Will Not Survive Production" — a 57-minute NLP Logix interview
with Anton Corner (Director of Data & AI Engineering) and Ryan Nent
(Software Engineer).  The episode's thesis is that a demo and a sustained
production system live under different constraints: the invisible 80% of
the work (governance, monitoring, runtime, databases, monitoring tooling)
is what makes a system operate reliably, and shipping a one-off demo
over-enthusiastically is exactly how production fails.

Export surface:
  * ProductionReadinessRule / ReadinessReport / SystemProfile — data model.
  * assess() / assess_answers() — readiness scoring & gating.
  * Run-assurance helpers: check_deterministic_output, detect_drift,
    circuit_breaker_state, retry_plan, human_escalation_required.
  * ProductionHardeningModule — the ENI platform Module wrapper.
  * create_production_hardening_module(config) — factory used by the platform.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from enterprise.platform_kernel import Event, HealthStatus, Module, module

from .production_hardening import (  # noqa: F401
    CATEGORIES, CheckOutcome, CircuitState, RiskLevel,
    ReadinessRule, RuleResult, CategoryResult, ReadinessReport,
    SystemProfile, assess, assess_answers, default_rules,
    DeterminismResult, check_deterministic_output,
    DriftResult, detect_drift,
    CircuitDecision, circuit_breaker_state,
    RetryDecision, retry_plan,
    EscalationDecision, human_escalation_required,
)

logger = logging.getLogger("eni.production_hardening")
__version__ = "1.0.0"


@module(
    name="production_hardening",
    version="1.0.0",
    config_defaults={
        # Whether the module may publish events on the shared bus.
        "publish_events": True,
        # Override the escalation threshold risk level used by the facade.
        "escalation_threshold": "HIGH",
        # Human label used as the event source for audit/observability.
        "source_label": "production_hardening",
    },
)
class ProductionHardeningModule(Module):
    """ENI platform wrapper around the production-readiness engine."""

    def __init__(self, config: Optional[dict[str, Any]] = None) -> None:
        super().__init__(config)
        self._event_bus: Optional[Any] = None
        self._rules: List[ReadinessRule] = list(default_rules())

    async def initialize(self) -> None:
        """Load config and mark the module healthy.

        Sets HEALTHY on success; on failure sets UNHEALTHY and re-raises.
        """
        try:
            cfg = self._config or {}
            self._escalation_threshold = RiskLevel(
                str(cfg.get("escalation_threshold", "HIGH")).upper()
            )
            self._publish_events = bool(cfg.get("publish_events", True))
            self._source_label = str(cfg.get("source_label", "production_hardening"))
            self._rules = list(default_rules())
            self.status = HealthStatus.HEALTHY
            logger.info("production_hardening module initialized")
        except Exception:
            self.status = HealthStatus.UNHEALTHY
            logger.exception("production_hardening initialize failed")
            raise

    async def health_check(self) -> HealthStatus:
        """Healthy iff rules are loaded (the readiness engine is ready)."""
        if self._rules:
            return HealthStatus.HEALTHY
        self.status = HealthStatus.UNHEALTHY
        return HealthStatus.UNHEALTHY

    async def shutdown(self) -> None:
        """Release the engine and return to UNKNOWN."""
        self._rules = []
        self._event_bus = None
        self.status = HealthStatus.UNKNOWN

    # ------------------------------------------------------------- event bus
    def set_event_bus(self, event_bus: Any) -> None:
        """Attach the shared EventBus.  Events are only published if the bus
        is not None (and publishing is enabled in config)."""
        self._event_bus = event_bus

    def _publish(self, topic: str, payload: dict[str, Any]) -> None:
        bus = self._event_bus
        if bus is None:
            return
        try:
            if not getattr(self, "_publish_events", True):
                return
            bus.publish(Event.create(topic=topic, source=self._source_label,
                                     payload=payload))
        except Exception:  # never let a bus failure break the facade
            logger.warning("production_hardening event publish failed", exc_info=True)

    # ------------------------------------------------------------- facade
    def categories(self) -> Dict[str, Dict[str, str]]:
        """Metadata for every readiness category (title/summary/ref)."""
        return dict(CATEGORIES)

    def rules(self) -> List[ReadinessRule]:
        """The grounded readiness checklist (each rule carries a transcript
        reference)."""
        return list(self._rules)

    def assess_answers(self, name: str,
                       answers: Dict[str, Any]) -> ReadinessReport:
        """Score a system from a plain answers dict and publish an event."""
        report = assess_answers(name, answers, rules=self._rules)
        self._publish(
            "production_hardening.assessment",
            {"system": name, "verdict": report.gate_verdict,
             "score": report.overall_score,
             "production_ready": report.production_ready},
        )
        return report

    def assess(self, system: SystemProfile) -> ReadinessReport:
        """Score a `SystemProfile` and publish an event."""
        report = assess(system, rules=self._rules)
        self._publish(
            "production_hardening.assessment",
            {"system": system.name, "verdict": report.gate_verdict,
             "score": report.overall_score,
             "production_ready": report.production_ready},
        )
        return report

    def check_determinism(self, observed: list[Any]) -> DeterminismResult:
        """Probe repeatability of a golden path across repeated runs."""
        return check_deterministic_output(observed)

    def check_drift(self, reference_mean: float, current_mean: float,
                    reference_std: float,
                    threshold_std: float = 2.0) -> DriftResult:
        """Detect data/model drift vs a reference distribution."""
        return detect_drift(reference_mean, current_mean, reference_std,
                            threshold_std)

    def breaker(self, failures_in_window: int, max_failures: int,
                cooldown_remaining: int = 0,
                allow_probe: bool = False) -> CircuitDecision:
        """Circuit-breaker decision for a brittle chain."""
        return circuit_breaker_state(failures_in_window, max_failures,
                                     cooldown_remaining, allow_probe)

    def retry(self, attempt: int, max_retries: int) -> RetryDecision:
        """Exponential-backoff retry decision."""
        return retry_plan(attempt, max_retries)

    def escalation(self, severity: RiskLevel) -> EscalationDecision:
        """Human-oversight gate using the configured threshold."""
        decision = human_escalation_required(severity, self._escalation_threshold)
        self._publish(
            "production_hardening.escalation",
            {"severity": severity.value, "human_required": decision.human_required},
        )
        return decision


def create_production_hardening_module(
    config: Optional[dict[str, Any]] = None,
) -> ProductionHardeningModule:
    return ProductionHardeningModule(config=config or {})


__all__ = [
    "CATEGORIES", "CheckOutcome", "CircuitState", "RiskLevel",
    "ReadinessRule", "RuleResult", "CategoryResult", "ReadinessReport",
    "SystemProfile", "assess", "assess_answers", "default_rules",
    "DeterminismResult", "check_deterministic_output",
    "DriftResult", "detect_drift",
    "CircuitDecision", "circuit_breaker_state",
    "RetryDecision", "retry_plan",
    "EscalationDecision", "human_escalation_required",
    "ProductionHardeningModule", "create_production_hardening_module",
    "__version__",
]
