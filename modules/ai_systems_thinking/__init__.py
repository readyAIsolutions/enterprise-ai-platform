"""ai_systems_thinking module — systems-thinking evaluation for AI system designs.

Grounded in the pulled JE Van Clief transcripts:

* ``NWyTsKTKka8`` — *Systems Thinking for People Who Build With AI*
* ``jjV1ckgPzI0`` — *I Charged $2000 For This AI Lecture (And I Underpriced It)*
* ``g3eWjeZPFiM`` — *Life, Liberty and the pursuit of Artificial Intelligence*

The module exposes a deterministic, network-free evaluation engine
(:class:`~enterprise.modules.ai_systems_thinking.assessor.SystemsThinker`)
that scores an AI system design across systems-thinking dimensions and emits:
per-dimension scores, identified feedback loops (including implicit ones found
by walking the coupling graph), leverage points, coupling analysis, risks of
unintended consequences, and an overall systems-health read.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from enterprise.platform_kernel import HealthStatus, Module, module

from .assessor import (  # noqa: F401
    AISystemDesign,
    Component,
    Connection,
    Contradiction,
    CouplingAnalysis,
    CouplingStrength,
    DesignContext,
    FeedbackLoop,
    Governance,
    LeveragePoint,
    LoopType,
    OverallRead,
    Risk,
    RiskLevel,
    SystemsAssessment,
    SystemsThinker,
    assess,
)

logger = logging.getLogger("eni.ai_systems_thinking")
__version__ = "1.0.0"

# Default dimension weights used by the overall read.
CONFIG_DEFAULTS: Dict[str, Any] = {
    "dimension_weights": {
        "holistic_view": 0.15,
        "modularity": 0.15,
        "feedback_loops": 0.20,
        "traceability": 0.15,
        "context_leverage": 0.15,
        "unintended_consequences": 0.10,
        "emergence_awareness": 0.10,
    },
}


def make_thinker() -> SystemsThinker:
    """Facade: construct the core systems-thinking evaluation engine."""
    return SystemsThinker()


@module(
    name="ai_systems_thinking",
    version="1.0.0",
    config_defaults=CONFIG_DEFAULTS,
)
class AiSystemsThinkingModule(Module):
    """Module wrapper binding the pure engine to the ENI platform lifecycle."""

    def __init__(self, config: Optional[dict[str, Any]] = None) -> None:
        super().__init__(config)
        self.thinker: Optional[SystemsThinker] = None

    async def initialize(self) -> None:
        try:
            self.thinker = make_thinker()
            self.status = HealthStatus.HEALTHY
        except Exception:
            self.status = HealthStatus.UNHEALTHY
            raise

    async def health_check(self) -> HealthStatus:
        if self.thinker is not None:
            self.status = HealthStatus.HEALTHY
        else:
            self.status = HealthStatus.UNHEALTHY
        return self.status

    async def shutdown(self) -> None:
        self.thinker = None
        self.status = HealthStatus.UNKNOWN

    # ---- facade: construct-and-return the core engine ------------------- #
    def engine(self) -> SystemsThinker:
        """Return the core evaluation engine (raises if not initialized)."""
        if self.thinker is None:
            raise RuntimeError("ai_systems_thinking module not initialized")
        return self.thinker

    def evaluate(self, design: AISystemDesign) -> SystemsAssessment:
        """Evaluate a system design through the systems-thinking lens."""
        return self.engine().evaluate(design)


def create_ai_systems_thinking_module(
    config: Optional[dict[str, Any]] = None,
) -> AiSystemsThinkingModule:
    return AiSystemsThinkingModule(config=config or {})


__all__ = [
    # core engine + input/output model
    "SystemsThinker",
    "AISystemDesign",
    "Component",
    "Connection",
    "FeedbackLoop",
    "DesignContext",
    "Governance",
    "CouplingStrength",
    "LoopType",
    "RiskLevel",
    "OverallRead",
    "SystemsAssessment",
    "CouplingAnalysis",
    "LeveragePoint",
    "Risk",
    "Contradiction",
    "assess",
    # module facade
    "make_thinker",
    "AiSystemsThinkingModule",
    "create_ai_systems_thinking_module",
    "__version__",
]
