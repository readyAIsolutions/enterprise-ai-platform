#!/usr/bin/env python3
"""Tests for DeploymentSecurityGate (Upgrade Run 4) — fail-closed deploy gate."""

import tempfile
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from enterprise.modules.model_security.deployment_gate import (
    DeploymentSecurityGate,
    DeploymentSecurityError,
)


def _gate(tmp, **kw):
    return DeploymentSecurityGate(audit_path=str(Path(tmp) / "audit.log"), **kw)


def test_healthy_gate_passes(tmp_path):
    g = _gate(tmp_path)
    r = g.check()
    assert r["ok"] is True
    assert r["failures"] == []


def test_audit_chain_enforced(tmp_path):
    g = _gate(tmp_path)
    r = g.check()
    assert r["audit_integrity_ok"] is True


def test_stop_rate_gate(tmp_path):
    g = _gate(tmp_path, min_stop_rate=1.0)
    # low stop rate -> fails (inspect without raising)
    r = g.check(stop_rate=0.5, raise_on_fail=False)
    assert r["ok"] is False
    assert any("stop rate" in f for f in r["failures"])

    # and it DOES raise when raising is enabled (fail-closed)
    try:
        g.check(stop_rate=0.5, raise_on_fail=True)
        raise AssertionError("should have raised")
    except DeploymentSecurityError:
        pass


def test_raise_on_fail(tmp_path):
    g = _gate(tmp_path, min_stop_rate=1.0)
    try:
        g.check(stop_rate=0.5, raise_on_fail=True)
        raise AssertionError("should have raised")
    except DeploymentSecurityError:
        pass  # expected
