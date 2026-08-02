"""
Enterprise-Grade Structured Communication Protocol for Agent Coordination.

This module provides a complete messaging infrastructure for inter-agent
communication within the OS. It enforces structured, concise, actionable,
versioned, auditable, and traceable messages with full threading support.

Classes:
    CompletionStatus: Enum for message lifecycle states.
    Priority: Enum for message priority levels.
    Message: Dataclass representing a structured agent message.
    MessageValidation: Static validation utilities for Message objects.
    MessageVersionTracker: Tracks versioned history of messages by ID.
    AuditTrail: Immutable, timestamped record of all message events.
    MessageBus: Central router for registering agents and routing messages.
"""

from __future__ import annotations

import heapq
import json
import threading
from collections import defaultdict
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple
from uuid import UUID, uuid4


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class CompletionStatus(str, Enum):
    """Lifecycle state of a message's associated work item."""

    PENDING = "pending"
    ACKNOWLEDGED = "acknowledged"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    BLOCKED = "blocked"


class Priority(str, Enum):
    """Priority levels for messages."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    BEST_EFFORT = "best_effort"


# ---------------------------------------------------------------------------
# Message Dataclass
# ---------------------------------------------------------------------------


@dataclass
class Message:
    """A structured, versioned, auditable message between agents.

    Every message in the system is immutable after creation.  Threading is
    achieved via ``parent_message_id``, which chains replies into a tree.

    Attributes:
        message_id: Universally unique identifier (UUID v4).
        task_id: Optional identifier of the parent task this message relates to.
        sender_id: Identifier of the sending agent.
        receiver_id: Identifier of the target agent, or ``"broadcast"``.
        timestamp: UTC-aware creation timestamp.
        objective: Short, actionable description of what is being requested.
        required_inputs: Data / artefacts the receiver needs to act.
        required_outputs: Expected deliverables from the receiver.
        dependencies: IDs of other tasks / messages that must complete first.
        confidence_level: 0.0 (no confidence) to 1.0 (absolute certainty).
        assumptions: Explicit assumptions the sender is operating under.
        risks: Known risks or failure modes.
        evidence: Supporting data or references backing the message content.
        completion_status: Current lifecycle state.
        version: Monotonically increasing version number (1-indexed).
        parent_message_id: For threading — the message this one replies to.
        priority: Urgency of the message.
    """

    message_id: UUID = field(default_factory=uuid4)
    task_id: Optional[str] = None
    sender_id: str = ""
    receiver_id: str = ""
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    objective: str = ""
    required_inputs: List[str] = field(default_factory=list)
    required_outputs: List[str] = field(default_factory=list)
    dependencies: List[str] = field(default_factory=list)
    confidence_level: float = 1.0
    assumptions: List[str] = field(default_factory=list)
    risks: List[str] = field(default_factory=list)
    evidence: List[str] = field(default_factory=list)
    completion_status: CompletionStatus = CompletionStatus.PENDING
    version: int = 1
    parent_message_id: Optional[UUID] = None
    priority: Priority = Priority.MEDIUM

    # ---- Serialization --------------------------------------------------

    def to_dict(self) -> Dict[str, Any]:
        """Return a JSON-serializable dictionary representation."""
        data: Dict[str, Any] = {
            "message_id": str(self.message_id),
            "task_id": self.task_id,
            "sender_id": self.sender_id,
            "receiver_id": self.receiver_id,
            "timestamp": self.timestamp.isoformat(),
            "objective": self.objective,
            "required_inputs": self.required_inputs,
            "required_outputs": self.required_outputs,
            "dependencies": self.dependencies,
            "confidence_level": self.confidence_level,
            "assumptions": self.assumptions,
            "risks": self.risks,
            "evidence": self.evidence,
            "completion_status": self.completion_status.value,
            "version": self.version,
            "parent_message_id": str(self.parent_message_id) if self.parent_message_id else None,
            "priority": self.priority.value,
        }
        return data

    def to_json(self, indent: int = 2) -> str:
        """Serialize to a JSON string."""
        return json.dumps(self.to_dict(), indent=indent, default=str)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Message":
        """Reconstitute a Message from a dictionary (e.g. JSON payload)."""
        return cls(
            message_id=UUID(data.get("message_id", str(uuid4()))),
            task_id=data.get("task_id"),
            sender_id=data.get("sender_id", ""),
            receiver_id=data.get("receiver_id", ""),
            timestamp=datetime.fromisoformat(data["timestamp"]) if "timestamp" in data else datetime.now(timezone.utc),
            objective=data.get("objective", ""),
            required_inputs=data.get("required_inputs", []),
            required_outputs=data.get("required_outputs", []),
            dependencies=data.get("dependencies", []),
            confidence_level=float(data.get("confidence_level", 1.0)),
            assumptions=data.get("assumptions", []),
            risks=data.get("risks", []),
            evidence=data.get("evidence", []),
            completion_status=CompletionStatus(data.get("completion_status", "pending")),
            version=int(data.get("version", 1)),
            parent_message_id=UUID(data["parent_message_id"]) if data.get("parent_message_id") else None,
            priority=Priority(data.get("priority", "medium")),
        )

    @classmethod
    def from_json(cls, json_str: str) -> "Message":
        """Reconstitute a Message from a JSON string."""
        return cls.from_dict(json.loads(json_str))


# ---------------------------------------------------------------------------
# Message Validation
# ---------------------------------------------------------------------------


class MessageValidation:
    """Static validation utilities for Message objects.

    All methods raise ``ValueError`` with a descriptive message when
    validation fails.
    """

    REQUIRED_FIELDS: Tuple[str, ...] = (
        "sender_id",
        "receiver_id",
        "objective",
    )

    @staticmethod
    def validate(message: Message) -> None:
        """Run all validation checks against *message*.

        Raises:
            ValueError: If any validation rule is violated.
        """
        MessageValidation._validate_required_fields(message)
        MessageValidation._validate_confidence(message)
        MessageValidation._validate_priority(message)
        MessageValidation._validate_timestamp(message)

    @staticmethod
    def _validate_required_fields(message: Message) -> None:
        """Ensure all mandatory string fields are non-empty."""
        for field_name in MessageValidation.REQUIRED_FIELDS:
            value = getattr(message, field_name, None)
            if not value or (isinstance(value, str) and not value.strip()):
                raise ValueError(
                    f"Message validation failed: '{field_name}' is required and must be non-empty."
                )

    @staticmethod
    def _validate_confidence(message: Message) -> None:
        """Confidence must be in [0.0, 1.0]."""
        if not (0.0 <= message.confidence_level <= 1.0):
            raise ValueError(
                f"Confidence level must be between 0.0 and 1.0, got {message.confidence_level}."
            )

    @staticmethod
    def _validate_priority(message: Message) -> None:
        """Priority must be a valid enum value."""
        if not isinstance(message.priority, Priority):
            raise ValueError(f"Invalid priority value: {message.priority}.")

    @staticmethod
    def _validate_timestamp(message: Message) -> None:
        """Timestamp must be timezone-aware (UTC)."""
        if message.timestamp.tzinfo is None:
            raise ValueError("Message timestamp must be timezone-aware (UTC).")

    @staticmethod
    def validate_agent_registered(agent_id: str, registered_agents: Set[str]) -> None:
        """Ensure *agent_id* is registered before sending."""
        if agent_id not in registered_agents:
            raise ValueError(
                f"Agent '{agent_id}' is not registered with the message bus."
            )


# ---------------------------------------------------------------------------
# Message Version Tracker
# ---------------------------------------------------------------------------


class MessageVersionTracker:
    """Tracks versioned history of messages keyed by ``message_id``.

    Each message ID maps to an ordered list of versions (oldest first).
    The tracker is thread-safe.
    """

    def __init__(self) -> None:
        """Initialise an empty version tracker."""
        self._versions: Dict[UUID, List[Message]] = defaultdict(list)
        self._lock: threading.Lock = threading.Lock()

    def record(self, message: Message) -> None:
        """Append *message* to the version chain for its ``message_id``."""
        with self._lock:
            self._versions[message.message_id].append(message)

    def get_history(self, message_id: UUID) -> List[Message]:
        """Return all recorded versions for *message_id* (oldest first)."""
        with self._lock:
            return list(self._versions.get(message_id, []))

    def get_latest(self, message_id: UUID) -> Optional[Message]:
        """Return the most recent version of *message_id*, or ``None``."""
        history = self.get_history(message_id)
        return history[-1] if history else None

    def version_count(self, message_id: UUID) -> int:
        """Return the number of recorded versions for *message_id*."""
        return len(self.get_history(message_id))


# ---------------------------------------------------------------------------
# Audit Trail
# ---------------------------------------------------------------------------


@dataclass
class AuditEntry:
    """An immutable, timestamped record of a message event.

    Attributes:
        timestamp: UTC moment the event was recorded.
        event: Description of what happened (e.g. 'sent', 'delivered',
            'acknowledged', 'failed', 'versioned').
        message_id: The message this entry refers to.
        details: Optional free-form metadata about the event.
    """

    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    event: str = ""
    message_id: Optional[UUID] = None
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp.isoformat(),
            "event": self.event,
            "message_id": str(self.message_id) if self.message_id else None,
            "details": self.details,
        }


class AuditTrail:
    """Complete, append-only, thread-safe audit log of message events.

    Every ``send``, ``broadcast``, version update, or error is recorded
    as an ``AuditEntry`` for full traceability.
    """

    def __init__(self) -> None:
        """Initialise an empty audit trail."""
        self._entries: List[AuditEntry] = []
        self._lock: threading.Lock = threading.Lock()

    def log(
        self,
        event: str,
        message_id: Optional[UUID] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> AuditEntry:
        """Record an event and return the created ``AuditEntry``."""
        entry = AuditEntry(
            timestamp=datetime.now(timezone.utc),
            event=event,
            message_id=message_id,
            details=details or {},
        )
        with self._lock:
            self._entries.append(entry)
        return entry

    def get_entries(self, message_id: Optional[UUID] = None) -> List[AuditEntry]:
        """Return all entries, optionally filtered by *message_id*."""
        with self._lock:
            if message_id is None:
                return list(self._entries)
            return [e for e in self._entries if e.message_id == message_id]

    def to_json(self, indent: int = 2) -> str:
        """Serialize the entire audit trail to JSON."""
        with self._lock:
            return json.dumps([e.to_dict() for e in self._entries], indent=indent, default=str)

    @property
    def total_events(self) -> int:
        """Total number of audit entries recorded."""
        with self._lock:
            return len(self._entries)


# ---------------------------------------------------------------------------
# Message Bus
# ---------------------------------------------------------------------------


class MessageBus:
    """Central message router for inter-agent communication.

    Agents must be registered before they can send or receive messages.
    The bus supports:
    - Point-to-point ``send()``
    - ``broadcast()`` to all registered agents
    - Threaded conversations via ``parent_message_id``
    - Full validation, versioning, and audit logging

    Example::

        bus = MessageBus()
        bus.register_agent("agent_alpha")
        bus.register_agent("agent_beta")

        msg = Message(
            sender_id="agent_alpha",
            receiver_id="agent_beta",
            objective="Analyse log file for anomalies",
            confidence_level=0.85,
        )
        bus.send(msg)

        inbox = bus.get_messages_for_agent("agent_beta")
        thread = bus.get_thread(msg.message_id)
    """

    def __init__(self) -> None:
        """Initialise the bus with empty agent registry and message queues."""
        self._agents: Set[str] = set()
        self._agent_lock: threading.Lock = threading.Lock()
        self._queues: Dict[str, List[Message]] = defaultdict(list)
        self._queue_lock: threading.Lock = threading.Lock()
        self._version_tracker: MessageVersionTracker = MessageVersionTracker()
        self._audit_trail: AuditTrail = AuditTrail()

    # -- Agent Management --------------------------------------------------

    def register_agent(self, agent_id: str) -> None:
        """Register an agent so it can participate in messaging.

        Idempotent — calling twice with the same ID is a no-op.
        """
        with self._agent_lock:
            if agent_id in self._agents:
                return
            self._agents.add(agent_id)
        self._audit_trail.log("agent_registered", details={"agent_id": agent_id})

    def unregister_agent(self, agent_id: str) -> None:
        """Remove an agent from the bus.  Queued messages are preserved."""
        with self._agent_lock:
            self._agents.discard(agent_id)
        self._audit_trail.log("agent_unregistered", details={"agent_id": agent_id})

    def is_agent_registered(self, agent_id: str) -> bool:
        """Return ``True`` if *agent_id* is currently registered."""
        with self._agent_lock:
            return agent_id in self._agents

    @property
    def registered_agents(self) -> Set[str]:
        """Return a snapshot of currently registered agent IDs."""
        with self._agent_lock:
            return set(self._agents)

    # -- Sending -----------------------------------------------------------

    def send(self, message: Message) -> None:
        """Validate, version, audit, and route *message* to its receiver.

        Raises:
            ValueError: If validation fails or the sender/receiver are not
                        registered (unless receiver is ``"broadcast"``).
        """
        # Validate the message structure
        MessageValidation.validate(message)

        # Validate sender and receiver are registered
        with self._agent_lock:
            registered = set(self._agents)

        MessageValidation.validate_agent_registered(message.sender_id, registered)

        if message.receiver_id != "broadcast":
            MessageValidation.validate_agent_registered(message.receiver_id, registered)

        # Record version
        self._version_tracker.record(message)

        # Route
        with self._queue_lock:
            if message.receiver_id == "broadcast":
                for agent_id in registered:
                    if agent_id != message.sender_id:  # Don't echo to self
                        self._queues[agent_id].append(message)
            else:
                self._queues[message.receiver_id].append(message)

        # Audit
        self._audit_trail.log(
            "message_sent",
            message_id=message.message_id,
            details={
                "sender": message.sender_id,
                "receiver": message.receiver_id,
                "objective": message.objective,
                "version": message.version,
            },
        )

    def broadcast(self, message: Message) -> None:
        """Convenience method — set receiver to 'broadcast' and send."""
        message.receiver_id = "broadcast"
        self.send(message)

    # -- Receiving ---------------------------------------------------------

    def get_messages_for_agent(
        self, agent_id: str, mark_read: bool = True
    ) -> List[Message]:
        """Return all queued messages for *agent_id*.

        Args:
            agent_id: The agent whose inbox to fetch.
            mark_read: If ``True`` (default), the messages are removed from
                       the queue after retrieval.
        """
        with self._queue_lock:
            messages = list(self._queues.get(agent_id, []))
            if mark_read:
                self._queues[agent_id] = []
        for msg in messages:
            self._audit_trail.log(
                "message_delivered",
                message_id=msg.message_id,
                details={"receiver": agent_id},
            )
        return messages

    def peek_messages_for_agent(self, agent_id: str) -> List[Message]:
        """Return queued messages without removing them (non-destructive)."""
        with self._queue_lock:
            return list(self._queues.get(agent_id, []))

    # -- Threading ---------------------------------------------------------

    def get_thread(self, root_message_id: UUID) -> List[Message]:
        """Return all messages in the thread rooted at *root_message_id*.

        A thread consists of the root message and every message whose
        ``parent_message_id`` chain leads back to it.  This performs a
        breadth-first traversal of the message graph.
        """
        thread_messages: List[Message] = []
        visited: Set[UUID] = set()
        queue: List[UUID] = [root_message_id]

        while queue:
            current_id = queue.pop(0)
            if current_id in visited:
                continue
            visited.add(current_id)

            # Find the root message from version tracker
            root_msg = self._version_tracker.get_latest(current_id)
            if root_msg:
                thread_messages.append(root_msg)

            # Find all replies
            with self._queue_lock:
                for agent_queue in self._queues.values():
                    for msg in agent_queue:
                        if (
                            msg.parent_message_id == current_id
                            and msg.message_id not in visited
                        ):
                            queue.append(msg.message_id)

            # Also scan version tracker for messages with matching parent
            with self._version_tracker._lock:
                for msg_id, versions in self._version_tracker._versions.items():
                    latest = versions[-1]
                    if (
                        latest.parent_message_id == current_id
                        and msg_id not in visited
                    ):
                        queue.append(msg_id)

        return thread_messages

    def reply(
        self,
        original: Message,
        sender_id: str,
        objective: str,
        **kwargs: Any,
    ) -> Message:
        """Create and send a reply to *original*, maintaining the thread.

        Args:
            original: The message being replied to.
            sender_id: Agent sending the reply (should be the original
                       receiver).
            objective: Short description of the reply.
            **kwargs: Any additional ``Message`` constructor arguments.

        Returns:
            The newly created and sent reply message.
        """
        reply_msg = Message(
            sender_id=sender_id,
            receiver_id=original.sender_id,
            objective=objective,
            parent_message_id=original.message_id,
            version=1,
            **kwargs,
        )
        self.send(reply_msg)
        return reply_msg

    # -- Versioning & Audit ------------------------------------------------

    @property
    def version_tracker(self) -> MessageVersionTracker:
        """Access the internal version tracker."""
        return self._version_tracker

    @property
    def audit_trail(self) -> AuditTrail:
        """Access the internal audit trail."""
        return self._audit_trail


# ---------------------------------------------------------------------------
# Priority-aware Message Queue (helper)
# ---------------------------------------------------------------------------


class PriorityMessageQueue:
    """A thread-safe priority queue specialised for Messages.

    Messages are ordered by priority (critical first) and, within the same
    priority, by timestamp (oldest first).
    """

    _PRIORITY_ORDER: Dict[Priority, int] = {
        Priority.CRITICAL: 0,
        Priority.HIGH: 1,
        Priority.MEDIUM: 2,
        Priority.LOW: 3,
        Priority.BEST_EFFORT: 4,
    }

    def __init__(self) -> None:
        """Initialise an empty priority queue."""
        self._heap: List[Tuple[int, float, int, Message]] = []
        self._counter: int = 0
        self._lock: threading.Lock = threading.Lock()

    def push(self, message: Message) -> None:
        """Push a message onto the queue."""
        priority_rank = self._PRIORITY_ORDER.get(message.priority, 2)
        # Negate timestamp so that earlier timestamps sort first
        ts = -message.timestamp.timestamp()
        with self._lock:
            self._counter += 1
            heapq.heappush(self._heap, (priority_rank, ts, self._counter, message))

    def pop(self) -> Optional[Message]:
        """Pop the highest-priority message, or ``None`` if empty."""
        with self._lock:
            if not self._heap:
                return None
            return heapq.heappop(self._heap)[3]

    def peek(self) -> Optional[Message]:
        """Return the highest-priority message without removing it."""
        with self._lock:
            if not self._heap:
                return None
            return self._heap[0][3]

    @property
    def size(self) -> int:
        """Number of messages currently in the queue."""
        with self._lock:
            return len(self._heap)

    @property
    def is_empty(self) -> bool:
        """``True`` if the queue contains no messages."""
        return self.size == 0

    def drain(self) -> List[Message]:
        """Remove and return all messages in priority order."""
        with self._lock:
            items = [heapq.heappop(self._heap)[3] for _ in range(len(self._heap))]
        return items