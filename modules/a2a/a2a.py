"""A2A Core -- Agent-to-Agent protocol (stdlib only).

ENI-first implementation of the Google A2A exchange model with zero external
dependencies. Provides the wire-shaped data primitives (AgentCard, AgentKey,
MessagePart, Message) and in-memory orchestration state (TaskState, Task,
TaskManager, AgentRegistry, A2AExchange, handoff helpers and A2AFacade).
"""

import json
import logging
import os
import sqlite3
import threading
import uuid
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Deque, Dict, List, Optional

__all__ = [
    "AgentCard",
    "AgentKey",
    "AgentRegistry",
    "A2AExchange",
    "A2AFacade",
    "A2AError",
    "AgentNotFoundError",
    "NoAgentForCapabilityError",
    "InMemoryTransport",
    "Message",
    "MessagePart",
    "MessageRole",
    "RouteResult",
    "Task",
    "TaskManager",
    "TaskRouter",
    "TaskState",
    "TaskStore",
    "decode_artifact",
    "decode_message",
    "decode_sse",
    "decode_task",
    "encode_artifact",
    "encode_message",
    "encode_sse",
    "encode_task",
    "handoff",
]

_logger = logging.getLogger("enterprise.a2a")

# ============================================================ Errors

class A2AError(Exception):
    """Base error for all A2A protocol violations."""

class TaskNotFoundError(A2AError, KeyError):
    """Raised when a task id cannot be resolved."""

class InvalidTransitionError(A2AError):
    """Raised when a task tries to move to a disallowed state."""

class AgentNotRegisteredError(A2AError):
    """Raised when an operation references an unknown agent card."""


class AgentNotFoundError(A2AError, KeyError):
    """Raised when a required agent cannot be resolved by id or name."""


class NoAgentForCapabilityError(A2AError, KeyError):
    """Raised when no registered agent offers a required capability."""


class TaskStoreError(A2AError):
    """Raised when the SQLite-backed TaskStore cannot operate (I/O, schema)."""

# ============================================================ Small helpers

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def _new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:16]}"

def _copy_mapping(value: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Best-effort deep copy so callers can't alias the stored mapping."""
    if value is None:
        return {}
    try:
        return json.loads(json.dumps(value))
    except (TypeError, ValueError):
        return dict(value)

# ============================================================ Enums

class TaskState(Enum):
    """Life-cycle of an A2A task."""

    SUBMITTED = "submitted"
    WORKING = "working"
    INPUT_REQUIRED = "input-required"
    COMPLETED = "completed"
    CANCELED = "canceled"
    FAILED = "failed"
    def can_transition_to(self, target: "TaskState") -> bool:
        """Return True if moving from this state to ``target`` is allowed."""
        return target in _TASK_TRANSITIONS.get(self, [])

# Module-level (NOT inside the Enum body: single-underscore names become Enum
# members and would shadow this dict).
_TASK_TRANSITIONS: Dict[TaskState, List[TaskState]] = {
    TaskState.SUBMITTED: [TaskState.WORKING, TaskState.INPUT_REQUIRED,
                          TaskState.COMPLETED, TaskState.CANCELED, TaskState.FAILED],
    TaskState.WORKING: [TaskState.INPUT_REQUIRED, TaskState.COMPLETED,
                        TaskState.CANCELED, TaskState.FAILED],
    TaskState.INPUT_REQUIRED: [TaskState.WORKING, TaskState.COMPLETED,
                               TaskState.CANCELED, TaskState.FAILED],
    TaskState.COMPLETED: [],
    TaskState.CANCELED: [],
    TaskState.FAILED: [TaskState.SUBMITTED],  # retry re-submits a failed task
}

class MessageRole(str, Enum):
    """Authoring role of a message."""

    AGENT = "agent"
    USER = "user"
    SYSTEM = "system"

class Cardinality(str, Enum):
    """Negotiated capability cardinality (A2A-style)."""

    SINGLE = "single"
    MULTIPLE = "multiple"

# ============================================================ Message primitives

@dataclass
class MessagePart:
    """One part of an A2A message (text by default; extensible via kind)."""

    text: str
    kind: str = "text"
    metadata: Dict[str, Any] = field(default_factory=dict)
    def to_dict(self) -> Dict[str, Any]:
        return {"kind": self.kind, "text": self.text, "metadata": dict(self.metadata)}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MessagePart":
        return cls(
            text=data.get("text", ""),
            kind=data.get("kind", "text"),
            metadata=dict(data.get("metadata") or {}),
        )

    @classmethod
    def text_part(cls, text: str) -> "MessagePart":
        return cls(text=text, kind="text")

@dataclass
class Message:
    """An A2A message exchange envelope."""

    message_id: str
    role: MessageRole
    parts: List[MessagePart] = field(default_factory=list)
    timestamp: str = field(default_factory=_now_iso)
    context: Dict[str, Any] = field(default_factory=dict)
    def to_dict(self) -> Dict[str, Any]:
        return {
            "messageId": self.message_id, "role": self.role.value,
            "parts": [p.to_dict() for p in self.parts], "timestamp": self.timestamp,
            "context": dict(self.context),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Message":
        parts = [
            MessagePart.from_dict(p) if isinstance(p, dict) else p
            for p in data.get("parts", [])
        ]
        role_raw = data.get("role", "agent")
        role = role_raw if isinstance(role_raw, MessageRole) else MessageRole(role_raw)
        return cls(
            message_id=data["messageId"], role=role, parts=parts,
            timestamp=data.get("timestamp", _now_iso()),
            context=dict(data.get("context") or {}),
        )

    @classmethod
    def user_text(cls, text: str, context: Optional[Dict[str, Any]] = None) -> "Message":
        return cls(
            message_id=_new_id("msg"),
            role=MessageRole.USER,
            parts=[MessagePart.text_part(text)],
            context=context or {},
        )
    def text(self) -> str:
        return "".join(p.text for p in self.parts)

# ============================================================ Agent primitives

@dataclass
class AgentCard:
    """Advertisement for an agent participating in the A2A network."""

    name: str
    description: str = ""
    url: str = ""
    version: str = "1.0.0"
    capabilities: List[str] = field(default_factory=list)
    skills: List[str] = field(default_factory=list)
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "url": self.url,
            "version": self.version,
            "capabilities": list(self.capabilities),
            "skills": list(self.skills),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AgentCard":
        return cls(
            name=data["name"],
            description=data.get("description", ""),
            url=data.get("url", ""),
            version=data.get("version", "1.0.0"),
            capabilities=list(data.get("capabilities") or []),
            skills=list(data.get("skills") or []),
        )

@dataclass
class AgentKey:
    """Stable address for an agent inside the ENI platform."""

    agent_id: str
    name: str = ""
    def to_dict(self) -> Dict[str, Any]:
        return {"agentId": self.agent_id, "name": self.name}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AgentKey":
        return cls(agent_id=data["agentId"], name=data.get("name", ""))

class AgentRegistry:
    """Thread-safe catalogue mapping agent ids to their AgentCard."""
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._cards: Dict[str, AgentCard] = {}
        self._by_name: Dict[str, str] = {}  # name -> agent_id
    def register(self, card: AgentCard) -> AgentKey:
        """Register (or refresh) a card, returning its AgentKey."""
        agent_id = _slug(card.name)
        with self._lock:
            self._cards[agent_id] = card
            self._by_name[card.name] = agent_id
        return AgentKey(agent_id=agent_id, name=card.name)
    def unregister(self, agent_id: str) -> bool:
        with self._lock:
            card = self._cards.pop(agent_id, None)
            if card is not None:
                self._by_name.pop(card.name, None)
                return True
            return False
    def get(self, agent_id: str) -> Optional[AgentCard]:
        with self._lock:
            return self._cards.get(agent_id)
    def resolve(self, ref: str) -> Optional[AgentKey]:
        """Resolve an agent id or agent name into an AgentKey (or None)."""
        with self._lock:
            if ref in self._cards:
                return AgentKey(agent_id=ref, name=self._cards[ref].name)
            name_ref = self._by_name.get(ref)
            if name_ref is not None:
                return AgentKey(agent_id=name_ref, name=self._cards[name_ref].name)
            return None
    def list(self) -> List[Dict[str, Any]]:
        """Return serialized cards, sorted by agent name."""
        with self._lock:
            return [
                c.to_dict()
                for _, c in sorted(self._cards.items(), key=lambda kv: kv[1].name)
            ]
    def as_keys(self) -> List[AgentKey]:
        with self._lock:
            return [
                AgentKey(agent_id=aid, name=c.name)
                for aid, c in self._cards.items()
            ]
    def count(self) -> int:
        with self._lock:
            return len(self._cards)
    def get_card(self, agent_id: str) -> Optional[AgentCard]:
        """Return the AgentCard for ``agent_id`` (or None if unknown)."""
        return self.get(agent_id)
    def agents_by_capability(self, capability: str) -> List[AgentCard]:
        """Return every registered card that offers ``capability`` (sorted)."""
        with self._lock:
            return sorted(
                (c for c in self._cards.values() if capability in c.capabilities),
                key=lambda c: c.name,
            )
    def agents_by_skill(self, skill: str) -> List[AgentCard]:
        """Return every registered card that lists ``skill`` (sorted)."""
        with self._lock:
            return sorted(
                (c for c in self._cards.values() if skill in c.skills),
                key=lambda c: c.name,
            )

def _slug(name: str) -> str:
    """Turn an agent name into a URL-friendly agent id."""
    out = []
    for ch in name.strip().lower():
        if ch.isalnum() or ch in "._-":
            out.append(ch)
        elif ch == " ":
            out.append("-")
    return "".join(out).strip("-.") or "agent"

# ============================================================ Task model

@dataclass
class Task:
    """A unit of work exchanged between agents."""

    task_id: str
    state: TaskState
    agent_id: str
    session_id: Optional[str] = None
    artifacts: List[Dict[str, Any]] = field(default_factory=list)
    messages: List[Message] = field(default_factory=list)
    context: Dict[str, Any] = field(default_factory=dict)
    idempotency_key: Optional[str] = None
    parent_task_id: Optional[str] = None
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)
    retries: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)
    def to_dict(self) -> Dict[str, Any]:
        d = {
            "taskId": self.task_id, "state": self.state.value, "agentId": self.agent_id,
            "sessionId": self.session_id, "artifacts": list(self.artifacts),
            "messages": [m.to_dict() for m in self.messages], "context": dict(self.context),
            "idempotencyKey": self.idempotency_key, "parentTaskId": self.parent_task_id,
            "createdAt": self.created_at, "updatedAt": self.updated_at,
            "retries": self.retries, "metadata": dict(self.metadata),
        }
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Task":
        return cls(
            task_id=data["taskId"], state=TaskState(data["state"]),
            agent_id=data["agentId"],
            session_id=data.get("sessionId"),
            artifacts=list(data.get("artifacts") or []),
            messages=[Message.from_dict(m) for m in data.get("messages", [])],
            context=dict(data.get("context") or {}),
            idempotency_key=data.get("idempotencyKey"),
            parent_task_id=data.get("parentTaskId"),
            created_at=data.get("createdAt", _now_iso()),
            updated_at=data.get("updatedAt", _now_iso()),
            retries=int(data.get("retries", 0)),
            metadata=dict(data.get("metadata") or {}),
        )

# ============================================================ TaskManager

class TaskManager:
    """Thread-safe, in-memory store for A2A tasks.

    Responsibilities: idempotent creation via idempotency keys; validated
    life-cycle transitions (rejecting invalid ones); message appending;
    bounded retries for re-submitting failed tasks; lookup / listing.
    """
    def __init__(self, max_tasks: int = 100000) -> None:
        self._lock = threading.RLock()
        self._tasks: Dict[str, Task] = {}
        self._by_idempotency: Dict[str, str] = {}
        self._max_tasks = max(1, int(max_tasks))
    def create_task(
        self,
        agent_id: str,
        message: Optional[Message] = None,
        *,
        idempotency_key: Optional[str] = None,
        parent_task_id: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        session_id: Optional[str] = None,
    ) -> Task:
        """Create a new task, idempotent when ``idempotency_key`` is supplied."""
        with self._lock:
            if len(self._tasks) >= self._max_tasks:
                raise A2AError(f"Task store is full ({self._max_tasks} tasks max)")
            if idempotency_key is not None:
                existing_id = self._by_idempotency.get(idempotency_key)
                if existing_id is not None:
                    return self._tasks[existing_id]
            task = Task(
                task_id=_new_id("task"),
                state=TaskState.SUBMITTED,
                agent_id=agent_id,
                session_id=session_id,
                messages=[message] if message is not None else [],
                context=_copy_mapping(context),
                idempotency_key=idempotency_key,
                parent_task_id=parent_task_id,
                metadata=_copy_mapping(metadata),
            )
            self._tasks[task.task_id] = task
            if idempotency_key is not None:
                self._by_idempotency[idempotency_key] = task.task_id
            return task
    def get_task(self, task_id: str) -> Task:
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None:
                raise TaskNotFoundError(f"Unknown task id: {task_id!r}")
            return task
    def has_task(self, task_id: str) -> bool:
        with self._lock:
            return task_id in self._tasks
    def list_tasks(
        self, agent_id: Optional[str] = None, state: Optional[TaskState] = None
    ) -> List[Task]:
        with self._lock:
            result = list(self._tasks.values())
        if agent_id is not None:
            result = [t for t in result if t.agent_id == agent_id]
        if state is not None:
            result = [t for t in result if t.state is state]
        return result
    def tasks_for_agent(self, agent_id: str) -> List[Task]:
        return self.list_tasks(agent_id=agent_id)
    def count(self) -> int:
        with self._lock:
            return len(self._tasks)
    def transition(self, task_id: str, new_state: TaskState) -> Task:
        """Move a task to ``new_state``, enforcing valid transitions."""
        with self._lock:
            task = self.get_task(task_id)
            if task.state is new_state:
                return task
            if not task.state.can_transition_to(new_state):
                raise InvalidTransitionError(
                    f"Illegal transition for task {task_id!r}: "
                    f"{task.state.value} -> {new_state.value}"
                )
            task.state = new_state
            task.updated_at = _now_iso()
            return task
    def add_message(self, task_id: str, message: Message) -> Message:
        with self._lock:
            task = self.get_task(task_id)
            if task.state in (TaskState.COMPLETED, TaskState.CANCELED):
                raise InvalidTransitionError(
                    f"Cannot append to task {task_id!r} in terminal state "
                    f"{task.state.value}"
                )
            task.messages.append(message)
            task.updated_at = _now_iso()
            return message
    def add_artifact(self, task_id: str, artifact: Dict[str, Any]) -> Dict[str, Any]:
        """Append an artifact (result payload) to a stored task."""
        with self._lock:
            task = self.get_task(task_id)
            if task.state in (TaskState.COMPLETED, TaskState.CANCELED):
                raise InvalidTransitionError(
                    f"Cannot add artifact to task {task_id!r} in terminal state "
                    f"{task.state.value}"
                )
            entry = dict(artifact)
            entry.setdefault("id", _new_id("art"))
            entry.setdefault("createdAt", _now_iso())
            task.artifacts.append(entry)
            task.updated_at = _now_iso()
            return entry
    def cancel(self, task_id: str) -> Task:
        return self.transition(task_id, TaskState.CANCELED)
    def complete(self, task_id: str) -> Task:
        return self.transition(task_id, TaskState.COMPLETED)
    def fail(self, task_id: str) -> Task:
        return self.transition(task_id, TaskState.FAILED)
    def mark_working(self, task_id: str) -> Task:
        return self.transition(task_id, TaskState.WORKING)
    def request_input(self, task_id: str) -> Task:
        return self.transition(task_id, TaskState.INPUT_REQUIRED)
    def retry(self, task_id: str, max_retries: int = 3) -> Task:
        """Re-submit a failed task, incrementing its retry counter."""
        with self._lock:
            task = self.get_task(task_id)
            if task.retries >= max_retries:
                raise A2AError(f"Task {task_id!r} exceeded max retries ({max_retries})")
            if task.state is not TaskState.FAILED:
                raise InvalidTransitionError(
                    f"Only failed tasks can be retried; task {task_id!r} is "
                    f"{task.state.value}"
                )
            task.retries += 1
            task.state = TaskState.SUBMITTED
            task.updated_at = _now_iso()
            return task
    def set_context(self, task_id: str, key: str, value: Any) -> Task:
        with self._lock:
            task = self.get_task(task_id)
            task.context[key] = value
            task.updated_at = _now_iso()
            return task

# ============================================================ Negotiation / exchange

class A2AExchange:
    """Handshake + negotiation helper between agents.

    Wraps an AgentRegistry plus a TaskManager to model the A2A flow: address an
    agent by key, negotiate capabilities, and route message payloads into tasks.
    """
    def __init__(
        self, registry: Optional[AgentRegistry] = None, tasks: Optional[TaskManager] = None
    ) -> None:
        self.registry = registry if registry is not None else AgentRegistry()
        self.tasks = tasks if tasks is not None else TaskManager()
    def negotiate(
        self, source: AgentKey, target: AgentKey, required_capability: Optional[str] = None
    ) -> Dict[str, Any]:
        """Produce a negotiation offer from ``source`` to ``target``."""
        target_card = self.registry.get(target.agent_id)
        if target_card is None:
            raise AgentNotRegisteredError(
                f"Negotiation target {target.agent_id!r} is not registered"
            )
        accepted = True
        reason = "capability matched"
        if required_capability is not None:
            matched = required_capability in target_card.capabilities
            accepted = matched
            reason = (
                "capability matched"
                if matched
                else f"capability {required_capability!r} not offered by target"
            )
        return {
            "offered": source.to_dict(),
            "targeted": target_card.to_dict(),
            "required_capability": required_capability,
            "accepted": accepted,
            "reason": reason,
        }
    def send_to_agent(
        self,
        source: AgentKey,
        target: AgentKey,
        message: Message,
        *,
        idempotency_key: Optional[str] = None,
        parent_task_id: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> Task:
        """Route a message from ``source`` to ``target`` as a new task."""
        if self.registry.get(target.agent_id) is None:
            raise AgentNotRegisteredError(
                f"Target agent {target.agent_id!r} is not registered"
            )
        joined_context = _copy_mapping(context)
        joined_context.setdefault("from", source.agent_id)
        return self.tasks.create_task(
            target.agent_id,
            message,
            idempotency_key=idempotency_key,
            parent_task_id=parent_task_id,
            context=joined_context,
        )

# ============================================================ Handoff

def handoff(
    exchange_or_registry: Any,
    tasks: Optional[TaskManager],
    parent_task: Task,
    target: AgentKey,
    message: Optional[Message] = None,
    *,
    context: Optional[Dict[str, Any]] = None,
    idempotency_key: Optional[str] = None,
) -> Task:
    """Hand a task off to another agent.

    Creates a child task for ``target`` linked to ``parent_task`` via
    ``parent_task_id`` and seeding its context from the parent's context
    (merged with any explicit ``context`` overrides).
    """
    registry = (
        exchange_or_registry.registry
        if isinstance(exchange_or_registry, A2AExchange)
        else exchange_or_registry
    )
    task_store = (
        exchange_or_registry.tasks if isinstance(exchange_or_registry, A2AExchange) else tasks
    )
    if task_store is None:
        task_store = TaskManager()
    if registry.get(target.agent_id) is None:
        raise AgentNotRegisteredError(
            f"Handoff target {target.agent_id!r} is not registered"
        )
    child_context = _copy_mapping(parent_task.context)
    child_context.update(_copy_mapping(context))
    child_context.setdefault("parent_task_id", parent_task.task_id)
    child_message = message
    if child_message is None:
        last = parent_task.messages[-1] if parent_task.messages else None
        child_message = Message.user_text(
            f"Handoff from {parent_task.task_id}"
            + (f": {last.text()}" if last else ""),
            context={"inherited_from": parent_task.task_id},
        )
    return task_store.create_task(
        target.agent_id,
        child_message,
        idempotency_key=idempotency_key,
        parent_task_id=parent_task.task_id,
        context=child_context,
        metadata={"handoff_from": parent_task.task_id},
    )

# ============================================================ Facade

class A2AFacade:
    """High-level entry point for the A2A protocol on the ENI platform.

    Combines an AgentRegistry, TaskManager and A2AExchange behind a simple API:

      * register_agent_card(card) -> AgentKey
      * list_agents() -> list[dict]
      * create_task(...) -> Task
      * get_task(task_id) -> Task
      * send_message(task_id, text_or_message, ...) -> Message
      * handoff(task_id, target, ...) -> Task
    """
    def __init__(
        self,
        registry: Optional[AgentRegistry] = None,
        tasks: Optional[TaskManager] = None,
    ) -> None:
        self.registry = registry if registry is not None else AgentRegistry()
        self.tasks = tasks if tasks is not None else TaskManager()
        self.exchange = A2AExchange(registry=self.registry, tasks=self.tasks)
    def register_agent_card(self, card: AgentCard) -> AgentKey:
        return self.registry.register(card)
    def unregister_agent(self, agent_id: str) -> bool:
        return self.registry.unregister(agent_id)
    def list_agents(self) -> List[Dict[str, Any]]:
        return self.registry.list()
    def resolve_agent(self, ref: str) -> Optional[AgentKey]:
        return self.registry.resolve(ref)
    def create_task(
        self,
        agent_ref: str,
        message: Optional[Any] = None,
        *,
        idempotency_key: Optional[str] = None,
        parent_task_id: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        session_id: Optional[str] = None,
    ) -> Task:
        """Create a task for the agent addressed by ``agent_ref``.

        ``message`` may be a Message, a plain string (auto-wrapped) or None.
        Idempotent when ``idempotency_key`` is supplied.
        """
        key = self._require_agent(agent_ref)
        return self.tasks.create_task(
            key.agent_id,
            _coerce_message(message),
            idempotency_key=idempotency_key,
            parent_task_id=parent_task_id,
            context=context,
            metadata=metadata,
            session_id=session_id,
        )
    def get_task(self, task_id: str) -> Task:
        return self.tasks.get_task(task_id)
    def list_tasks(
        self, agent_ref: Optional[str] = None, state: Optional[TaskState] = None
    ) -> List[Task]:
        agent_id = None
        if agent_ref is not None:
            key = self.registry.resolve(agent_ref)
            if key is not None:
                agent_id = key.agent_id
        return self.tasks.list_tasks(agent_id=agent_id, state=state)
    def send_message(
        self,
        task_id: str,
        message: Any,
        *,
        role: MessageRole = MessageRole.USER,
        context: Optional[Dict[str, Any]] = None,
    ) -> Message:
        """Append a message to an existing task (Message or plain string)."""
        if isinstance(message, Message):
            msg = message
        elif isinstance(message, str):
            msg = Message(
                message_id=_new_id("msg"),
                role=role,
                parts=[MessagePart.text_part(message)],
                context=context or {},
            )
        else:
            raise TypeError(
                f"message must be a str or Message, got {type(message).__name__}"
            )
        return self.tasks.add_message(task_id, msg)
    def transition(self, task_id: str, state: TaskState) -> Task:
        return self.tasks.transition(task_id, state)
    def complete_task(self, task_id: str) -> Task:
        return self.tasks.complete(task_id)
    def cancel_task(self, task_id: str) -> Task:
        return self.tasks.cancel(task_id)
    def handoff(
        self,
        task_id: str,
        target_ref: str,
        message: Any = None,
        *,
        context: Optional[Dict[str, Any]] = None,
        idempotency_key: Optional[str] = None,
    ) -> Task:
        """Hand the task identified by ``task_id`` off to ``target_ref``.

        Creates a child task whose parent_task_id points back at this parent
        and whose context inherits the parent's context (merged with overrides).
        """
        parent = self.tasks.get_task(task_id)
        target_key = self._require_agent(target_ref)
        child_context = _merged_context(parent.context, context)
        child_context.setdefault("parent_task_id", parent.task_id)
        return self.tasks.create_task(
            target_key.agent_id,
            _coerce_message(message),
            idempotency_key=idempotency_key,
            parent_task_id=parent.task_id,
            context=child_context,
            metadata={"handoff_from": parent.task_id},
        )
    def negotiate(
        self,
        source_ref: str,
        target_ref: str,
        required_capability: Optional[str] = None,
    ) -> Dict[str, Any]:
        source = self._require_agent(source_ref)
        target = self._require_agent(target_ref)
        return self.exchange.negotiate(source, target, required_capability)
    def _require_agent(self, agent_ref: str) -> AgentKey:
        key = self.registry.resolve(agent_ref)
        if key is None:
            raise AgentNotRegisteredError(
                f"Unknown agent: {agent_ref!r}. Register it first."
            )
        return key

def _coerce_message(message: Any) -> Optional[Message]:
    """Normalise a message argument into a Message or None."""
    if message is None or isinstance(message, Message):
        return message
    if isinstance(message, str):
        return Message.user_text(message)
    raise TypeError(f"message must be a str, Message or None, got {type(message).__name__}")

def _merged_context(
    parent_context: Dict[str, Any], overrides: Optional[Dict[str, Any]]
) -> Dict[str, Any]:
    merged = _copy_mapping(parent_context)
    merged.update(_copy_mapping(overrides))
    return merged


# ============================================================ SQLite TaskStore

_DEFAULT_TASK_DB = os.path.join("data", "a2a_tasks.db")


def _json_dumps(value: Any) -> str:
    return json.dumps(value, separators=(",", ":"))


def _json_loads(value: Optional[str], fallback: Any) -> Any:
    if value is None:
        return fallback
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return fallback


class TaskStore:
    """SQLite-backed, durable store for A2A tasks.

    Each task is persisted as one row (``id, session_id, agent_id, state,
    messages, artifacts, context, idempotency_key, parent_task_id,
    created_at, updated_at, retries, metadata``) with the JSON-ish columns
    stored as compact JSON text. The store enforces the same validated
    :class:`TaskState` life-cycle as :class:`TaskManager` but survives restarts:
    ``initialize()`` re-creates the schema if needed and reloads every
    persisted task back into memory. Every mutation is written through to the
    database immediately, so a crash between mutations never loses an accepted
    state change. When ``:memory:`` is used as the path the store behaves like
    a real backend for a single process but is not durable across restarts
    (useful for tests).
    """

    _SCHEMA = """
    CREATE TABLE IF NOT EXISTS tasks (
        id TEXT PRIMARY KEY,
        session_id TEXT,
        agent_id TEXT NOT NULL,
        state TEXT NOT NULL,
        messages TEXT NOT NULL,
        artifacts TEXT NOT NULL,
        context TEXT NOT NULL,
        idempotency_key TEXT,
        parent_task_id TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        retries INTEGER NOT NULL DEFAULT 0,
        metadata TEXT NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_tasks_agent ON tasks(agent_id);
    CREATE INDEX IF NOT EXISTS idx_tasks_state ON tasks(state);
    CREATE INDEX IF NOT EXISTS idx_tasks_session ON tasks(session_id);
    CREATE INDEX IF NOT EXISTS idx_tasks_idem ON tasks(idempotency_key);
    """

    def __init__(self, db_path: Optional[str] = None) -> None:
        self._db_path = str(db_path or _DEFAULT_TASK_DB)
        self._lock = threading.RLock()
        self._conn: Optional[sqlite3.Connection] = None
        self._tasks: Dict[str, Task] = {}
        self._by_idempotency: Dict[str, str] = {}

    # -- lifecycle ------------------------------------------------------

    @property
    def db_path(self) -> str:
        return self._db_path

    @property
    def is_open(self) -> bool:
        return self._conn is not None

    def initialize(self) -> "TaskStore":
        """Open the DB (creating schema + parent dir) and reload persisted tasks."""
        if self._conn is not None:
            return self
        try:
            if self._db_path != ":memory:":
                parent = os.path.dirname(os.path.abspath(self._db_path))
                if parent:
                    os.makedirs(parent, exist_ok=True)
            conn = sqlite3.connect(self._db_path, check_same_thread=False)
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.executescript(self._SCHEMA)
            conn.commit()
        except sqlite3.Error as exc:  # noqa: BLE001 - surface as module error
            raise TaskStoreError(f"Failed to open SQLite task store: {exc}") from exc
        with self._lock:
            self._conn = conn
            self._reload()
        return self

    def _reload(self) -> None:
        """Load every persisted row back into the in-memory task cache."""
        assert self._conn is not None
        self._tasks.clear()
        self._by_idempotency.clear()
        try:
            for row in self._conn.execute(
                "SELECT id, session_id, agent_id, state, messages, artifacts, "
                "context, idempotency_key, parent_task_id, created_at, "
                "updated_at, retries, metadata FROM tasks"
            ):
                (
                    task_id, session_id, agent_id, state_raw, messages_raw,
                    artifacts_raw, context_raw, idem, parent, created, updated,
                    retries, metadata_raw,
                ) = row
                task = Task(
                    task_id=task_id,
                    state=TaskState(state_raw),
                    agent_id=agent_id,
                    session_id=session_id,
                    artifacts=_json_loads(artifacts_raw, []),
                    messages=[
                        Message.from_dict(m) for m in _json_loads(messages_raw, [])
                    ],
                    context=_json_loads(context_raw, {}) or {},
                    idempotency_key=idem,
                    parent_task_id=parent,
                    created_at=created,
                    updated_at=updated,
                    retries=int(retries),
                    metadata=_json_loads(metadata_raw, {}) or {},
                )
                self._tasks[task_id] = task
                if idem is not None:
                    self._by_idempotency[idem] = task_id
        except (sqlite3.Error, ValueError) as exc:  # noqa: BLE001
            raise TaskStoreError(f"Failed to reload task store: {exc}") from exc

    def close(self) -> None:
        """Flush and close the SQLite connection (idempotent)."""
        with self._lock:
            if self._conn is not None:
                try:
                    self._conn.commit()
                except sqlite3.Error:  # noqa: BLE001
                    pass
                try:
                    self._conn.close()
                except sqlite3.Error:  # noqa: BLE001
                    pass
                self._conn = None

    def __enter__(self) -> "TaskStore":
        return self.initialize()

    def __exit__(self, *exc: Any) -> None:
        self.close()

    # -- write-through persistence helpers ------------------------------

    def _require_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            raise TaskStoreError("TaskStore not initialized (call initialize())")
        return self._conn

    def _insert(self, task: Task) -> None:
        conn = self._require_conn()
        conn.execute(
            "INSERT INTO tasks (id, session_id, agent_id, state, messages, "
            "artifacts, context, idempotency_key, parent_task_id, created_at, "
            "updated_at, retries, metadata) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                task.task_id, task.session_id, task.agent_id, task.state.value,
                _json_dumps([m.to_dict() for m in task.messages]),
                _json_dumps(task.artifacts), _json_dumps(task.context),
                task.idempotency_key, task.parent_task_id, task.created_at,
                task.updated_at, task.retries, _json_dumps(task.metadata),
            ),
        )
        conn.commit()

    def _update_row(self, task: Task) -> None:
        conn = self._require_conn()
        conn.execute(
            "UPDATE tasks SET state=?, messages=?, artifacts=?, context=?, "
            "updated_at=?, retries=?, metadata=? WHERE id=?",
            (
                task.state.value,
                _json_dumps([m.to_dict() for m in task.messages]),
                _json_dumps(task.artifacts), _json_dumps(task.context),
                task.updated_at, task.retries, _json_dumps(task.metadata),
                task.task_id,
            ),
        )
        conn.commit()

    # -- task API (TaskManager-compatible surface) ----------------------

    def create_task(
        self,
        agent_id: str,
        message: Optional[Message] = None,
        *,
        idempotency_key: Optional[str] = None,
        parent_task_id: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        session_id: Optional[str] = None,
    ) -> Task:
        with self._lock:
            if idempotency_key is not None:
                existing_id = self._by_idempotency.get(idempotency_key)
                if existing_id is not None:
                    return self._tasks[existing_id]
            task = Task(
                task_id=_new_id("task"),
                state=TaskState.SUBMITTED,
                agent_id=agent_id,
                session_id=session_id if session_id is not None else _new_id("sess"),
                messages=[message] if message is not None else [],
                context=_copy_mapping(context),
                idempotency_key=idempotency_key,
                parent_task_id=parent_task_id,
                metadata=_copy_mapping(metadata),
            )
            self._insert(task)
            self._tasks[task.task_id] = task
            if idempotency_key is not None:
                self._by_idempotency[idempotency_key] = task.task_id
            return task

    def get_task(self, task_id: str) -> Task:
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None:
                raise TaskNotFoundError(f"Unknown task id: {task_id!r}")
            return task

    def has_task(self, task_id: str) -> bool:
        with self._lock:
            return task_id in self._tasks

    def list_tasks(
        self, agent_id: Optional[str] = None, state: Optional[TaskState] = None
    ) -> List[Task]:
        with self._lock:
            result = list(self._tasks.values())
        if agent_id is not None:
            result = [t for t in result if t.agent_id == agent_id]
        if state is not None:
            result = [t for t in result if t.state is state]
        return result

    def tasks_for_agent(self, agent_id: str) -> List[Task]:
        return self.list_tasks(agent_id=agent_id)

    def tasks_for_session(self, session_id: str) -> List[Task]:
        with self._lock:
            return [t for t in self._tasks.values() if t.session_id == session_id]

    def count(self) -> int:
        with self._lock:
            return len(self._tasks)

    def transition(self, task_id: str, new_state: TaskState) -> Task:
        with self._lock:
            task = self.get_task(task_id)
            if task.state is new_state:
                return task
            if not task.state.can_transition_to(new_state):
                raise InvalidTransitionError(
                    f"Illegal transition for task {task_id!r}: "
                    f"{task.state.value} -> {new_state.value}"
                )
            task.state = new_state
            task.updated_at = _now_iso()
            self._update_row(task)
            return task

    def add_message(self, task_id: str, message: Message) -> Message:
        with self._lock:
            task = self.get_task(task_id)
            if task.state in (TaskState.COMPLETED, TaskState.CANCELED):
                raise InvalidTransitionError(
                    f"Cannot append to task {task_id!r} in terminal state "
                    f"{task.state.value}"
                )
            task.messages.append(message)
            task.updated_at = _now_iso()
            self._update_row(task)
            return message

    def add_artifact(self, task_id: str, artifact: Dict[str, Any]) -> Dict[str, Any]:
        with self._lock:
            task = self.get_task(task_id)
            if task.state in (TaskState.COMPLETED, TaskState.CANCELED):
                raise InvalidTransitionError(
                    f"Cannot add artifact to task {task_id!r} in terminal state "
                    f"{task.state.value}"
                )
            entry = dict(artifact)
            entry.setdefault("id", _new_id("art"))
            entry.setdefault("createdAt", _now_iso())
            task.artifacts.append(entry)
            task.updated_at = _now_iso()
            self._update_row(task)
            return entry

    def cancel(self, task_id: str) -> Task:
        return self.transition(task_id, TaskState.CANCELED)

    def complete(self, task_id: str) -> Task:
        return self.transition(task_id, TaskState.COMPLETED)

    def fail(self, task_id: str) -> Task:
        return self.transition(task_id, TaskState.FAILED)

    def mark_working(self, task_id: str) -> Task:
        return self.transition(task_id, TaskState.WORKING)

    def request_input(self, task_id: str) -> Task:
        return self.transition(task_id, TaskState.INPUT_REQUIRED)

    def retry(self, task_id: str, max_retries: int = 3) -> Task:
        with self._lock:
            task = self.get_task(task_id)
            if task.retries >= max_retries:
                raise A2AError(f"Task {task_id!r} exceeded max retries ({max_retries})")
            if task.state is not TaskState.FAILED:
                raise InvalidTransitionError(
                    f"Only failed tasks can be retried; task {task_id!r} is "
                    f"{task.state.value}"
                )
            task.retries += 1
            task.state = TaskState.SUBMITTED
            task.updated_at = _now_iso()
            self._update_row(task)
            return task

    def set_context(self, task_id: str, key: str, value: Any) -> Task:
        with self._lock:
            task = self.get_task(task_id)
            task.context[key] = value
            task.updated_at = _now_iso()
            self._update_row(task)
            return task


# ============================================================ In-memory transport

class InMemoryTransport:
    """Injectable, network-free transport for A2A ``send``/``get``.

    Messages travel as envelopes of ``{"to", "from", "taskId", "payload"}``.
    Each destination address has a FIFO queue; ``send`` appends to the target
    queue and ``get`` (or ``receive``) pops from an address's queue. The same
    transport may be shared by many agents (a local message bus) without any
    sockets or threads.
    """

    def __init__(self) -> None:
        self._queues: Dict[str, Deque[Dict[str, Any]]] = defaultdict(deque)
        self._lock = threading.RLock()
        self._closed = False

    @property
    def is_closed(self) -> bool:
        return self._closed

    def send(
        self,
        to: str,
        payload: Any,
        *,
        _from: Optional[str] = None,
        task_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Queue an envelope addressed to ``to``."""
        if self._closed:
            raise A2AError("InMemoryTransport is closed")
        envelope = {
            "to": to,
            "from": _from,
            "taskId": task_id,
            "payload": payload,
            "sentAt": _now_iso(),
        }
        with self._lock:
            self._queues[to].append(envelope)
        return envelope

    def send_envelope(self, envelope: Dict[str, Any]) -> Dict[str, Any]:
        """Queue a pre-built envelope dict (``'to'`` is required)."""
        if self._closed:
            raise A2AError("InMemoryTransport is closed")
        to = envelope.get("to")
        if not to:
            raise A2AError("Envelope missing required 'to' address")
        env = dict(envelope)
        env.setdefault("sentAt", _now_iso())
        with self._lock:
            self._queues[to].append(env)
        return env

    def receive(self, address: str) -> Optional[Dict[str, Any]]:
        """Return the oldest envelope for ``address`` or None if the queue is empty."""
        with self._lock:
            q = self._queues.get(address)
            if not q:
                return None
            return q.popleft()

    def get(self, address: str, timeout: float = 0.0) -> Optional[Dict[str, Any]]:
        """Block (up to ``timeout`` seconds) for the next envelope at ``address``.

        ``timeout`` of 0 returns immediately; a negative timeout blocks forever.
        """
        import time as _time

        deadline = None if timeout < 0 else _time.monotonic() + max(0.0, timeout)
        while True:
            envelope = self.receive(address)
            if envelope is not None:
                return envelope
            if self._closed:
                return None
            if deadline is not None and _time.monotonic() >= deadline:
                return None
            _time.sleep(0.001)

    def pending(self, address: Optional[str] = None) -> int:
        with self._lock:
            if address is not None:
                return len(self._queues.get(address, ()))
            return sum(len(q) for q in self._queues.values())

    def close(self) -> None:
        self._closed = True
        with self._lock:
            for q in self._queues.values():
                q.clear()
            self._queues.clear()

    # -- async wrappers -------------------------------------------------

    async def asend(self, to: str, payload: Any, **kw: Any) -> Dict[str, Any]:
        return self.send(to, payload, **kw)

    async def aget(self, address: str, timeout: float = 0.0) -> Optional[Dict[str, Any]]:
        return self.get(address, timeout=timeout)


# ============================================================ Router / exchange

@dataclass
class RouteResult:
    """Outcome of routing a task to an agent by capability."""

    task: Task
    task_id: str
    agent_id: str
    capability: str
    state: TaskState
    transitions: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "taskId": self.task_id,
            "agentId": self.agent_id,
            "capability": self.capability,
            "state": self.state.value,
            "transitions": list(self.transitions),
        }


class TaskRouter:
    """Route a task to an agent by capability and track its status changes.

    Uses an :class:`AgentRegistry` for discovery and any
    ``TaskManager``-compatible store (in-memory or the SQLite
    :class:`TaskStore`) for durable task state. Each route:

      1. finds agents offering the requested capability (``prefer`` picks one),
      2. creates the task (``submitted``),
      3. moves it to ``working`` via a validated transition,
      4. records the transition trace and returns a :class:`RouteResult`.

    An async twin (``aroute``) is provided for event-loop callers.
    """

    def __init__(
        self,
        registry: Optional[AgentRegistry] = None,
        store: Optional[Any] = None,
    ) -> None:
        self.registry = registry if registry is not None else AgentRegistry()
        self.store = store if store is not None else TaskManager()

    def _select_agent(self, capability: str, prefer: Optional[str]) -> AgentCard:
        cards = self.registry.agents_by_capability(capability)
        if not cards:
            raise NoAgentForCapabilityError(
                f"No registered agent offers capability {capability!r}"
            )
        if prefer is not None:
            for card in cards:
                if card.name == prefer:
                    return card
        return cards[0]

    def route(
        self,
        capability: str,
        message: Any = None,
        *,
        session_id: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
        prefer: Optional[str] = None,
        source: Optional[str] = None,
    ) -> RouteResult:
        """Route a message to an agent offering ``capability``."""
        card = self._select_agent(capability, prefer)
        agent_id = _slug(card.name)
        msg = _coerce_message(message)
        joined = _copy_mapping(context)
        if source is not None:
            joined.setdefault("from", source)
        task = self.store.create_task(
            agent_id, msg, session_id=session_id, context=joined
        )
        transitions = [task.state.value]
        task = self.store.mark_working(task.task_id)
        transitions.append(task.state.value)
        return RouteResult(
            task=task,
            task_id=task.task_id,
            agent_id=agent_id,
            capability=capability,
            state=task.state,
            transitions=transitions,
        )

    async def aroute(self, capability: str, message: Any = None, **kw: Any) -> RouteResult:
        """Async variant of :meth:`route`."""
        return self.route(capability, message, **kw)

    def route_to_agent(
        self,
        agent_ref: str,
        message: Any = None,
        *,
        session_id: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> RouteResult:
        """Route directly to a specific agent, rejecting unknown targets."""
        key = self.registry.resolve(agent_ref)
        if key is None:
            raise AgentNotFoundError(f"Unknown agent: {agent_ref!r}")
        task = self.store.create_task(
            key.agent_id,
            _coerce_message(message),
            session_id=session_id,
            context=context,
        )
        transitions = [task.state.value]
        task = self.store.mark_working(task.task_id)
        transitions.append(task.state.value)
        return RouteResult(
            task=task,
            task_id=task.task_id,
            agent_id=key.agent_id,
            capability="",
            state=task.state,
            transitions=transitions,
        )


# ============================================================ encode / decode

def encode_message(message: Message) -> str:
    """Serialize a :class:`Message` to a compact JSON string (wire format)."""
    return _json_dumps(message.to_dict())


def decode_message(text: str) -> Message:
    """Deserialize a JSON string back into a :class:`Message`."""
    data = json.loads(text)
    if isinstance(data, str):
        data = json.loads(data)
    return Message.from_dict(data)


def encode_task(task: Task) -> str:
    """Serialize a :class:`Task` to a compact JSON string."""
    return _json_dumps(task.to_dict())


def decode_task(text: str) -> Task:
    """Deserialize a JSON string back into a :class:`Task`."""
    data = json.loads(text)
    if isinstance(data, str):
        data = json.loads(data)
    return Task.from_dict(data)


def encode_artifact(artifact: Dict[str, Any]) -> str:
    """Serialize an artifact dict to a JSON string."""
    return _json_dumps(artifact)


def decode_artifact(text: str) -> Dict[str, Any]:
    """Deserialize a JSON string back into an artifact dict."""
    data = json.loads(text)
    if isinstance(data, str):
        data = json.loads(data)
    return dict(data)


def encode_sse(event: str, data: Any) -> str:
    """Encode an SSE (HTTP/SSE-style) frame: ``event`` + ``json`` data lines."""
    lines = [f"event: {event}"]
    payload = data if isinstance(data, str) else _json_dumps(data)
    for line in str(payload).splitlines():
        lines.append(f"data: {line}")
    lines.append("")
    return "\n".join(lines)


def decode_sse(text: str):
    """Decode an SSE frame into ``(event, data)`` where data is parsed as JSON.

    Returns ``(event, None)`` when no ``event:`` line is present.
    """
    event: Optional[str] = None
    data_lines: List[str] = []
    for line in str(text).splitlines():
        if line.startswith("event:"):
            event = line[len("event:"):].strip()
        elif line.startswith("data:"):
            data_lines.append(line[len("data:"):].strip())
    if not data_lines:
        return event, None
    raw = "\n".join(data_lines)
    try:
        return event, json.loads(raw)
    except (TypeError, ValueError):
        return event, raw
