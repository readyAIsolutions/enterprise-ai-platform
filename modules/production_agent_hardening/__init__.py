"""Production Agent Hardening module — ship a demo agent that survives production.

Implements the production-readiness lessons from two pulled JE Van Clief
transcripts:

  * "Two Engineers on Why Your Agent Demo Will Not Survive Production"
    — observability ("understand how things are running"), error handling,
      retries, secrets, cost bounds, and the "demo trap" of canned/hardcoded
      behavior that does not generalize.

  * "Systems Thinking for People Who Build With AI"
    — a systems lens (feedback loops, coupling, emergent behavior) on why
      ~95% of agentic AI initiatives never make real-world impact (as cited
      from MIT Project Nanda), and how to reason about the whole system
      rather than only the happy path.

Export surface:
  * harden_spec — score an agent spec across hardening dimensions.
  * run_readiness_check — CI-grade production gate.
  * systems_feedback_loop — feedback-loop / coupling analysis.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from enterprise.platform_kernel import HealthStatus, Module, module

from .hardening import (  # noqa: F401
    CRITICAL,
    DEMO_TRAP_SIGNATURES,
    DEFAULT_WEIGHTS,
    Finding,
    HardeningReport,
    PASS,
    WARNING,
    harden_spec,
    run_readiness_check,
    systems_feedback_loop,
)

logger = logging.getLogger("eni.production_agent_hardening")
__version__ = "1.0.0"


@module(
    name="production_agent_hardening",
    version="1.0.0",
    config_defaults={"min_score": 70.0, "required": ["secrets", "error_handling", "observability"]},
)
class ProductionAgentHardeningModule(Module):
    def __init__(self, config: Optional[dict[str, Any]] = None) -> None:
        super().__init__(config)
        self.default_min_score: float = 70.0
        self.required: List[str] = ["secrets", "error_handling", "observability"]

    async def initialize(self) -> None:
        self.default_min_score = float(self.config.get("min_score", 70.0))
        self.required = list(self.config.get(
            "required", ["secrets", "error_handling", "observability"]))
        self.status = HealthStatus.HEALTHY

    async def health_check(self) -> HealthStatus:
        return HealthStatus.HEALTHY

    async def shutdown(self) -> None:
        self.status = HealthStatus.UNKNOWN

    # facade
    def harden(self, spec: Dict[str, Any],
               weights: Optional[Dict[str, int]] = None,
               fail_on: Optional[List[str]] = None) -> Dict[str, Any]:
        """Score an agent spec; returns a HardeningReport as a dict."""
        return harden_spec(spec, weights=weights, fail_on=fail_on).to_dict()

    def readiness(self, spec: Dict[str, Any],
                  min_score: Optional[float] = None,
                  required: Optional[List[str]] = None) -> Dict[str, Any]:
        """Production gate: is this spec ready? Uses module defaults if absent."""
        return run_readiness_check(
            spec,
            min_score=min_score if min_score is not None else self.default_min_score,
            required=required if required is not None else self.required,
        )

    def systems(self, spec: Dict[str, Any]) -> Dict[str, Any]:
        """Systems-thinking lens: feedback loops + coupling for an agent graph."""
        return systems_feedback_loop(spec)


def create_production_agent_hardening_module(
        config: Optional[dict[str, Any]] = None) -> ProductionAgentHardeningModule:
    return ProductionAgentHardeningModule(config=config or {})


__all__ = [
    "ProductionAgentHardeningModule",
    "create_production_agent_hardening_module",
    "harden_spec",
    "run_readiness_check",
    "systems_feedback_loop",
    "HardeningReport",
    "Finding",
    "DEFAULT_WEIGHTS",
    "DEMO_TRAP_SIGNATURES",
    "CRITICAL",
    "WARNING",
    "PASS",
    "__version__",
]
