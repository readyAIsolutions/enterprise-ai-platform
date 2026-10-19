"""``rag_strategy_router`` — intent-based VECTOR / GRAPH / HYBRID RAG router.

Grounded entirely in the real pulled transcript ``ColeMedin/p0FERNkpyHE.md``
("Introducing RAG 2.0: Agentic RAG + Knowledge Graphs (FREE Template)"). The
talk shows an agent that can "pick and choose how it explores the knowledge":
a **vector database** lookup for single-entity / broad-semantic fact questions
("what are the AI initiatives for Google"), a **knowledge-graph** traversal for
relational / multi-entity questions ("how are OpenAI and Microsoft related"),
or **both** when the query carries both intents / explicitly asks to "use both
search types".

This module is a ROUTER / DISPATCHER that classifies query intent and selects a
strategy — it is NOT itself a retriever and does not depend on the existing
``agentic_rag`` / ``knowledge_graph`` / ``rag`` / ``hybrid_kg_retrieval``
modules. Retrievers are injected by the caller.

Export surface:
  * Strategy                 — VECTOR / GRAPH / HYBRID enum.
  * RouteDecision            — strategy + confidence + matched_signals + rationale.
  * Signal                   — a single transcript-grounded routing signal.
  * QueryClassifier          — deterministic intent scorer.
  * StrategyRouter           — route / route_batch / dispatch + retriever registry.
  * RagStrategyRouterModule  — the ENI platform Module wrapper.
  * create_rag_strategy_router_module(config) — factory used by the platform.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Mapping, Optional, Sequence

from enterprise.platform_kernel import HealthStatus, Module, module

from .core import (  # noqa: F401
    QueryClassifier,
    RouteDecision,
    Signal,
    Strategy,
    StrategyRouter,
    all_strategies,
    create_router,
    default_signals,
)

logger = logging.getLogger("eni.rag_strategy_router")

__version__ = "1.0.0"


@module(
    name="rag_strategy_router",
    version="1.0.0",
    config_defaults={
        "hybrid_margin": 0.34,
        "default_strategy": "vector",
        "signal_weights": {},
    },
)
class RagStrategyRouterModule(Module):
    """ENI platform wrapper around the :class:`StrategyRouter`."""

    def __init__(self, config: Optional[dict[str, Any]] = None) -> None:
        super().__init__(config)
        self.router: Optional[StrategyRouter] = None
        self._event_bus: Any = None

    # ----------------------------------------------------------- lifecycle
    async def initialize(self) -> None:
        weights = dict(self._config.get("signal_weights", {}) or {})
        margin = float(self._config.get("hybrid_margin", 0.34))
        default_strategy = Strategy.from_value(
            self._config.get("default_strategy", "vector")
        )
        classifier = QueryClassifier(
            weights=weights,
            hybrid_margin=margin,
            default_strategy=default_strategy,
        )
        self.router = StrategyRouter(classifier=classifier)
        self._status = HealthStatus.HEALTHY
        logger.info("rag_strategy_router module initialized")

    async def health_check(self) -> HealthStatus:
        return (
            HealthStatus.HEALTHY
            if self.router is not None
            else HealthStatus.UNHEALTHY
        )

    async def shutdown(self) -> None:
        self.router = None
        self._status = HealthStatus.UNKNOWN

    def set_event_bus(self, event_bus: Any) -> None:
        self._event_bus = event_bus

    # --------------------------------------------------------------- facade
    def route(self, query: str) -> RouteDecision:
        """Classify a single query and return its :class:`RouteDecision`."""
        return self.router.route(query)

    def route_batch(self, queries: Sequence[str]) -> List[RouteDecision]:
        """Route a sequence of queries, preserving order."""
        return self.router.route_batch(queries)

    def dispatch(
        self,
        query: str,
        *,
        retrievers: Optional[Mapping[Any, Any]] = None,
    ) -> Dict[str, Any]:
        """Route ``query`` and invoke the retriever for the chosen strategy."""
        return self.router.dispatch(query, retrievers=retrievers)

    def register_retriever(self, strategy: Any, retriever: Any) -> None:
        """Register a callable retriever for a strategy on the router."""
        self.router.register_retriever(strategy, retriever)

    def strategies(self) -> List[Strategy]:
        """Return all supported strategies."""
        return all_strategies()


def create_rag_strategy_router_module(
    config: Optional[dict[str, Any]] = None,
) -> RagStrategyRouterModule:
    """Factory used by the platform to construct the module."""
    return RagStrategyRouterModule(config=config or {})


__all__ = [
    "Strategy",
    "RouteDecision",
    "Signal",
    "QueryClassifier",
    "StrategyRouter",
    "RagStrategyRouterModule",
    "create_rag_strategy_router_module",
    "create_router",
    "default_signals",
    "all_strategies",
    "__version__",
]
