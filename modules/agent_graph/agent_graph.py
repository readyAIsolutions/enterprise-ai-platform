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
from typing import Any, Callable, Dict, List, Optional, Union

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
# ============================================================================
# Durable state-graph DSL (LangGraph-style) with SQLite checkpointing
# ----------------------------------------------------------------------------
# Extends the module with:
#   - StateGraph / DiGraphBuilder : add_node / add_edge / add_conditional_edge
#   - topological execution over a shared mutable state dict, max_steps guard
#   - SqliteCheckpointStore : durable, resumable per-node checkpoints
#   - resume(run_id) : replay from last checkpoint, skipping completed nodes
#   - supervisor fan-out : a supervisor node routes to subgraphs
#   - clear errors on missing node / edge / cycle
# ============================================================================

import json
import os
import sqlite3
import threading
import time
from pathlib import Path

__all__ += [
    "RoutingFn",
    "SqliteCheckpointStore",
    "StateGraphRun",
    "StateGraph",
    "DiGraphBuilder",
    "DEFAULT_DB_PATH",
]

# Type aliases for the DSL
RoutingFn = Callable[[State], Optional[str]]

# Default database location for durable checkpoints (relative to cwd).
DEFAULT_DB_PATH = os.path.join("data", "agent_graph_state.db")

_INITIAL_NODE = ""  # sentinel node name used for the seq-0 checkpoint


class SqliteCheckpointStore:
    """Durable, resumable checkpoint store backed by SQLite.

    Snapshots both the full state and each node's returned update after every
    node execution, keyed by ``run_id`` and an incrementing sequence number, so
    a partially-completed run can be replayed / resumed from its last
    checkpoint later — even across store re-open.

    Args:
        db_path: Optional SQLite database path. If ``None`` an in-memory
            database is used (ideal for tests). Defaults to ``data/``.
    """

    def __init__(self, db_path: Optional[Union[str, Path]] = None) -> None:
        self._db_path = db_path
        self._lock = threading.RLock()
        self._owns_conn = True
        if db_path is None:
            target = ":memory:"
        else:
            path = Path(db_path)
            parent = path.parent if str(path.parent) else Path(".")
            parent.mkdir(parents=True, exist_ok=True)
            target = str(path)
        self._conn = sqlite3.connect(target, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._create_schema()

    # -- schema -------------------------------------------------------------

    def _create_schema(self) -> None:
        with self._lock:
            cur = self._conn.cursor()
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS state_runs (
                    run_id          TEXT PRIMARY KEY,
                    graph_name      TEXT NOT NULL,
                    mode            TEXT NOT NULL,
                    start_node      TEXT,
                    status          TEXT NOT NULL,
                    completed_nodes TEXT NOT NULL,
                    created_at      REAL NOT NULL
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS state_checkpoints (
                    run_id      TEXT NOT NULL,
                    seq         INTEGER NOT NULL,
                    node        TEXT NOT NULL,
                    state_json  TEXT NOT NULL,
                    result_json TEXT,
                    PRIMARY KEY (run_id, seq)
                )
                """
            )
            self._conn.commit()

    # -- run lifecycle ------------------------------------------------------

    def create_run(
        self,
        run_id: str,
        graph_name: str,
        mode: str = "default",
        start_node: Optional[str] = None,
    ) -> None:
        """Register a new run row before the first checkpoint is written."""
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO state_runs "
                "(run_id, graph_name, mode, start_node, status, completed_nodes, created_at) "
                "VALUES (?, ?, ?, ?, 'running', ?, ?)",
                (run_id, graph_name, mode, start_node, "[]", time.time()),
            )
            self._conn.commit()

    def save_initial(self, run_id: str, state: State) -> None:
        """Persist the seq-0 (pre-execution) state snapshot."""
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO state_checkpoints "
                "(run_id, seq, node, state_json, result_json) VALUES (?, 0, ?, ?, NULL)",
                (run_id, _INITIAL_NODE, json.dumps(state)),
            )
            self._conn.commit()

    def save_step(
        self,
        run_id: str,
        seq: int,
        node: str,
        state: State,
        result: State,
    ) -> None:
        """Persist a completed node's state + result, appending to the path."""
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO state_checkpoints "
                "(run_id, seq, node, state_json, result_json) VALUES (?, ?, ?, ?, ?)",
                (run_id, seq, node, json.dumps(state), json.dumps(result)),
            )
            cur = self._conn.execute(
                "SELECT completed_nodes FROM state_runs WHERE run_id = ?",
                (run_id,),
            )
            row = cur.fetchone()
            completed = []
            if row is not None and row["completed_nodes"]:
                completed = json.loads(row["completed_nodes"])
            completed.append(node)
            self._conn.execute(
                "UPDATE state_runs SET completed_nodes = ? WHERE run_id = ?",
                (json.dumps(completed), run_id),
            )
            self._conn.commit()

    def mark_complete(self, run_id: str) -> None:
        """Mark a run as fully complete."""
        with self._lock:
            self._conn.execute(
                "UPDATE state_runs SET status = 'complete' WHERE run_id = ?",
                (run_id,),
            )
            self._conn.commit()

    # -- reads --------------------------------------------------------------

    def load(self, run_id: str) -> List[Dict[str, Any]]:
        """Return the ordered list of state snapshots (deep copies) for run."""
        frames = self.frames(run_id)
        return [copy.deepcopy(f["state"]) for f in frames]

    def frames(self, run_id: str) -> List[Dict[str, Any]]:
        """Return ordered ``{seq, node, state, result}`` frames for a run."""
        with self._lock:
            cur = self._conn.execute(
                "SELECT seq, node, state_json, result_json FROM state_checkpoints "
                "WHERE run_id = ? ORDER BY seq ASC",
                (run_id,),
            )
            out = []
            for row in cur.fetchall():
                out.append(
                    {
                        "seq": row["seq"],
                        "node": row["node"],
                        "state": json.loads(row["state_json"]),
                        "result": (
                            json.loads(row["result_json"])
                            if row["result_json"] is not None
                            else None
                        ),
                    }
                )
        return out

    def state_at(self, run_id: str) -> State:
        """Return the most recent state snapshot for ``run_id``."""
        frames = self.frames(run_id)
        if not frames:
            raise KeyError(f"No checkpoint for run_id {run_id!r}")
        return copy.deepcopy(frames[-1]["state"])

    def completed_nodes(self, run_id: str) -> List[str]:
        """Return the ordered list of node names completed so far."""
        with self._lock:
            cur = self._conn.execute(
                "SELECT completed_nodes FROM state_runs WHERE run_id = ?",
                (run_id,),
            )
            row = cur.fetchone()
        if row is None:
            raise KeyError(f"No run_id {run_id!r} in store")
        if not row["completed_nodes"]:
            return []
        return json.loads(row["completed_nodes"])

    def status(self, run_id: str) -> str:
        """Return the run status ('running' or 'complete')."""
        with self._lock:
            cur = self._conn.execute(
                "SELECT status FROM state_runs WHERE run_id = ?", (run_id,)
            )
            row = cur.fetchone()
        if row is None:
            raise KeyError(f"No run_id {run_id!r} in store")
        return row["status"]

    def has(self, run_id: str) -> bool:
        """True if any checkpoints exist for ``run_id``."""
        with self._lock:
            cur = self._conn.execute(
                "SELECT 1 FROM state_checkpoints WHERE run_id = ? LIMIT 1",
                (run_id,),
            )
            return cur.fetchone() is not None

    def list_runs(self) -> List[str]:
        """All persisted run ids (including incomplete / resumable)."""
        with self._lock:
            cur = self._conn.execute("SELECT run_id FROM state_runs ORDER BY created_at")
            return [row["run_id"] for row in cur.fetchall()]

    def clear(self) -> None:
        """Drop all persisted checkpoints."""
        with self._lock:
            self._conn.execute("DELETE FROM state_checkpoints")
            self._conn.execute("DELETE FROM state_runs")
            self._conn.commit()

    def close(self) -> None:
        """Close the underlying SQLite connection."""
        with self._lock:
            self._conn.close()

    def __len__(self) -> int:
        with self._lock:
            cur = self._conn.execute("SELECT COUNT(DISTINCT run_id) FROM state_runs")
            return int(cur.fetchone()[0])


@dataclass
class StateGraphRun:
    """Result of a :class:`StateGraph` execution or resume.

    Attributes:
        run_id: Checkpoint key for this run.
        final_state: State after execution.
        path: Nodes executed during this run segment.
        all_path: Cumulative node path (including segments resumed earlier).
        checkpoints: Ordered state snapshots written for this run.
        mode: Execution mode label.
        resumed: True when this run continued from a prior checkpoint.
        status: 'complete' or 'partial'.
    """

    run_id: str
    final_state: State = field(default_factory=dict)
    path: List[str] = field(default_factory=list)
    all_path: List[str] = field(default_factory=list)
    checkpoints: List[State] = field(default_factory=list)
    mode: str = "default"
    resumed: bool = False
    status: str = "complete"

    @property
    def length(self) -> int:
        """Nodes executed in this run segment."""
        return len(self.path)


class StateGraph:
    """Durable, resumable state-graph DSL (LangGraph-style).

    Build a directed graph of stateful nodes with static and conditional edges,
    execute it over a shared mutable state dict, and checkpoint every step to a
    SQLite store so a run can be resumed from its last checkpoint later.

    Edges::

        g.add_node("a", fn_a)
        g.add_node("b", fn_b)
        g.add_edge("a", "b")                 # static edge
        g.add_conditional_edge("b", router)  # router(state) -> next node name

    Args:
        name: Optional graph name tag for runs.
        checkpoint_store: Optional :class:`SqliteCheckpointStore`. A fresh one
            backed by ``db_path`` is created when omitted.
        db_path: SQLite path used to create a store when none is supplied.
            Defaults to ``data/``. Pass ``None`` for an in-memory store.
        start / end: START / END marker names.
        max_steps: Upper bound on executed nodes guarding against cycles.
    """

    def __init__(
        self,
        name: Optional[str] = None,
        checkpoint_store: Optional[SqliteCheckpointStore] = None,
        db_path: Optional[Union[str, Path]] = DEFAULT_DB_PATH,
        start: str = START,
        end: str = END,
        max_steps: int = 1000,
    ) -> None:
        self.name = name or "state_graph"
        self.start = start
        self.end = end
        self.max_steps = max_steps
        self.store = (
            checkpoint_store
            if checkpoint_store is not None
            else SqliteCheckpointStore(db_path=db_path)
        )
        self._nodes: Dict[str, GraphNode] = {}
        self._static: Dict[str, List[str]] = {}  # node -> list of static successors
        self._conditional: Dict[str, RoutingFn] = {}  # node -> routing fn
        self._order: List[str] = []  # declaration order
        self._supervisors: Dict[str, SupervisorSpec] = {}

    # -- build-time API -----------------------------------------------------

    @property
    def nodes(self) -> List[str]:
        return list(self._order)

    def add_node(self, name: str, fn: Optional[NodeFn] = None) -> "StateGraph":
        """Register a node; returns self for chaining."""
        if not isinstance(name, str) or not name.strip():
            raise ValueError("node name must be a non-empty string")
        if name == self.end:
            raise ValueError(f"node name {name!r} collides with the END marker")
        if name in self._nodes:
            raise ValueError(f"node already exists: {name!r}")
        self._nodes[name] = GraphNode(name=name, fn=fn)
        self._order.append(name)
        return self

    def add_edge(self, a: str, b: str) -> "StateGraph":
        """Connect ``a`` -> ``b`` with a static edge; returns self."""
        self._require_node(a, "add_edge source")
        if b != self.end:
            self._require_node(b, "add_edge target")
        if a in self._conditional:
            raise ValueError(
                f"node {a!r} already has a conditional edge; use one routing style"
            )
        self._static.setdefault(a, []).append(b)
        return self

    def add_conditional_edge(self, a: str, routing_fn: RoutingFn) -> "StateGraph":
        """Attach a routing function to ``a``; ``routing_fn(state) -> node name``.

        The router's return value names the next node to execute (may be the END
        marker or ``None`` to terminate). Returns self.
        """
        self._require_node(a, "add_conditional_edge source")
        if not callable(routing_fn):
            raise TypeError("routing_fn must be callable")
        if a in self._conditional:
            raise ValueError(f"node {a!r} already has a conditional edge")
        if a in self._static:
            raise ValueError(
                f"node {a!r} already has a static edge; use one routing style"
            )
        self._conditional[a] = routing_fn
        return self

    def add_supervisor(
        self,
        name: str,
        route_key: str,
        workers: Dict[Any, Union[NodeFn, "StateGraph"]],
        coordinator: Optional[NodeFn] = None,
    ) -> "StateGraph":
        """Add a supervisor node that fans out to one of ``workers``.

        The supervisor reads ``state[route_key]``, selects the matching worker
        (a callable or a sub-:class:`StateGraph`), executes it, and merges the
        result back into the shared state. Fanning out to a subgraph runs that
        subgraph inline and folds its final state into the parent. Returns self.
        """
        if not isinstance(route_key, str) or not route_key:
            raise ValueError("route_key must be a non-empty string")
        if not workers:
            raise ValueError("supervisor requires at least one worker")

        def _supervisor_fn(state: State) -> State:
            route = state.get(route_key)
            if route not in workers:
                raise KeyError(
                    f"supervisor {name!r}: no worker for {route_key}={route!r} "
                    f"(registered: {sorted(map(str, workers.keys()))})"
                )
            worker = workers[route]
            if isinstance(worker, StateGraph):
                # Fan out to a subgraph, folding its final state into parent.
                sub_run = worker.run(
                    copy.deepcopy(state),
                    run_id=f"{self.name}:{route}",
                )
                return dict(sub_run.final_state)
            return worker(state) or {}

        return self.add_node(name, _supervisor_fn)

    # -- error helpers ------------------------------------------------------

    def _require_node(self, name: str, ctx: str) -> None:
        if name in (self.start, self.end):
            return
        if name not in self._nodes:
            raise ValueError(f"{ctx}: undefined node {name!r}")

    def _entry_node(self) -> str:
        """Resolve the single execution entry node.

        Prefers an explicit START node, else a unique root with no incoming
        static edges. A node whose only outgoing edges are to END / none is a
        pure leaf and is ignored when it is the sole non-leaf root.
        """
        explicit = self.start if self.start in self._nodes else None
        if explicit is not None:
            return explicit
        incoming: set[str] = set()
        for dsts in self._static.values():
            for dst in dsts:
                if dst != self.end:
                    incoming.add(dst)
        roots = [n for n in self._order if n not in incoming]
        if len(roots) == 1:
            return roots[0]
        if len(roots) == 0:
            raise ValueError(
                "state graph has no entry point: every node has an incoming edge"
            )

        def is_source(n: str) -> bool:
            if n in self._conditional:
                return True
            return any(dst in self._nodes for dst in self._static.get(n, []))

        non_leaf = [n for n in roots if is_source(n)]
        if len(non_leaf) == 1:
            return non_leaf[0]
        raise ValueError(
            f"state graph has multiple entry points {roots}; "
            "define an explicit start node"
        )

    def _route(self, node: str, state: State) -> Optional[str]:
        """Determine the next node after ``node`` (None / END terminates)."""
        if node in self._conditional:
            nxt = self._conditional[node](state)
            if nxt is None:
                return None
            if not isinstance(nxt, str):
                raise TypeError(
                    f"routing_fn on {node!r} returned {type(nxt).__name__}, "
                    "expected a node name"
                )
            if nxt == self.end:
                return self.end
            if nxt not in self._nodes:
                raise ValueError(
                    f"routing_fn on {node!r} returned undefined node {nxt!r}"
                )
            return nxt
        dsts = self._static.get(node, [])
        if not dsts:
            return None
        if len(dsts) == 1:
            nxt = dsts[0]
            if nxt == self.end:
                return self.end
            if nxt not in self._nodes:
                raise ValueError(f"node {node!r} routes to undefined node {nxt!r}")
            return nxt
        # Multiple static successors = fan-out; the sequential engine can only
        # follow one path, so require an explicit conditional edge to route.
        raise ValueError(
            f"node {node!r} has {len(dsts)} static successors {dsts}; "
            "fan-out is not runnable sequentially — use a conditional edge to route"
        )

    # -- execution ----------------------------------------------------------

    def topological_order(self) -> List[str]:
        """Best-effort topological order over static edges (Kahn's algorithm).

        Conditional edges are excluded because their targets are only known at
        runtime; nodes that source a conditional edge are placed in declaration
        order after their static dependencies.
        """
        in_deg: Dict[str, int] = {n: 0 for n in self._order}
        adj: Dict[str, List[str]] = {n: [] for n in self._order}
        for src, dsts in self._static.items():
            for dst in dsts:
                if dst in self._nodes:
                    in_deg[dst] += 1
                    adj[src].append(dst)
        ready = [n for n in self._order if in_deg[n] == 0]
        ready.sort(key=self._order.index)
        result: List[str] = []
        while ready:
            node = ready.pop(0)
            result.append(node)
            for nxt in adj[node]:
                in_deg[nxt] -= 1
                if in_deg[nxt] == 0:
                    ready.append(nxt)
                    ready.sort(key=self._order.index)
        # Conditional sources that were not reachable via static edges are
        # appended in declaration order; a genuine static cycle leaves nodes
        # out of Kahn's result and is an error.
        if len(result) < len(self._order):
            remaining = [n for n in self._order if n not in result]
            raise ValueError(
                "state graph contains a static cycle "
                f"(nodes not topologically ordered: {remaining}); "
                "cannot compute topological order"
            )
        return result

    def run(
        self,
        initial_state: Optional[State] = None,
        run_id: Optional[str] = None,
        mode: str = "default",
        resume: bool = False,
    ) -> StateGraphRun:
        """Execute the graph against ``initial_state``, checkpointing each step.

        Args:
            initial_state: Starting state dict.
            run_id: Explicit checkpoint key (UUID4 if omitted).
            mode: Pass-through execution mode label.
            resume: If True and ``run_id`` already has checkpoints, resume from
                the last checkpoint instead of starting fresh.

        Returns:
            A :class:`StateGraphRun`.
        """
        run_id = run_id or str(uuid.uuid4())
        resumed = resume and self.store.has(run_id)

        if resumed:
            state = self.store.state_at(run_id)
            completed = self.store.completed_nodes(run_id)
            all_path = list(completed)
            if completed:
                last_done = completed[-1]
                current = self._route(last_done, state)
            else:
                current = self._entry_node()
        else:
            state = dict(initial_state or {})
            self.store.create_run(
                run_id, self.name, mode, start_node=self._entry_node()
            )
            self.store.save_initial(run_id, copy.deepcopy(state))
            current = self._entry_node()
            all_path = []

        path: List[str] = []
        checkpoints = self.store.load(run_id)
        seq = len(checkpoints) - 1  # next checkpoint sequence number
        steps = 0

        while current is not None and current != self.end:
            steps += 1
            if steps > self.max_steps:
                raise RuntimeError(
                    f"state graph run {run_id!r} exceeded max_steps={self.max_steps}; "
                    "aborting to prevent an unbounded cycle"
                )
            node = self._nodes[current]
            path.append(current)
            result = node(state) or {}
            if not isinstance(result, dict):
                raise TypeError(
                    f"node {current!r} returned {type(result).__name__}, expected dict"
                )
            state.update(result)
            seq += 1
            self.store.save_step(run_id, seq, current, copy.deepcopy(state), result)
            current = self._route(current, state)

        status = "complete"
        if self.store.status(run_id) != "complete":
            self.store.mark_complete(run_id)

        all_path = all_path + path
        return StateGraphRun(
            run_id=run_id,
            final_state=copy.deepcopy(state),
            path=list(path),
            all_path=list(all_path),
            checkpoints=self.store.load(run_id),
            mode=mode,
            resumed=resumed,
            status=status,
        )

    def resume(self, run_id: str) -> StateGraphRun:
        """Replay ``run_id`` from its last checkpoint, skipping completed nodes.

        Raises:
            KeyError: if no checkpoints exist for ``run_id``.
        """
        if not self.store.has(run_id):
            raise KeyError(f"No checkpoint for run_id {run_id!r}")
        return self.run(resume=True, run_id=run_id)


# Alias kept for ergonomic parity with the task wording.
DiGraphBuilder = StateGraph


@dataclass
class SupervisorSpec:
    """Internal spec describing a supervisor node's fan-out configuration."""

    name: str
    route_key: str
    workers: Dict[Any, Any]
    coordinator: Optional[NodeFn] = None
