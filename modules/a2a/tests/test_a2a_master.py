"""Master-class tests for the a2a module's enterprise additions.

Covers the durable, discovery, routing, transport and wire-format layers that
sit on top of the base in-memory protocol covered by :mod:`test_a2a`:

  - Vertical TaskState transition table: valid moves allowed, terminal
    ``completed`` is an absorbing state, and ``working -> input-required`` is
    only valid when a turn genuinely needs the peer.
  - SQLite-backed TaskStore: durability across close/re-open (survives
    restart), reload-on-init, and write-through of messages/artifacts/session.
  - AgentCard registry discovery: get_card, agents_by_capability, agents_by_skill.
  - TaskRouter: dispatch by capability, prefer-selection, transition tracking,
    rejection of unknown capabilities/agents, async interface.
  - JSON wire encode/decode helpers (message/task/artifact/SSE frame).
  - In-memory transport send/get (sync + async).
  - Module lifecycle with persistence config + create_a2a_module factory.

Run with:
    python3 -m pytest modules/a2a -q -p no:cacheprovider
"""

from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING, Any

import pytest

if TYPE_CHECKING:
    from pathlib import Path
from enterprise.modules.a2a import (
    A2AModule,
    AgentCard,
    AgentNotFoundError,
    AgentRegistry,
    InMemoryTransport,
    InvalidTransitionError,
    Message,
    MessagePart,
    MessageRole,
    NoAgentForCapabilityError,
    RouteResult,
    TaskRouter,
    TaskState,
    TaskStore,
    create_a2a_module,
    decode_artifact,
    decode_message,
    decode_sse,
    decode_task,
    encode_artifact,
    encode_message,
    encode_sse,
    encode_task,
)
from enterprise.modules.a2a.a2a import (
    A2AError,
    TaskManager,
    TaskStoreError,
)
from enterprise.platform_kernel import HealthStatus

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def card(name: str, capabilities: list[str], skills: list[str] | None = None) -> AgentCard:
    return AgentCard(
        name=name,
        description=f"{name} agent",
        capabilities=capabilities,
        skills=skills or [],
    )


def msg(text: str = "hello") -> Message:
    return Message.user_text(text)


def make_store(db_path: str | None = None) -> TaskStore:
    store = TaskStore(db_path=db_path or ":memory:")
    return store.initialize()


# ---------------------------------------------------------------------------
# Vertical TaskState transition table
# ---------------------------------------------------------------------------


class TestTaskStateMachine:
    def test_happy_path_submitted_to_working_to_completed(self) -> None:
        store = make_store()
        task = store.create_task("a", msg(), session_id="s1")
        assert task.state is TaskState.SUBMITTED
        store.mark_working(task.task_id)
        assert task.state is TaskState.WORKING
        store.complete(task.task_id)
        assert task.state is TaskState.COMPLETED

    def test_completed_is_terminal_absorbing_state(self) -> None:
        store = make_store()
        task = store.create_task("a")
        store.complete(task.task_id)
        for target in (
            TaskState.WORKING,
            TaskState.INPUT_REQUIRED,
            TaskState.CANCELED,
            TaskState.FAILED,
            TaskState.SUBMITTED,
        ):
            assert not task.state.can_transition_to(target)
            with pytest.raises(InvalidTransitionError):
                store.transition(task.task_id, target)

    def test_canceled_is_terminal(self) -> None:
        store = make_store()
        task = store.create_task("a")
        store.cancel(task.task_id)
        with pytest.raises(InvalidTransitionError):
            store.transition(task.task_id, TaskState.SUBMITTED)

    def test_working_cannot_regress_to_submitted(self) -> None:
        store = make_store()
        task = store.create_task("a")
        store.mark_working(task.task_id)
        with pytest.raises(InvalidTransitionError):
            store.transition(task.task_id, TaskState.SUBMITTED)

    def test_submitted_can_go_directly_to_input_required(self) -> None:
        assert TaskState.SUBMITTED.can_transition_to(TaskState.INPUT_REQUIRED)

    def test_working_to_input_required_then_back_to_working(self) -> None:
        store = make_store()
        task = store.create_task("a")
        store.mark_working(task.task_id)
        store.request_input(task.task_id)  # a turn needs the peer
        assert task.state is TaskState.INPUT_REQUIRED
        store.mark_working(task.task_id)
        assert task.state is TaskState.WORKING

    def test_failed_can_be_retried_to_submitted(self) -> None:
        store = make_store()
        task = store.create_task("a", session_id="s1")
        store.fail(task.task_id)
        store.retry(task.task_id)
        assert task.state is TaskState.SUBMITTED
        assert task.retries == 1


# ---------------------------------------------------------------------------
# SQLite persistence (survives restart)
# ---------------------------------------------------------------------------


class TestTaskStorePersistence:
    def test_round_trip_across_reopen(self, tmp_path: Path) -> None:
        db = str(tmp_path / "tasks.db")
        store = make_store(db)
        task = store.create_task("bookkeeper", msg("balance"), session_id="sess-1")
        task = store.mark_working(task.task_id)
        store.add_message(task.task_id, Message.user_text("second message"))
        store.add_artifact(task.task_id, {"kind": "excel", "rows": 42})
        task_id = task.task_id
        store.close()

        # Simulate a restart: a brand new store on the same path reloads on init.
        reopened = TaskStore(db_path=db).initialize()
        task = reopened.get_task(task_id)
        assert task.state is TaskState.WORKING
        assert task.session_id == "sess-1"
        texts = [m.text() for m in task.messages]
        assert texts == ["balance", "second message"]
        assert task.artifacts[0]["rows"] == 42
        reopened.close()

    def test_reload_on_init_restores_all_tasks(self, tmp_path: Path) -> None:
        db = str(tmp_path / "tasks.db")
        store = make_store(db)
        a = store.create_task("agent-a", session_id="s1")
        b = store.create_task("agent-b", session_id="s2")
        store.complete(b.task_id)
        store.close()

        reopened = TaskStore(db_path=db).initialize()
        assert reopened.count() == 2
        assert reopened.get_task(a.task_id).state is TaskState.SUBMITTED
        assert reopened.get_task(b.task_id).state is TaskState.COMPLETED
        reopened.close()

    def test_transition_is_durable_after_reopen(self, tmp_path: Path) -> None:
        db = str(tmp_path / "tasks.db")
        store = make_store(db)
        task = store.create_task("a")
        store.fail(task.task_id)
        store.retry(task.task_id)
        retries = task.retries
        store.close()

        reopened = TaskStore(db_path=db).initialize()
        restored = reopened.get_task(task.task_id)
        assert restored.retries == retries
        assert restored.state is TaskState.SUBMITTED
        reopened.close()

    def test_session_filter(self) -> None:
        store = make_store()
        store.create_task("a", session_id="sess-x")
        store.create_task("b", session_id="sess-x")
        store.create_task("c", session_id="sess-y")
        assert len(store.tasks_for_session("sess-x")) == 2
        assert len(store.tasks_for_session("sess-y")) == 1

    def test_auto_generated_session_id(self) -> None:
        store = make_store()
        task = store.create_task("a")
        assert task.session_id
        assert str(task.session_id).startswith("sess-")

    def test_in_memory_store_is_usable_without_disk(self) -> None:
        store = make_store()
        task = store.create_task("a", msg("x"))
        assert store.count() == 1
        assert store.get_task(task.task_id).messages[0].text() == "x"

    def test_uninitialized_store_raises(self) -> None:
        store = TaskStore(":memory:")
        with pytest.raises(TaskStoreError):
            store.create_task("a")

    def test_store_write_through_list_matches(self) -> None:
        store = make_store()
        task = store.create_task("bookkeeper", msg(), session_id="s1")
        store.complete(task.task_id)
        done = store.list_tasks(state=TaskState.COMPLETED)
        assert [t.task_id for t in done] == [task.task_id]


# ---------------------------------------------------------------------------
# AgentCard registry discovery
# ---------------------------------------------------------------------------


class TestAgentDiscovery:
    def _reg(self) -> AgentRegistry:
        reg = AgentRegistry()
        reg.register(card("Broker", ["trading", "ledger.query"], ["execution"]))
        reg.register(card("Auditor", ["ledger.query"], ["reconciliation"]))
        reg.register(card("Underwriter", ["risk"], ["modeling"]))
        return reg

    def test_get_card_by_id(self) -> None:
        reg = self._reg()
        got = reg.get_card("broker")
        assert got is not None
        assert got.name == "Broker"
        assert reg.get_card("nope") is None

    def test_agents_by_capability(self) -> None:
        reg = self._reg()
        matches = reg.agents_by_capability("ledger.query")
        assert [m.name for m in matches] == ["Auditor", "Broker"]  # sorted by name

    def test_agents_by_capability_none(self) -> None:
        assert self._reg().agents_by_capability("quantum") == []

    def test_agents_by_skill(self) -> None:
        reg = self._reg()
        matches = reg.agents_by_skill("reconciliation")
        assert [m.name for m in matches] == ["Auditor"]

    def test_facade_discovery_round_trip(self) -> None:
        reg = self._reg()
        assert reg.count() == 3
        names = {c["name"] for c in reg.list()}
        assert names == {"Broker", "Auditor", "Underwriter"}


# ---------------------------------------------------------------------------
# TaskRouter dispatch
# ---------------------------------------------------------------------------


class TestTaskRouter:
    def _router(self) -> TaskRouter:
        reg = AgentRegistry()
        reg.register(card("Broker", ["trading"], ["execution"]))
        reg.register(card("Auditor", ["ledger.query"], ["reconciliation"]))
        return TaskRouter(registry=reg, store=TaskManager())

    def test_dispatches_by_capability_and_tracks_transitions(self) -> None:
        router = self._router()
        result = router.route("ledger.query", "audit the books", session_id="s1")
        assert isinstance(result, RouteResult)
        assert result.agent_id == "auditor"
        assert result.state is TaskState.WORKING
        assert result.transitions == ["submitted", "working"]
        assert result.task.session_id == "s1"

    def test_prefer_selects_named_agent(self) -> None:
        reg = AgentRegistry()
        reg.register(card("Broker", ["trading"]))
        reg.register(card("Matching", ["trading"]))
        router = TaskRouter(registry=reg, store=TaskManager())
        result = router.route("trading", prefer="Matching")
        assert result.agent_id == "matching"

    def test_rejects_unknown_capability(self) -> None:
        router = self._router()
        with pytest.raises(NoAgentForCapabilityError):
            router.route("no-such-capability")

    def test_route_to_agent_rejects_unknown_agent(self) -> None:
        router = self._router()
        with pytest.raises(AgentNotFoundError):
            router.route_to_agent("ghost", "hi")

    def test_async_route(self) -> None:
        router = self._router()

        async def _run() -> RouteResult:
            return await router.aroute("trading", "go")

        result = asyncio.run(_run())
        assert result.agent_id == "broker"
        assert result.state is TaskState.WORKING


# ---------------------------------------------------------------------------
# Wire encode / decode
# ---------------------------------------------------------------------------


class TestWireEncodeDecode:
    def test_message_round_trip(self) -> None:
        m = Message(
            message_id="msg-1",
            role=MessageRole.AGENT,
            parts=[MessagePart.text_part("payload"), MessagePart("x", kind="table")],
        )
        text = encode_message(m)
        assert isinstance(text, str)
        restored = decode_message(text)
        assert restored.role is MessageRole.AGENT
        assert restored.text() == "payloadx"

    def test_task_round_trip(self) -> None:
        store = make_store()
        task = store.create_task("bookkeeper", msg("go"), session_id="s1")
        store.add_artifact(task.task_id, {"kind": "json"})
        text = encode_task(task)
        restored = decode_task(text)
        assert restored.task_id == task.task_id
        assert restored.agent_id == "bookkeeper"
        assert restored.session_id == "s1"
        assert len(restored.artifacts) == 1

    def test_artifact_round_trip(self) -> None:
        art = {"kind": "report", "rows": 7}
        assert decode_artifact(encode_artifact(art)) == art

    def test_sse_frame_round_trip(self) -> None:
        frame = encode_sse("task.update", {"taskId": "t1", "state": "working"})
        event, data = decode_sse(frame)
        assert event == "task.update"
        assert json.loads(json.dumps(data)) == {"taskId": "t1", "state": "working"}

    def test_sse_without_event_returns_none(self) -> None:
        event, data = decode_sse('data: {"a": 1}\n\n')
        assert event is None
        assert data == {"a": 1}


# ---------------------------------------------------------------------------
# In-memory transport
# ---------------------------------------------------------------------------


class TestInMemoryTransport:
    def test_send_get_fifo(self) -> None:
        t = InMemoryTransport()
        t.send("broker", {"cmd": "buy"}, _from="trader", task_id="t1")
        t.send("broker", {"cmd": "sell"})
        first = t.get("broker")
        second = t.get("broker")
        assert first["payload"] == {"cmd": "buy"}
        assert first["taskId"] == "t1"
        assert second["payload"] == {"cmd": "sell"}
        assert t.get("broker") is None  # queue drained

    def test_send_envelope_and_pending(self) -> None:
        t = InMemoryTransport()
        t.send_envelope({"to": "broker", "payload": {"x": 1}})
        t.send_envelope({"to": "auditor", "payload": {"y": 2}})
        assert t.pending("broker") == 1
        assert t.pending() == 2

    def test_receive_and_empty(self) -> None:
        t = InMemoryTransport()
        t.send("broker", 1)
        assert t.receive("broker") is not None
        assert t.receive("broker") is None

    def test_closed_transport_rejects_send(self) -> None:
        t = InMemoryTransport()
        t.close()
        with pytest.raises(A2AError):
            t.send("broker", "x")

    def test_async_send_get(self) -> None:
        t = InMemoryTransport()

        async def _run() -> dict[str, Any]:
            await t.asend("broker", {"cmd": "buy"})
            return await t.aget("broker")

        env = asyncio.run(_run())
        assert env["payload"] == {"cmd": "buy"}


# ---------------------------------------------------------------------------
# Module lifecycle + persistence config + factory
# ---------------------------------------------------------------------------


class TestModuleMaster:
    async def test_persisting_module_health_and_store(self, tmp_path: Path) -> None:
        db = str(tmp_path / "m.db")
        mod = A2AModule(config={"db_path": db})
        assert mod.persists is True
        await mod.initialize()
        assert await mod.health_check() is HealthStatus.HEALTHY
        assert mod.store is not None
        assert mod.router is not None
        assert mod.transport is not None
        mod.register_agent_card(card("Broker", ["trading"]))
        result = mod.router.route("trading", "buy")  # type: ignore[union-attr]
        assert result.state is TaskState.WORKING
        await mod.shutdown()
        assert mod.facade is None
        assert mod.store is None

    async def test_durability_through_module_restart(self, tmp_path: Path) -> None:
        db = str(tmp_path / "m2.db")
        mod = A2AModule(config={"db_path": db})
        await mod.initialize()
        mod.register_agent_card(card("Broker", ["trading"]))
        task = mod.create_task("broker", "hello", session_id="persist-me")
        mod.transition(task.task_id, TaskState.COMPLETED)
        task_id = task.task_id
        await mod.shutdown()

        mod2 = create_a2a_module({"db_path": db})
        await mod2.initialize()
        restored = mod2.get_task(task_id)
        assert restored.state is TaskState.COMPLETED
        assert restored.session_id == "persist-me"
        await mod2.shutdown()

    async def test_default_module_is_in_memory(self) -> None:
        mod = A2AModule()
        await mod.initialize()
        assert mod.persists is False
        assert mod.store is None
        await mod.shutdown()

    async def test_factory_builds_module(self) -> None:
        mod = create_a2a_module({"max_tasks": 5})
        assert isinstance(mod, A2AModule)
        assert mod.max_tasks == 5
        await mod.initialize()
        assert await mod.health_check() is HealthStatus.HEALTHY
        await mod.shutdown()
