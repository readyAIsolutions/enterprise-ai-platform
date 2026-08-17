"""Tests for shared_workspace (live multi-editor, lock, merge, history, silo)."""
from __future__ import annotations

from pathlib import Path

from enterprise.modules.shared_workspace import (
    SharedWorkspace, anonymize_for_share, create_shared_workspace_module,
)


def test_lock_prevents_second_editor(tmp_path):
    ws = SharedWorkspace(tmp_path)
    assert ws.lock("note.md", "alice") is True
    assert ws.lock("note.md", "bob") is False   # bob can't lock (alice has it)
    assert ws.unlock("note.md", "alice") is True
    assert ws.lock("note.md", "bob") is True    # freed, bob can take it


def test_write_and_read(tmp_path):
    ws = SharedWorkspace(tmp_path)
    r = ws.write("a.md", "hello", author="alice")
    assert r["ok"] is True and r["conflict"] is False
    assert ws.read("a.md") == "hello"
    assert (tmp_path / "a.md").exists()


def test_merge_conflict_does_not_clobber(tmp_path):
    ws = SharedWorkspace(tmp_path)
    ws.write("shared.md", "version ONE", author="alice")
    # external change simulates another editor writing to disk
    (tmp_path / "shared.md").write_text("version TWO")
    # alice tries to write a different version -> conflict, no clobber
    r = ws.write("shared.md", "version THREE", author="alice")
    assert r["conflict"] is True
    assert r["ok"] is False
    # disk unchanged (not clobbered)
    assert (tmp_path / "shared.md").read_text() == "version TWO"


def test_locked_write_refused(tmp_path):
    ws = SharedWorkspace(tmp_path)
    ws.lock("locked.md", "carol")
    r = ws.write("locked.md", "x", author="dave")
    assert r["ok"] is False
    assert "locked" in r.get("reason", "").lower()
    # force overrides
    assert ws.write("locked.md", "y", author="dave", force=True)["ok"] is True


def test_history_and_query(tmp_path):
    ws = SharedWorkspace(tmp_path)
    ws.write("proposal.md", "content1", author="alice")
    ws.write("proposal.md", "content2", author="bob")
    h = ws.history(limit=10)
    assert len(h) >= 2
    # query by author or path
    assert ws.query("bob", limit=5)
    assert ws.query("proposal", limit=5)


def test_anonymize_before_share():
    raw = "use api_key=sk-1234abcd and password hunter42 and token abc"
    out = anonymize_for_share(raw)
    assert "sk-1234abcd" not in out
    assert "hunter42" not in out
    assert "<redacted>" in out


def test_module_initializes(tmp_path):
    import asyncio
    m = create_shared_workspace_module({"root": str(tmp_path / "ws")})
    asyncio.run(m.initialize())
    assert m.ws is not None
    assert asyncio.run(m.health_check()).value in ("healthy", "HEALTHY") or "HEALTHY" in str(asyncio.run(m.health_check()))
    r = m.write("x.md", "hi", author="test")
    assert r["ok"] is True