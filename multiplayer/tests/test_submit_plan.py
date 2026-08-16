"""Tests for plan fan-out: server.submit_plan turns one goal into N step-tasks."""
from __future__ import annotations

import asyncio
import os

from enterprise.multiplayer.server.server import MultiplayerServer


def _server(tmp_path, **kw):
    kw.setdefault("data_dir", str(tmp_path))
    return MultiplayerServer(**kw)


def test_submit_plan_fans_goal_into_steps(tmp_path):
    s = _server(tmp_path)
    res = asyncio.run(s.submit_plan("build a small to-do app"))
    assert res.get("steps", 0) >= 4
    assert res.get("task_ids")
    # each task carries distinct feature + step so filenames won't collide
    features = set()
    for tid in res["task_ids"]:
        rec = asyncio.run(s.board.get_task(tid))
        assert rec is not None
        assert rec.feature, "task should carry a feature"
        features.add((rec.feature, rec.step))
    assert len(features) == len(res["task_ids"]), "steps must be unique"


def test_submit_plan_respects_auth(tmp_path):
    s = _server(tmp_path, auth_token="sekret")
    res = asyncio.run(s.submit_plan("build x", token="wrong"))
    assert res.get("ok") is False
    assert "unauthorized" in res.get("error", "")


def test_submit_plan_sets_tenant(tmp_path):
    s = _server(tmp_path)
    res = asyncio.run(s.submit_plan("build y", tenant="acme"))
    assert res.get("tenant") == "acme"
    for tid in res.get("task_ids", []):
        assert s._task_tenant.get(tid) == "acme"