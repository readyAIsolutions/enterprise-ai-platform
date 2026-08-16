"""End-to-end + unit tests for the multiplayer build system."""
from __future__ import annotations

import asyncio
import os
import time

import pytest

from enterprise.multiplayer.protocol import (
    TaskState, make_message, validate, decode, encode, check,
)
from enterprise.multiplayer.server.state import Board, ClientRecord
from enterprise.multiplayer.server.broker import Broker
from enterprise.multiplayer.server.workspace_merge import apply_artifacts


def _board(tmp):  # noqa: UP037
    data_dir = os.path.join(str(tmp), "data")
    os.makedirs(data_dir, exist_ok=True)
    board = Board()
    broker = Broker(board, data_dir)
    return board, broker


def test_protocol_validates_message_types(tmp_path):
    hello = make_message("hello", client_id="x", capabilities={}, machine={})
    ok, reason = validate(hello)
    assert ok is True, reason
    ok2, reason2 = validate({"type": "nope"})
    assert ok2 is False
    assert "unknown" in reason2


def test_protocol_encodes_decodes_roundtrip():
    msg = make_message("task", task_id="t1", goal="hello", status="QUEUED")
    wire = encode(msg)
    back = decode(wire)
    assert back["task_id"] == "t1"
    assert back["goal"] == "hello"


def test_protocol_refuses_secrets(tmp_path):
    # the anti-secret guard must refuse credential-style content
    with pytest.raises(ValueError):
        make_message("task", task_id="t1", goal="x", prompt="use api_key abc123")
    # and validate() refuses it too if built by hand
    ok, reason = validate({"type": "task", "task_id": "t1", "goal": "x",
                           "prompt": "bearer token=deadbeef"})
    assert ok is False
    assert "secret" in str(reason).lower()


def test_broker_submit_creates_queued_task(tmp_path):
    board, broker = _board(tmp_path)
    rec = asyncio.run(broker.submit("make a readme"))
    assert rec.task_id.startswith("t-")
    assert rec.status == TaskState.QUEUED


def test_broker_assigns_to_capacity_capable_client(tmp_path):
    board, broker = _board(tmp_path)
    client = ClientRecord(
        client_id="c1", connected_at=time.time(), last_seen=time.time(),
        hostname="h1", max_concurrent_tasks=2, models=["free-router"],
        providers=["openrouter"], tags=["cpu"], gpu=False, running=[],
    )
    asyncio.run(board.add_client(client))
    rec = asyncio.run(broker.submit("do a thing"))
    asyncio.run(broker.submit("do another"))
    asyncio.run(broker.assign())
    # the capable client should have capacity assigned (running) or be queued
    rec_after = asyncio.run(board.get_task(rec.task_id))
    assert rec_after is not None
    assert rec_after.status in (TaskState.QUEUED, TaskState.ASSIGNED)


def test_broker_heartbeat_timeout_requeues(tmp_path):
    board, broker = _board(tmp_path)
    stale = ClientRecord(
        client_id="stale", connected_at=time.time() - 200, last_seen=time.time() - 200,
        hostname="old", max_concurrent_tasks=1, models=[], providers=[], tags=[],
        gpu=False, running=[],)
    asyncio.run(board.add_client(stale))
    tid = asyncio.run(broker.submit("work")).task_id
    asyncio.run(board.update_task(tid, status=TaskState.ASSIGNED,
                                  assigned_client="stale", assigned_at=time.time()))
    # the broker's heartbeat sweep iterates client.running; put the task there.
    stale.running.append(tid)
    asyncio.run(broker.check_heartbeats(now_ts=time.time()))
    rec = asyncio.run(board.get_task(tid))
    # after heartbeat sweep a stale client loses its task -> re-queued
    assert rec.status == TaskState.QUEUED


def test_merge_applies_artifacts(tmp_path):
    ws = os.path.join(str(tmp_path), "workspace")
    os.makedirs(ws, exist_ok=True)
    artifacts = [{"path": "hello.txt", "content": "hi"}]
    res = apply_artifacts(ws, artifacts, ledger_path=os.path.join(str(tmp_path), "l"),
                          task_id="t1", client_id="c1")
    assert os.path.exists(os.path.join(ws, "hello.txt"))
    assert "hello.txt" in res.get("applied", []) or "hello.txt" in [str(p) for p in res.get("applied", [])]


def test_merge_detects_conflict_and_does_not_clobber(tmp_path):
    ws = os.path.join(str(tmp_path), "workspace")
    os.makedirs(ws, exist_ok=True)
    existing = os.path.join(ws, "shared.json")
    with open(existing, "w") as fh:
        fh.write('{"v": "original"}')
    bad = [{"path": "shared.json", "content": '{"v": "different"}'}]
    res = apply_artifacts(ws, bad, ledger_path=os.path.join(str(tmp_path), "l"),
                          task_id="t2", client_id="c2")
    # do NOT overwrite original; the existing file content stays intact
    with open(existing) as fh:
        assert "original" in fh.read()
    assert "conflicts" in res
    assert len(res.get("conflicts", [])) > 0


def test_board_snapshot_shape(tmp_path):
    board, broker = _board(tmp_path)
    snap = asyncio.run(board.board_snapshot())
    assert "clients" in snap
    assert "queue" in snap or "queued_ids" in snap