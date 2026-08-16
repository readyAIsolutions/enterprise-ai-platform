"""Tests for server hardening: auth token, per-tenant workspaces, snapshot."""
from __future__ import annotations

import asyncio
import os

from enterprise.multiplayer.server.server import MultiplayerServer


def _auth(tmp_path, **kw):
    kw.setdefault("data_dir", str(tmp_path))
    return MultiplayerServer(**kw)


def test_auth_rejects_bad_token(tmp_path):
    s = _auth(tmp_path, auth_token="sekret")
    assert s._check_auth("sekret") is True
    assert s._check_auth("nope") is False
    assert s._check_auth("") is False


def test_auth_disabled_accepts_any(tmp_path):
    s = _auth(tmp_path)
    assert s._check_auth("") is True
    assert s._check_auth("anything") is True


def test_submit_requires_auth_when_enabled(tmp_path):
    s = _auth(tmp_path, auth_token="sekret")
    res = asyncio.run(s.submit("goal", token="wrong"))
    assert res.get("ok") is False
    assert "unauthorized" in res.get("error", "")


def test_tenant_workspaces_are_isolated(tmp_path):
    s = _auth(tmp_path)
    a = s._tenant_workspace("acme")
    b = s._tenant_workspace("globex")
    assert a != b
    assert a.startswith(os.path.join(str(tmp_path), "wspace"))
    assert os.path.isdir(a) and os.path.isdir(b)
    with open(os.path.join(a, "x.txt"), "w") as fh:
        fh.write("acme-only")
    assert not os.path.exists(os.path.join(b, "x.txt"))


def test_tenant_allowlist_gate(tmp_path):
    s = _auth(tmp_path, tenants={"acme": ["alice", "bob"]})
    assert s._client_allowed("alice", "acme") is True
    assert s._client_allowed("eve", "acme") is False
    assert s._client_allowed("eve", "default") is True


def test_snapshot_exposes_tenants_and_auth(tmp_path):
    s = _auth(tmp_path, tenants={"acme": []}, auth_token="t")
    snap = asyncio.run(s.board_snapshot())
    assert snap["auth_required"] is True
    assert "acme" in snap["tenants"]