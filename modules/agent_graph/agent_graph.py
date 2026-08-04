"""ENI Agent Graph Module — langgraph-style stateful agent graph engine.

A dependency-free (stdlib-only) orchestration engine for building and running
directed graphs of agent nodes. Each node is a plain callable that receives a
mutable ``dict`` state and returns an updated ``dict``; edges may carry a
conditional predicate so the execution path is chosen at runtime.

Features:
- :class:`GraphNode` — a named callable ``(state: dict) -> dict``.
- :class:`GraphEdge` — a directed ``from -> to`` link with optional condition.
- :class:`AgentGraph` — ``add_node`` / ``add_edge`` with validation (an edge
  referencing an undefined node raises ``ValueError``) and a ``run`` method
  that walks the graph in topological order honoring conditional edges, with
  START/END markers and cycle/back-edge protection via ``max_steps``.
- :class:`StateCheckpointStore` — in-memory persistence of intermediate states
  keyed by ``run_id``.
- :class:`GraphRun` — result object carrying ``run_id``, ``final_state``,
  ``path`` (visited nodes) and ``checkpoints`` (intermediate states).
- :class:`SupervisorGraph` — a coordinator node that routes to worker nodes
  based on a state key.

All components are stdlib-only (``copy``, ``dataclasses``, ``uuid``).

Version: 1.0.0
Python: 3.11+
"""

from __future__ import annotations

import copy
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

__all__ = [
    "START",
    "END",
    "GraphNode",
    "GraphEdge",
    "AgentGraph",
    "StateCheckpointStore",
    "GraphRun",
    "SupervisorGraph",
    "AgentGraphFacade",
]

# Reserved pseudo-node names (langgraph-style markers). START is an optional
# explicit entry point; END is an optional explicit terminal marker.
START = "__start__"
END = "__end__"

# Type aliases
State = Dict[str, Any]
NodeFn = Callable[[State], Optional[State]]
ConditionFn = Callable[[State], bool]


@dataclass
class GraphNode:
    """A single named node in an agent graph.

    Attributes:
        name: Unique name of the node.
        fn: Callable invoked with the current state dict; must return a dict
            (or None to leave state unchanged).
    """

    name: str
    fn: Optional[NodeFn] = None

    def __call__(self, state: State) -> State:
        """Invoke this node against ``state``, merging its returned update."""
        if self.fn is None:
            return {}
        result = self.fn(state)
        if result is None:
            return {}
        if not isinstance(result, dict):
            raise TypeError(
                f"node {self.name!r} returned {type(result).__name__}, expected dict"
            )
        return result


@dataclass
class GraphEdge:
    """A directed edge between nodes, optionally gated by a predicate.

    Attributes:
        from_node: Source node name.
        to_node: Target node name (may be the END marker).
        condition: Optional predicate ``(state) -> bool``. When present the
            edge is only traversable when the predicate evaluates to True.
    """

    from_node: str
    to_node: str
    condition: Optional[ConditionFn] = None

    def __repr__(self) -> str:
        tag = "" if self.condition is None else " (conditional)"
        return f"<GraphEdge {self.from_node} -> {self.to_node}{tag}>"


@dataclass
class GraphRun:
    """Result object produced by :meth:`AgentGraph.run`.

    Attributes:
        run_id: Unique identifier for this run, used as the checkpoint key.
        final_state: The final state dict after the run.
        path: Ordered list of visited node names.
        checkpoints: List of intermediate states, including the initial state
            followed by the state after each executed node.
        mode: Execution mode string passed through from ``run`` (default
            ``"default"``).
    """

    run_id: str
    final_state: State = field(default_factory=dict)
    path: List[str] = field(default_factory=list)
    checkpoints: List[State] = field(default_factory=list)
    mode: str = "default"

    @property
    def length(self) -> int:
        """Number of nodes executed in this run."""
        return len(self.path)

    def checkpoint_at(self, index: int) -> State:
        """Return a deep copy of the checkpoint at ``index``."""
        return copy.deepcopy(self.checkpoints[index])


class StateCheckpointStore:
    """In-memory store of intermediate states keyed by ``run_id``.

    Persists an ordered list of state snapshots per run so a graph execution
    can be replayed or inspected after completion.

    Attributes:
        _runs: mapping of ``run_id`` -> list of deep-copied states.
    """

    def __init__(self) -> None:
        self._runs: Dict[str, List[State]] = {}

    def save(self, run_id: str, state: State) -> None:
        """Append a deep copy of ``state`` to the history for ``run_id``."""
        self._runs.setdefault(run_id, []).append(copy.deepcopy(state))

    def load(self, run_id: str) -> List[State]:
        """Return the ordered list of states for ``run_id``.

        Raises:
            KeyError: if no run with ``run_id`` exists.
        """
        if run_id not in self._runs:
            raise KeyError(f"No checkpoint for run_id {run_id!r}")
        return [copy.deepcopy(s) for s in self._runs[run_id]]

    def latest(self, run_id: str) -> State:
        """Return the most recent state snapshot for ``run_id`` (deep copy)."""
        history = self.load(run_id)
        return copy.deepcopy(history[-1])

    def has(self, run_id: str) -> bool:
        """Return True if any checkpoints exist for ``run_id``."""
        return run_id in self._runs

    def list_runs(self) -> List[str]:
        """Return all ``run_id`` keys in insertion order."""
        return list(self._runs.keys())

    def clear(self) -> None:
        """Drop all persisted checkpoints."""
        self._runs.clear()

    def __len__(self) -> int:
        return len(self._runs)


class AgentGraph:
    """A stateful, directed graph of agent nodes executable in topological
    order while honoring conditional edges.

    Args:
        start: Optional explicit START marker/entry node name.
        end: Optional explicit END marker/terminal node name.
        store: Optional :class:`StateCheckpointStore`; a fresh one is created
            if omitted.
        max_steps: Upper bound on executed nodes per run, guarding against
            unbounded cycles / back-edges.
    """

    def __init__(
        self,
        start: str = START,
        end: str = END,
        store: Optional[StateCheckpointStore] = None,
        max_steps: int = 1000,
    ) -> None:
        self.start = start
        self.end = end
        self.store = store if store is not None else StateCheckpointStore()
        self.max_steps = max_steps
        self._nodes: Dict[str, GraphNode] = {}
        self._edges: List[GraphEdge] = []
        self._out: Dict[str, List[GraphEdge]] = defaultdict(list)

    # -- Build time API -----------------------------------------------------

    @property
    def nodes(self) -> List[str]:
        """Names of all defined nodes in insertion order."""
        return list(self._nodes.keys())

    @property
    def edges(self) -> List[GraphEdge]:
        """All defined edges."""
        return list(self._edges)

    def add_node(self, name: str, fn: Optional[NodeFn] = None) -> GraphNode:
        """Register a node.

        Args:
            name: Unique node name (non-empty string).
            fn: Callable ``(state: dict) -> dict | None``.

        Returns:
            The created :class:`GraphNode`.

        Raises:
            ValueError: if the name is empty or already in use.
        """
        if not isinstance(name, str) or not name.strip():
            raise ValueError("node name must be a non-empty string")
        if name in self._nodes:
            raise ValueError(f"node already exists: {name!r}")
        node = GraphNode(name=name, fn=fn)
        self._nodes[name] = node
        return node

    def add_edge(
        self,
        from_node: str,
        to_node: str,
        condition: Optional[ConditionFn] = None,
    ) -> GraphEdge:
        """Connect ``from_node`` to ``to_node``, optionally gated by a predicate.

        Args:
            from_node: Source node name.
            to_node: Target node name (may be the END marker).
            condition: Optional predicate ``(state) -> bool``.

        Returns:
            The created :class:`GraphEdge`.

        Raises:
            ValueError: if either end references an undefined node (an
                explicit START/END marker is always permitted).
        """
        if from_node != self.start and from_node not in self._nodes:
            raise ValueError(f"undefined source node for edge: {from_node!r}")
        if to_node != self.end and to_node not in self._nodes:
            raise ValueError(f"undefined target node for edge: {to_node!r}")
        if condition is not None and not callable(condition):
            raise TypeError("edge condition must be callable or None")
        edge = GraphEdge(
            from_node=from_node, to_node=to_node, condition=condition
        )
        self._edges.append(edge)
        self._out[from_node].append(edge)
        return edge

    # -- Execution ----------------------------------------------------------

    def run(
        self,
        initial_state: Optional[State] = None,
        mode: str = "default",
        run_id: Optional[str] = None,
    ) -> GraphRun:
        """Execute the graph from its entry point against ``initial_state``.

        The state is copied before execution (the caller's dict is never
        mutated). Intermediate states are deep-copied into the checkpoint
        store under ``run_id`` and collected in the returned :class:`GraphRun`.

        Args:
            initial_state: Starting state dict.
            mode: Pass-through execution mode label.
            run_id: Optional explicit id; a UUID4 is generated if omitted.

        Returns:
            A :class:`GraphRun` describing the execution.

        Raises:
            ValueError: if the graph has no resolvable entry point.
            RuntimeError: if ``max_steps`` is exceeded (cycle protection).
        """
        run_id = run_id or str(uuid.uuid4())
        state = dict(initial_state or {})
        checkpoints: List[State] = [copy.deepcopy(state)]
        self.store.save(run_id, copy.deepcopy(state))

        path: List[str] = []
        current = self._entry_node()
        steps = 0

        while current is not None and current != self.end:
            steps += 1
            if steps > self.max_steps:
                raise RuntimeError(
                    f"run {run_id!r} exceeded max_steps={self.max_steps}; "
                    "aborting to prevent an unbounded cycle"
                )
            node = self._nodes[current]
            path.append(current)
            update = node(state)
            if update:
                state.update(update)
            checkpoints.append(copy.deepcopy(state))
            self.store.save(run_id, copy.deepcopy(state))
            current = self._next_node(current, state)

        return GraphRun(
            run_id=run_id,
            final_state=copy.deepcopy(state),
            path=list(path),
            checkpoints=checkpoints,
            mode=mode,
        )

    def _entry_node(self) -> Optional[str]:
        """Resolve the execution entry point.

        An explicit START marker/node wins if present; otherwise a single node
        with no incoming edges (or explicitly targeted by a START-marker edge)
        is used. No/ambiguous roots raise.
        """
        if self.start in self._nodes:
            return self.start

        incoming: set[str] = set()
        start_targets: set[str] = set()
        for edge in self._edges:
            if edge.to_node in (self.start, self.end):
                continue
            if edge.from_node == self.start:
                # An edge originating from the START marker designates entry.
                start_targets.add(edge.to_node)
            elif edge.from_node in self._nodes:
                incoming.add(edge.to_node)

        seeded = bool(start_targets)
        roots: List[str] = []
        for node_name in self._nodes:
            if node_name in start_targets:
                roots.append(node_name)
            elif not seeded and node_name not in incoming:
                roots.append(node_name)

        if len(roots) == 1:
            return roots[0]
        if len(roots) == 0:
            raise ValueError("graph has no entry point: no START node and no source node")
        raise ValueError(
            "graph has multiple entry points; define an explicit START node"
        )

    def _next_node(self, node: str, state: State) -> Optional[str]:
        """Choose the next node after executing ``node``.

        Unconditional edges are always candidates; conditional edges are only
        candidates when their predicate is True for the current ``state``. If
        multiple candidates remain the first (in definition order) is chosen.
        Returns None when there is no reachable successor (terminal).
        """
        candidates: List[str] = []
        for edge in self._out.get(node, []):
            if edge.condition is None:
                candidates.append(edge.to_node)
            else:
                matched = edge.condition(state)
                if not isinstance(matched, bool) and matched is not None:
                    raise TypeError(
                        f"condition on {edge.from_node!r} -> {edge.to_node!r} "
                        "must return a bool"
                    )
                if matched:
                    candidates.append(edge.to_node)
        # Deduplicate preserving definition order.
        seen: List[str] = []
        for candidate in candidates:
            if candidate not in seen:
                seen.append(candidate)
        return seen[0] if seen else None


class SupervisorGraph:
    """Coordinator/worker pattern helper.

    A coordinator node inspects ``state[self.route_key]`` and the execution is
    routed to exactly one registered worker. Each worker is a terminal (no
    further routing after it completes).

    Args:
        route_key: State key examined to pick a worker.
        start: START marker.
        end: END marker.
        coordinator: Optional coordinator callable. Defaults to a pass-through
            that leaves the state unchanged.
    """

    def __init__(
        self,
        route_key: str = "task",
        start: str = START,
        end: str = END,
        coordinator: Optional[NodeFn] = None,
    ) -> None:
        self.route_key = route_key
        self.graph = AgentGraph(start=start, end=end)
        self._workers: Dict[str, NodeFn] = {}
        self._routes: Dict[str, Any] = {}
        self._coordinator = coordinator
        if self._coordinator is None:
            self._coordinator = lambda state: {}  # pass-through
        self.graph.add_node("coordinator", self._coordinator)
        self.graph.add_edge(start, "coordinator")

    def add_worker(
        self,
        name: str,
        fn: NodeFn,
        route: Optional[Any] = None,
    ) -> str:
        """Register a worker node.

        Args:
            name: Unique worker node name.
            fn: Worker callable ``(state) -> dict``.
            route: Value of ``state[route_key]`` that selects this worker; if
                omitted the worker ``name`` itself is used as the route value.

        Returns:
            The worker name (for chaining).
        """
        if name in self._workers:
            raise ValueError(f"worker already exists: {name!r}")
        route_value = route if route is not None else name
        self._workers[name] = fn
        self._routes[name] = route_value
        self.graph.add_node(name, fn)
        self.graph.add_edge(
            "coordinator",
            name,
            condition=self._route_condition(route_value),
        )
        # A worker is terminal.
        self.graph.add_edge(name, self.graph.end)
        return name

    def _route_condition(self, route_value: Any) -> ConditionFn:
        key = self.route_key

        def _cond(state: State) -> bool:
            return state.get(key, state.get("_route")) == route_value

        return _cond

    # -- Convenience --------------------------------------------------------

    @property
    def workers(self) -> List[str]:
        """Registered worker names."""
        return list(self._workers.keys())

    def run(
        self,
        initial_state: Optional[State] = None,
        **kwargs: Any,
    ) -> GraphRun:
        """Run the supervisor graph (delegates to :meth:`AgentGraph.run`)."""
        return self.graph.run(initial_state, **kwargs)


class AgentGraphFacade:
    """Public facade for building and running agent graphs.

    Owns a single :class:`StateCheckpointStore` shared by every graph it
    builds, so checkpoints remain queryable via ``get_checkpoint`` /
    ``list_runs`` regardless of which graph executed the run.

    Usage::

        facade = AgentGraphFacade()
        g = facade.build_graph()
        g.add_node("a", lambda s: {"x": s.get("x", 0) + 1})
        g.add_edge("a", g.end)
        run = facade.run_graph({"x": 0})
    """

    def __init__(self) -> None:
        self._store = StateCheckpointStore()
        self._graph: Optional[AgentGraph] = None

    # -- Shape the graph ----------------------------------------------------

    @property
    def graph(self) -> Optional[AgentGraph]:
        """The currently built graph (None until ``build_graph`` is called)."""
        return self._graph

    def build_graph(
        self,
        start: str = START,
        end: str = END,
        max_steps: int = 1000,
    ) -> AgentGraph:
        """Create (or replace) the active graph bound to this facade's store."""
        self._graph = AgentGraph(
            start=start, end=end, store=self._store, max_steps=max_steps
        )
        return self._graph

    def add_node(self, name: str, fn: Optional[NodeFn] = None) -> GraphNode:
        """Add a node to the active graph."""
        return self._require_graph().add_node(name, fn)

    def add_edge(
        self,
        from_node: str,
        to_node: str,
        condition: Optional[ConditionFn] = None,
    ) -> GraphEdge:
        """Add an edge to the active graph."""
        return self._require_graph().add_edge(from_node, to_node, condition=condition)

    # -- Execute / inspect --------------------------------------------------

    def run_graph(
        self,
        initial_state: Optional[State] = None,
        mode: str = "default",
        run_id: Optional[str] = None,
    ) -> GraphRun:
        """Run the active graph and return its :class:`GraphRun`."""
        return self._require_graph().run(initial_state, mode=mode, run_id=run_id)

    def get_checkpoint(self, run_id: str) -> List[State]:
        """Return the persisted state history for ``run_id``.

        Raises:
            KeyError: if no such run exists.
        """
        return self._store.load(run_id)

    def list_runs(self) -> List[str]:
        """Return all run ids persisted by this facade's store."""
        return self._store.list_runs()

    def clear(self) -> None:
        """Clear all persisted checkpoints."""
        self._store.clear()

    def _require_graph(self) -> AgentGraph:
        if self._graph is None:
            raise RuntimeError("agent_graph facade has no graph; call build_graph() first")
        return self._graph
