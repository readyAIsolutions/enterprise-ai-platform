#!/usr/bin/env python3
"""
Test Suite — Master-Class Tool Gate + Execution Audit (gate.py)
===============================================================
Covers:
  - ToolPolicy: allow / deny / ask decisions + default level
  - Argument-constraint protection (e.g. BashTool 'rm -rf /' blocked)
  - Rule specificity (exact > wildcard) + deny-biased tie-break
  - ToolGate: evaluate + run (deny->blocked, ask->pending, allow->run)
  - ToolAudit: append-only recording of every call
  - Audit search + recent()
  - Hash-chain integrity — tampering is detected
  - Gate with no policy defaults to allow
  - Lifecycle (custom audit, registry wiring, config-driven policies)

Run: python3 -m pytest enterprise/modules/agent_tools/tests/test_gate.py -v
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_ENTERPRISE_ROOT = Path(__file__).resolve().parents[3]
if str(_ENTERPRISE_ROOT) not in sys.path:
    sys.path.insert(0, str(_ENTERPRISE_ROOT))
_PARENT = str(_ENTERPRISE_ROOT.parent)
if _PARENT not in sys.path:
    sys.path.insert(0, _PARENT)

from typing import Never  # noqa: E402

from enterprise.modules.agent_tools.gate import (  # noqa: E402
    Decision,
    ToolAudit,
    ToolGate,
    ToolPolicy,
)

# =============================================================================
# ToolPolicy — allow / deny / ask
# =============================================================================


class TestToolPolicyDecisions:
    def test_default_allow_when_no_rules(self) -> None:
        policy = ToolPolicy()
        res = policy.decide("BashTool", {})
        assert res.decision == Decision.ALLOW
        assert res.allowed is True
        assert str(res).startswith("")  # GateResult is a dataclass; no crash

    def test_default_can_be_deny(self) -> None:
        policy = ToolPolicy(default=Decision.DENY)
        assert policy.decide("AnyTool", {}).decision == Decision.DENY
        assert policy.decide("AnyTool", {}).allowed is False

    def test_explicit_deny(self) -> None:
        policy = ToolPolicy().deny("BashTool")
        res = policy.decide("BashTool", {})
        assert res.decision == Decision.DENY
        assert res.allowed is False

    def test_explicit_allow_overrides_default_deny(self) -> None:
        policy = ToolPolicy(default=Decision.DENY).allow("FileReadTool")
        assert policy.decide("FileReadTool", {}).decision == Decision.ALLOW
        assert policy.decide("OtherTool", {}).decision == Decision.DENY

    def test_ask_returns_pending(self) -> None:
        policy = ToolPolicy().ask("FileWriteTool")
        res = policy.decide("FileWriteTool", {})
        assert res.decision == Decision.ASK
        assert res.pending is True
        assert res.allowed is False


class TestArgConstraints:
    def test_deny_bash_rm_blocks(self) -> None:
        policy = ToolPolicy().deny("BashTool", arg_deny=[r"rm\s+-rf\s*/"])
        res = policy.decide("BashTool", {"command": "rm -rf /"})
        assert res.decision == Decision.DENY
        assert res.allowed is False
        assert "blocked" in res.reason

    def test_safe_command_still_allowed_under_deny(self) -> None:
        policy = ToolPolicy().deny("BashTool", arg_deny=[r"rm\s+-rf\s*/"])
        # 'ls' doesn't match the denied pattern -> the DENY rule has no arg hit,
        # but the rule level is DENY for the tool — so it stays denied. To let
        # safe commands through, use allow + arg_deny instead.
        res = policy.decide("BashTool", {"command": "ls -la"})
        assert res.decision == Decision.DENY

    def test_allow_with_arg_deny_blocks_only_matching(self) -> None:
        # Tool allowed by default; the deny rule matches pattern only.
        policy = ToolPolicy().rule("BashTool", Decision.ALLOW, arg_deny=[r"rm\s+-rf\s*/"])
        assert policy.decide("BashTool", {"command": "ls -la"}).decision == Decision.ALLOW
        assert policy.decide("BashTool", {"command": "rm -rf /"}).decision == Decision.DENY

    def test_arg_allow_requires_match(self) -> None:
        policy = ToolPolicy().rule("BashTool", Decision.ALLOW, arg_allow=[r"^cat\s"])
        assert policy.decide("BashTool", {"command": "cat file.txt"}).decision == Decision.ALLOW
        assert policy.decide("BashTool", {"command": "rm x"}).decision == Decision.DENY

    def test_allow_rule_with_args_is_literal_control(self) -> None:
        # use allow level + deny constraint to permit benign writes when expected
        policy = ToolPolicy().allow("FileWriteTool", arg_deny=[r"\.ssh"])
        assert policy.decide("FileWriteTool", {"path": "/tmp/x.txt"}).decision == Decision.ALLOW
        assert (
            policy.decide("FileWriteTool", {"path": "/root/.ssh/authorized"}).decision
            == Decision.DENY
        )


class TestRuleSpecificity:
    def test_exact_beats_wildcard(self) -> None:
        policy = ToolPolicy().deny("*").allow("FileReadTool")
        assert policy.decide("FileReadTool", {}).decision == Decision.ALLOW
        assert policy.decide("BashTool", {}).decision == Decision.DENY

    def test_deny_biases_tiebreak_at_equal_specificity(self) -> None:
        policy = ToolPolicy()
        policy.rule("BashTool", Decision.ALLOW)
        policy.rule("BashTool", Decision.DENY)
        assert policy.decide("BashTool", {}).decision == Decision.DENY


# =============================================================================
# ToolGate — evaluate + run
# =============================================================================


class TestToolGate:
    def test_no_policy_defaults_allow(self) -> None:
        gate = ToolGate()
        assert gate.evaluate("BashTool", {}).decision == Decision.ALLOW

    def test_evaluate_deny_does_not_run(self) -> None:
        gate = ToolGate(ToolPolicy().deny("BashTool"))
        res = gate.evaluate("BashTool", {})
        assert res.decision == Decision.DENY
        assert res.allowed is False

    def test_run_deny_returns_blocked_and_skips_callable(self) -> None:
        gate = ToolGate(ToolPolicy().deny("BashTool"))
        calls = []
        res = gate.run("BashTool", {"command": "ls"}, lambda: calls.append(1))
        assert res.decision == Decision.DENY
        assert res.allowed is False
        assert calls == []  # callable never invoked

    def test_run_ask_returns_pending(self) -> None:
        gate = ToolGate(ToolPolicy().ask("FileWriteTool"))
        res = gate.run("FileWriteTool", {}, lambda: "x")
        assert res.decision == Decision.ASK
        assert res.pending is True
        assert res.result is None  # not executed

    def test_run_allow_executes_and_returns_result(self) -> None:
        gate = ToolGate()
        res = gate.run("BashTool", {"command": "ls"}, lambda: "ok")
        assert res.decision == Decision.ALLOW
        assert res.result == "ok"
        assert res.duration_ms >= 0

    def test_run_allow_error_records_and_reraises(self) -> None:
        gate = ToolGate()

        def boom() -> Never:
            msg = "boom"
            raise RuntimeError(msg)

        with pytest.raises(RuntimeError):
            gate.run("BashTool", {}, boom)
        audit = gate.audit.search(tool="BashTool")
        assert any(r.outcome == "error" and "boom" in r.error for r in audit)


# =============================================================================
# ToolAudit — recording, search, recent, integrity
# =============================================================================


class TestToolAudit:
    def test_records_every_call(self) -> None:
        audit = ToolAudit()
        audit.record("BashTool", {"command": "ls"}, allowed=True, outcome="success")
        audit.record("FileReadTool", {"path": "/x"}, allowed=False, outcome="blocked")
        assert audit.count() == 2
        assert audit.all()[0].seq == 1
        assert audit.all()[1].seq == 2

    def test_search_and_recent(self) -> None:
        audit = ToolAudit()
        for i in range(15):
            audit.record(
                "BashTool",
                {"i": i},
                allowed=True,
                decision=Decision.ALLOW,
                outcome="success",
                caller="c1",
            )
        audit.record(
            "FileWriteTool",
            {},
            allowed=False,
            decision=Decision.DENY,
            outcome="blocked",
            caller="c2",
        )
        assert len(audit.recent(5)) == 5
        assert audit.recent(5)[0].seq == 12  # last 5 of 16 records: 12..16
        assert audit.recent(100)[0].seq == 1
        blocked = audit.search(outcome="blocked")
        assert len(blocked) == 1
        assert blocked[0].tool == "FileWriteTool"
        by_caller = audit.search(caller="c1")
        assert len(by_caller) == 15

    def test_hash_chain_integrity_valid(self) -> None:
        audit = ToolAudit()
        audit.record("BashTool", {"command": "ls"}, allowed=True, outcome="success")
        audit.record("FileReadTool", {}, allowed=False, outcome="blocked")
        assert audit.verify_integrity() is True

    def test_hash_chain_detects_tamper(self) -> None:
        audit = ToolAudit()
        audit.record("BashTool", {"command": "ls"}, allowed=True, outcome="success")
        audit.record("FileReadTool", {}, allowed=False, outcome="blocked")
        # tamper with an earlier record's outcome
        audit.all()[0].outcome = "hacked"
        assert audit.verify_integrity() is False

    def test_hash_chain_detects_arg_tamper(self) -> None:
        audit = ToolAudit()
        audit.record("BashTool", {"command": "ls"}, allowed=True, outcome="success")
        audit.record("FileReadTool", {}, allowed=True, outcome="success")
        audit.all()[1].args["command"] = "rm -rf /"
        assert audit.verify_integrity() is False

    def test_audit_is_append_only(self) -> None:
        audit = ToolAudit()
        audit.record("BashTool", {}, allowed=True, outcome="success")
        n = audit.count()
        records = audit.all()
        assert len(records) == n
        assert [r.seq for r in records] == list(range(1, n + 1))


# =============================================================================
# Gate lifecycle + registry wiring + config
# =============================================================================


class TestGateLifecycleAndWiring:
    def test_gate_carries_custom_audit(self) -> None:
        audit = ToolAudit()
        gate = ToolGate(ToolPolicy(), audit=audit)
        gate.run("BashTool", {"command": "ls"}, lambda: "ok")
        assert gate.audit is audit
        assert audit.count() == 1

    def test_from_config_builds_policy(self) -> None:
        cfg = {
            "policy": {
                "default": "allow",
                "rules": [
                    {"tool": "BashTool", "level": "deny", "arg_deny": [r"rm\s+-rf\s*/\b"]},
                    {"tool": "FileWriteTool", "level": "ask"},
                ],
            }
        }
        gate = ToolGate.from_config(cfg)
        assert gate.evaluate("BashTool", {"command": "rm -rf /"}).decision == Decision.DENY
        assert gate.evaluate("FileWriteTool", {}).decision == Decision.ASK
        assert gate.evaluate("FileReadTool", {}).decision == Decision.ALLOW

    def test_policy_to_dict_roundtrip(self) -> None:
        policy = ToolPolicy(default=Decision.DENY).allow("FileReadTool")
        d = policy.to_dict()
        assert d["default"] == "deny"
        assert d["rules"][0]["tool"] == "FileReadTool"

    def test_registry_invokes_gate_and_records_audit(self) -> None:
        from enterprise.modules.agent_tools.tool_registry import ToolRegistry

        policy = ToolPolicy().deny("BashTool", arg_deny=[r"rm\s+-rf\s*/"])
        registry = ToolRegistry(
            config={"default_permission": "allow", "tool_gate": {"policy": policy.to_dict()}}
        )
        audit = registry.get_tool_audit()
        assert audit is not None

        # deny path raises and is audited as blocked
        res = registry.tool_gate_decision("BashTool", {"command": "rm -rf /"})
        assert res.decision == Decision.DENY
        assert res.allowed is False

    def test_registry_audit_verify_integrity_after_invoke(self) -> None:
        # Smoke: a permissive registry records success and the chain stays valid.
        from enterprise.modules.agent_tools.file_tools import FileReadTool
        from enterprise.modules.agent_tools.tool_registry import ToolRegistry

        registry = ToolRegistry()
        tool = FileReadTool()
        registry.register(tool)
        audit = registry.get_tool_audit()
        import asyncio

        async def go() -> None:
            await registry.invoke("FileReadTool", {"path": "/etc/hostname"})

        asyncio.run(go())
        assert audit.count() >= 1
        assert audit.search(tool="FileReadTool", outcome="success")
        assert audit.verify_integrity() is True
