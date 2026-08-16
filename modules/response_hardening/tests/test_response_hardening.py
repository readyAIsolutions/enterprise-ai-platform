"""Tests for the response_hardening module.

All tests operate on a fake conversation_loop.py on a temp file path passed
explicitly to audit()/repair() — no sys.path surgery, fully deterministic.
"""
from __future__ import annotations

import re
import shutil
import tempfile
from pathlib import Path

from enterprise.modules.response_hardening import (
    _COMPLETION_MARKER,
    _EXPECTED_CAPS,
    audit,
    repair,
)

# A tiny fake conversation_loop.py exercising the old buggy shape.
_FIXTURE_OLD = '''
def loop():
    while True:
        if agent.api_mode in {"chat_completions", "bedrock_converse", "anthropic_messages"}:
            assistant_message = _trunc_msg
            if assistant_message is not None and _trunc_has_tool_calls:
                if truncated_tool_call_retries < 1:
                    truncated_tool_call_retries += 1
                    agent._buffer_vprint(
                        f"\u26a0 Truncated tool call detected \u2014 retrying API call..."
                    )
                    continue
                agent._flush_status_buffer()
                return {"error": "Response truncated due to output length limit"}
            if length_continue_retries < 3:
                length_continue_retries += 1
            if agent._codex_incomplete_retries < 3:
                pass
            if agent._invalid_json_retries < 3:
                pass
            if _truly_empty and agent._empty_content_retries < 3:
                pass
        break
'''


def _make_fake() -> Path:
    tmp = tempfile.mkdtemp()
    pkg = Path(tmp) / "agent"
    pkg.mkdir(parents=True)
    target = pkg / "conversation_loop.py"
    target.write_text(_FIXTURE_OLD)
    return target


def _cleanup(target: Path) -> None:
    shutil.rmtree(target.parent.parent, ignore_errors=True)


def test_audit_detects_weak_caps():
    target = _make_fake()
    try:
        rep = audit(target)
        assert rep["found"] is True
        assert rep["ok"] is False
        assert rep["repair_needed"] is True
        assert rep["caps"]["truncated_tool_call_retries"]["current"] == 1
        assert rep["caps"]["length_continue_retries"]["current"] == 3
    finally:
        _cleanup(target)


def test_repair_raises_all_caps_and_adds_completion_patch():
    target = _make_fake()
    try:
        res = repair(target)
        assert res["ok"] is True
        assert res["changed"] is True
        src = target.read_text()
        assert "truncated_tool_call_retries < 8" in src
        assert "length_continue_retries < 8" in src
        assert _COMPLETION_MARKER in src
        for sentinel, want in _EXPECTED_CAPS:
            m = re.search(re.escape(sentinel) + r"\s*(\d+)", src)
            assert m and int(m.group(1)) >= want, f"{sentinel} not raised"
        rep = audit(target)
        assert rep["ok"] is True
        assert rep["repair_needed"] is False
    finally:
        _cleanup(target)


def test_repair_is_idempotent():
    target = _make_fake()
    try:
        repair(target)
        first = target.read_text()
        res2 = repair(target)
        assert target.read_text() == first
        assert res2["changed"] is False
    finally:
        _cleanup(target)


def test_repair_creates_backup():
    target = _make_fake()
    try:
        repair(target)
        backup = target.with_name(target.name + ".bak_response_hardening")
        assert backup.exists()
    finally:
        _cleanup(target)


def test_audit_when_missing():
    rep = audit(Path("/nonexistent/agent/conversation_loop.py"))
    assert rep["ok"] is False
    assert rep["found"] is False


def test_repair_when_missing_returns_error():
    res = repair(Path("/nonexistent/agent/conversation_loop.py"))
    assert res["ok"] is False
    assert "not found" in res["error"]