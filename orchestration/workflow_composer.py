"""
Workflow Composer: Declarative DAG-Based Workflow Builder and Execution Engine.

Supports sequential, parallel, conditional, and fan-out execution patterns.
Built around a directed acyclic graph (DAG) model where nodes are tasks
and edges represent data/control dependencies. Includes validation,
execution tracing, retry policies, and timeout handling.

Key capabilities:
  - Declarative workflow definition via a fluent builder API
  - DAG-based topological execution with cycle detection
  - Sequential, parallel, conditional (branch/merge), and fan-out patterns
  - Execution context propagation through the graph
  - Retry policies per-node with backoff
  - Timeout enforcement
  - Execution tracing and audit history
"""

from __future__ import annotations

import asyncio
import enum
import heapq
import logging
import threading
import time
import uuid
from collections import defaultdict, deque
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from dataclasses import dataclass, field
from typing import (
    Any, Callable, Dict, Generic, Iterable, List, Optional,
    Set, Tuple, TypeVar, Union,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class WorkflowError(Exception):
    """Base exception for workflow-related errors."""
    pass


class CycleDetectedError(WorkflowError):
    """Raised when a cycle is detected in the workflow DAG."""

    def __init__(self, cycle: List[str]):
        self.cycle = cycle
        super().__init__(f"Cycle detected in workflow: {' -> '.join(cycle)}")


class NodeNotFoundError(WorkflowError):
    """Raised when referencing a node that does not exist."""

    def __init__(self, node_id: str):
        self.node_id = node_id
        super().__init__(f"Node not found: {node_id}")


class WorkflowExecutionError(WorkflowError):
    """Raised when a workflow execution fails."""

    def __init__(self, message: str, node_id: Optional[str] = None,
                 errors: Optional[Dict[str, Exception]] = None):
        self.node_id = node_id
        self.errors = errors or {}
        super().__init__(message)


class NodeTimeoutError(WorkflowError):
    """Raised when a node execution exceeds its timeout."""

    def __init__(self, node_id: str, timeout_seconds: float):
        self.node_id = node_id
        self.timeout_seconds = timeout_seconds
        super().__init__(f"Node '{node_id}' timed out after {timeout_seconds}s")


# ---------------------------------------------------------------------------
# Enums and Constants
# ---------------------------------------------------------------------------

class ExecutionMode(enum.Enum):
    """How a node or group of nodes executes."""
    SEQUENTIAL = "sequential"
    PARALLEL = "parallel"
    CONDITIONAL = "conditional"
    FAN_OUT = "fan_out"
    FAN_IN = "fan_in"


class NodeState(enum.Enum):
    """Possible states of a workflow node during execution."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    TIMED_OUT = "timed_out"


class ExecutionPolicy(enum.Enum):
    """How the workflow handles node failures."""
    FAIL_FAST = "fail_fast"       # stop all execution on first failure
    CONTINUE = "continue"         # continue independent branches
    FAIL_AT_END = "fail_at_end"   # complete all possible, fail at end


# ---------------------------------------------------------------------------
# Data Models
# ---------------------------------------------------------------------------

T = TypeVar("T")
ContextT = TypeVar("ContextT", bound=Dict[str, Any])


@dataclass
class RetryPolicy:
    """Defines retry behavior for a workflow node.

    Attributes:
        max_retries: Maximum number of retry attempts.
        backoff_base: Base seconds for exponential backoff.
        backoff_factor: Multiplier for exponential backoff.
        max_backoff: Cap on backoff delay.
        retryable_exceptions: Exception types that trigger a retry.
    """
    max_retries: int = 0
    backoff_base: float = 1.0
    backoff_factor: float = 2.0
    max_backoff: float = 60.0
    retryable_exceptions: Tuple[type, ...] = (Exception,)

    def delay(self, attempt: int) -> float:
        """Compute backoff delay for a given retry attempt (0-indexed)."""
        return min(self.backoff_base * (self.backoff_factor ** attempt),
                   self.max_backoff)


@dataclass
class NodeResult:
    """Captures the result of executing a single workflow node.

    Attributes:
        node_id: The node identifier.
        state: Final execution state.
        output: The node's output value (None if failed/skipped).
        error: Exception information if the node failed.
        started_at: Monotonic timestamp of start.
        finished_at: Monotonic timestamp of completion.
        retries: Number of retry attempts taken.
    """
    node_id: str
    state: NodeState
    output: Any = None
    error: Optional[Exception] = None
    started_at: float = 0.0
    finished_at: float = 0.0
    retries: int = 0

    @property
    def duration_ms(self) -> float:
        return (self.finished_at - self.started_at) * 1000.0

    @property
    def success(self) -> bool:
        return self.state == NodeState.COMPLETED


@dataclass
class WorkflowResult:
    """Aggregate result for an entire workflow execution.

    Attributes:
        workflow_id: Unique identifier for the execution run.
        node_results: Map of node_id -> NodeResult.
        started_at: Monotonic start timestamp.
        finished_at: Monotonic finish timestamp.
        success: Whether the workflow completed without failures.
        errors: Map of node_id -> exception for failed nodes.
    """
    workflow_id: str
    node_results: Dict[str, NodeResult] = field(default_factory=dict)
    started_at: float = 0.0
    finished_at: float = 0.0
    success: bool = True
    errors: Dict[str, Exception] = field(default_factory=dict)

    @property
    def duration_ms(self) -> float:
        return (self.finished_at - self.started_at) * 1000.0


# ---------------------------------------------------------------------------
# Graph / DAG Structures
# ---------------------------------------------------------------------------

@dataclass
class Edge:
    """A directed edge between two nodes in the workflow DAG.

    Attributes:
        source: Source node id.
        target: Target node id.
        data_key: Optional key mapping for data flow from source output
                  into target input context.
        condition: Optional callable predicate; edge only traversed when True.
    """
    source: str
    target: str
    data_key: Optional[str] = None
    condition: Optional[Callable[[Dict[str, Any]], bool]] = None


# ---------------------------------------------------------------------------
# Workflow Node
# ---------------------------------------------------------------------------

class WorkflowNode:
    """A single node in the workflow DAG representing a unit of work.

    Each node has a unique id, an async/sync handler function, and metadata
    governing its execution behaviour (mode, timeout, retry policy).

    Handlers receive the shared execution *context* (a dict) and return
    a result that is stored back into the context under `node_id` unless
    ``output_key`` is specified.
    """

    __slots__ = (
        "node_id", "handler", "mode", "timeout", "retry_policy",
        "output_key", "depends_on", "metadata", "condition",
    )

    def __init__(
        self,
        node_id: str,
        handler: Callable[[Dict[str, Any]], Any],
        *,
        mode: ExecutionMode = ExecutionMode.SEQUENTIAL,
        timeout: Optional[float] = None,
        retry_policy: Optional[RetryPolicy] = None,
        output_key: Optional[str] = None,
        depends_on: Optional[List[str]] = None,
        condition: Optional[Callable[[Dict[str, Any]], bool]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        self.node_id = node_id
        self.handler = handler
        self.mode = mode
        self.timeout = timeout
        self.retry_policy = retry_policy or RetryPolicy()
        self.output_key = output_key or node_id
        self.depends_on = depends_on or []
        self.condition = condition
        self.metadata = metadata or {}

    def __repr__(self) -> str:
        return (f"WorkflowNode(id={self.node_id!r}, mode={self.mode.value}, "
                f"deps={self.depends_on})")


# ---------------------------------------------------------------------------
# Directed Acyclic Graph
# ---------------------------------------------------------------------------

class DAG:
    """A directed acyclic graph used to model workflow topology.

    Provides cycle detection, topological ordering, and dependency queries.
    """

    def __init__(self):
        # adjacency: node_id -> set of successors (downstream nodes)
        self._adj: Dict[str, Set[str]] = defaultdict(set)
        # reverse adjacency: node_id -> set of predecessors (upstream nodes)
        self._rev_adj: Dict[str, Set[str]] = defaultdict(set)
        self._nodes: Set[str] = set()

    def add_node(self, node_id: str) -> None:
        """Register a node in the graph (no-op if already present)."""
        if node_id not in self._nodes:
            self._nodes.add(node_id)
            self._adj.setdefault(node_id, set())
            self._rev_adj.setdefault(node_id, set())

    def add_edge(self, source: str, target: str) -> None:
        """Add a directed edge source -> target.

        Raises:
            NodeNotFoundError: If either node is not in the graph.
            CycleDetectedError: If adding this edge would create a cycle.
        """
        if source not in self._nodes:
            raise NodeNotFoundError(source)
        if target not in self._nodes:
            raise NodeNotFoundError(target)

        if target in self._adj[source]:
            return  # edge already exists

        self._adj[source].add(target)
        self._rev_adj[target].add(source)

        if self._has_cycle():
            self._adj[source].discard(target)
            self._rev_adj[target].discard(source)
            raise CycleDetectedError(self._detect_cycle())

    def predecessors(self, node_id: str) -> Set[str]:
        """Return the set of nodes that directly precede *node_id*."""
        return self._rev_adj.get(node_id, set()).copy()

    def successors(self, node_id: str) -> Set[str]:
        """Return the set of nodes that directly follow *node_id*."""
        return self._adj.get(node_id, set()).copy()

    def roots(self) -> Set[str]:
        """Nodes with no predecessors (entry points)."""
        return {n for n in self._nodes if not self._rev_adj.get(n)}

    def leaves(self) -> Set[str]:
        """Nodes with no successors (exit points)."""
        return {n for n in self._nodes if not self._adj.get(n)}

    def topological_order(self) -> List[str]:
        """Return a topological sort (Kahn's algorithm).

        Raises:
            CycleDetectedError: If the graph contains a cycle.
        """
        in_degree: Dict[str, int] = {
            n: len(self._rev_adj.get(n, set())) for n in self._nodes
        }
        queue: deque[str] = deque(
            n for n, deg in in_degree.items() if deg == 0
        )
        result: List[str] = []

        while queue:
            node = queue.popleft()
            result.append(node)
            for successor in self._adj.get(node, set()):
                in_degree[successor] -= 1
                if in_degree[successor] == 0:
                    queue.append(successor)

        if len(result) != len(self._nodes):
            raise CycleDetectedError(self._detect_cycle())

        return result

    def _has_cycle(self) -> bool:
        """True if the graph contains at least one cycle."""
        try:
            self.topological_order()
            return False
        except CycleDetectedError:
            return True

    def _detect_cycle(self) -> List[str]:
        """Return one cycle path using DFS."""
        WHITE, GRAY, BLACK = 0, 1, 2
        color: Dict[str, int] = {n: WHITE for n in self._nodes}
        parent: Dict[str, Optional[str]] = {}

        def dfs(node: str) -> Optional[List[str]]:
            color[node] = GRAY
            for neighbor in self._adj.get(node, set()):
                if color[neighbor] == GRAY:
                    # back edge -> cycle
                    path = [neighbor, node]
                    cur = node
                    while parent.get(cur) is not None and parent[cur] != neighbor:
                        cur = parent[cur]
                        path.append(cur)
                    path.append(neighbor)
                    path.reverse()
                    return path
                if color[neighbor] == WHITE:
                    parent[neighbor] = node
                    cycle = dfs(neighbor)
                    if cycle:
                        return cycle
            color[node] = BLACK
            return None

        for node in self._nodes:
            if color[node] == WHITE:
                cycle = dfs(node)
                if cycle:
                    return cycle
        return []

    def nodes(self) -> Set[str]:
        return self._nodes.copy()

    def __len__(self) -> int:
        return len(self._nodes)


# ---------------------------------------------------------------------------
# Fluent Workflow Builder
# ---------------------------------------------------------------------------

class WorkflowBuilder:
    """Fluent API for declaratively constructing a Workflow.

    Usage::

        wf = (WorkflowBuilder("data-pipeline")
              .node("extract", handler=extract_fn)
              .node("transform", handler=transform_fn, depends_on=["extract"])
              .node("load", handler=load_fn, depends_on=["transform"])
              .edge("extract", "transform")
              .edge("transform", "load")
              .build())
    """

    def __init__(self, name: str = "workflow"):
        self._name = name
        self._nodes: Dict[str, WorkflowNode] = {}
        self._edges: List[Edge] = []
        self._policy: ExecutionPolicy = ExecutionPolicy.FAIL_FAST

    def node(
        self,
        node_id: str,
        handler: Callable[[Dict[str, Any]], Any],
        *,
        mode: ExecutionMode = ExecutionMode.SEQUENTIAL,
        timeout: Optional[float] = None,
        retry_policy: Optional[RetryPolicy] = None,
        output_key: Optional[str] = None,
        depends_on: Optional[List[str]] = None,
        condition: Optional[Callable[[Dict[str, Any]], bool]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> "WorkflowBuilder":
        """Declare a node in the workflow."""
        self._nodes[node_id] = WorkflowNode(
            node_id=node_id,
            handler=handler,
            mode=mode,
            timeout=timeout,
            retry_policy=retry_policy,
            output_key=output_key,
            depends_on=depends_on,
            condition=condition,
            metadata=metadata,
        )
        return self

    def edge(
        self,
        source: str,
        target: str,
        *,
        data_key: Optional[str] = None,
        condition: Optional[Callable[[Dict[str, Any]], bool]] = None,
    ) -> "WorkflowBuilder":
        """Add a directed edge between two nodes."""
        self._edges.append(Edge(source=source, target=target,
                                data_key=data_key, condition=condition))
        return self

    def fan_out(
        self,
        source: str,
        targets: List[str],
        **edge_kwargs: Any,
    ) -> "WorkflowBuilder":
        """Create edges from *source* to every node in *targets* (fan-out)."""
        for target in targets:
            self.edge(source, target, **edge_kwargs)
        return self

    def fan_in(
        self,
        sources: List[str],
        target: str,
        **edge_kwargs: Any,
    ) -> "WorkflowBuilder":
        """Create edges from every node in *sources* to *target* (fan-in)."""
        for source in sources:
            self.edge(source, target, **edge_kwargs)
        return self

    def sequential(
        self,
        *node_ids: str,
        handler_factory: Optional[Callable[[str], Callable]] = None,
        **node_kwargs: Any,
    ) -> "WorkflowBuilder":
        """Declare a sequence of nodes chained one after another.

        If *handler_factory* is given it is called with each node_id to
        produce the handler; otherwise nodes must already be registered.
        """
        ids = list(node_ids)
        for i, nid in enumerate(ids):
            if handler_factory:
                self.node(nid, handler_factory(nid), **node_kwargs)
            if i > 0:
                self.edge(ids[i - 1], nid)
        return self

    def parallel(
        self,
        *node_ids: str,
        join_on: Optional[str] = None,
        handler_factory: Optional[Callable[[str], Callable]] = None,
        **node_kwargs: Any,
    ) -> "WorkflowBuilder":
        """Declare a set of nodes that run in parallel.

        If *join_on* is provided, a synthetic join node is created that
        depends on all parallel nodes (fan-in pattern).
        """
        ids = list(node_ids)
        for nid in ids:
            if handler_factory:
                self.node(nid, handler_factory(nid),
                          mode=ExecutionMode.PARALLEL, **node_kwargs)
        if join_on:
            # Join node just passes context through by default
            self.node(join_on, lambda ctx: ctx, mode=ExecutionMode.FAN_IN)
            self.fan_in(ids, join_on)
        return self

    def conditional(
        self,
        node_id: str,
        condition: Callable[[Dict[str, Any]], bool],
        true_handler: Callable[[Dict[str, Any]], Any],
        false_handler: Optional[Callable[[Dict[str, Any]], Any]] = None,
        *,
        true_node_id: Optional[str] = None,
        false_node_id: Optional[str] = None,
        **node_kwargs: Any,
    ) -> "WorkflowBuilder":
        """Declare a conditional branch.

        Evaluates *condition* on the context; runs *true_handler* if True,
        *false_handler* (if provided) otherwise.
        """
        true_id = true_node_id or f"{node_id}_true"
        false_id = false_node_id or f"{node_id}_false"

        self.node(node_id, lambda ctx: ctx, mode=ExecutionMode.CONDITIONAL,
                  **node_kwargs)
        self.node(true_id, true_handler)
        self.node(false_id, false_handler or (lambda ctx: None))
        self.edge(node_id, true_id, condition=lambda ctx: condition(ctx))
        self.edge(node_id, false_id, condition=lambda ctx: not condition(ctx))
        return self

    def with_policy(self, policy: ExecutionPolicy) -> "WorkflowBuilder":
        """Set the execution failure policy."""
        self._policy = policy
        return self

    def build(self) -> "Workflow":
        """Construct and validate the final Workflow."""
        # Auto-add nodes referenced in edges but not declared
        all_node_ids = set(self._nodes.keys())
        for edge in self._edges:
            all_node_ids.add(edge.source)
            all_node_ids.add(edge.target)

        return Workflow(
            name=self._name,
            nodes=self._nodes,
            edges=self._edges,
            policy=self._policy,
        )


# ---------------------------------------------------------------------------
# Workflow
# ---------------------------------------------------------------------------

class Workflow:
    """An executable DAG-based workflow.

    Instantiated via :class:`WorkflowBuilder` and executed with
    :meth:`execute` (sync) or :meth:`execute_async` (async).
    """

    def __init__(
        self,
        name: str,
        nodes: Dict[str, WorkflowNode],
        edges: List[Edge],
        policy: ExecutionPolicy = ExecutionPolicy.FAIL_FAST,
    ):
        self.name = name
        self.nodes = nodes
        self.edges = edges
        self.policy = policy
        self._dag = DAG()
        self._edge_map: Dict[str, List[Edge]] = defaultdict(list)
        self._build_dag()

    # ---- DAG construction & validation ----

    def _build_dag(self) -> None:
        """Reify nodes and edges into the internal DAG."""
        for nid in self.nodes:
            self._dag.add_node(nid)

        for edge in self.edges:
            self._dag.add_node(edge.source)
            self._dag.add_node(edge.target)
            self._dag.add_edge(edge.source, edge.target)
            self._edge_map[edge.source].append(edge)

        # Ensure nodes referenced only via edges exist as no-op stubs
        for nid in self._dag.nodes():
            if nid not in self.nodes:
                self.nodes[nid] = WorkflowNode(
                    node_id=nid, handler=lambda ctx: ctx
                )

    def validate(self) -> List[str]:
        """Validate the workflow and return a list of issues (empty = valid)."""
        issues: List[str] = []

        # Check for cycles (topological order handles this)
        try:
            self._dag.topological_order()
        except CycleDetectedError as e:
            issues.append(str(e))

        # Check all dependencies are satisfied
        for nid, node in self.nodes.items():
            for dep in node.depends_on:
                if dep not in self.nodes:
                    issues.append(f"Node '{nid}' depends on unknown node '{dep}'")
                elif dep not in self._dag.predecessors(nid):
                    issues.append(
                        f"Node '{nid}' declares dependency on '{dep}' "
                        f"but no edge {dep} -> {nid} exists"
                    )

        # Check for disconnected subgraphs
        roots = self._dag.roots()
        if len(roots) > 1 and len(self.nodes) > 2:
            issues.append(
                f"Multiple root nodes detected: {roots}. "
                f"Ensure they share a common entry point or are intentional."
            )

        return issues

    def topological_order(self) -> List[str]:
        """Return nodes in topological execution order."""
        return self._dag.topological_order()

    # ---- Execution ----

    def execute(
        self,
        initial_context: Optional[Dict[str, Any]] = None,
        *,
        max_workers: int = 8,
    ) -> WorkflowResult:
        """Execute synchronously using a thread pool.

        Args:
            initial_context: Initial key-value context shared across nodes.
            max_workers: Maximum number of threads for parallel execution.

        Returns:
            WorkflowResult with per-node outcomes and aggregate status.
        """
        return asyncio.run(self.execute_async(initial_context,
                                               max_workers=max_workers))

    async def execute_async(
        self,
        initial_context: Optional[Dict[str, Any]] = None,
        *,
        max_workers: int = 8,
    ) -> WorkflowResult:
        """Execute asynchronously.

        Nodes are scheduled based on topological readiness: a node starts
        once all its upstream dependencies have completed successfully
        (or been skipped).
        """
        issues = self.validate()
        if issues:
            raise WorkflowExecutionError(
                f"Workflow validation failed: {'; '.join(issues)}"
            )

        context: Dict[str, Any] = dict(initial_context or {})
        workflow_id = uuid.uuid4().hex[:12]
        result = WorkflowResult(workflow_id=workflow_id)
        result.started_at = time.monotonic()

        node_results: Dict[str, NodeResult] = {}
        in_degree: Dict[str, int] = {
            nid: len(self._dag.predecessors(nid))
            for nid in self._dag.nodes()
        }
        ready: asyncio.Queue[str] = asyncio.Queue()
        for nid, deg in in_degree.items():
            if deg == 0:
                await ready.put(nid)

        completed_count = 0
        total_nodes = len(self._dag.nodes())
        lock = asyncio.Lock()
        loop = asyncio.get_running_loop()
        executor = ThreadPoolExecutor(max_workers=max_workers)

        async def run_node(nid: str) -> None:
            nonlocal completed_count
            node = self.nodes.get(nid)
            if node is None:
                return

            # Check conditional edges — if all incoming conditional edges
            # evaluate to False, skip the node
            predecessors = self._dag.predecessors(nid)
            if predecessors:
                should_skip = True
                for pred in predecessors:
                    for edge in self._edge_map.get(pred, []):
                        if edge.target == nid and edge.condition:
                            if edge.condition(context):
                                should_skip = False
                                break
                        elif edge.target == nid and not edge.condition:
                            # unconditional edge means run
                            should_skip = False
                            break
                    if not should_skip:
                        break
                if should_skip:
                    nr = NodeResult(node_id=nid, state=NodeState.SKIPPED,
                                    started_at=time.monotonic(),
                                    finished_at=time.monotonic())
                    async with lock:
                        node_results[nid] = nr
                        completed_count += 1
                    await _enqueue_successors(nid)
                    return

            # Check node-level condition
            if node.condition and not node.condition(context):
                nr = NodeResult(node_id=nid, state=NodeState.SKIPPED,
                                started_at=time.monotonic(),
                                finished_at=time.monotonic())
                async with lock:
                    node_results[nid] = nr
                    completed_count += 1
                await _enqueue_successors(nid)
                return

            # Execute with retry
            nr = await _execute_with_retry(node, context, loop, executor)
            async with lock:
                node_results[nid] = nr
                if nr.success:
                    context[node.output_key] = nr.output
                else:
                    result.errors[nid] = nr.error or Exception("unknown error")
                    if self.policy == ExecutionPolicy.FAIL_FAST:
                        result.success = False
                completed_count += 1

            if nr.success or self.policy != ExecutionPolicy.FAIL_FAST:
                await _enqueue_successors(nid)

        async def _enqueue_successors(nid: str) -> None:
            for succ in self._dag.successors(nid):
                async with lock:
                    in_degree[succ] -= 1
                    if in_degree[succ] == 0:
                        await ready.put(succ)

        async def _execute_with_retry(
            node: WorkflowNode,
            ctx: Dict[str, Any],
            event_loop: asyncio.AbstractEventLoop,
            thread_pool: ThreadPoolExecutor,
        ) -> NodeResult:
            start = time.monotonic()
            last_error: Optional[Exception] = None
            retries = 0

            for attempt in range(node.retry_policy.max_retries + 1):
                try:
                    output = await _call_handler(
                        node, node.handler, ctx, node.timeout, event_loop, thread_pool
                    )
                    return NodeResult(
                        node_id=node.node_id,
                        state=NodeState.COMPLETED,
                        output=output,
                        started_at=start,
                        finished_at=time.monotonic(),
                        retries=retries,
                    )
                except NodeTimeoutError:
                    return NodeResult(
                        node_id=node.node_id,
                        state=NodeState.TIMED_OUT,
                        error=NodeTimeoutError(node.node_id, node.timeout or 0),
                        started_at=start,
                        finished_at=time.monotonic(),
                        retries=retries,
                    )
                except Exception as exc:
                    if not isinstance(exc, node.retry_policy.retryable_exceptions):
                        return NodeResult(
                            node_id=node.node_id,
                            state=NodeState.FAILED,
                            error=exc,
                            started_at=start,
                            finished_at=time.monotonic(),
                            retries=retries,
                        )
                    last_error = exc
                    if attempt < node.retry_policy.max_retries:
                        retries += 1
                        delay = node.retry_policy.delay(attempt)
                        logger.warning(
                            "Node %s attempt %d failed: %s. Retrying in %.1fs",
                            node.node_id, attempt + 1, exc, delay,
                        )
                        await asyncio.sleep(delay)

            return NodeResult(
                node_id=node.node_id,
                state=NodeState.FAILED,
                error=last_error,
                started_at=start,
                finished_at=time.monotonic(),
                retries=retries,
            )

        async def _call_handler(
            node: WorkflowNode,
            handler: Callable,
            ctx: Dict[str, Any],
            timeout: Optional[float],
            event_loop: asyncio.AbstractEventLoop,
            thread_pool: ThreadPoolExecutor,
        ) -> Any:
            if asyncio.iscoroutinefunction(handler):
                coro = handler(ctx)
                if timeout:
                    return await asyncio.wait_for(coro, timeout=timeout)
                return await coro
            else:
                future = event_loop.run_in_executor(thread_pool, handler, ctx)
                if timeout:
                    try:
                        return await asyncio.wait_for(future, timeout=timeout)
                    except asyncio.TimeoutError:
                        raise NodeTimeoutError(node.node_id, timeout) from None
                return await future

        # ---- Main execution loop ----
        try:
            while completed_count < total_nodes:
                try:
                    nid = await asyncio.wait_for(ready.get(), timeout=0.1)
                except asyncio.TimeoutError:
                    # Check if we are deadlocked (fail_fast + errors)
                    if self.policy == ExecutionPolicy.FAIL_FAST and result.errors:
                        break
                    continue

                asyncio.create_task(run_node(nid))
        finally:
            executor.shutdown(wait=False)

        # Allow running tasks to settle
        await asyncio.sleep(0.05)

        result.node_results = node_results
        result.finished_at = time.monotonic()
        result.success = len(result.errors) == 0
        return result

    # ---- Introspection ----

    def dump_graph(self) -> str:
        """Return a Mermaid-compatible diagram description."""
        lines = ["graph TD"]
        for nid in self._dag.nodes():
            node = self.nodes.get(nid)
            mode = node.mode.value if node else "seq"
            label = f"{nid}[{mode}]"
            lines.append(f"    {nid}{label}")
        for edge in self.edges:
            cond = "|cond|" if edge.condition else ""
            lines.append(f"    {edge.source} -->{cond} {edge.target}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Prebuilt Pattern Factories
# ---------------------------------------------------------------------------

def sequential_pipeline(
    name: str,
    stages: List[Tuple[str, Callable[[Dict[str, Any]], Any]]],
    **kwargs: Any,
) -> Workflow:
    """Factory: create a simple linear pipeline."""
    builder = WorkflowBuilder(name)
    for i, (nid, handler) in enumerate(stages):
        deps = [stages[i - 1][0]] if i > 0 else None
        builder.node(nid, handler, depends_on=deps, **kwargs)
        if i > 0:
            builder.edge(stages[i - 1][0], nid)
    return builder.build()


def parallel_fanout(
    name: str,
    source_id: str,
    source_handler: Callable[[Dict[str, Any]], Any],
    workers: List[Tuple[str, Callable[[Dict[str, Any]], Any]]],
    collector_id: str = "collect",
    collector_handler: Optional[Callable[[Dict[str, Any]], Any]] = None,
    **kwargs: Any,
) -> Workflow:
    """Factory: fan-out from source to parallel workers then fan-in to collector."""
    builder = WorkflowBuilder(name)
    builder.node(source_id, source_handler)
    worker_ids = []
    for wid, whandler in workers:
        builder.node(wid, whandler, mode=ExecutionMode.PARALLEL, **kwargs)
        worker_ids.append(wid)
    builder.node(
        collector_id,
        collector_handler or (lambda ctx: ctx),
        mode=ExecutionMode.FAN_IN,
    )
    builder.fan_out(source_id, worker_ids)
    builder.fan_in(worker_ids, collector_id)
    return builder.build()


def conditional_branch(
    name: str,
    condition: Callable[[Dict[str, Any]], bool],
    true_handler: Callable[[Dict[str, Any]], Any],
    false_handler: Callable[[Dict[str, Any]], Any],
    after_handler: Optional[Callable[[Dict[str, Any]], Any]] = None,
) -> Workflow:
    """Factory: if/else branching with optional post-branch join."""
    builder = WorkflowBuilder(name)
    builder.conditional(
        "branch", condition, true_handler, false_handler,
        true_node_id="true_branch", false_node_id="false_branch",
    )
    if after_handler:
        builder.node("after", after_handler)
        builder.fan_in(["true_branch", "false_branch"], "after")
    return builder.build()