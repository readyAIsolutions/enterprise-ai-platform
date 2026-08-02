"""
ENI Enterprise Integration Layer — Central Event Hub
=====================================================
Production-grade event routing backbone that connects all enterprise modules
through the Platform Kernel EventBus. Defines standard event schemas,
module-to-module communication contracts, and reliable event delivery.

Architecture:
    EventSchema        — Standardized event shape with typed payloads
    EventBus           — Publish/subscribe message bus with async routing
    EventRouter        — Rule-based routing engine with pattern matching
    EventSubscription  — Module subscription management
    EventContract      — Module-to-module communication contracts
    DeadLetterQueue    — Failed event handling and replay
    EventTracer        — Distributed tracing via correlation IDs

Standard Event Categories:
    - system.*         — Platform lifecycle events (startup, shutdown, health)
    - kernel.*         — Kernel operations (context, gate, audit)
    - module.*         — Module lifecycle (activate, deactivate, upgrade)
    - agent.*          — Agent communication (task, message, status)
    - data.*           — Data governance (classify, lifecycle, access)
    - safety.*         — Safety & security (guardrail, incident, alert)
    - knowledge.*      — Knowledge graph (entity, relationship, provenance)
    - release.*        — Release & change (deploy, rollback, gate)
"""

import asyncio
import hashlib
import json
import logging
import re
import threading
import time
import uuid
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import (
    Any,
    Awaitable,
    Callable,
    Dict,
    List,
    Optional,
    Pattern,
    Set,
    Tuple,
    Union,
)

logger = logging.getLogger("eni.integration.event_hub")

# ---------------------------------------------------------------------------
# Core Data Types
# ---------------------------------------------------------------------------


class EventPriority(str, Enum):
    """Event priority levels for routing and processing order."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class EventStatus(str, Enum):
    """Lifecycle status of an event in the hub."""

    RECEIVED = "received"
    ROUTED = "routed"
    DELIVERED = "delivered"
    FAILED = "failed"
    DEAD_LETTERED = "dead_lettered"
    REPLAYED = "replayed"
    DROPPED = "dropped"


class ContractDirection(str, Enum):
    """Direction of a module communication contract."""

    PRODUCES = "produces"
    CONSUMES = "consumes"
    BIDIRECTIONAL = "bidirectional"


# ---------------------------------------------------------------------------
# Event Schema
# ---------------------------------------------------------------------------


@dataclass
class EventSchema:
    """Immutable definition of a standard event type.

    Attributes:
        event_type: Fully-qualified event type (e.g. 'module.privacy.data_classified')
        version: Schema version for evolution support
        description: Human-readable description
        required_fields: Fields that MUST be present in payload
        optional_fields: Fields that MAY be present
        payload_schema: JSON Schema for the payload (optional)
        category: Event category for grouping (system, module, agent, etc.)
        ttl_seconds: Time-to-live in seconds; events older than this are dropped
    """

    event_type: str
    version: str = "1.0"
    description: str = ""
    required_fields: List[str] = field(default_factory=list)
    optional_fields: List[str] = field(default_factory=list)
    payload_schema: Optional[Dict[str, Any]] = None
    category: str = ""
    ttl_seconds: int = 3600

    def validate(self, payload: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """Validate payload against required fields. Returns (valid, errors)."""
        errors = []
        for field_name in self.required_fields:
            if field_name not in payload:
                errors.append(f"Missing required field: {field_name}")
        return len(errors) == 0, errors


# ---------------------------------------------------------------------------
# Event Envelope
# ---------------------------------------------------------------------------


@dataclass
class EventEnvelope:
    """Complete event with metadata for routing and tracing.

    Attributes:
        event_id: Universally unique event identifier
        event_type: Fully-qualified event type string
        source: Originating module/component identifier
        payload: Event data payload
        priority: Processing priority
        correlation_id: For distributed tracing across events
        causation_id: The event_id that caused this event
        timestamp: UTC timestamp of event creation
        ttl_seconds: Time-to-live from this event's perspective
        status: Current lifecycle status
        retry_count: Number of delivery attempts
        max_retries: Maximum delivery attempts before dead-lettering
        trace_context: OpenTelemetry-compatible trace context
        headers: Arbitrary routing headers
        metadata: Additional extensible metadata
    """

    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    event_type: str = ""
    source: str = ""
    payload: Dict[str, Any] = field(default_factory=dict)
    priority: EventPriority = EventPriority.MEDIUM
    correlation_id: Optional[str] = None
    causation_id: Optional[str] = None
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    ttl_seconds: int = 3600
    status: EventStatus = EventStatus.RECEIVED
    retry_count: int = 0
    max_retries: int = 3
    trace_context: Dict[str, str] = field(default_factory=dict)
    headers: Dict[str, str] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_expired(self) -> bool:
        """Check if the event has exceeded its TTL."""
        try:
            created = datetime.fromisoformat(self.timestamp.replace("Z", "+00:00"))
            age = (datetime.now(timezone.utc) - created).total_seconds()
            return age > self.ttl_seconds
        except Exception:
            return False

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "EventEnvelope":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


# ---------------------------------------------------------------------------
# Event Subscription
# ---------------------------------------------------------------------------


@dataclass
class EventSubscription:
    """A module's subscription to event types.

    Attributes:
        subscription_id: Unique subscription identifier
        module_name: Subscribing module name
        event_patterns: Glob or regex patterns for event types
        handler: Async callable that processes matching events
        priority: Only receive events at or above this priority
        max_concurrency: Maximum concurrent event handlers
        dead_letter_on_failure: Whether to dead-letter failed events
        active: Whether subscription is currently active
    """

    subscription_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    module_name: str = ""
    event_patterns: List[str] = field(default_factory=list)
    handler: Optional[Callable[[EventEnvelope], Awaitable[None]]] = None
    priority: EventPriority = EventPriority.LOW
    max_concurrency: int = 10
    dead_letter_on_failure: bool = True
    active: bool = True
    _compiled_patterns: List[Pattern] = field(default_factory=list, repr=False)

    def __post_init__(self):
        self._compile_patterns()

    def _compile_patterns(self):
        """Compile glob-style patterns to regex."""
        self._compiled_patterns = []
        for pattern in self.event_patterns:
            # Convert glob to regex: * → .*, ? → ., ** → .*
            regex = pattern.replace(".", r"\.").replace("**", "___DOUBLESTAR___")
            regex = regex.replace("*", "[^.]+").replace("___DOUBLESTAR___", ".*")
            self._compiled_patterns.append(re.compile(f"^{regex}$"))

    def matches(self, event_type: str) -> bool:
        """Check if this subscription matches a given event type."""
        for pattern in self._compiled_patterns:
            if pattern.match(event_type):
                return True
        return False


# ---------------------------------------------------------------------------
# Communication Contract
# ---------------------------------------------------------------------------


@dataclass
class EventContract:
    """Formal module-to-module communication contract.

    Defines what events a module produces and consumes, establishing
    explicit interfaces between modules for system-wide traceability.
    """

    contract_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    producer_module: str = ""
    consumer_module: str = ""
    event_types: List[str] = field(default_factory=list)
    direction: ContractDirection = ContractDirection.BIDIRECTIONAL
    description: str = ""
    sla_ms: Optional[int] = None  # Maximum expected processing latency
    schema_version: str = "1.0"
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    active: bool = True


# ---------------------------------------------------------------------------
# Dead Letter Queue
# ---------------------------------------------------------------------------


class DeadLetterQueue:
    """Persistent dead-letter queue for events that failed delivery.

    Stores events that exceed their max_retries so they can be
    inspected, debugged, and replayed later.
    """

    def __init__(self, max_size: int = 10000):
        self.max_size = max_size
        self._queue: List[EventEnvelope] = []
        self._lock = threading.Lock()

    def enqueue(self, event: EventEnvelope, reason: str = ""):
        """Move an event to the dead-letter queue."""
        event.status = EventStatus.DEAD_LETTERED
        event.metadata["dead_letter_reason"] = reason
        event.metadata["dead_lettered_at"] = datetime.now(timezone.utc).isoformat()
        with self._lock:
            if len(self._queue) >= self.max_size:
                self._queue.pop(0)  # Drop oldest
            self._queue.append(event)
        logger.warning(
            "Event %s dead-lettered: %s (reason: %s)",
            event.event_id,
            event.event_type,
            reason,
        )

    def get_all(self, limit: int = 100) -> List[EventEnvelope]:
        """Get dead-lettered events for inspection."""
        with self._lock:
            return list(self._queue[-limit:])

    def get_by_id(self, event_id: str) -> Optional[EventEnvelope]:
        """Find a specific dead-lettered event."""
        with self._lock:
            for event in self._queue:
                if event.event_id == event_id:
                    return event
        return None

    def replay(self, event_id: str) -> Optional[EventEnvelope]:
        """Remove from DLQ for replay."""
        with self._lock:
            for i, event in enumerate(self._queue):
                if event.event_id == event_id:
                    event.status = EventStatus.REPLAYED
                    event.retry_count = 0
                    return self._queue.pop(i)
        return None

    def clear(self):
        """Clear the dead-letter queue."""
        with self._lock:
            self._queue.clear()

    @property
    def size(self) -> int:
        with self._lock:
            return len(self._queue)


# ---------------------------------------------------------------------------
# Event Tracer (Distributed Tracing)
# ---------------------------------------------------------------------------


class EventTracer:
    """Lightweight distributed tracing for event flows.

    Maintains correlation between events using correlation_id
    and causation_id chains so entire event flows can be reconstructed.
    """

    def __init__(self, max_traces: int = 10000):
        self.max_traces = max_traces
        self._traces: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        self._lock = threading.Lock()

    def record(self, event: EventEnvelope):
        """Record an event in the trace graph."""
        trace_id = event.correlation_id or event.event_id
        entry = {
            "event_id": event.event_id,
            "event_type": event.event_type,
            "source": event.source,
            "timestamp": event.timestamp,
            "status": event.status.value,
            "causation_id": event.causation_id,
        }
        with self._lock:
            if len(self._traces) >= self.max_traces:
                # Remove oldest trace
                oldest = min(self._traces.keys(), key=lambda k: len(self._traces[k]))
                del self._traces[oldest]
            self._traces[trace_id].append(entry)

    def get_trace(self, correlation_id: str) -> List[Dict[str, Any]]:
        """Get the full trace for a correlation ID."""
        with self._lock:
            return list(self._traces.get(correlation_id, []))


# ---------------------------------------------------------------------------
# Event Bus
# ---------------------------------------------------------------------------


class EventBus:
    """Central publish-subscribe event bus for module-to-module communication.

    Features:
        - Async event publishing with priority queue
        - Pattern-based subscription matching
        - Concurrent delivery with semaphore-based throttling
        - Automatic dead-lettering for failed deliveries
        - Built-in distributed tracing
        - Schema validation before delivery
    """

    def __init__(self, max_queue_size: int = 10000, worker_count: int = 4):
        self.max_queue_size = max_queue_size
        self.worker_count = worker_count
        self._subscriptions: Dict[str, EventSubscription] = {}
        self._schemas: Dict[str, EventSchema] = {}
        self._contracts: Dict[str, EventContract] = {}
        self._dlq = DeadLetterQueue()
        self._tracer = EventTracer()
        self._priority_queues: Dict[EventPriority, asyncio.Queue] = {
            p: asyncio.Queue(maxsize=max_queue_size) for p in EventPriority
        }
        self._workers: List[asyncio.Task] = []
        self._running = False
        self._lock = threading.Lock()
        self._event_counter: Dict[str, int] = defaultdict(int)
        self._delivery_semaphore: Dict[str, asyncio.Semaphore] = {}

        # Register standard schemas
        self._register_standard_schemas()

    # ── Schema Management ────────────────────────────────────────────────

    def _register_standard_schemas(self):
        """Register the standard set of event schemas for all modules."""
        schemas = [
            # System events
            EventSchema("system.startup", category="system", description="Platform startup"),
            EventSchema("system.shutdown", category="system", description="Platform shutdown"),
            EventSchema("system.health_check", category="system",
                        required_fields=["status", "modules"],
                        description="Periodic health check result"),
            EventSchema("system.error", category="system",
                        required_fields=["error_type", "message"],
                        description="System-level error event"),

            # Kernel events
            EventSchema("kernel.context.created", category="kernel",
                        required_fields=["session_id", "project"],
                        description="New kernel context created"),
            EventSchema("kernel.context.finalized", category="kernel",
                        required_fields=["session_id"],
                        description="Kernel context finalized"),
            EventSchema("kernel.gate.passed", category="kernel",
                        required_fields=["session_id", "gate_name"],
                        description="Quality gate passed"),
            EventSchema("kernel.gate.failed", category="kernel",
                        required_fields=["session_id", "gate_name", "reason"],
                        description="Quality gate failed"),
            EventSchema("kernel.module.activated", category="kernel",
                        required_fields=["module_name", "authority"],
                        description="Module activated in kernel"),
            EventSchema("kernel.audit.entry", category="kernel",
                        required_fields=["session_id", "event"],
                        description="Audit log entry created"),

            # Module events
            EventSchema("module.activated", category="module",
                        required_fields=["module_name", "version"],
                        description="Module activated"),
            EventSchema("module.deactivated", category="module",
                        required_fields=["module_name"],
                        description="Module deactivated"),
            EventSchema("module.error", category="module",
                        required_fields=["module_name", "error"],
                        description="Module-level error"),

            # Agent events
            EventSchema("agent.task.created", category="agent",
                        required_fields=["task_id", "objective"],
                        description="New agent task created"),
            EventSchema("agent.task.completed", category="agent",
                        required_fields=["task_id", "result"],
                        description="Agent task completed"),
            EventSchema("agent.task.failed", category="agent",
                        required_fields=["task_id", "error"],
                        description="Agent task failed"),
            EventSchema("agent.message.sent", category="agent",
                        required_fields=["message_id", "sender", "receiver"],
                        description="Inter-agent message sent"),
            EventSchema("agent.conflict.detected", category="agent",
                        required_fields=["conflict_id", "agents_involved"],
                        description="Agent conflict detected"),

            # Data governance events
            EventSchema("data.classified", category="data",
                        required_fields=["data_id", "sensitivity", "classifications"],
                        description="Data classified"),
            EventSchema("data.lifecycle.changed", category="data",
                        required_fields=["asset_id", "from_stage", "to_stage"],
                        description="Data lifecycle stage changed"),
            EventSchema("data.access.requested", category="data",
                        required_fields=["data_id", "requester", "purpose"],
                        description="Data access requested"),
            EventSchema("data.access.granted", category="data",
                        required_fields=["data_id", "requester"],
                        description="Data access granted"),
            EventSchema("data.access.denied", category="data",
                        required_fields=["data_id", "requester", "reason"],
                        description="Data access denied"),
            EventSchema("data.privacy.dsar_submitted", category="data",
                        required_fields=["dsar_id", "subject_id"],
                        description="DSAR submitted"),
            EventSchema("data.compliance.assessed", category="data",
                        required_fields=["framework", "controls_passed", "controls_total"],
                        description="Compliance assessment completed"),

            # Safety events
            EventSchema("safety.guardrail.triggered", category="safety",
                        required_fields=["guardrail_name", "content_hash", "result"],
                        description="Safety guardrail triggered"),
            EventSchema("safety.guardrail.blocked", category="safety",
                        required_fields=["guardrail_name", "content_hash", "reason"],
                        description="Content blocked by guardrail"),
            EventSchema("safety.incident.created", category="safety",
                        required_fields=["incident_id", "severity", "description"],
                        description="Safety incident created"),
            EventSchema("safety.incident.resolved", category="safety",
                        required_fields=["incident_id", "resolution"],
                        description="Safety incident resolved"),
            EventSchema("safety.evaluation.completed", category="safety",
                        required_fields=["eval_id", "model_id", "score"],
                        description="AI safety evaluation completed"),
            EventSchema("safety.alert.triggered", category="safety",
                        required_fields=["alert_id", "alert_type", "severity"],
                        description="Safety alert triggered"),

            # Knowledge graph events
            EventSchema("knowledge.entity.created", category="knowledge",
                        required_fields=["entity_id", "entity_type", "name"],
                        description="Knowledge graph entity created"),
            EventSchema("knowledge.entity.updated", category="knowledge",
                        required_fields=["entity_id"],
                        description="Knowledge graph entity updated"),
            EventSchema("knowledge.relationship.created", category="knowledge",
                        required_fields=["source_id", "target_id", "rel_type"],
                        description="Knowledge graph relationship created"),
            EventSchema("knowledge.contradiction.detected", category="knowledge",
                        required_fields=["entity_id", "contradicting_sources"],
                        description="Knowledge contradiction detected"),
            EventSchema("knowledge.contradiction.resolved", category="knowledge",
                        required_fields=["entity_id", "resolution_strategy"],
                        description="Knowledge contradiction resolved"),
            EventSchema("knowledge.ingestion.completed", category="knowledge",
                        required_fields=["source", "entities_ingested"],
                        description="Knowledge ingestion completed"),

            # Release events
            EventSchema("release.deploy.started", category="release",
                        required_fields=["release_id", "strategy", "target"],
                        description="Deployment started"),
            EventSchema("release.deploy.completed", category="release",
                        required_fields=["release_id", "duration_seconds"],
                        description="Deployment completed"),
            EventSchema("release.deploy.rolled_back", category="release",
                        required_fields=["release_id", "reason"],
                        description="Deployment rolled back"),
            EventSchema("release.gate.passed", category="release",
                        required_fields=["release_id", "gate_name"],
                        description="Release gate passed"),
            EventSchema("release.gate.failed", category="release",
                        required_fields=["release_id", "gate_name", "reason"],
                        description="Release gate failed"),
            EventSchema("release.change.approved", category="release",
                        required_fields=["change_id", "approver"],
                        description="Change request approved"),
            EventSchema("release.change.rejected", category="release",
                        required_fields=["change_id", "approver", "reason"],
                        description="Change request rejected"),

            # Customer experience events
            EventSchema("cx.ticket.created", category="customer",
                        required_fields=["ticket_id", "customer_id", "severity"],
                        description="Support ticket created"),
            EventSchema("cx.ticket.resolved", category="customer",
                        required_fields=["ticket_id", "resolution"],
                        description="Support ticket resolved"),
            EventSchema("cx.feedback.received", category="customer",
                        required_fields=["feedback_id", "source", "sentiment"],
                        description="Customer feedback received"),

            # Innovation events
            EventSchema("innovation.experiment.started", category="innovation",
                        required_fields=["experiment_id", "hypothesis"],
                        description="Experiment started"),
            EventSchema("innovation.experiment.completed", category="innovation",
                        required_fields=["experiment_id", "outcome"],
                        description="Experiment completed"),
            EventSchema("innovation.ip.registered", category="innovation",
                        required_fields=["ip_id", "category", "title"],
                        description="IP asset registered"),

            # Disaster recovery events
            EventSchema("dr.backup.started", category="dr",
                        required_fields=["backup_id", "target"],
                        description="Backup started"),
            EventSchema("dr.backup.completed", category="dr",
                        required_fields=["backup_id", "size_bytes", "duration"],
                        description="Backup completed"),
            EventSchema("dr.backup.failed", category="dr",
                        required_fields=["backup_id", "error"],
                        description="Backup failed"),
            EventSchema("dr.recovery.initiated", category="dr",
                        required_fields=["recovery_id", "plan", "mode"],
                        description="Recovery initiated"),
            EventSchema("dr.exercise.scheduled", category="dr",
                        required_fields=["exercise_id", "exercise_type", "scheduled_date"],
                        description="DR exercise scheduled"),
            EventSchema("dr.crisis.activated", category="dr",
                        required_fields=["crisis_id", "severity", "team"],
                        description="Crisis response activated"),
            EventSchema("dr.crisis.deactivated", category="dr",
                        required_fields=["crisis_id", "resolution"],
                        description="Crisis response deactivated"),
        ]

        for schema in schemas:
            self.register_schema(schema)

    def register_schema(self, schema: EventSchema):
        """Register an event schema."""
        with self._lock:
            self._schemas[schema.event_type] = schema

    def get_schema(self, event_type: str) -> Optional[EventSchema]:
        """Get a registered event schema."""
        return self._schemas.get(event_type)

    def list_schemas(self) -> Dict[str, Dict[str, Any]]:
        """List all registered schemas."""
        return {
            et: {
                "version": s.version,
                "description": s.description,
                "category": s.category,
                "required_fields": s.required_fields,
            }
            for et, s in self._schemas.items()
        }

    # ── Subscription Management ──────────────────────────────────────────

    def subscribe(self, subscription: EventSubscription):
        """Register an event subscription."""
        with self._lock:
            self._subscriptions[subscription.subscription_id] = subscription
            self._delivery_semaphore[subscription.subscription_id] = asyncio.Semaphore(
                subscription.max_concurrency
            )
        logger.info(
            "Subscription %s registered for module %s (%d patterns)",
            subscription.subscription_id,
            subscription.module_name,
            len(subscription.event_patterns),
        )

    def unsubscribe(self, subscription_id: str):
        """Remove an event subscription."""
        with self._lock:
            sub = self._subscriptions.pop(subscription_id, None)
            self._delivery_semaphore.pop(subscription_id, None)
        if sub:
            logger.info("Subscription %s removed (module: %s)", subscription_id, sub.module_name)

    def get_subscriptions(self, event_type: str) -> List[EventSubscription]:
        """Get all active subscriptions matching an event type."""
        matching = []
        with self._lock:
            for sub in self._subscriptions.values():
                if sub.active and sub.matches(event_type):
                    matching.append(sub)
        return matching

    def list_subscriptions(self) -> List[Dict[str, Any]]:
        """List all subscriptions."""
        with self._lock:
            return [
                {
                    "subscription_id": s.subscription_id,
                    "module_name": s.module_name,
                    "event_patterns": s.event_patterns,
                    "active": s.active,
                    "max_concurrency": s.max_concurrency,
                }
                for s in self._subscriptions.values()
            ]

    # ── Contract Management ──────────────────────────────────────────────

    def register_contract(self, contract: EventContract):
        """Register a module-to-module communication contract."""
        with self._lock:
            self._contracts[contract.contract_id] = contract
        logger.info(
            "Contract %s: %s → %s (%d event types)",
            contract.contract_id,
            contract.producer_module,
            contract.consumer_module,
            len(contract.event_types),
        )

    def get_contracts(self, module_name: str) -> List[EventContract]:
        """Get all contracts involving a module."""
        with self._lock:
            return [
                c for c in self._contracts.values()
                if c.producer_module == module_name or c.consumer_module == module_name
            ]

    # ── Event Publishing ─────────────────────────────────────────────────

    async def publish(self, event_data: Dict[str, Any], wait: bool = False) -> str:
        """Publish an event to the hub.

        Args:
            event_data: Event data dict with at least event_type, source, payload
            wait: If True, wait for all subscribers to process before returning

        Returns:
            The event_id of the published event.
        """
        # Create envelope
        envelope = EventEnvelope(
            event_type=event_data.get("event_type", ""),
            source=event_data.get("source", "unknown"),
            payload=event_data.get("payload", {}),
            priority=EventPriority(event_data.get("priority", "medium")),
            correlation_id=event_data.get("correlation_id"),
            causation_id=event_data.get("causation_id"),
            headers=event_data.get("headers", {}),
            metadata=event_data.get("metadata", {}),
        )

        # Validate against schema
        schema = self._schemas.get(envelope.event_type)
        if schema:
            valid, errors = schema.validate(envelope.payload)
            if not valid:
                logger.warning(
                    "Event %s validation failed: %s",
                    envelope.event_type,
                    "; ".join(errors),
                )

        # Check TTL
        if envelope.is_expired:
            logger.warning("Event %s expired before publishing, dropping", envelope.event_id)
            envelope.status = EventStatus.DROPPED
            return envelope.event_id

        # Route to matching subscribers
        envelope.status = EventStatus.RECEIVED
        self._tracer.record(envelope)
        self._event_counter[envelope.event_type] += 1

        matching_subs = self.get_subscriptions(envelope.event_type)
        if not matching_subs:
            logger.debug("No subscribers for event type: %s", envelope.event_type)
            envelope.status = EventStatus.ROUTED
            return envelope.event_id

        # Queue for each matching subscriber
        tasks = []
        for sub in matching_subs:
            if sub.handler is None:
                continue
            # Check priority filter
            prio_order = {
                EventPriority.CRITICAL: 0,
                EventPriority.HIGH: 1,
                EventPriority.MEDIUM: 2,
                EventPriority.LOW: 3,
            }
            if prio_order[envelope.priority] > prio_order[sub.priority]:
                continue
            tasks.append(self._deliver_to_subscriber(sub, envelope))

        envelope.status = EventStatus.ROUTED

        if wait and tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

        return envelope.event_id

    async def _deliver_to_subscriber(self, sub: EventSubscription, envelope: EventEnvelope):
        """Deliver an event to a single subscriber with retry and dead-lettering."""
        sem = self._delivery_semaphore.get(sub.subscription_id)
        if sem is None:
            return

        async with sem:
            for attempt in range(envelope.max_retries + 1):
                try:
                    envelope.retry_count = attempt
                    await sub.handler(envelope)  # type: ignore[misc]
                    envelope.status = EventStatus.DELIVERED
                    self._tracer.record(envelope)
                    return
                except Exception as exc:
                    logger.error(
                        "Delivery attempt %d/%d failed for event %s to %s: %s",
                        attempt + 1,
                        envelope.max_retries,
                        envelope.event_id,
                        sub.module_name,
                        exc,
                    )
                    if attempt < envelope.max_retries:
                        await asyncio.sleep(min(2 ** attempt, 30))  # Exponential backoff
                    else:
                        if sub.dead_letter_on_failure:
                            self._dlq.enqueue(envelope, str(exc))
                        envelope.status = EventStatus.FAILED
                        self._tracer.record(envelope)

    # ── Worker Management ────────────────────────────────────────────────

    async def start(self):
        """Start the event bus worker pool."""
        self._running = True
        self._workers = [
            asyncio.create_task(self._worker(i)) for i in range(self.worker_count)
        ]
        logger.info("EventBus started with %d workers", self.worker_count)

    async def stop(self):
        """Stop the event bus gracefully."""
        self._running = False
        for worker in self._workers:
            worker.cancel()
        if self._workers:
            await asyncio.gather(*self._workers, return_exceptions=True)
        self._workers.clear()
        logger.info("EventBus stopped")

    async def _worker(self, worker_id: int):
        """Background worker that processes events from priority queues."""
        while self._running:
            try:
                # Process events in priority order
                event = None
                for priority in EventPriority:
                    try:
                        event = self._priority_queues[priority].get_nowait()
                        break
                    except asyncio.QueueEmpty:
                        continue

                if event is None:
                    await asyncio.sleep(0.01)
                    continue

                # Process the event
                await self._process_event(event)

            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Worker %d error", worker_id)

    async def _process_event(self, event: EventEnvelope):
        """Process a dequeued event."""
        matching_subs = self.get_subscriptions(event.event_type)
        tasks = [self._deliver_to_subscriber(sub, event) for sub in matching_subs if sub.handler]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    # ── Dead Letter Queue ────────────────────────────────────────────────

    def get_dead_letters(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Get dead-lettered events."""
        return [e.to_dict() for e in self._dlq.get_all(limit)]

    async def replay_dead_letter(self, event_id: str) -> bool:
        """Replay a dead-lettered event."""
        event = self._dlq.replay(event_id)
        if event:
            await self.publish(event.to_dict())
            return True
        return False

    # ── Tracing ──────────────────────────────────────────────────────────

    def get_trace(self, correlation_id: str) -> List[Dict[str, Any]]:
        """Get the distributed trace for a correlation ID."""
        return self._tracer.get_trace(correlation_id)

    # ── Stats ────────────────────────────────────────────────────────────

    def get_stats(self) -> Dict[str, Any]:
        """Get event hub statistics."""
        with self._lock:
            return {
                "total_events": sum(self._event_counter.values()),
                "event_types_count": len(self._event_counter),
                "schemas_registered": len(self._schemas),
                "subscriptions_active": sum(1 for s in self._subscriptions.values() if s.active),
                "contracts_registered": len(self._contracts),
                "dead_letter_count": self._dlq.size,
                "workers": self.worker_count,
                "running": self._running,
            }


# ---------------------------------------------------------------------------
# Synchronous Event Publisher (for non-async callers)
# ---------------------------------------------------------------------------


class SyncEventPublisher:
    """Synchronous event publisher that bridges sync code to the async EventBus.

    Used by the kernel and non-async modules to publish events without
    needing an asyncio event loop in their calling context.
    """

    def __init__(self, event_bus: EventBus):
        self._event_bus = event_bus
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._ready = threading.Event()

    def start(self):
        """Start the background event loop thread."""
        def run_loop():
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)
            self._ready.set()
            self._loop.run_forever()

        self._thread = threading.Thread(target=run_loop, daemon=True, name="event-publisher")
        self._thread.start()
        self._ready.wait()

    def stop(self):
        """Stop the background event loop."""
        if self._loop and self._loop.is_running():
            self._loop.call_soon_threadsafe(self._loop.stop)
        if self._thread:
            self._thread.join(timeout=5)

    def publish(self, event_data: Dict[str, Any]) -> str:
        """Publish an event synchronously (fire-and-forget)."""
        if self._loop is None:
            logger.warning("SyncEventPublisher not started; event dropped")
            return ""

        event_id = str(uuid.uuid4())
        asyncio.run_coroutine_threadsafe(
            self._event_bus.publish(event_data), self._loop
        )
        return event_id


# ---------------------------------------------------------------------------
# Singleton Access
# ---------------------------------------------------------------------------

_event_bus_instance: Optional[EventBus] = None
_sync_publisher_instance: Optional[SyncEventPublisher] = None


def get_event_hub() -> EventBus:
    """Get the singleton EventBus instance."""
    global _event_bus_instance
    if _event_bus_instance is None:
        _event_bus_instance = EventBus()
    return _event_bus_instance


def get_sync_publisher() -> SyncEventPublisher:
    """Get the singleton SyncEventPublisher instance."""
    global _sync_publisher_instance
    if _sync_publisher_instance is None:
        hub = get_event_hub()
        _sync_publisher_instance = SyncEventPublisher(hub)
        _sync_publisher_instance.start()
    return _sync_publisher_instance


# ---------------------------------------------------------------------------
# Convenience: publish an event without importing EventBus directly
# ---------------------------------------------------------------------------


def publish_event(
    event_type: str,
    source: str,
    payload: Dict[str, Any],
    priority: str = "medium",
    correlation_id: Optional[str] = None,
) -> str:
    """Convenience function to publish an event synchronously.

    Example:
        >>> publish_event("safety.guardrail.triggered", "safety_governance",
        ...               {"guardrail_name": "toxicity", "result": "passed"})
    """
    publisher = get_sync_publisher()
    return publisher.publish({
        "event_type": event_type,
        "source": source,
        "payload": payload,
        "priority": priority,
        "correlation_id": correlation_id,
    })


# ---------------------------------------------------------------------------
# Pre-built module contracts
# ---------------------------------------------------------------------------


def create_standard_contracts() -> List[EventContract]:
    """Create the standard set of module-to-module communication contracts.

    These define the formal event interfaces between all enterprise modules.
    """
    return [
        EventContract(
            producer_module="safety_governance",
            consumer_module="kernel",
            event_types=["safety.guardrail.triggered", "safety.incident.created"],
            direction=ContractDirection.PRODUCES,
            description="Safety module reports guardrail triggers and incidents to kernel",
        ),
        EventContract(
            producer_module="safety_governance",
            consumer_module="release_change",
            event_types=["safety.guardrail.blocked", "safety.evaluation.completed"],
            direction=ContractDirection.PRODUCES,
            description="Safety evaluation results feed into release quality gates",
        ),
        EventContract(
            producer_module="privacy_data",
            consumer_module="kernel",
            event_types=["data.classified", "data.access.granted", "data.access.denied"],
            direction=ContractDirection.PRODUCES,
            description="Privacy module reports data classification and access events",
        ),
        EventContract(
            producer_module="privacy_data",
            consumer_module="customer_experience",
            event_types=["data.privacy.dsar_submitted"],
            direction=ContractDirection.PRODUCES,
            description="DSAR submissions flow from CX to privacy module",
        ),
        EventContract(
            producer_module="knowledge_graph",
            consumer_module="prompt_context",
            event_types=["knowledge.entity.created", "knowledge.relationship.created"],
            direction=ContractDirection.PRODUCES,
            description="Knowledge graph updates feed prompt context enrichment",
        ),
        EventContract(
            producer_module="agent_coordination",
            consumer_module="kernel",
            event_types=["agent.task.created", "agent.task.completed", "agent.task.failed"],
            direction=ContractDirection.PRODUCES,
            description="Agent task lifecycle reported to kernel",
        ),
        EventContract(
            producer_module="release_change",
            consumer_module="kernel",
            event_types=["release.deploy.started", "release.deploy.completed", "release.gate.failed"],
            direction=ContractDirection.PRODUCES,
            description="Release events reported to kernel for audit",
        ),
        EventContract(
            producer_module="release_change",
            consumer_module="disaster_recovery",
            event_types=["release.deploy.started", "release.deploy.completed"],
            direction=ContractDirection.PRODUCES,
            description="Deployment events trigger DR backup pre/post hooks",
        ),
        EventContract(
            producer_module="disaster_recovery",
            consumer_module="kernel",
            event_types=["dr.backup.completed", "dr.backup.failed", "dr.crisis.activated"],
            direction=ContractDirection.PRODUCES,
            description="DR events reported to kernel",
        ),
        EventContract(
            producer_module="disaster_recovery",
            consumer_module="safety_governance",
            event_types=["dr.crisis.activated", "dr.crisis.deactivated"],
            direction=ContractDirection.PRODUCES,
            description="Crisis events trigger safety incident creation",
        ),
        EventContract(
            producer_module="innovation_rd",
            consumer_module="knowledge_graph",
            event_types=["innovation.ip.registered"],
            direction=ContractDirection.PRODUCES,
            description="IP registrations create knowledge graph entities",
        ),
        EventContract(
            producer_module="customer_experience",
            consumer_module="developer_experience",
            event_types=["cx.feedback.received"],
            direction=ContractDirection.PRODUCES,
            description="Customer feedback feeds into developer experience metrics",
        ),
        EventContract(
            producer_module="customer_experience",
            consumer_module="safety_governance",
            event_types=["cx.ticket.created"],
            direction=ContractDirection.PRODUCES,
            description="High-severity tickets may trigger safety incident creation",
        ),
    ]