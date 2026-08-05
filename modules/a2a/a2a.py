"""A2A Core -- Agent-to-Agent protocol (stdlib only).

ENI-first implementation of the Google A2A exchange model with zero external
dependencies. Provides the wire-shaped data primitives (AgentCard, AgentKey,
MessagePart, Message) and in-memory orchestration state (TaskState, Task,
TaskManager, AgentRegistry, A2AExchange, handoff helpers and A2AFacade).
"""

import json
import logging
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

__all__ = [
    "AgentCard",
    "AgentKey",
    "AgentRegistry",
    "A2AExchange",
    "A2AFacade",
    "A2AError",
    "Message",
    "MessagePart",
    "MessageRole",
    "Task",
    "TaskManager",
    "TaskState",
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
