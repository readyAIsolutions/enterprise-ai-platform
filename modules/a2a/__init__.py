"""ENI A2A Module -- Agent-to-Agent protocol (Google A2A style).

A stdlib-only implementation of agent-to-agent messaging and task
orchestration. Agents advertise themselves with an ``AgentCard`` (resolved to
an ``AgentKey``), exchange structured ``Message`` envelopes, and coordinate
work through ``Task`` objects in an in-memory ``TaskManager`` that enforces
valid life-cycle transitions, idempotency keys and bounded retries.

The module is a registered Platform Kernel module implementing the standard
lifecycle (``initialize`` / ``health_check`` / ``shutdown``) and the event-bus
wiring contract (``set_event_bus``). A public ``A2AFacade`` exposes
``register_agent_card`` / ``list_agents`` / ``create_task`` / ``get_task`` /
``send_message`` / ``handoff``.

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

from .a2a import (
    A2AError,
    A2AExchange,
    A2AFacade,
    AgentCard,
    AgentKey,
    AgentNotFoundError,
    AgentNotRegisteredError,
    AgentRegistry,
    InMemoryTransport,
    InvalidTransitionError,
    Message,
    MessagePart,
    MessageRole,
    NoAgentForCapabilityError,
    RouteResult,
    Task,
    TaskManager,
    TaskNotFoundError,
    TaskRouter,
    TaskState,
    TaskStore,
    decode_artifact,
    decode_message,
    decode_sse,
    decode_task,
    encode_artifact,
    encode_message,
    encode_sse,
    encode_task,
    handoff,
)
from .http_transport import (
    A2AHttpClient,
    A2AHttpServer,
    A2ATransportError,
    A2ATransportTimeout,
    MemoryFailureInjector,
    OutOfOrderError,
)

__version__ = "1.0.0"
__module__ = "a2a"

__all__ = [
    "__version__",
    "A2AModule",
    "create_a2a_module",
    # Facade + exchange + router + transport
    "A2AFacade",
    "A2AExchange",
    "TaskRouter",
    "RouteResult",
    "InMemoryTransport",
    # HTTP transport
    "A2AHttpServer",
    "A2AHttpClient",
    "A2ATransportError",
    "A2ATransportTimeout",
    "MemoryFailureInjector",
    "OutOfOrderError",
    # Core data primitives
    "AgentCard",
    "AgentKey",
    "AgentRegistry",
    "Message",
    "MessagePart",
    "MessageRole",
    "Task",
    "TaskManager",
    "TaskState",
    "TaskStore",
    "handoff",
    # Wire encode/decode helpers
    "encode_message",
    "decode_message",
    "encode_task",
    "decode_task",
    "encode_artifact",
    "decode_artifact",
    "encode_sse",
    "decode_sse",
    # Errors
    "A2AError",
    "TaskNotFoundError",
    "InvalidTransitionError",
    "AgentNotRegisteredError",
    "AgentNotFoundError",
    "NoAgentForCapabilityError",
]

_logger = logging.getLogger("enterprise.a2a")


@module(name="a2a", version="1.0.0")
class A2AModule(Module):
    """Enterprise A2A Module -- Agent-to-Agent protocol orchestration.

    Wraps an :class:`A2AFacade` behind the Platform Kernel module lifecycle
    and exposes the facade operations (``register_agent_card``,
    ``list_agents``, ``create_task``, ``get_task``, ``send_message``,
    ``handoff``) plus state helpers.

    Configuration (dict passed to ``__init__``):
        max_tasks (int): Maximum tasks the in-memory store will hold
            (default 100000).

    Events published (when an event bus is wired via ``set_event_bus``):
        - a2a.agent.registered -- an agent card was registered.
        - a2a.task.created     -- a task was created.
        - a2a.task.message     -- a message was appended to a task.
        - a2a.task.handoff     -- a task was handed off to another agent.
    """

    def __init__(self, config: Dict[str, Any] | None = None) -> None:
        super().__init__(config)
        self._facade: A2AFacade | None = None
        self._router: TaskRouter | None = None
        self._transport: InMemoryTransport | None = None
        self._store: TaskStore | None = None
        self._event_bus: EventBus | None = None
        self._lock = threading.RLock()
        self._max_tasks: int = int(self._config.get("max_tasks", 100000) or 100000)
        # Optional SQLite persistence: pass db_path (relative paths resolve
        # against the repo's data/ dir by default per the module contract).
        db_path = self._config.get("db_path")
        persist = bool(self._config.get("persist", False))
        if db_path and not persist:
            persist = True
        self._persist: bool = persist
        self._db_path: Optional[str] = str(db_path) if db_path else None

    # -- Properties ---------------------------------------------------------

    @property
    def facade(self) -> A2AFacade | None:
        """Return the active A2AFacade (None before initialization)."""
        with self._lock:
            return self._facade

    @property
    def router(self) -> TaskRouter | None:
        """Return the active :class:`TaskRouter` (None before initialization)."""
        with self._lock:
            return self._router

    @property
    def transport(self) -> InMemoryTransport | None:
        """Return the active in-memory transport (None before initialization)."""
        with self._lock:
            return self._transport

    @property
    def store(self) -> TaskStore | None:
        """Return the SQLite :class:`TaskStore` when persistence is enabled (else None)."""
        with self._lock:
            return self._store

    @property
    def persists(self) -> bool:
        """True when this module is configured with SQLite persistence."""
        return self._persist

    @property
    def max_tasks(self) -> int:
        """Configured maximum number of tasks."""
        return self._max_tasks

    # -- Lifecycle ----------------------------------------------------------

    async def initialize(self) -> None:
        """Build the A2AFacade and mark the module healthy."""
        with self._lock:
            self._status = HealthStatus.STARTING
        _logger.info("A2A module initializing (max_tasks=%s)", self._max_tasks)
        try:
            registry = AgentRegistry()
            store: TaskStore | None = None
            if self._persist:
                path = self._db_path or "data/a2a_tasks.db"
                store = TaskStore(db_path=path)
                store.initialize()
                tasks: Any = store
            else:
                tasks = TaskManager(max_tasks=self._max_tasks)
            facade = A2AFacade(registry=registry, tasks=tasks)
            router = TaskRouter(registry=registry, store=tasks)
            transport = InMemoryTransport()
            with self._lock:
                self._facade = facade
                self._router = router
                self._transport = transport
                self._store = store
                self._status = HealthStatus.HEALTHY
            _logger.info("A2A module initialized (persist=%s)", self._persist)
        except Exception as exc:  # noqa: BLE001 - lifecycle must report UNHEALTHY
            _logger.exception("Failed to initialize a2a module: %s", exc)
            with self._lock:
                self._status = HealthStatus.UNHEALTHY
            raise

    async def health_check(self) -> HealthStatus:
        """A healthy A2A module has an initialized facade."""
        with self._lock:
            if self._facade is not None and self._status is HealthStatus.HEALTHY:
                return HealthStatus.HEALTHY
            if self._status is HealthStatus.UNHEALTHY:
                return HealthStatus.UNHEALTHY
            self._status = HealthStatus.UNKNOWN
            return self._status

    async def shutdown(self) -> None:
        """Gracefully shut down, releasing the facade and closing the store."""
        with self._lock:
            self._status = HealthStatus.STOPPING
            _logger.info("Shutting down a2a module...")
            store = self._store
            self._facade = None
            self._router = None
            self._transport = None
            self._store = None
            if store is not None and store.is_open:
                store.close()
            self._status = HealthStatus.HEALTHY

    # -- Event Bus Wiring ---------------------------------------------------

    def set_event_bus(self, event_bus: EventBus) -> None:
        """Wire the platform EventBus into this module."""
        with self._lock:
            self._event_bus = event_bus

    # -- Public facade ------------------------------------------------------

    def register_agent_card(self, card: AgentCard) -> AgentKey:
        """Register an agent card, returning its AgentKey."""
        facade = self._require_facade()
        key = facade.register_agent_card(card)
        self._emit("a2a.agent.registered", {"agentId": key.agent_id, "name": key.name})
        return key

    def list_agents(self) -> List[Dict[str, Any]]:
        """Return serialized AgentCards for every registered agent."""
        return self._require_facade().list_agents()

    def create_task(
        self,
        agent_ref: str,
        message: Any = None,
        *,
        idempotency_key: Optional[str] = None,
        parent_task_id: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
        session_id: Optional[str] = None,
    ) -> Task:
        """Create a task for the agent addressed by ``agent_ref``."""
        facade = self._require_facade()
        task = facade.create_task(
            agent_ref,
            message,
            idempotency_key=idempotency_key,
            parent_task_id=parent_task_id,
            context=context,
            session_id=session_id,
        )
        self._emit(
            "a2a.task.created",
            {"taskId": task.task_id, "agentId": task.agent_id, "state": task.state.value},
        )
        return task

    def get_task(self, task_id: str) -> Task:
        """Return the task with ``task_id`` (raises if unknown)."""
        return self._require_facade().get_task(task_id)

    def transition(self, task_id: str, state: TaskState) -> Task:
        """Move a task to a new state (validated)."""
        return self._require_facade().transition(task_id, state)

    def send_message(
        self,
        task_id: str,
        message: Any,
        *,
        role: MessageRole = MessageRole.USER,
        context: Optional[Dict[str, Any]] = None,
    ) -> Message:
        """Append a message to an existing task."""
        facade = self._require_facade()
        msg = facade.send_message(task_id, message, role=role, context=context)
        self._emit(
            "a2a.task.message",
            {"taskId": task_id, "messageId": msg.message_id, "role": msg.role.value},
        )
        return msg

    def handoff(
        self,
        task_id: str,
        target_ref: str,
        message: Any = None,
        *,
        context: Optional[Dict[str, Any]] = None,
        idempotency_key: Optional[str] = None,
    ) -> Task:
        """Hand the task identified by ``task_id`` off to ``target_ref``."""
        facade = self._require_facade()
        child = facade.handoff(
            task_id,
            target_ref,
            message,
            context=context,
            idempotency_key=idempotency_key,
        )
        self._emit(
            "a2a.task.handoff",
            {
                "taskId": task_id,
                "childTaskId": child.task_id,
                "targetAgent": child.agent_id,
            },
        )
        return child

    # -- Helpers ------------------------------------------------------------

    def _require_facade(self) -> A2AFacade:
        facade = self.facade
        if facade is None:
            raise RuntimeError("a2a module is not initialized")
        return facade

    def _emit(self, topic: str, payload: Dict[str, Any]) -> None:
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


def create_a2a_module(
    config: Optional[Dict[str, Any]] = None,
) -> A2AModule:
    """Create (but do not initialize) an :class:`A2AModule` from config.

    Args:
        config: Optional dict. Supported keys:
            - ``max_tasks`` (int): max tasks in the in-memory store (default 100000).
            - ``persist`` (bool): enable SQLite persistence (default False).
            - ``db_path`` (str): SQLite database path for persistence. Relative
              paths resolve against the default ``data/`` directory
              (``data/a2a_tasks.db``). Implies ``persist=True``.
    """
    return A2AModule(config=config or {})
