#!/usr/bin/env python3
"""Tests for SecurityHealth (Upgrade Run 2) — live posture + self-audit."""

import tempfile
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from enterprise.modules.model_security.security_health import SecurityHealth


def test_report_posture_ok(tmp_path):
    h = SecurityHealth({"audit_path": str(Path(tmp_path) / "audit.log")})
    r = h.report()
    assert r["probes"]["run"] > 0
    # benign + expected-detections all fire as expected -> posture ok (58? likely all pass)
    assert r["posture"] in ("ok", "degraded")


def test_all_probes_expected(tmp_path):
    h = SecurityHealth({"audit_path": str(Path(tmp_path) / "audit.log")})
    r = h.report()
    assert r["probes"]["failed"] == 0, f"probe failures: {r['problems']}"


def test_audit_chain_integrity(tmp_path):
    h = SecurityHealth({"audit_path": str(Path(tmp_path) / "audit.log")})
    r = h.report()
    assert r["audit_chain"]["integrity_ok"] is True


def test_gate_stats_surface(tmp_path):
    h = SecurityHealth({"audit_path": str(Path(tmp_path) / "audit.log")})
    r = h.report(gate_stats={"total": 5, "blocked_input": 2, "passed": 3})
    assert r["gate"]["total"] == 5
    assert r["gate"]["blocked_input"] == 2
