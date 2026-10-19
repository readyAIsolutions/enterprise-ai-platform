"""Agentic RAG retrieval-strategy planner module.

Grounded in Cole Medin's "Introducing RAG 2.0: Agentic RAG + Knowledge Graphs"
(YouTube p0FERNkpyHE). The agent is given BOTH a vector/semantic-search tool and
a knowledge-graph tool and "picks and chooses how it explores the knowledge".
This module is the PLANNER/ROUTER: given a query it decides which retrieval
tool(s) to use (vector vs graph vs hybrid) and in what order, and emits a
structured plan. It plans over abstract tool interfaces; it does not itself
implement a vector DB or a graph DB.
"""

from __future__ import annotations

import logging
from typing import Any

from enterprise.platform_kernel import EventBus, HealthStatus, Module, module

from .core import (  # noqa: F401
    GRAPH,
    HYBRID,
    VECTOR,
    ClassificationResult,
    InMemoryTool,
    PlanExecutor,
    QueryClassifier,
    RagPlanner,
    RetrievalPlan,
    RetrievalStep,
    RetrievalTool,
    RetrievalToolABC,
    ToolKind,
)

logger = logging.getLogger("eni.agentic_rag_planner")
__version__ = "1.0.0"


@module(name="agentic_rag_planner", version="1.0.0")
class AgenticRagPlannerModule(Module):
    """ENI platform wrapper around the agentic RAG retrieval-strategy planner."""

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        super().__init__(config)
        self._event_bus: EventBus | None = None
        self._planner: RagPlanner | None = None

    async def initialize(self) -> None:
        self._status = HealthStatus.STARTING
        try:
            self._planner = RagPlanner()
            # Smoke-test routing so a broken classifier surfaces at boot.
            plan = self._planner.plan("how is Google connected to OpenAI")
            assert plan.strategy is ToolKind.GRAPH
            assert self._planner.plan("explain how transformers work").strategy is ToolKind.VECTOR
            self._status = HealthStatus.HEALTHY
            logger.info("agentic_rag_planner module initialized")
            if self._event_bus is not None:
                try:
                    self._event_bus.publish("agentic_rag_planner.initialized", {})
                except Exception:  # pragma: no cover - event bus optional
                    logger.debug("event bus publish failed", exc_info=True)
        except Exception:
            self._status = HealthStatus.UNHEALTHY
            logger.exception("agentic_rag_planner module failed to initialize")
            raise

    async def health_check(self) -> HealthStatus:
        return self._status

    async def shutdown(self) -> None:
        self._status = HealthStatus.STOPPING
        logger.info("agentic_rag_planner module shutting down")

    def set_event_bus(self, event_bus: EventBus) -> None:
        self._event_bus = event_bus

    # ------------------------------------------------------------- facade
    def plan(self, query: str) -> RetrievalPlan:
        """Decide which retrieval tool(s) to use for a query and return a plan."""
        planner = self._planner or RagPlanner()
        result = planner.plan(query)
        if self._event_bus is not None:
            try:
                self._event_bus.publish(
                    "agentic_rag_planner.plan",
                    {"query": query, "strategy": result.strategy.value},
                )
            except Exception:  # pragma: no cover - event bus optional
                logger.debug("event bus publish failed", exc_info=True)
        return result

    def plan_multi(
        self, query: str, prior_result_counts: list[int] | None = None
    ) -> RetrievalPlan:
        """Produce an iterative/refined plan with agentic fallback steps."""
        planner = self._planner or RagPlanner()
        return planner.plan_multi(query, prior_result_counts)


def create_agentic_rag_planner_module(
    config: dict[str, Any] | None = None,
) -> AgenticRagPlannerModule:
    return AgenticRagPlannerModule(config=config or {})


__all__ = [
    "AgenticRagPlannerModule",
    "create_agentic_rag_planner_module",
    "RagPlanner",
    "QueryClassifier",
    "ClassificationResult",
    "RetrievalPlan",
    "RetrievalStep",
    "RetrievalTool",
    "RetrievalToolABC",
    "PlanExecutor",
    "InMemoryTool",
    "ToolKind",
    "VECTOR",
    "GRAPH",
    "HYBRID",
    "__version__",
]
