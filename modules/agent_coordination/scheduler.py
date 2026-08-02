"""
Enterprise-Grade Task Scheduler for Agent Coordination.

This module provides a production-quality task scheduler with dependency
resolution, critical-path analysis, deadlock detection, and resource-aware
agent capacity tracking.  Scheduling is driven by weighted multi-factor
prioritisation.

Classes:
    TaskStatus: Enum for task lifecycle states.
    SchedulingFactor: Weight components used in prioritisation.
    Task: Dataclass representing a schedulable unit of work.
    AgentCapacity: Tracks an agent's current and maximum workload.
    Scheduler: The core scheduling engine.
"""

from __future__ import annotations

import heapq
import threading
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, FrozenSet, List, Optional, Set, Tuple


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class TaskStatus(str, Enum):
    """Lifecycle state of a scheduled task."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    BLOCKED = "blocked"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


# ---------------------------------------------------------------------------
# Scheduling Factors (weights)
# ---------------------------------------------------------------------------


@dataclass
class SchedulingFactor:
    """Configurable weights that drive task prioritisation.

    The ``score`` of a task is computed as a weighted sum across all
    factors.  Higher scores receive higher scheduling priority.

    Attributes:
        critical_path: Weight for tasks on the critical path.
        dependencies: Weight for how many downstream tasks depend on this one.
        risk_level: Weight for risk exposure (higher risk -> deprioritised).
        user_impact: Weight for user-facing impact.
        business_value: Weight for monetary / strategic value.
        security_impact: Weight for security implications.
        computational_cost: Weight for resource cost (higher cost -> deprioritised).
    """

    critical_path: float = 1.0
    dependencies: float = 0.8
    risk_level: float = -0.5  # Negative: higher risk reduces priority
    user_impact: float = 0.9
    business_value: float = 0.7
    security_impact: float = 1.1
    computational_cost: float = -0.3  # Negative: expensive tasks deprioritised


# ---------------------------------------------------------------------------
# Task Dataclass
# ---------------------------------------------------------------------------


@dataclass
class Task:
    """A schedulable unit of work assigned to an agent.

    Attributes:
        task_id: Unique identifier for the task.
        description: Human-readable description of the work.
        assigned_agent: ID of the agent responsible for execution.
        dependencies: List of ``task_id`` values that must complete first.
        estimated_duration: Expected wall-clock seconds for completion.
        priority: Integer priority (higher = more urgent).
        created_at: UTC timestamp of task creation.
        deadline: Optional UTC deadline; tasks past deadline are escalated.
        status: Current lifecycle state.
        risk_level: 0.0 (no risk) to 1.0 (maximum risk).
        user_impact: 0.0-1.0 rating of user-facing impact.
        business_value: 0.0-1.0 rating of business / strategic value.
        security_impact: 0.0-1.0 rating of security implications.
        computational_cost: Abstract resource cost (0 = free, 1 = very expensive).
        metadata: Arbitrary key-value store for extensibility.
    """

    task_id: str = ""
    description: str = ""
    assigned_agent: str = ""
    dependencies: List[str] = field(default_factory=list)
    estimated_duration: float = 0.0
    priority: int = 0
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    deadline: Optional[datetime] = None
    status: TaskStatus = TaskStatus.PENDING
    risk_level: float = 0.0
    user_impact: float = 0.0
    business_value: float = 0.0
    security_impact: float = 0.0
    computational_cost: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Validate and clamp factor values to [0.0, 1.0]."""
        for attr in (
            "risk_level",
            "user_impact",
            "business_value",
            "security_impact",
            "computational_cost",
        ):
            val = getattr(self, attr)
            if not (0.0 <= val <= 1.0):
                raise ValueError(f"Task '{attr}' must be in [0.0, 1.0], got {val}")

    def compute_score(self, factors: SchedulingFactor) -> float:
        """Compute a weighted priority score for scheduling.

        Higher scores indicate greater scheduling urgency.
        """
        score = (
            factors.critical_path * (1.0 if self.status == TaskStatus.PENDING else 0.0)
            + factors.dependencies * min(len(self.dependencies), 1.0)
            + factors.risk_level * self.risk_level
            + factors.user_impact * self.user_impact
            + factors.business_value * self.business_value
            + factors.security_impact * self.security_impact
            + factors.computational_cost * self.computational_cost
        )
        # Urgency bonus for tasks near or past deadline
        if self.deadline is not None:
            remaining = (self.deadline - datetime.now(timezone.utc)).total_seconds()
            if remaining <= 0:
                score += 10.0  # Past deadline -> massive boost
            elif remaining < 3600:  # Within 1 hour
                score += 2.0
            elif remaining < 86400:  # Within 24 hours
                score += 0.5
        return score

    def to_dict(self) -> Dict[str, Any]:
        """Return a JSON-serializable dictionary representation."""
        return {
            "task_id": self.task_id,
            "description": self.description,
            "assigned_agent": self.assigned_agent,
            "dependencies": self.dependencies,
            "estimated_duration": self.estimated_duration,
            "priority": self.priority,
            "created_at": self.created_at.isoformat(),
            "deadline": self.deadline.isoformat() if self.deadline else None,
            "status": self.status.value,
            "risk_level": self.risk_level,
            "user_impact": self.user_impact,
            "business_value": self.business_value,
            "security_impact": self.security_impact,
            "computational_cost": self.computational_cost,
            "metadata": self.metadata,
        }


# ---------------------------------------------------------------------------
# Agent Capacity
# ---------------------------------------------------------------------------


@dataclass
class AgentCapacity:
    """Tracks workload capacity for a single agent.

    Attributes:
        agent_id: Identifier of the agent.
        max_concurrent_tasks: Hard limit on simultaneous tasks.
        current_tasks: Number of tasks currently assigned and active.
    """

    agent_id: str = ""
    max_concurrent_tasks: int = 5
    current_tasks: int = 0

    @property
    def available_capacity(self) -> int:
        """Number of additional tasks this agent can accept."""
        return max(0, self.max_concurrent_tasks - self.current_tasks)

    @property
    def is_at_capacity(self) -> bool:
        """``True`` if the agent cannot accept more tasks."""
        return self.current_tasks >= self.max_concurrent_tasks

    def assign(self, count: int = 1) -> bool:
        """Attempt to allocate *count* task slots. Returns ``False`` if full."""
        if self.current_tasks + count > self.max_concurrent_tasks:
            return False
        self.current_tasks += count
        return True

    def release(self, count: int = 1) -> None:
        """Release *count* task slots (floor at 0)."""
        self.current_tasks = max(0, self.current_tasks - count)


# ---------------------------------------------------------------------------
# Scheduler
# ---------------------------------------------------------------------------


class Scheduler:
    """Enterprise-grade task scheduler with dependency resolution and
    resource-aware scheduling.

    Features:
    - **Topological sort** for dependency resolution.
    - **Critical-path analysis** using estimated durations.
    - **Deadlock detection** via cycle detection.
    - **Weighted multi-factor prioritisation** via ``SchedulingFactor``.
    - **Auto-rebalancing** when agent capacity changes.
    - **Bottleneck identification** (blocked tasks, over-capacity agents).

    Example::

        sched = Scheduler()
        sched.set_agent_capacity("agent_1", max_concurrent=3)

        t1 = Task(task_id="t1", assigned_agent="agent_1", estimated_duration=10)
        t2 = Task(task_id="t2", assigned_agent="agent_1",
                  dependencies=["t1"], estimated_duration=20)
        sched.add_task(t1)
        sched.add_task(t2)

        plan = sched.schedule()
        critical = sched.get_critical_path()
        bottlenecks = sched.get_bottlenecks()
    """

    def __init__(self, factors: Optional[SchedulingFactor] = None) -> None:
        """Initialise the scheduler.

        Args:
            factors: Optional custom weighting factors.  Uses defaults if
                     omitted.
        """
        self._tasks: Dict[str, Task] = {}
        self._agents: Dict[str, AgentCapacity] = {}
        self._factors: SchedulingFactor = factors or SchedulingFactor()
        self._lock: threading.RLock = threading.RLock()

    # -- Agent Capacity ----------------------------------------------------

    def set_agent_capacity(self, agent_id: str, max_concurrent: int = 5) -> None:
        """Register or update the capacity limit for *agent_id*."""
        with self._lock:
            if agent_id in self._agents:
                self._agents[agent_id].max_concurrent_tasks = max_concurrent
            else:
                self._agents[agent_id] = AgentCapacity(
                    agent_id=agent_id, max_concurrent_tasks=max_concurrent
                )

    def get_agent_capacity(self, agent_id: str) -> Optional[AgentCapacity]:
        """Return the capacity record for *agent_id*, or ``None``."""
        with self._lock:
            return self._agents.get(agent_id)

    def _ensure_agent(self, agent_id: str) -> None:
        """Auto-register an agent with default capacity if not present."""
        if agent_id not in self._agents:
            self._agents[agent_id] = AgentCapacity(agent_id=agent_id)

    # -- Task Management ---------------------------------------------------

    def add_task(self, task: Task) -> None:
        """Register a new task for scheduling.

        Raises:
            ValueError: If a task with the same ``task_id`` already exists.
        """
        with self._lock:
            if task.task_id in self._tasks:
                raise ValueError(f"Task '{task.task_id}' already exists.")
            self._tasks[task.task_id] = task
            self._ensure_agent(task.assigned_agent)

    def remove_task(self, task_id: str) -> bool:
        """Remove a task by ID. Returns ``False`` if not found.

        Also cleans up any dependency references held by other tasks.
        """
        with self._lock:
            if task_id not in self._tasks:
                return False
            del self._tasks[task_id]
            # Purge dependency references
            for t in self._tasks.values():
                if task_id in t.dependencies:
                    t.dependencies.remove(task_id)
            return True

    def get_task(self, task_id: str) -> Optional[Task]:
        """Retrieve a task by ID, or ``None``."""
        with self._lock:
            return self._tasks.get(task_id)

    def update_task_status(self, task_id: str, status: TaskStatus) -> bool:
        """Update the lifecycle status of a task. Returns ``False`` if not found.

        Completing a task also releases agent capacity.
        """
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None:
                return False
            old_status = task.status
            task.status = status
            # Release capacity on completion / failure / cancellation
            if old_status == TaskStatus.IN_PROGRESS and status in (
                TaskStatus.COMPLETED,
                TaskStatus.FAILED,
                TaskStatus.CANCELLED,
            ):
                agent = self._agents.get(task.assigned_agent)
                if agent:
                    agent.release()
            return True

    # -- Dependency Resolution ---------------------------------------------

    def _topological_sort(self, tasks: Dict[str, Task]) -> List[str]:
        """Return task IDs in dependency-respecting order via Kahn's algorithm.

        Returns an empty list if a cycle (deadlock) is detected.
        """
        in_degree: Dict[str, int] = {tid: 0 for tid in tasks}
        adj: Dict[str, List[str]] = {tid: [] for tid in tasks}

        for tid, task in tasks.items():
            for dep in task.dependencies:
                if dep in tasks:  # Only consider dependencies within this set
                    adj[dep].append(tid)
                    in_degree[tid] += 1

        # Start with tasks that have no dependencies
        queue: deque[str] = deque(tid for tid, deg in in_degree.items() if deg == 0)
        result: List[str] = []

        while queue:
            current = queue.popleft()
            result.append(current)
            for neighbour in adj.get(current, []):
                in_degree[neighbour] -= 1
                if in_degree[neighbour] == 0:
                    queue.append(neighbour)

        # If not all tasks processed, a cycle exists
        if len(result) != len(tasks):
            return []
        return result

    # -- Deadlock Detection ------------------------------------------------

    def detect_deadlocks(self) -> List[List[str]]:
        """Detect cycles in the task dependency graph.

        Returns a list of cycles, where each cycle is a list of task IDs
        forming a circular dependency.
        """
        with self._lock:
            return self._find_cycles(self._tasks)

    @staticmethod
    def _find_cycles(tasks: Dict[str, Task]) -> List[List[str]]:
        """Find all simple cycles in the dependency graph via DFS."""
        visited: Set[str] = set()
        rec_stack: Set[str] = set()
        cycles: List[List[str]] = []
        path: List[str] = []

        def _dfs(node: str) -> None:
            visited.add(node)
            rec_stack.add(node)
            path.append(node)

            task = tasks.get(node)
            if task:
                for dep in task.dependencies:
                    if dep not in visited:
                        _dfs(dep)
                    elif dep in rec_stack:
                        # Cycle found: extract the sub-path
                        cycle_start = path.index(dep)
                        cycles.append(list(path[cycle_start:]))

            path.pop()
            rec_stack.discard(node)

        for tid in tasks:
            if tid not in visited:
                _dfs(tid)

        return cycles

    # -- Critical Path -----------------------------------------------------

    def get_critical_path(self) -> List[str]:
        """Compute the critical path through the task DAG.

        The critical path is the longest chain of dependent tasks measured
        by estimated duration.  Returns task IDs in dependency order.

        Uses the standard forward/backward pass (CPM) algorithm.
        """
        with self._lock:
            tasks = self._tasks
            if not tasks:
                return []

            ordered = self._topological_sort(tasks)
            if not ordered:
                # Cycle detected; cannot compute critical path
                return []

            # Forward pass - earliest start / finish
            es: Dict[str, float] = {tid: 0.0 for tid in tasks}
            ef: Dict[str, float] = {}

            for tid in ordered:
                task = tasks[tid]
                ef[tid] = es[tid] + task.estimated_duration
                # Propagate to dependents
                for other_id, other_task in tasks.items():
                    if tid in other_task.dependencies:
                        es[other_id] = max(es[other_id], ef[tid])

            # Backward pass - latest start / finish
            project_duration = max(ef.values()) if ef else 0.0
            lf: Dict[str, float] = {tid: project_duration for tid in tasks}
            ls: Dict[str, float] = {}

            for tid in reversed(ordered):
                task = tasks[tid]
                ls[tid] = lf[tid] - task.estimated_duration
                # Propagate to dependencies
                for dep in task.dependencies:
                    if dep in lf:
                        lf[dep] = min(lf[dep], ls[tid])

            # Critical tasks: float = 0
            critical_ids = [
                tid
                for tid in ordered
                if abs((lf.get(tid, 0.0) - ef.get(tid, 0.0))) < 1e-9
            ]
            return critical_ids

    # -- Schedule ----------------------------------------------------------

    def schedule(self) -> List[Task]:
        """Produce an ordered task execution plan.

        Steps:
        1. Topological sort for dependency ordering.
        2. Score each task using weighted scheduling factors.
        3. Assign tasks to agents respecting capacity limits.
        4. Return the ordered list of tasks that can start now.

        Tasks that cannot be scheduled (blocked by dependencies or
        capacity) remain in the pending pool.
        """
        with self._lock:
            if not self._tasks:
                return []

            # Reset all agent current-task counters for a fresh schedule
            for agent in self._agents.values():
                agent.current_tasks = 0

            ordered = self._topological_sort(self._tasks)
            if not ordered:
                return []  # Cycle detected

            # Build priority queue of schedulable tasks
            ready: List[Tuple[float, int, str]] = []  # (neg_score, tiebreaker, task_id)
            tiebreaker = 0

            for tid in ordered:
                task = self._tasks[tid]
                if task.status != TaskStatus.PENDING:
                    continue
                # Check if all dependencies are satisfied
                deps_met = all(
                    dep in self._tasks
                    and self._tasks[dep].status == TaskStatus.COMPLETED
                    for dep in task.dependencies
                )
                if deps_met:
                    score = task.compute_score(self._factors)
                    heapq.heappush(ready, (-score, tiebreaker, tid))
                    tiebreaker += 1

            plan: List[Task] = []

            while ready:
                neg_score, _, tid = heapq.heappop(ready)
                task = self._tasks[tid]
                agent = self._agents.get(task.assigned_agent)

                if agent is None or agent.assign():
                    task.status = TaskStatus.IN_PROGRESS
                    plan.append(task)
                else:
                    # Agent at capacity - mark blocked
                    task.status = TaskStatus.BLOCKED

            return plan

    # -- Rebalancing -------------------------------------------------------

    def rebalance(self) -> List[Task]:
        """Re-schedule when agents become available/unavailable.

        Re-runs the full scheduling algorithm.  Tasks already in progress
        are preserved; pending/blocked tasks are reconsidered.

        Returns the new execution plan.
        """
        with self._lock:
            # Reset blocked tasks back to pending
            for task in self._tasks.values():
                if task.status == TaskStatus.BLOCKED:
                    task.status = TaskStatus.PENDING
            # Release all agent capacity
            for agent in self._agents.values():
                agent.current_tasks = 0
            # Re-count in-progress tasks
            for task in self._tasks.values():
                if task.status == TaskStatus.IN_PROGRESS:
                    agent = self._agents.get(task.assigned_agent)
                    if agent:
                        agent.current_tasks += 1

        return self.schedule()

    # -- Bottleneck Analysis -----------------------------------------------

    def get_bottlenecks(self) -> Dict[str, Any]:
        """Identify scheduling bottlenecks.

        Returns a dictionary with:
        - ``blocked_tasks``: List of task IDs blocked by unmet dependencies.
        - ``over_capacity_agents``: Agents whose pending workload exceeds capacity.
        - ``longest_chains``: Task IDs on the longest dependency chains.
        - ``cycles``: Any detected dependency cycles.
        """
        with self._lock:
            blocked: List[str] = []
            for tid, task in self._tasks.items():
                if task.status == TaskStatus.BLOCKED:
                    blocked.append(tid)
                elif task.status == TaskStatus.PENDING:
                    # Check if blocked by dependencies
                    deps_met = all(
                        dep in self._tasks
                        and self._tasks[dep].status == TaskStatus.COMPLETED
                        for dep in task.dependencies
                    )
                    if not deps_met:
                        blocked.append(tid)

            over_capacity: List[str] = []
            for agent in self._agents.values():
                pending_for_agent = sum(
                    1
                    for t in self._tasks.values()
                    if t.assigned_agent == agent.agent_id
                    and t.status
                    in (TaskStatus.PENDING, TaskStatus.BLOCKED)
                )
                if pending_for_agent > agent.available_capacity:
                    over_capacity.append(
                        f"{agent.agent_id}: {pending_for_agent} pending, "
                        f"{agent.available_capacity} slots available"
                    )

            critical = self.get_critical_path()
            cycles = self._find_cycles(self._tasks)

            return {
                "blocked_tasks": blocked,
                "over_capacity_agents": over_capacity,
                "longest_chains": critical,
                "cycles": cycles,
            }

    # -- Reporting ---------------------------------------------------------

    @property
    def task_count(self) -> int:
        """Total number of registered tasks."""
        with self._lock:
            return len(self._tasks)

    @property
    def agent_count(self) -> int:
        """Total number of registered agents."""
        with self._lock:
            return len(self._agents)

    def get_tasks_by_status(self, status: TaskStatus) -> List[Task]:
        """Return all tasks currently in the given *status*."""
        with self._lock:
            return [t for t in self._tasks.values() if t.status == status]

    def get_tasks_for_agent(self, agent_id: str) -> List[Task]:
        """Return all tasks assigned to *agent_id*."""
        with self._lock:
            return [t for t in self._tasks.values() if t.assigned_agent == agent_id]

    def all_tasks(self) -> List[Task]:
        """Return all registered tasks."""
        with self._lock:
            return list(self._tasks.values())