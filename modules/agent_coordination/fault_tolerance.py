"""
Enterprise-Grade Fault Tolerance System
=======================================
Part of the Agent Communication & Coordination OS Module.

Provides comprehensive fault detection, recovery, and graceful degradation
for multi-agent systems.  Includes:

* Continuous health monitoring via heartbeats, timeouts, and error rates.
* Multi-layered recovery: retry with exponential backoff, task reassignment,
  agent isolation, work preservation, and incident recording.
* Circuit breaker pattern to prevent cascading failures from repeated faults.
* Agent redundancy configuration for hot/warm/cold standby patterns.
* Incident tracking with root cause analysis support.

Recovery Strategy (ordered):
  1. Detect failure
  2. Retry with exponential backoff + jitter
  3. Reassign task to alternative agent
  4. Isolate failing agent
  5. Continue where possible
  6. Preserve intermediate work
  7. Record incident

Author: Eni Builder OS
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import random
import time
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import  datetime, timezone
from enum import Enum, auto
from typing import (
    Any,
    Awaitable,
    Callable,
    Dict,
    List,
    Optional,
    Set,
    Tuple,
)

logger = logging.getLogger(__name__)


# =========================================================================
# Enums
# =========================================================================


class AgentStatus(Enum):
    """Health status of an individual agent."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    FAILED = "failed"
    ISOLATED = "isolated"
    STARTING = "starting"


class IncidentSeverity(Enum):
    """Severity level of a fault incident."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class CircuitState(Enum):
    """States of a circuit breaker."""

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class RecoveryPhase(Enum):
    """Phases of the recovery protocol."""

    DETECTION = "detection"
    RETRY = "retry"
    REASSIGN = "reassign"
    ISOLATE = "isolate"
    CONTINUE = "continue"
    PRESERVE = "preserve"
    RECORD = "record"


class RedundancyMode(Enum):
    """Redundancy configuration for agent pools."""

    HOT = "hot"
    WARM = "warm"
    COLD = "cold"


# =========================================================================
# Data Classes
# =========================================================================


@dataclass
class HeartbeatRecord:
    """A single heartbeat entry for an agent."""

    timestamp: datetime
    latency_ms: float
    success: bool
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentHealth:
    """Health snapshot for an individual agent.

    Attributes:
        agent_id: Unique identifier for the agent.
        status: Current health status.
        last_heartbeat: Timestamp of the most recent heartbeat.
        failure_count: Consecutive or rolling-window failure count.
        current_task: Identifier of the task currently being processed.
        recovery_attempts: Number of recovery attempts made.
        registered_at: When the agent was first registered.
        redundancy_mode: Hot/warm/cold standby configuration.
        redundancy_group: Logical group for redundancy (e.g. "worker-pool-a").
        heartbeat_history: Recent heartbeat records for trend analysis.
        error_rate: Rolling error rate (0.0–1.0).
        circuit_state: Current circuit breaker state for this agent.
        last_failure_type: Type or class of the most recent failure.
    """

    agent_id: str
    status: AgentStatus = AgentStatus.STARTING
    last_heartbeat: Optional[datetime] = None
    failure_count: int = 0
    current_task: Optional[str] = None
    recovery_attempts: int = 0
    registered_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    redundancy_mode: RedundancyMode = RedundancyMode.WARM
    redundancy_group: str = ""
    heartbeat_history: List[HeartbeatRecord] = field(default_factory=list)
    error_rate: float = 0.0
    circuit_state: CircuitState = CircuitState.CLOSED
    last_failure_type: str = ""

    _max_heartbeat_history: int = field(default=100, repr=False)

    def record_heartbeat(self, latency_ms: float, success: bool = True,
                         metadata: Optional[Dict[str, Any]] = None) -> None:
        """Record a heartbeat, maintaining bounded history and updating error_rate."""
        hb = HeartbeatRecord(
            timestamp=datetime.now(timezone.utc),
            latency_ms=latency_ms,
            success=success,
            metadata=metadata or {},
        )
        self.last_heartbeat = hb.timestamp
        self.heartbeat_history.append(hb)
        if len(self.heartbeat_history) > self._max_heartbeat_history:
            self.heartbeat_history = self.heartbeat_history[-self._max_heartbeat_history:]
        total = len(self.heartbeat_history)
        failures = sum(1 for h in self.heartbeat_history if not h.success)
        self.error_rate = failures / total if total > 0 else 0.0

    def increment_failure(self, failure_type: str = "") -> None:
        """Increment the failure counter and record the failure type."""
        self.failure_count += 1
        self.last_failure_type = failure_type
        self.record_heartbeat(latency_ms=-1.0, success=False,
                              metadata={"failure_type": failure_type})

    def reset_failures(self) -> None:
        """Reset failure counters after successful recovery."""
        self.failure_count = 0
        self.recovery_attempts = 0
        self.error_rate = 0.0
        self.last_failure_type = ""
        self.status = AgentStatus.HEALTHY
        self.circuit_state = CircuitState.CLOSED


@dataclass
class Incident:
    """A recorded fault incident with root cause analysis support.

    Attributes:
        incident_id: Unique identifier.
        agent_id: The agent that experienced the fault.
        task_id: The task that was affected.
        detected_at: When the fault was first detected.
        severity: Severity of the incident.
        failure_type: Classification of the failure.
        root_cause: Identified root cause (populated post-analysis).
        recovery_actions: Ordered list of recovery actions attempted.
        recovery_successful: Whether recovery restored service.
        related_incidents: IDs of related incidents for correlation.
        metadata: Arbitrary additional context.
        resolved_at: When the incident was fully resolved (if applicable).
    """

    incident_id: str
    agent_id: str
    task_id: Optional[str]
    detected_at: datetime
    severity: IncidentSeverity
    failure_type: str
    root_cause: Optional[str] = None
    recovery_actions: List[str] = field(default_factory=list)
    recovery_successful: bool = False
    related_incidents: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    resolved_at: Optional[datetime] = None

    def add_recovery_action(self, phase: RecoveryPhase, detail: str) -> None:
        """Record a recovery action taken during incident handling."""
        self.recovery_actions.append(f"[{phase.value}] {detail}")

    def resolve(self, root_cause: str, success: bool) -> None:
        """Mark the incident as resolved with root cause analysis."""
        self.root_cause = root_cause
        self.recovery_successful = success
        self.resolved_at = datetime.now(timezone.utc)


@dataclass
class RetryPolicy:
    """Configuration for retry behavior.

    Attributes:
        max_retries: Maximum number of retry attempts before escalation.
        base_delay_seconds: Starting delay before first retry.
        max_delay_seconds: Maximum delay cap.
        backoff_multiplier: Factor by which delay increases each retry.
        jitter: Whether to add random jitter to delays.
        deadline_seconds: Absolute deadline after which no more retries
            are attempted regardless of remaining max_retries.
    """

    max_retries: int = 3
    base_delay_seconds: float = 1.0
    max_delay_seconds: float = 60.0
    backoff_multiplier: float = 2.0
    jitter: bool = True
    deadline_seconds: float = 300.0

    def compute_delay(self, attempt: int) -> float:
        """Compute the delay for a given retry attempt using exponential backoff.

        Args:
            attempt: Zero-indexed attempt number (0 = first retry).

        Returns:
            Delay in seconds, capped at max_delay_seconds.
        """
        delay = self.base_delay_seconds * (self.backoff_multiplier ** attempt)
        delay = min(delay, self.max_delay_seconds)
        if self.jitter:
            jitter_range = delay * 0.25
            delay += random.uniform(-jitter_range, jitter_range)
            delay = max(0.0, delay)
        return delay


@dataclass
class CircuitBreaker:
    """Circuit breaker pattern for repeated failures.

    Tracks failure counts and opens the circuit when a threshold is
    exceeded, preventing further calls for a cooldown period.  After the
    cooldown, transitions to half-open to test recovery.

    Attributes:
        failure_threshold: Number of failures before opening the circuit.
        cooldown_seconds: How long the circuit stays open before half-open.
        half_open_max_requests: Max requests allowed in half-open state.
    """

    failure_threshold: int = 5
    cooldown_seconds: float = 30.0
    half_open_max_requests: int = 3

    state: CircuitState = field(default=CircuitState.CLOSED, init=False)
    _failure_count: int = field(default=0, init=False)
    _last_failure_time: Optional[datetime] = field(default=None, init=False)
    _opened_at: Optional[datetime] = field(default=None, init=False)
    _half_open_requests: int = field(default=0, init=False)

    def record_success(self) -> None:
        """Record a successful call; may close a half-open circuit."""
        if self.state == CircuitState.HALF_OPEN:
            self._half_open_requests += 1
            if self._half_open_requests >= self.half_open_max_requests:
                self._transition_to(CircuitState.CLOSED)
                self._failure_count = 0
                self._half_open_requests = 0
        else:
            self._failure_count = 0

    def record_failure(self) -> None:
        """Record a failed call; may open the circuit."""
        self._failure_count += 1
        self._last_failure_time = datetime.now(timezone.utc)
        if self.state == CircuitState.HALF_OPEN:
            self._transition_to(CircuitState.OPEN)
            self._half_open_requests = 0
        elif (self.state == CircuitState.CLOSED
              and self._failure_count >= self.failure_threshold):
            self._transition_to(CircuitState.OPEN)

    def allow_request(self) -> bool:
        """Return True if a request should be allowed through."""
        if self.state == CircuitState.CLOSED:
            return True
        if self.state == CircuitState.OPEN:
            if self._opened_at:
                elapsed = (datetime.now(timezone.utc) - self._opened_at).total_seconds()
                if elapsed >= self.cooldown_seconds:
                    self._transition_to(CircuitState.HALF_OPEN)
                    self._half_open_requests = 0
                    return True
            return False
        return True  # HALF_OPEN

    def _transition_to(self, new_state: CircuitState) -> None:
        """Transition to a new circuit state, logging the change."""
        old_state = self.state
        self.state = new_state
        if new_state == CircuitState.OPEN:
            self._opened_at = datetime.now(timezone.utc)
        logger.info("Circuit breaker: %s -> %s (failures=%d)",
                    old_state.name, new_state.name, self._failure_count)


@dataclass
class Checkpoint:
    """A saved intermediate work checkpoint for recovery.

    Attributes:
        checkpoint_id: Unique identifier.
        task_id: The task this checkpoint belongs to.
        agent_id: The agent that produced the checkpoint.
        data: Serialized intermediate state.
        created_at: When the checkpoint was created.
        sequence: Monotonically increasing sequence number.
        content_hash: SHA-256 hash of the data for integrity verification.
    """

    checkpoint_id: str
    task_id: str
    agent_id: str
    data: Dict[str, Any]
    created_at: datetime
    sequence: int
    content_hash: str = ""

    def __post_init__(self) -> None:
        if not self.content_hash:
            serialized = json.dumps(self.data, sort_keys=True, default=str)
            self.content_hash = hashlib.sha256(serialized.encode("utf-8")).hexdigest()


@dataclass
class SystemHealthReport:
    """Aggregate health report for the entire agent system."""

    generated_at: datetime
    total_agents: int
    healthy: int
    degraded: int
    failed: int
    isolated: int
    overall_status: str
    open_circuits: int
    active_incidents: int
    redundancy_coverage: float
    details: List[Dict[str, Any]] = field(default_factory=list)


# =========================================================================
# Exceptions
# =========================================================================


class FaultToleranceError(Exception):
    """Base exception for fault tolerance system errors."""


class AgentNotFoundError(FaultToleranceError):
    """Raised when an agent ID is not found in the registry."""


class NoAvailableAgentsError(FaultToleranceError):
    """Raised when no alternative agents are available for reassignment."""


class CircuitOpenError(FaultToleranceError):
    """Raised when a request is blocked by an open circuit breaker."""


class RetryExhaustedError(FaultToleranceError):
    """Raised when all retries have been exhausted."""


# =========================================================================
# Fault Tolerance Manager
# =========================================================================


class FaultToleranceManager:
    """Central fault tolerance manager for multi-agent systems.

    Orchestrates health monitoring, failure detection, recovery protocols,
    and incident tracking.  Designed for asynchronous operation with
    pluggable health check callbacks.

    Typical usage::

        ftm = FaultToleranceManager()

        # Register agents
        ftm.register_agent("worker-1", redundancy_group="pool-a")
        ftm.register_agent("worker-2", redundancy_group="pool-a",
                            redundancy_mode=RedundancyMode.HOT)

        # Set health check callback
        async def check_agent(aid): return True
        ftm.set_health_check(check_agent)

        # Start monitoring (runs in background)
        monitor_task = asyncio.create_task(ftm.monitor_agents(interval=5.0))

        # Handle failure when detected
        await ftm.handle_failure("worker-1")

        # Get system health
        report = ftm.get_system_health()
    """

    def __init__(self) -> None:
        self._agents: Dict[str, AgentHealth] = {}
        self._redundancy_groups: Dict[str, List[str]] = defaultdict(list)
        self._circuit_breakers: Dict[str, CircuitBreaker] = {}
        self._retry_policy: RetryPolicy = RetryPolicy()
        self._checkpoints: Dict[str, List[Checkpoint]] = defaultdict(list)
        self._incidents: Dict[str, Incident] = {}
        self._active_incidents: Set[str] = set()
        self._health_check_cb: Optional[Callable[[str], Awaitable[bool]]] = None
        self._monitoring_active: bool = False
        self._last_monitor_tick: Optional[datetime] = None

    # ------------------------------------------------------------------
    # Agent Registration
    # ------------------------------------------------------------------

    def register_agent(
        self,
        agent_id: str,
        redundancy_group: str = "",
        redundancy_mode: RedundancyMode = RedundancyMode.WARM,
        circuit_threshold: int = 5,
        circuit_cooldown: float = 30.0,
    ) -> AgentHealth:
        """Register an agent with the fault tolerance manager."""
        health = AgentHealth(
            agent_id=agent_id,
            status=AgentStatus.STARTING,
            redundancy_mode=redundancy_mode,
            redundancy_group=redundancy_group,
        )
        self._agents[agent_id] = health
        if redundancy_group:
            self._redundancy_groups[redundancy_group].append(agent_id)
        self._circuit_breakers[agent_id] = CircuitBreaker(
            failure_threshold=circuit_threshold,
            cooldown_seconds=circuit_cooldown,
        )
        logger.info("Registered agent '%s' in group '%s' (%s mode)",
                    agent_id, redundancy_group, redundancy_mode.value)
        return health

    def deregister_agent(self, agent_id: str) -> None:
        """Remove an agent from the registry.

        Raises AgentNotFoundError if the agent is not registered.
        """
        if agent_id not in self._agents:
            raise AgentNotFoundError(f"Agent '{agent_id}' is not registered.")
        health = self._agents.pop(agent_id)
        self._circuit_breakers.pop(agent_id, None)
        if health.redundancy_group:
            group = self._redundancy_groups.get(health.redundancy_group, [])
            if agent_id in group:
                group.remove(agent_id)
        logger.info("Deregistered agent '%s'", agent_id)

    def set_health_check(
        self, callback: Callable[[str], Awaitable[bool]],
    ) -> None:
        """Register an async health check callback.

        The callback receives an agent_id and returns True if the agent
        is healthy, False otherwise.
        """
        self._health_check_cb = callback
        logger.info("Health check callback registered")

    def set_retry_policy(self, policy: RetryPolicy) -> None:
        """Override the default retry policy."""
        self._retry_policy = policy
        logger.info("Retry policy updated: max_retries=%d, deadline=%.1fs",
                    policy.max_retries, policy.deadline_seconds)

    # ------------------------------------------------------------------
    # Health Monitoring
    # ------------------------------------------------------------------

    async def monitor_agents(
        self, interval: float = 10.0, max_duration: Optional[float] = None,
    ) -> None:
        """Run continuous agent health monitoring.

        Designed to be run as a background task.  Periodically checks all
        registered agents and updates their health status.

        Args:
            interval: Seconds between health check sweeps.
            max_duration: If set, stop monitoring after this many seconds.
        """
        self._monitoring_active = True
        started_at = time.monotonic()
        logger.info("Agent health monitoring started (interval=%.1fs)", interval)

        while self._monitoring_active:
            self._last_monitor_tick = datetime.now(timezone.utc)
            await self._health_sweep()
            if max_duration and (time.monotonic() - started_at) >= max_duration:
                logger.info("Monitoring duration limit reached (%.1fs)", max_duration)
                break
            await asyncio.sleep(interval)

        self._monitoring_active = False
        logger.info("Agent health monitoring stopped")

    def stop_monitoring(self) -> None:
        """Signal the monitoring loop to stop at the next interval."""
        self._monitoring_active = False

    async def _health_sweep(self) -> None:
        """Perform a single health sweep of all registered agents."""
        if not self._health_check_cb:
            logger.debug("No health check callback registered; skipping sweep")
            return

        for agent_id, health in list(self._agents.items()):
            try:
                is_healthy = await self._health_check_cb(agent_id)
                if is_healthy:
                    health.record_heartbeat(latency_ms=0.0, success=True)
                    self._circuit_breakers[agent_id].record_success()
                    if health.status == AgentStatus.DEGRADED:
                        health.status = AgentStatus.HEALTHY
                        health.reset_failures()
                        logger.info("Agent '%s' recovered to HEALTHY", agent_id)
                else:
                    health.increment_failure("health_check_failed")
                    self._circuit_breakers[agent_id].record_failure()
                    if health.status != AgentStatus.FAILED:
                        health.status = AgentStatus.DEGRADED
                        logger.warning("Agent '%s' DEGRADED (health check failed)", agent_id)
            except Exception:
                logger.exception("Health check error for agent '%s'", agent_id)
                health.increment_failure("health_check_error")
                self._circuit_breakers[agent_id].record_failure()
                if health.status != AgentStatus.FAILED:
                    health.status = AgentStatus.DEGRADED

    # ------------------------------------------------------------------
    # Failure Handling
    # ------------------------------------------------------------------

    async def handle_failure(
        self,
        agent_id: str,
        task_id: Optional[str] = None,
        failure_type: str = "unknown",
        preserve_work: bool = True,
    ) -> Incident:
        """Execute the full recovery protocol for a failed agent.

        Recovery phases (ordered):
          1. Detect – record the failure
          2. Retry – attempt retries with exponential backoff
          3. Reassign – hand off task to alternative agent
          4. Isolate – remove failing agent from pool
          5. Continue – signal downstream to proceed
          6. Preserve – save intermediate work
          7. Record – create incident record

        Raises AgentNotFoundError if the agent is not registered.
        """
        if agent_id not in self._agents:
            raise AgentNotFoundError(f"Agent '{agent_id}' is not registered.")

        health = self._agents[agent_id]

        # Phase 1: DETECTION
        incident = Incident(
            incident_id=str(uuid.uuid4()),
            agent_id=agent_id,
            task_id=task_id,
            detected_at=datetime.now(timezone.utc),
            severity=self._classify_severity(failure_type),
            failure_type=failure_type,
        )
        incident.add_recovery_action(
            RecoveryPhase.DETECTION,
            f"Failure '{failure_type}' detected on agent '{agent_id}'",
        )
        health.increment_failure(failure_type)
        self._circuit_breakers[agent_id].record_failure()

        logger.warning("Handling failure on agent '%s' (type=%s, failures=%d)",
                       agent_id, failure_type, health.failure_count)

        # Phase 2: RETRY
        if task_id is not None:
            retry_success = await self._retry_with_backoff(agent_id)
            if retry_success:
                incident.add_recovery_action(
                    RecoveryPhase.RETRY,
                    f"Retry succeeded for task '{task_id}'",
                )
                health.reset_failures()
                incident.resolve(root_cause="transient_failure_recovered_by_retry",
                                 success=True)
                self._record_incident(incident)
                return incident
            else:
                incident.add_recovery_action(RecoveryPhase.RETRY, "Retries exhausted")

        # Phase 3: REASSIGN
        reassigned = False
        if task_id is not None:
            reassigned = await self.reassign_tasks(agent_id)
            if reassigned:
                incident.add_recovery_action(
                    RecoveryPhase.REASSIGN,
                    f"Task '{task_id}' reassigned",
                )
            else:
                incident.add_recovery_action(
                    RecoveryPhase.REASSIGN,
                    f"No alternative agent for task '{task_id}'",
                )

        # Phase 4: ISOLATE
        await self.isolate_agent(agent_id)
        incident.add_recovery_action(
            RecoveryPhase.ISOLATE, f"Agent '{agent_id}' isolated",
        )

        # Phase 5: CONTINUE
        incident.add_recovery_action(
            RecoveryPhase.CONTINUE, "System continues with reduced capacity",
        )

        # Phase 6: PRESERVE
        if preserve_work and task_id:
            await self._preserve_work(agent_id, task_id)
            incident.add_recovery_action(
                RecoveryPhase.PRESERVE,
                f"Intermediate work preserved for task '{task_id}'",
            )

        # Phase 7: RECORD
        root_cause = (
            "agent_failure_with_successful_reassignment" if reassigned
            else f"agent_failure_type_{failure_type}"
        )
        incident.resolve(root_cause=root_cause, success=reassigned)
        self._record_incident(incident)
        incident.add_recovery_action(
            RecoveryPhase.RECORD,
            f"Incident '{incident.incident_id}' recorded",
        )

        return incident

    async def _retry_with_backoff(self, agent_id: str) -> bool:
        """Attempt retries with exponential backoff for a failed agent."""
        if agent_id not in self._agents:
            return False

        health = self._agents[agent_id]
        breaker = self._circuit_breakers[agent_id]

        if not breaker.allow_request():
            logger.warning("Circuit open for agent '%s'; skipping retries", agent_id)
            return False

        if not self._health_check_cb:
            return False

        deadline = time.monotonic() + self._retry_policy.deadline_seconds

        for attempt in range(self._retry_policy.max_retries):
            if time.monotonic() >= deadline:
                logger.warning("Retry deadline reached for agent '%s'", agent_id)
                return False

            delay = self._retry_policy.compute_delay(attempt)
            logger.debug("Retry attempt %d/%d for agent '%s' — waiting %.2fs",
                         attempt + 1, self._retry_policy.max_retries,
                         agent_id, delay)
            await asyncio.sleep(delay)

            try:
                if await self._health_check_cb(agent_id):
                    logger.info("Retry %d succeeded for agent '%s'",
                                attempt + 1, agent_id)
                    health.record_heartbeat(latency_ms=0.0, success=True)
                    breaker.record_success()
                    return True
            except Exception:
                logger.exception("Retry %d error for agent '%s'",
                                 attempt + 1, agent_id)

            breaker.record_failure()

        logger.error("All %d retries exhausted for agent '%s'",
                     self._retry_policy.max_retries, agent_id)
        return False

    async def isolate_agent(self, agent_id: str) -> None:
        """Isolate a failing agent by opening its circuit breaker."""
        if agent_id in self._agents:
            self._agents[agent_id].status = AgentStatus.ISOLATED
        if agent_id in self._circuit_breakers:
            breaker = self._circuit_breakers[agent_id]
            for _ in range(breaker.failure_threshold):
                breaker.record_failure()
            breaker.allow_request()  # transitions to OPEN
        logger.warning("Agent '%s' isolated", agent_id)

    async def reassign_tasks(self, failed_agent_id: str) -> bool:
        """Reassign the failed agent's current task to an alternative agent.

        Selects from the same redundancy group, preferring HEALTHY agents,
        then HOT > WARM > COLD.
        """
        health = self._agents.get(failed_agent_id)
        if not health or not health.current_task:
            return False

        task_id = health.current_task
        target_agent = await self._select_alternative(failed_agent_id)

        if target_agent is None:
            logger.error(
                "No alternative agent available to reassign task '%s' from '%s'",
                task_id, failed_agent_id,
            )
            return False

        target_health = self._agents[target_agent]
        target_health.current_task = task_id
        health.current_task = None

        # Restore from latest checkpoint if available
        checkpoints = self._checkpoints.get(task_id, [])
        if checkpoints:
            latest = max(checkpoints, key=lambda c: c.sequence)
            logger.info("Restoring task '%s' from checkpoint seq=%d to agent '%s'",
                        task_id, latest.sequence, target_agent)

        logger.info("Reassigned task '%s' from '%s' to '%s' (%s)",
                    task_id, failed_agent_id, target_agent,
                    target_health.redundancy_mode.value)
        return True

    async def _select_alternative(self, failed_agent_id: str) -> Optional[str]:
        """Select the best alternative agent for task reassignment."""
        health = self._agents.get(failed_agent_id)
        if not health:
            return None

        group = health.redundancy_group
        if group:
            candidates = [
                aid for aid in self._redundancy_groups.get(group, [])
                if aid != failed_agent_id and aid in self._agents
            ]
        else:
            candidates = [
                aid for aid in self._agents if aid != failed_agent_id
            ]
        if not candidates:
            return None

        def _score(agent_id: str) -> Tuple[int, int]:
            agent = self._agents[agent_id]
            status_score = {
                AgentStatus.HEALTHY: 0, AgentStatus.DEGRADED: 10,
                AgentStatus.STARTING: 20, AgentStatus.FAILED: 100,
                AgentStatus.ISOLATED: 200,
            }.get(agent.status, 1000)
            redundancy_score = {
                RedundancyMode.HOT: 0, RedundancyMode.WARM: 1, RedundancyMode.COLD: 2,
            }.get(agent.redundancy_mode, 99)
            return (status_score, redundancy_score)

        best = min(candidates, key=_score)
        best_health = self._agents[best]
        if best_health.status in (AgentStatus.FAILED, AgentStatus.ISOLATED):
            return None
        return best

    # ------------------------------------------------------------------
    # Work Preservation
    # ------------------------------------------------------------------

    async def _preserve_work(self, agent_id: str, task_id: str) -> None:
        """Save a checkpoint of intermediate work for recovery."""
        sequence = len(self._checkpoints.get(task_id, []))
        checkpoint = Checkpoint(
            checkpoint_id=str(uuid.uuid4()),
            task_id=task_id,
            agent_id=agent_id,
            data={
                "agent_id": agent_id,
                "task_id": task_id,
                "saved_at": datetime.now(timezone.utc).isoformat(),
                "sequence": sequence,
            },
            created_at=datetime.now(timezone.utc),
            sequence=sequence,
        )
        self._checkpoints[task_id].append(checkpoint)
        max_ckpts = 20
        if len(self._checkpoints[task_id]) > max_ckpts:
            self._checkpoints[task_id] = self._checkpoints[task_id][-max_ckpts:]
        logger.info("Checkpoint saved: task='%s' agent='%s' seq=%d",
                    task_id, agent_id, sequence)

    def get_latest_checkpoint(self, task_id: str) -> Optional[Checkpoint]:
        """Return the most recent checkpoint for a task."""
        checkpoints = self._checkpoints.get(task_id, [])
        if not checkpoints:
            return None
        return max(checkpoints, key=lambda c: c.sequence)

    # ------------------------------------------------------------------
    # Incident Tracking
    # ------------------------------------------------------------------

    def record_incident(self, incident: Incident) -> None:
        """Record an incident in the log. Convenience alias."""
        self._record_incident(incident)

    def _record_incident(self, incident: Incident) -> None:
        """Store an incident and track it as active if unresolved."""
        self._incidents[incident.incident_id] = incident
        if not incident.resolved_at:
            self._active_incidents.add(incident.incident_id)
        logger.info("Incident recorded: id=%s agent=%s severity=%s type=%s resolved=%s",
                    incident.incident_id, incident.agent_id,
                    incident.severity.value, incident.failure_type,
                    incident.resolved_at is not None)

    def resolve_incident(self, incident_id: str, root_cause: str,
                         success: bool) -> Optional[Incident]:
        """Mark a previously recorded incident as resolved."""
        incident = self._incidents.get(incident_id)
        if incident is None:
            return None
        incident.resolve(root_cause=root_cause, success=success)
        self._active_incidents.discard(incident_id)
        logger.info("Incident '%s' resolved: %s", incident_id, root_cause)
        return incident

    def get_active_incidents(self) -> List[Incident]:
        """Return all currently unresolved incidents."""
        return [
            self._incidents[iid]
            for iid in self._active_incidents
            if iid in self._incidents
        ]

    def get_incident(self, incident_id: str) -> Optional[Incident]:
        """Retrieve an incident by ID."""
        return self._incidents.get(incident_id)

    # ------------------------------------------------------------------
    # System Health Reporting
    # ------------------------------------------------------------------

    def get_system_health(self) -> SystemHealthReport:
        """Generate an aggregate health report for the entire system."""
        status_counts: Dict[AgentStatus, int] = {
            AgentStatus.HEALTHY: 0,
            AgentStatus.DEGRADED: 0,
            AgentStatus.FAILED: 0,
            AgentStatus.ISOLATED: 0,
            AgentStatus.STARTING: 0,
        }
        for health in self._agents.values():
            status_counts[health.status] += 1

        open_circuits = sum(
            1 for cb in self._circuit_breakers.values()
            if cb.state == CircuitState.OPEN
        )

        # Redundancy coverage: groups with >= 2 healthy members
        groups_covered = 0
        total_groups = len(self._redundancy_groups)
        for group, members in self._redundancy_groups.items():
            healthy_in_group = sum(
                1 for aid in members
                if aid in self._agents
                and self._agents[aid].status == AgentStatus.HEALTHY
            )
            if healthy_in_group >= 2:
                groups_covered += 1
        coverage = groups_covered / total_groups if total_groups > 0 else 1.0

        # Overall status
        if status_counts[AgentStatus.FAILED] > 0 or status_counts[AgentStatus.ISOLATED] > 0:
            overall = "critical"
        elif status_counts[AgentStatus.DEGRADED] > 0:
            overall = "degraded"
        else:
            overall = "healthy"

        # Per-agent details
        details = []
        for agent_id, health in self._agents.items():
            breaker = self._circuit_breakers.get(agent_id)
            details.append({
                "agent_id": agent_id,
                "status": health.status.value,
                "circuit_state": breaker.state.value if breaker else "unknown",
                "last_heartbeat": (
                    health.last_heartbeat.isoformat()
                    if health.last_heartbeat else None
                ),
                "failure_count": health.failure_count,
                "error_rate": round(health.error_rate, 4),
                "recovery_attempts": health.recovery_attempts,
                "current_task": health.current_task,
                "redundancy_group": health.redundancy_group,
                "redundancy_mode": health.redundancy_mode.value,
            })

        return SystemHealthReport(
            generated_at=datetime.now(timezone.utc),
            total_agents=len(self._agents),
            healthy=status_counts[AgentStatus.HEALTHY],
            degraded=status_counts[AgentStatus.DEGRADED],
            failed=status_counts[AgentStatus.FAILED],
            isolated=status_counts[AgentStatus.ISOLATED],
            overall_status=overall,
            open_circuits=open_circuits,
            active_incidents=len(self._active_incidents),
            redundancy_coverage=round(coverage, 4),
            details=details,
        )

    def get_agent_health(self, agent_id: str) -> Optional[AgentHealth]:
        """Retrieve the health record for a specific agent."""
        return self._agents.get(agent_id)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _classify_severity(failure_type: str) -> IncidentSeverity:
        """Map a failure type string to an incident severity."""
        critical_types = {
            "crash", "data_loss", "security_breach", "permanent_failure",
            "resource_exhaustion", "deadlock",
        }
        high_types = {
            "timeout", "connection_lost", "authentication_failed",
            "authorization_failed", "state_corruption",
        }
        medium_types = {
            "performance_degradation", "partial_failure", "retry_exhausted",
            "health_check_failed", "health_check_error",
        }
        ft_lower = failure_type.lower()
        if ft_lower in critical_types:
            return IncidentSeverity.CRITICAL
        elif ft_lower in high_types:
            return IncidentSeverity.HIGH
        elif ft_lower in medium_types:
            return IncidentSeverity.MEDIUM
        return IncidentSeverity.LOW


# =========================================================================
# Convenience Factory
# =========================================================================


def create_fault_tolerance_manager(
    retry_policy: Optional[RetryPolicy] = None,
    agents: Optional[List[Tuple[str, str, RedundancyMode]]] = None,
) -> FaultToleranceManager:
    """Create a pre-configured FaultToleranceManager.

    Args:
        retry_policy: Optional custom retry policy.
        agents: Optional list of (agent_id, redundancy_group, redundancy_mode)
            tuples to register on creation.

    Returns:
        A ready-to-use FaultToleranceManager.
    """
    ftm = FaultToleranceManager()
    if retry_policy:
        ftm.set_retry_policy(retry_policy)
    if agents:
        for agent_id, group, mode in agents:
            ftm.register_agent(agent_id, redundancy_group=group,
                               redundancy_mode=mode)
    return ftm