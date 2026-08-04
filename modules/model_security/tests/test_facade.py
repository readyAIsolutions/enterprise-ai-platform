#!/usr/bin/env python3
"""Tests for the Unified Security Surface on ModelSecurityModule (Upgrade Run 5)."""

import asyncio
import tempfile
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import pytest

from enterprise.modules.model_security.model_security import ModelSecurityModule


def _mod(tmp):
    return ModelSecurityModule({
        "audit_path": str(Path(tmp) / "audit.log"),
        "policy_path": str(Path(tmp) / "policies.yaml"),
    })


def test_new_gate_wraps_model(tmp_path):
    m = _mod(tmp_path)
    asyncio.run(m.initialize())
    called = {"n": 0}
    def model(p):
        called["n"] += 1
        return "OK:" + p
    wrapped = m.new_gate_wrapped(model, "facade_model", "local")
    r = wrapped("hello")
    assert r.passed
    assert called["n"] == 1
    asyncio.run(m.shutdown())


def test_security_health_facade(tmp_path):
    m = _mod(tmp_path)
    report = m.security_health()
    assert report["posture"] in ("ok", "degraded")
    assert report["probes"]["run"] > 0


def test_redteam_facade(tmp_path):
    m = _mod(tmp_path)
    r = m.redteam()
    assert r["total"] >= 10
    assert r["stop_rate"] == 1.0, f"slips: {r['slips']}"


def test_deploy_gate_facade_ok(tmp_path):
    m = _mod(tmp_path)
    r = m.assert_deploy_secure(raise_on_fail=False)
    assert r["ok"] is True
