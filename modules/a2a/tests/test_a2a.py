"""Unit tests for the a2a (Agent-to-Agent) enterprise module.

Covers the Google A2A-style protocol primitives and the Platform Kernel
module:

  - AgentCard / AgentKey (de)serialization to/from dict.
  - MessagePart / Message construction and (de)serialization.
  - Task life-cycle transitions, including invalid-transition rejection.
  - Idempotent task creation via idempotency keys.
  - Message send appending to a task's history.
  - Handoff creating a child task with parent link + inherited context.
  - Facade-level register/list/create/get/send/handoff operations.
  - Module lifecycle (initialize/health_check/shutdown) + event publishing.
  - set_event_bus wiring.

Run with:
    python3 -m pytest modules/a2a/tests -q
"""

from __future__ import annotations

import asyncio
from typing import Any, List

import pytest

from enterprise.modules.a2a import (
    A2AError,
    A2AFacade,
    A2AModule,
    AgentCard,
    AgentKey,
    AgentNotRegisteredError,
    AgentRegistry,
    InvalidTransitionError,
    Message,
    MessagePart,
    MessageRole,
    Task,
    TaskManager,
    TaskNotFoundError,
    TaskState,
    handoff,
)
from enterprise.modules.a2a.a2a import A2AExchange
from enterprise.platform_kernel import EventBus, HealthStatus

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def sample_card(name: str = "bookkeeper") -> AgentCard:
    return AgentCard(
        name=name,
        description="Maintains ledgers.",
        url="https://eni.local/agents/bookkeeper",
        version="2.1.0",
        capabilities=["bookkeeping", "ledger.query"],
        skills=["double-entry", "reconciliation"],
    )


def sample_message(text: str = "balance the ledger") -> Message:
    return Message.user_text(text, context={"request_id": "r-1"})


# ---------------------------------------------------------------------------
# MessagePrimitives
# ---------------------------------------------------------------------------


class TestMessagePart:
    def test_text_part_defaults(self) -> None:
        part = MessagePart.text_part("hello")
        assert part.text == "hello"
        assert part.kind == "text"
        assert part.metadata == {}

    def test_to_from_dict_roundtrip(self) -> None:
        part = MessagePart("x", kind="text", metadata={"lang": "en"})
        restored = MessagePart.from_dict(part.to_dict())
        assert restored.text == "x"
        assert restored.kind == "text"
        assert restored.metadata == {"lang": "en"}


class TestMessage:
    def test_user_text_builds_message(self) -> None:
        msg = Message.user_text("run forecast", context={"k": "v"})
        assert msg.role is MessageRole.USER
        assert msg.text() == "run forecast"
        assert msg.context == {"k": "v"}
        assert msg.message_id.startswith("msg-")

    def test_to_from_dict_roundtrip(self) -> None:
        msg = sample_message("audit trail")
        data = msg.to_dict()
        assert data["role"] == "user"
        assert data["messageId"] == msg.message_id
        restored = Message.from_dict(data)
        assert restored.message_id == msg.message_id
        assert restored.role is MessageRole.USER
        assert restored.text() == "audit trail"
        assert restored.parts[0].kind == "text"

    def test_json_serializable(self) -> None:
        import json

        json.dumps(sample_message("x").to_dict())  # must not raise


# ---------------------------------------------------------------------------
# AgentCard / AgentKey / AgentRegistry
# ---------------------------------------------------------------------------


class TestAgentCard:
    def test_to_from_dict_roundtrip(self) -> None:
        card = sample_card()
        restored = AgentCard.from_dict(card.to_dict())
        assert restored.name == "bookkeeper"
        assert restored.version == "2.1.0"
        assert restored.capabilities == ["bookkeeping", "ledger.query"]
        assert restored.skills == ["double-entry", "reconciliation"]

    def test_defaults_when_omitted(self) -> None:
        card = AgentCard.from_dict({"name": "m"})
        assert card.description == ""
        assert card.version == "1.0.0"
        assert card.capabilities == []
        assert card.skills == []

    def test_json_serializable(self) -> None:
        import json

        json.dumps(sample_card().to_dict())


class TestAgentRegistry:
    def test_register_returns_key_and_resolves_by_id(self) -> None:
        reg = AgentRegistry()
        key = reg.register(sample_card())
        assert key.agent_id == "bookkeeper"
        assert reg.get("bookkeeper").name == "bookkeeper"

    def test_resolve_by_name(self) -> None:
        reg = AgentRegistry()
        reg.register(sample_card("Audit Agent"))
        key = reg.resolve("audit-agent")
        assert key is not None
        assert key.agent_id == "audit-agent"
        assert key.name == "Audit Agent"

    def test_resolve_unknown_returns_none(self) -> None:
        assert AgentRegistry().resolve("ghost") is None

    def test_unregister(self) -> None:
        reg = AgentRegistry()
        reg.register(sample_card())
        assert reg.unregister("bookkeeper") is True
        assert reg.unregister("bookkeeper") is False

    def test_list_sorted_by_name(self) -> None:
        reg = AgentRegistry()
        reg.register(sample_card("zulu"))
        reg.register(sample_card("alpha"))
        names = [c["name"] for c in reg.list()]
        assert names == ["alpha", "zulu"]
        assert reg.count() == 2


# ---------------------------------------------------------------------------
# Task life-cycle
# ---------------------------------------------------------------------------


class TestTaskState:
    def test_valid_transitions(self) -> None:
        assert TaskState.SUBMITTED.can_transition_to(TaskState.WORKING)
        assert TaskState.WORKING.can_transition_to(TaskState.COMPLETED)
        assert TaskState.SUBMITTED.can_transition_to(TaskState.FAILED)
        assert TaskState.FAILED.can_transition_to(TaskState.SUBMITTED)  # retry

    def test_invalid_transitions(self) -> None:
        assert not TaskState.SUBMITTED.can_transition_to(TaskState.SUBMITTED)
        assert not TaskState.COMPLETED.can_transition_to(TaskState.WORKING)
        assert not TaskState.CANCELED.can_transition_to(TaskState.SUBMITTED)
        assert not TaskState.WORKING.can_transition_to(TaskState.SUBMITTED)


class TestTaskSerialization:
    def test_to_from_dict_roundtrip(self) -> None:
        task = Task(
            task_id="task-1",
            state=TaskState.WORKING,
            agent_id="bookkeeper",
            messages=[sample_message("hi")],
            context={"region": "emea"},
            idempotency_key="idem-1",
            parent_task_id="task-0",
            retries=1,
        )
        data = task.to_dict()
        assert data["taskId"] == "task-1"
        assert data["state"] == "working"
        assert data["parentTaskId"] == "task-0"
        restored = Task.from_dict(data)
        assert restored.task_id == "task-1"
        assert restored.state is TaskState.WORKING
        assert restored.retries == 1
        assert restored.messages[0].text() == "hi"


class TestTaskManager:
    def _manager(self) -> TaskManager:
        return TaskManager()

    def test_create_task_starts_submitted(self) -> None:
        mgr = self._manager()
        task = mgr.create_task("agent-1", sample_message("go"))
        assert task.state is TaskState.SUBMITTED
        assert task.agent_id == "agent-1"
        assert len(task.messages) == 1
        assert mgr.count() == 1

    def test_idempotent_creation_same_key_returns_same_task(self) -> None:
        mgr = self._manager()
        first = mgr.create_task("agent-1", sample_message("a"), idempotency_key="k1")
        second = mgr.create_task("agent-1", sample_message("b"), idempotency_key="k1")
        assert first.task_id == second.task_id
        assert mgr.count() == 1
        # message from the first attempt is preserved; no duplicate append
        assert len(first.messages) == 1

    def test_idempotent_creation_different_keys_create_distinct_tasks(self) -> None:
        mgr = self._manager()
        a = mgr.create_task("a", idempotency_key="k1")
        b = mgr.create_task("a", idempotency_key="k2")
        assert a.task_id != b.task_id
        assert mgr.count() == 2

    def test_get_task_returns_same_object(self) -> None:
        mgr = self._manager()
        task = mgr.create_task("a")
        assert mgr.get_task(task.task_id) is task

    def test_get_task_unknown_raises(self) -> None:
        with pytest.raises(TaskNotFoundError):
            self._manager().get_task("nope")

    def test_valid_transition_chain(self) -> None:
        mgr = self._manager()
        task = mgr.create_task("a")
        mgr.mark_working(task.task_id)
        assert task.state is TaskState.WORKING
        mgr.complete(task.task_id)
        assert task.state is TaskState.COMPLETED

    def test_invalid_transition_rejected(self) -> None:
        mgr = self._manager()
        task = mgr.create_task("a")
        mgr.complete(task.task_id)
        with pytest.raises(InvalidTransitionError):
            mgr.transition(task.task_id, TaskState.WORKING)
        # state unchanged after rejection
        assert task.state is TaskState.COMPLETED

    def test_complete_then_cancel_rejected(self) -> None:
        mgr = self._manager()
        task = mgr.create_task("a")
        mgr.complete(task.task_id)
        with pytest.raises(InvalidTransitionError):
            mgr.cancel(task.task_id)

    def test_retry_failed_task(self) -> None:
        mgr = self._manager()
        task = mgr.create_task("a")
        mgr.fail(task.task_id)
        mgr.retry(task.task_id)
        assert task.state is TaskState.SUBMITTED
        assert task.retries == 1

    def test_retry_rejects_non_failed(self) -> None:
        mgr = self._manager()
        task = mgr.create_task("a")
        with pytest.raises(InvalidTransitionError):
            mgr.retry(task.task_id)

    def test_retry_exceeds_max(self) -> None:
        mgr = self._manager()
        task = mgr.create_task("a")
        mgr.fail(task.task_id)
        mgr.retry(task.task_id, max_retries=1)
        mgr.fail(task.task_id)
        with pytest.raises(A2AError):
            mgr.retry(task.task_id, max_retries=1)

    def test_cancel_flow(self) -> None:
        mgr = self._manager()
        task = mgr.create_task("a")
        mgr.cancel(task.task_id)
        assert task.state is TaskState.CANCELED

    def test_request_input(self) -> None:
        mgr = self._manager()
        task = mgr.create_task("a")
        mgr.request_input(task.task_id)
        assert task.state is TaskState.INPUT_REQUIRED

    def test_add_message_appends_to_task(self) -> None:
        mgr = self._manager()
        task = mgr.create_task("a", sample_message("initial"))
        mgr.add_message(task.task_id, sample_message("first"))
        msg = mgr.add_message(task.task_id, sample_message("second"))
        assert len(task.messages) == 3  # initial + 2 appended
        assert task.messages[-1] is msg
        assert task.messages[-1].text() == "second"

    def test_add_message_to_completed_rejected(self) -> None:
        mgr = self._manager()
        task = mgr.create_task("a")
        mgr.complete(task.task_id)
        with pytest.raises(InvalidTransitionError):
            mgr.add_message(task.task_id, sample_message("late"))

    def test_list_filter_by_agent_and_state(self) -> None:
        mgr = self._manager()
        a = mgr.create_task("agent-a")
        b = mgr.create_task("agent-b")
        mgr.complete(b.task_id)
        assert len(mgr.tasks_for_agent("agent-a")) == 1
        done = mgr.list_tasks(state=TaskState.COMPLETED)
        assert len(done) == 1
        assert done[0].task_id == b.task_id


# ---------------------------------------------------------------------------
# Handoff helper
# ---------------------------------------------------------------------------


class TestHandoff:
    def test_handoff_links_parent_and_inherits_context(self) -> None:
        reg = AgentRegistry()
        reg.register(sample_card("accountant"))
        reg.register(sample_card("auditor"))
        mgr = TaskManager()
        parent = mgr.create_task(
            "accountant",
            sample_message("do the books"),
            context={"region": "emea", "year": 2025},
        )
        exchange = A2AExchange(registry=reg, tasks=mgr)
        child = handoff(
            exchange,
            mgr,
            parent,
            reg.resolve("auditor"),
            Message.user_text("review the books"),
        )
        assert child.parent_task_id == parent.task_id
        assert child.agent_id == "auditor"
        assert child.context["region"] == "emea"
        assert child.context["year"] == 2025
        assert child.metadata.get("handoff_from") == parent.task_id

    def test_handoff_target_must_be_registered(self) -> None:
        reg = AgentRegistry()
        reg.register(sample_card("accountant"))
        mgr = TaskManager()
        parent = mgr.create_task("accountant")
        exchange = A2AExchange(registry=reg, tasks=mgr)
        with pytest.raises(AgentNotRegisteredError):
            handoff(exchange, mgr, parent, AgentKey(agent_id="ghost", name="ghost"))


# ---------------------------------------------------------------------------
# A2AExchange negotiation
# ---------------------------------------------------------------------------


class TestA2AExchange:
    def test_send_to_agent_creates_task_with_source_context(self) -> None:
        reg = AgentRegistry()
        reg.register(sample_card("accountant"))
        reg.register(sample_card("auditor"))
        mgr = TaskManager()
        ex = A2AExchange(registry=reg, tasks=mgr)
        task = ex.send_to_agent(
            reg.resolve("accountant"),
            reg.resolve("auditor"),
            Message.user_text("please audit"),
        )
        assert task.agent_id == "auditor"
        assert task.context.get("from") == "accountant"

    def test_negotiate_capability_match(self) -> None:
        reg = AgentRegistry()
        reg.register(sample_card("auditor"))  # capability ledger.query
        ex = A2AExchange(registry=reg)
        result = ex.negotiate(
            reg.resolve("auditor"), reg.resolve("auditor"), "ledger.query"
        )
        assert result["accepted"] is True

    def test_negotiate_capability_mismatch(self) -> None:
        reg = AgentRegistry()
        reg.register(sample_card("auditor"))
        ex = A2AExchange(registry=reg)
        result = ex.negotiate(reg.resolve("auditor"), reg.resolve("auditor"), "llm")
        assert result["accepted"] is False
        assert "not offered" in result["reason"]


# ---------------------------------------------------------------------------
# A2AFacade
# ---------------------------------------------------------------------------


class TestA2AFacade:
    def _facade(self) -> A2AFacade:
        facade = A2AFacade()
        facade.register_agent_card(sample_card("accountant"))
        facade.register_agent_card(sample_card("auditor"))
        return facade

    def test_register_and_list_agents(self) -> None:
        facade = A2AFacade()
        key = facade.register_agent_card(sample_card("accountant"))
        assert key.agent_id == "accountant"
        assert len(facade.list_agents()) == 1
        assert facade.list_agents()[0]["name"] == "accountant"

    def test_create_task_returns_submitted_task(self) -> None:
        facade = self._facade()
        task = facade.create_task("accountant", "open the ledger")
        assert task.agent_id == "accountant"
        assert task.state is TaskState.SUBMITTED
        assert task.messages[0].text() == "open the ledger"

    def test_create_task_unknown_agent_raises(self) -> None:
        facade = A2AFacade()
        with pytest.raises(AgentNotRegisteredError):
            facade.create_task("ghost", "hello")

    def test_idempotent_create_through_facade(self) -> None:
        facade = self._facade()
        a = facade.create_task("accountant", "x", idempotency_key="idem-A")
        b = facade.create_task("accountant", "x", idempotency_key="idem-A")
        assert a.task_id == b.task_id

    def test_get_task(self) -> None:
        facade = self._facade()
        task = facade.create_task("accountant")
        assert facade.get_task(task.task_id).task_id == task.task_id

    def test_send_message_appends(self) -> None:
        facade = self._facade()
        task = facade.create_task("accountant", "start")
        msg = facade.send_message(task.task_id, "more detail")
        assert task.messages[-1].text() == "more detail"
        assert msg.message_id == task.messages[-1].message_id

    def test_send_message_accepts_agent_role(self) -> None:
        facade = self._facade()
        task = facade.create_task("accountant")
        msg = facade.send_message(task.task_id, "done", role=MessageRole.AGENT)
        assert msg.role is MessageRole.AGENT

    def test_facade_transition_and_complete(self) -> None:
        facade = self._facade()
        task = facade.create_task("accountant")
        facade.transition(task.task_id, TaskState.WORKING)
        assert task.state is TaskState.WORKING
        facade.complete_task(task.task_id)
        assert task.state is TaskState.COMPLETED

    def test_handoff_through_facade(self) -> None:
        facade = self._facade()
        parent = facade.create_task("accountant", "triage", context={"env": "prod"})
        child = facade.handoff(parent.task_id, "auditor", "review please")
        assert child.parent_task_id == parent.task_id
        assert child.agent_id == "auditor"
        assert child.context["env"] == "prod"
        assert child.context.get("parent_task_id") == parent.task_id

    def test_negotiate_through_facade(self) -> None:
        facade = self._facade()
        result = facade.negotiate("accountant", "auditor", "ledger.query")
        assert result["accepted"] is True


# ---------------------------------------------------------------------------
# Module lifecycle
# ---------------------------------------------------------------------------


class TestA2AModule:
    async def test_initialize_healthy(self) -> None:
        mod = A2AModule(config={"max_tasks": 50})
        assert mod.status is HealthStatus.UNKNOWN
        await mod.initialize()
        assert mod.status is HealthStatus.HEALTHY
        assert mod.facade is not None
        assert mod.max_tasks == 50

    async def test_health_check_unknown_before_init(self) -> None:
        mod = A2AModule()
        assert await mod.health_check() is HealthStatus.UNKNOWN

    async def test_health_check_healthy_after_init(self) -> None:
        mod = A2AModule()
        await mod.initialize()
        assert await mod.health_check() is HealthStatus.HEALTHY

    async def test_shutdown_releases_facade(self) -> None:
        mod = A2AModule()
        await mod.initialize()
        await mod.shutdown()
        assert mod.facade is None

    async def test_operation_before_init_raises(self) -> None:
        mod = A2AModule()
        with pytest.raises(RuntimeError, match="not initialized"):
            mod.list_agents()
        with pytest.raises(RuntimeError, match="not initialized"):
            mod.create_task("accountant")

    async def test_module_facade_operations(self) -> None:
        mod = A2AModule()
        await mod.initialize()
        mod.register_agent_card(sample_card("accountant"))
        task = mod.create_task("accountant", "hello")
        assert mod.get_task(task.task_id).task_id == task.task_id
        mod.send_message(task.task_id, "world")
        assert task.messages[-1].text() == "world"

    async def test_registered_with_platform(self) -> None:
        from enterprise.platform_kernel import _MODULE_REGISTRY

        assert "a2a" in _MODULE_REGISTRY
        cls = _MODULE_REGISTRY["a2a"]
        assert issubclass(cls, A2AModule)

    async def test_set_event_bus_and_emit(self) -> None:
        bus = EventBus(config={"async_dispatch": False})
        received: List[str] = []

        @bus.subscribe("a2a.agent.registered")
        def _on_registered(event: Any) -> None:
            received.append(event.topic)

        mod = A2AModule()
        mod.set_event_bus(bus)
        await mod.initialize()
        mod.register_agent_card(sample_card("accountant"))
        assert "a2a.agent.registered" in received

    async def test_task_created_event_emitted(self) -> None:
        bus = EventBus(config={"async_dispatch": False})
        received: List[str] = []

        @bus.subscribe("a2a.task.created")
        def _on_created(event: Any) -> None:
            received.append(event.topic)

        mod = A2AModule()
        mod.set_event_bus(bus)
        await mod.initialize()
        mod.register_agent_card(sample_card("accountant"))
        mod.create_task("accountant", "go")
        assert "a2a.task.created" in received

    async def test_default_max_tasks(self) -> None:
        mod = A2AModule()
        assert mod.max_tasks == 100000

    async def test_name_and_version(self) -> None:
        mod = A2AModule()
        assert mod.name == "a2a"
        assert mod.version == "1.0.0"
        assert mod.module_id


# ---------------------------------------------------------------------------
# Async smoke: run all module async tests via asyncio
# ---------------------------------------------------------------------------


def test_async_module_lifecycle_e2e() -> None:
    async def _run() -> None:
        mod = A2AModule()
        await mod.initialize()
        mod.register_agent_card(sample_card("accountant"))
        mod.register_agent_card(sample_card("auditor"))
        parent = mod.create_task("accountant", "start", context={"team": "core"})
        child = mod.handoff(parent.task_id, "auditor", "review")
        assert child.parent_task_id == parent.task_id
        assert child.context["team"] == "core"
        assert await mod.health_check() is HealthStatus.HEALTHY
        await mod.shutdown()

    asyncio.run(_run())
