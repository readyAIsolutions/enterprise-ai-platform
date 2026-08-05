"""ENI Agent Graph Module — langgraph-style stateful agent graph orchestration.

A dependency-free (stdlib-only) engine for building and running directed
graphs of stateful agent nodes, with checkpoint persistence for replay and
inspection.

Features:
- ``add_node`` / ``add_edge`` build-time validation (undefined node targets
  raise ``ValueError``).
- ``run`` walks the graph in topological order, honoring conditional edges,
  with START/END markers and cycle/back-edge protection via ``max_steps``.
- :class:`StateCheckpointStore` persists intermediate states keyed by
  ``run_id``.
- :class:`SupervisorGraph` — a coordinator node that routes to worker nodes
  based on a state key.
- :class:`AgentGraphFacade` — public surface: ``build_graph``, ``add_node``,
  ``add_edge``, ``run_graph``, ``get_checkpoint``, ``list_runs``.

Version: 1.0.0
Python: 3.11+
"""

from __future__ import annotations

import logging
import threading
from typing import Any, Dict, List, Optional

from enterprise.platform_kernel import (
    Event,
    EventBus,
    EventPriority,
    HealthStatus,
    Module,
    module,
)

from .agent_graph import (
    START,
    END,
    AgentGraph,
    AgentGraphFacade,
    GraphEdge,
    GraphNode,
    GraphRun,
    StateCheckpointStore,
    SupervisorGraph,
)

__version__ = "1.0.0"
__module__ = "agent_graph"

__all__ = [
    "__version__",
    "AgentGraphModule",
    # Core framework
    "AgentGraph",
    "AgentGraphFacade",
    "GraphNode",
    "GraphEdge",
    "GraphRun",
    "StateCheckpointStore",
    "SupervisorGraph",
    "START",
    "END",
]

_logger = logging.getLogger("enterprise.agent_graph")


@module(name="agent_graph", version="1.0.0")
class AgentGraphModule(Module):
    """Enterprise Agent Graph Module — stateful agent graph orchestration.

    Wraps an :class:`AgentGraphFacade` (and its shared
    :class:`StateCheckpointStore`) behind the Platform Kernel module lifecycle,
    and exposes a small public surface for building and running graphs,
    querying checkpoints and listing persisted runs.

    Configuration (dict passed to ``__init__``):
        max_steps (int): Cycle-protection bound applied to graphs built by
            this module (default 1000).

    Events published (when an event bus is wired via ``set_event_bus``):
        - agent_graph.run.completed — a graph run finished.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(config)
        self._facade: AgentGraphFacade | None = None
        self._event_bus: EventBus | None = None
        self._lock = threading.RLock()
        self._max_steps: int = int(self._config.get("max_steps", 1000) or 1000)

    # -- Properties ---------------------------------------------------------

    @property
    def facade(self) -> AgentGraphFacade | None:
        """Return the active facade (None before initialization)."""
        with self._lock:
            return self._facade

    @property
    def max_steps(self) -> int:
        """Configured cycle-protection bound."""
        return self._max_steps

    # -- Lifecycle ----------------------------------------------------------

    async def initialize(self) -> None:
        """Build the facade and its shared checkpoint store."""
        with self._lock:
            self._status = HealthStatus.STARTING

        _logger.info("Agent graph initializing (max_steps=%s)", self._max_steps)
        try:
            facade = AgentGraphFacade()
            graph = facade.build_graph(max_steps=self._max_steps)
            with self._lock:
                self._facade = facade
                self._graph = graph
                self._status = HealthStatus.HEALTHY
            _logger.info("Agent graph initialized")
        except Exception as exc:  # noqa: BLE001 - lifecycle must report UNHEALTHY
            _logger.exception("Failed to initialize agent_graph: %s", exc)
            with self._lock:
                self._status = HealthStatus.UNHEALTHY
            raise

    async def health_check(self) -> HealthStatus:
        """A healthy facade is built and ready to run graphs."""
        with self._lock:
            if self._facade is not None and self._status is HealthStatus.HEALTHY:
                return HealthStatus.HEALTHY
            if self._status is HealthStatus.UNHEALTHY:
                return HealthStatus.UNHEALTHY
            self._status = HealthStatus.UNKNOWN
            return self._status

    async def shutdown(self) -> None:
        """Gracefully shut down the module, clearing persisted checkpoints."""
        with self._lock:
            self._status = HealthStatus.STOPPING
            _logger.info("Shutting down agent_graph module...")
            if self._facade is not None:
                self._facade.clear()
            self._facade = None
            self._graph = None
            self._status = HealthStatus.HEALTHY

    # -- Event Bus Wiring ---------------------------------------------------

    def set_event_bus(self, event_bus: EventBus) -> None:
        """Wire the platform EventBus into this module.

        Called by the Platform Kernel after module discovery but before
        ``initialize()``. If an event bus is already active it is replaced
        gracefully.
        """
        with self._lock:
            self._event_bus = event_bus

    # -- Public facade ------------------------------------------------------

    def build_graph(self, start: str = START, end: str = END) -> AgentGraph:
        """Create (or replace) the active graph bound to this module's store."""
        return self._require_facade().build_graph(
            start=start, end=end, max_steps=self._max_steps
        )

    def add_node(self, name: str, fn: Any = None) -> GraphNode:
        """Add a node to the active graph."""
        return self._require_facade().add_node(name, fn)

    def add_edge(
        self,
        from_node: str,
        to_node: str,
        condition: Any = None,
    ) -> GraphEdge:
        """Add an edge to the active graph."""
        return self._require_facade().add_edge(from_node, to_node, condition=condition)

    def run_graph(
        self,
        initial_state: Optional[Dict[str, Any]] = None,
        mode: str = "default",
        run_id: Optional[str] = None,
    ) -> GraphRun:
        """Run the active graph, emit a completion event, and return the run."""
        facade = self._require_facade()
        run = facade.run_graph(initial_state, mode=mode, run_id=run_id)
        self._emit(
            "agent_graph.run.completed",
            {"run_id": run.run_id, "nodes": run.length, "mode": run.mode},
        )
        return run

    def get_checkpoint(self, run_id: str) -> List[Dict[str, Any]]:
        """Return persisted state history for ``run_id``."""
        return self._require_facade().get_checkpoint(run_id)

    def list_runs(self) -> List[str]:
        """Return all persisted run ids."""
        return self._require_facade().list_runs()

    # -- Helpers ------------------------------------------------------------

    def _require_facade(self) -> AgentGraphFacade:
        facade = self.facade
        if facade is None:
            raise RuntimeError("agent_graph module is not initialized")
        return facade

    def _emit(self, topic: str, payload: Dict[str, Any]) -> None:
        """Publish an event on the wired bus (no-op if none is set)."""
        with self._lock:
            bus = self._event_bus
        if bus is None:
            return
        try:
            bus.publish(
                Event.create(
                    topic,
                    source=self.name,
                    payload=payload,
                    priority=EventPriority.NORMAL,
                )
            )
        except Exception as exc:  # noqa: BLE001 - defensive
            _logger.warning("Failed to publish event %s: %s", topic, exc)
