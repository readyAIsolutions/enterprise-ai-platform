"""Engineering Tradeoff module — a satisficing (not 'best'-maximising) engine.

Grounded in the real pulled JE Van Clief transcript
"data/transcripts/JEVanClief/-YursW-UIoY.md" — "A Pagani, a Toyota, and Why
'Best' Is a Trap in AI". The thesis is that chasing the absolute "best" is a
trap: "best becomes relative" and the right answer comes from "figuring out
your actual need". The $5M Pagani Zonda is the absolute best on paper, but
the cheap, reliable Toyota that satisfies your real constraints is the
satisficing winner.

Export surface:
  * TradeoffEngine  — weighted multi-criteria satisficing decision engine.
  * Option/Constraint/Dimension — the data model for candidates & hard rules.
  * TradeoffResult  — ranking + absolute best vs satisficing winner + tradeoffs.
  * EngineeringTradeoffModule — the ENI platform Module wrapper.
  * create_engineering_tradeoff_module(config) — factory used by the platform.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Sequence

from enterprise.platform_kernel import HealthStatus, Module, module

from .engineering_tradeoff import (  # noqa: F401
    Constraint, Dimension, Option, ScoredOption, TradeoffAnalysis,
    TradeoffEngine, TradeoffResult, make_engine,
)

logger = logging.getLogger("eni.engineering_tradeoff")
__version__ = "1.0.0"


@module(
    name="engineering_tradeoff",
    version="1.0.0",
    config_defaults={
        "weights": {},          # per-dimension importance overrides
        "dimensions": ["cost", "quality", "speed", "robustness", "effort"],
        "default_weight": 1.0,
    },
)
class EngineeringTradeoffModule(Module):
    """ENI platform wrapper around the TradeoffEngine satisficing engine."""

    def __init__(self, config: Optional[dict[str, Any]] = None) -> None:
        super().__init__(config)
        self.engine: Optional[TradeoffEngine] = None

    async def initialize(self) -> None:
        weights: Dict[str, float] = dict(self._config.get("weights") or {})
        self.engine = make_engine(weights)
        self.status = HealthStatus.HEALTHY
        logger.info("engineering_tradeoff module initialized")

    async def health_check(self) -> HealthStatus:
        return (HealthStatus.HEALTHY if self.engine is not None
                else HealthStatus.UNHEALTHY)

    async def shutdown(self) -> None:
        self.engine = None
        self.status = HealthStatus.UNKNOWN

    # ------------------------------------------------------------- facade
    def dimensions(self) -> List[str]:
        return list(self.engine.dimensions())

    def evaluate(
        self,
        options: Sequence[Option],
        constraints: Sequence[Constraint] = (),
    ) -> TradeoffResult:
        """Score, rank and pick the satisficing winner for a decision."""
        return self.engine.evaluate(options, constraints)

    def pick_satisficing(
        self,
        options: Sequence[Option],
        constraints: Sequence[Constraint] = (),
    ) -> Optional[Option]:
        """Return the winning feasible option (the 'Toyota'), or None if no
        option satisfies every hard constraint."""
        result = self.engine.evaluate(options, constraints)
        return result.satisficing_winner.option if result.satisficing_winner else None


def create_engineering_tradeoff_module(
    config: Optional[dict[str, Any]] = None,
) -> EngineeringTradeoffModule:
    return EngineeringTradeoffModule(config=config or {})


__all__ = [
    "Constraint", "Dimension", "Option", "ScoredOption", "TradeoffAnalysis",
    "TradeoffEngine", "TradeoffResult", "EngineeringTradeoffModule",
    "create_engineering_tradeoff_module", "make_engine", "__version__",
]
