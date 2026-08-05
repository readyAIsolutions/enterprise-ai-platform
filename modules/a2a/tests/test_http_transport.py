"""Hermetic tests for the real A2A HTTP transport.

Starts an :class:`A2AHttpServer` on an ephemeral port (``port=0``) in a daemon
thread and drives it with an :class:`A2AHttpClient` over real HTTP. Exercises:

  * task submission, retrieval, cancellation and health round trips
  * 404 (unknown task) and 400 (bad payload) JSON error handling
  * client parsing of typed errors (TaskNotFoundError / A2AError)
  * ``MemoryFailureInjector`` drop / timeout / out-of-order behaviour,
    including retry-once-then-surface transport errors
  * both in-memory (TaskManager) and durable (TaskStore) backing stores

Run with:
    python3 -m pytest modules/a2a/tests/test_http_transport.py -q
"""

from __future__ import annotations

import json
from typing import Generator

import pytest

from enterprise.modules.a2a.a2a import TaskManager, TaskState, TaskStore
from enterprise.modules.a2a.http_transport import (
    A2AHttpClient,
    A2AHttpServer,
    A2ATransportError,
    A2ATransportTimeout,
    MemoryFailureInjector,
    OutOfOrderError,
)
from enterprise.modules.a2a import A2AError, TaskNotFoundError


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def server_inmem() -> Generator[A2AHttpServer, None, None]:
    """A2AHttpServer over an in-memory TaskManager on an ephemeral port."""
    srv = A2AHttpServer(port=0, store=TaskManager())
    srv.start()
    try:
        yield srv
    finally:
        srv.stop()


@pytest.fixture()
def server_sqlite() -> Generator[A2AHttpServer, None, None]:
    """A2AHttpServer over a durable in-memory SQLite TaskStore."""
    srv = A2AHttpServer(port=0, store=TaskStore(db_path=":memory:"))
    srv.start()
    try:
        yield srv
    finally:
        srv.stop()


@pytest.fixture()
def client(server_inmem: A2AHttpServer) -> A2AHttpClient:
    return A2AHttpClient(server_inmem.base_url)


# ---------------------------------------------------------------------------
# Server lifecycle / health
# ---------------------------------------------------------------------------


def test_server_binds_ephemeral_port(server_inmem: A2AHttpServer) -> None:
    assert server_inmem.started
    assert server_inmem.port > 0
    assert server_inmem.base_url.startswith("http://")


def test_health_endpoint(client: A2AHttpClient) -> None:
    health = client.health()
    assert health["status"] == "ok"
    assert health["module"] == "a2a"


def test_client_send_task_creates_submitted(client: A2AHttpClient) -> None:
    task = client.send_task("analyst", "hello")
    assert task.task_id
    assert task.state is TaskState.SUBMITTED
    assert task.agent_id == "analyst"
    assert task.messages and "hello" in task.messages[0].text()


# ---------------------------------------------------------------------------
# Round trips
# ---------------------------------------------------------------------------


def test_send_then_get_round_trip(client: A2AHttpClient) -> None:
    created = client.send_task("analyst", "summarize the ledger")
    fetched = client.get_task(created.task_id)
    assert fetched.task_id == created.task_id
    assert fetched.state is TaskState.SUBMITTED
    assert fetched.messages and "summarize" in fetched.messages[0].text()


def test_get_returns_messages_and_state(client: A2AHttpClient) -> None:
    created = client.send_task("analyst", "returns artifacts")
    task = client.get_task(created.task_id)
    assert task.messages, "task should carry its submitted message"
    assert task.messages[0].text() == "returns artifacts"
    assert task.state.value == "submitted"


def test_cancel_transitions_task(client: A2AHttpClient) -> None:
    created = client.send_task("analyst", "cancel me")
    canceled = client.cancel_task(created.task_id)
    assert canceled.state is TaskState.CANCELED
    # a canceled task is terminal; subsequent get reflects it
    assert client.get_task(created.task_id).state is TaskState.CANCELED


def test_cancel_with_message_and_idempotency(client: A2AHttpClient) -> None:
    created = client.send_task(
        "analyst", "work", idempotency_key="idem-1", session_id="sess-9"
    )
    assert created.idempotency_key == "idem-1"
    assert created.session_id == "sess-9"
    # idempotent re-send returns the same task
    again = client.send_task("analyst", "work", idempotency_key="idem-1")
    assert again.task_id == created.task_id


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


def test_unknown_task_returns_404(client: A2AHttpClient) -> None:
    with pytest.raises(TaskNotFoundError):
        client.get_task("no-such-task")


def test_unknown_task_cancel_returns_404(client: A2AHttpClient) -> None:
    with pytest.raises(TaskNotFoundError):
        client.cancel_task("no-such-task")


def test_missing_agent_id_returns_400(client: A2AHttpClient) -> None:
    with pytest.raises(A2AError):
        client.send_task("", "hello")


def test_bad_payload_returns_400_error_json(client: A2AHttpClient) -> None:
    # Craft a raw request with an invalid body to assert the 400 JSON contract.
    resp = client._raw("POST", "/tasks/send", {"message": "x"})  # no agentId
    code, body = resp
    assert code == 400
    data = json.loads(body)
    assert "error" in data


def test_server_unknown_route_returns_404(client: A2AHttpClient) -> None:
    code, body = client._raw("GET", "/nonsense")
    assert code == 404
    data = json.loads(body)
    assert data["error"]["code"] == 404


# ---------------------------------------------------------------------------
# Failure injection
# ---------------------------------------------------------------------------


def test_drop_once_then_retry_succeeds(server_inmem: A2AHttpServer) -> None:
    injector = MemoryFailureInjector()
    created = A2AHttpClient(server_inmem.base_url).send_task("analyst", "first")
    inj_client = A2AHttpClient(
        server_inmem.base_url, injector=injector, max_retries=1
    )
    injector.drop(1)
    # first attempt dropped (timeout), retry succeeds against the real server
    task = inj_client.get_task(created.task_id)
    assert task.task_id == created.task_id
    assert task.state is TaskState.SUBMITTED
    assert injector.dropped == 1


def test_timeout_once_then_retry_succeeds(server_inmem: A2AHttpServer) -> None:
    injector = MemoryFailureInjector()
    client = A2AHttpClient(server_inmem.base_url, injector=injector, max_retries=1)
    created = client.send_task("analyst", "time me")
    injector.timeout_response(1)
    task = client.get_task(created.task_id)
    assert task.task_id == created.task_id
    assert injector.timeouts == 1


def test_repeated_drop_surfaces_transport_error(server_inmem: A2AHttpServer) -> None:
    injector = MemoryFailureInjector()
    client = A2AHttpClient(server_inmem.base_url, injector=injector, max_retries=1)
    created = client.send_task("analyst", "never delivered")
    injector.drop(5)  # drop both the attempt and its single retry
    with pytest.raises(A2ATransportError):
        client.get_task(created.task_id)


def test_repeated_timeout_surfaces_transport_error(server_inmem: A2AHttpServer) -> None:
    injector = MemoryFailureInjector()
    client = A2AHttpClient(server_inmem.base_url, injector=injector, max_retries=1)
    created = client.send_task("analyst", "stall")
    injector.timeout_response(5)
    with pytest.raises(A2ATransportError):
        client.get_task(created.task_id)


def test_out_of_order_stale_response_retries(server_inmem: A2AHttpServer) -> None:
    injector = MemoryFailureInjector()
    client = A2AHttpClient(server_inmem.base_url, injector=injector, max_retries=1)
    task_a = client.send_task("analyst", "a")
    task_b = client.send_task("analyst", "b")
    # arm reorder for the next get: a stale copy of task A is delivered
    injector.reorder(1)
    task = client.get_task(task_b.task_id)
    # client detected the stale (out-of-order) response and retried to real one
    assert task.task_id == task_b.task_id
    assert task.messages and task.messages[0].text() == "b"
    assert injector.reordered == 1


# ---------------------------------------------------------------------------
# Durable store + typed-parser coverage
# ---------------------------------------------------------------------------


def test_durable_taskstore_round_trip(server_sqlite: A2AHttpServer) -> None:
    client = A2AHttpClient(server_sqlite.base_url)
    created = client.send_task("bookkeeper", "post entry")
    fetched = client.get_task(created.task_id)
    assert fetched.task_id == created.task_id
    assert fetched.agent_id == "bookkeeper"
    assert fetched.state is TaskState.SUBMITTED


def test_durable_taskstore_cancel(server_sqlite: A2AHttpServer) -> None:
    client = A2AHttpClient(server_sqlite.base_url)
    created = client.send_task("bookkeeper", "void entry")
    assert client.cancel_task(created.task_id).state is TaskState.CANCELED
    assert client.get_task(created.task_id).state is TaskState.CANCELED


def test_injector_armed_state_toggles() -> None:
    injector = MemoryFailureInjector()
    assert not injector.armed
    injector.drop(1)
    assert injector.armed
    assert injector.intercept("GET", "/tasks/x") == "drop"
    assert not injector.armed
    injector.reset()
    assert not injector.armed


def test_send_task_preserves_metadata_context(client: A2AHttpClient) -> None:
    task = client.send_task(
        "analyst",
        "with meta",
        context={"k": "v"},
        metadata={"owner": "ops"},
    )
    assert task.context.get("k") == "v"
    assert task.metadata.get("owner") == "ops"
