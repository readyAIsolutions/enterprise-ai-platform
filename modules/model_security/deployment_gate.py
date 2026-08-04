#!/usr/bin/env python3
"""
UPGRADE RUN 4 — DeploymentSecurityGate: fail-closed deployment gate.

Decision: security must gate CONTROL-PLANE actions, not just model traffic.
This provides `assert_secure()` which runs the SecurityHealth self-audit and
RAISES (fails closed) unless the posture is healthy — intended to be called
before deploy / release / serve decisions so an unhealthy security posture
cannot silently ship. `required` failures are non-negotiable; `advisory` ones
are reported.

Stdlib-only.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from enterprise.modules.model_security.security_health import SecurityHealth


class DeploymentSecurityError(Exception):
    """Raised when the security posture fails a required gate."""


class DeploymentSecurityGate:
    """
    Call gate.check() before any deploy/release/serve. If required probes fail
    or the audit chain is broken, it raises and blocks. Optional `min_stop_rate`
    enforces the red-team stop rate (e.g. 1.0) on top.
    """

    REQUIRED_PROBES = {
        "injection.direct_override",
        "injection.delimiter",
        "jailbreak.persona",
        "jailbreak.ignore_rules",
        "secret.api_key",
        "pii.email",
        "output.secret_leak",
        "output.clean_allows",
    }

    def __init__(
        self,
        audit_path: str = "data/security_gate_audit.log",
        min_stop_rate: float = 1.0,
        require_audit_integrity: bool = True,
        config: Optional[Dict[str, Any]] = None,
    ):
        # Accept either a positional audit_path OR a config dict.
        if isinstance(audit_path, dict):
            config = audit_path
            audit_path = config.get("audit_path", "data/security_gate_audit.log")
        cfg = config or {}
        self.audit_path = cfg.get("audit_path") or audit_path
        self.health = SecurityHealth({"audit_path": self.audit_path})
        self.min_stop_rate = min_stop_rate
        self.require_audit_integrity = require_audit_integrity

    def check(
        self,
        gate_stats: Optional[Dict[str, Any]] = None,
        stop_rate: Optional[float] = None,
        raise_on_fail: bool = True,
    ) -> Dict[str, Any]:
        """Run the gate. If raise_on_fail, raise DeploymentSecurityError on failure."""
        report = self.health.report(gate_stats=gate_stats)

        failures = []
        # Check required probes by name.
        for p in self.health._probe():
            name = p["name"]
            if name in self.REQUIRED_PROBES and not p["ok"]:
                failures.append(f"required probe failed: {name} (expected_block={p['expected']})")

        if self.require_audit_integrity and not report["audit_chain"]["integrity_ok"]:
            failures.append("audit chain integrity check failed")

        if stop_rate is not None and stop_rate < self.min_stop_rate:
            failures.append(f"red-team stop rate {stop_rate} < required {self.min_stop_rate}")

        ok = len(failures) == 0
        result = {
            "ok": ok,
            "posture": report["posture"],
            "failures": failures,
            "probes_passed": report["probes"]["passed"],
            "probes_run": report["probes"]["run"],
            "audit_integrity_ok": report["audit_chain"]["integrity_ok"],
            "gate": gate_stats or {},
        }
        if not ok and raise_on_fail:
            raise DeploymentSecurityError(f"Deployment gate blocked: {failures}")
        return result
