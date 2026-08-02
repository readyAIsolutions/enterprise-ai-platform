"""
Tests for Policy Engine — covers policy definition (JSON/YAML), enforcement,
audit logging, conflict detection, compliance mapping, and serialization.
"""

import json
import pytest
from copy import deepcopy

from enterprise.foundation.policy_engine import (
    Severity,
    EnforcementAction,
    ComplianceFramework,
    PolicyError,
    PolicyDefinitionError,
    PolicyConflictError,
    RuleCondition,
    PolicyRule,
    PolicyDefinition,
    Violation,
    PolicySet,
    PolicyEnforcer,
    EnforcementResult,
    AuditLogger,
    AuditEntry,
    ConflictDetector,
    ConflictReport,
    ComplianceMapper,
    ComplianceMapping,
    DataPrivacyPreset,
    SecurityPreset,
)


# ────────────────────────────────────────────────────────────────────
# RuleCondition
# ────────────────────────────────────────────────────────────────────

class TestRuleCondition:
    def test_eq(self):
        c = RuleCondition("field", "eq", "hello")
        assert c.evaluate({"field": "hello"})
        assert not c.evaluate({"field": "world"})

    def test_neq(self):
        c = RuleCondition("field", "neq", "hello")
        assert c.evaluate({"field": "world"})
        assert not c.evaluate({"field": "hello"})

    def test_regex(self):
        c = RuleCondition("content", "regex", r"\b[A-Z]{3}\b")
        assert c.evaluate({"content": "The code is ABC here"})
        assert not c.evaluate({"content": "no uppercase codes"})

    def test_regex_invalid(self):
        c = RuleCondition("content", "regex", r"[invalid")
        assert not c.evaluate({"content": "anything"})

    def test_contains(self):
        c = RuleCondition("text", "contains", "secret")
        assert c.evaluate({"text": "my secret data"})
        assert not c.evaluate({"text": "nothing here"})

    def test_gt(self):
        c = RuleCondition("score", "gt", 10)
        assert c.evaluate({"score": 15})
        assert not c.evaluate({"score": 5})

    def test_lt(self):
        c = RuleCondition("score", "lt", 10)
        assert c.evaluate({"score": 5})
        assert not c.evaluate({"score": 15})

    def test_gte_lte(self):
        gte = RuleCondition("score", "gte", 10)
        lte = RuleCondition("score", "lte", 10)
        assert gte.evaluate({"score": 10})
        assert lte.evaluate({"score": 10})

    def test_in(self):
        c = RuleCondition("role", "in", ["admin", "superadmin"])
        assert c.evaluate({"role": "admin"})
        assert not c.evaluate({"role": "user"})

    def test_not_in(self):
        c = RuleCondition("role", "not_in", ["banned", "suspended"])
        assert c.evaluate({"role": "user"})
        assert not c.evaluate({"role": "banned"})

    def test_exists(self):
        c = RuleCondition("email", "exists")
        assert c.evaluate({"email": "a@b.com"})
        assert not c.evaluate({})

    def test_not_exists(self):
        c = RuleCondition("email", "not_exists")
        assert c.evaluate({})
        assert not c.evaluate({"email": "a@b.com"})

    def test_any_of(self):
        c = RuleCondition("status", "any_of", ["active", "pending"])
        assert c.evaluate({"status": "active"})
        assert not c.evaluate({"status": "inactive"})

    def test_negate(self):
        c = RuleCondition("field", "eq", "hello", negate=True)
        assert not c.evaluate({"field": "hello"})
        assert c.evaluate({"field": "world"})

    def test_unsupported_operator_raises(self):
        with pytest.raises(PolicyDefinitionError):
            RuleCondition("f", "invalid_op", "v")

    def test_serialization_roundtrip(self):
        c = RuleCondition("field", "regex", r"\d+", negate=True)
        d = c.to_dict()
        c2 = RuleCondition.from_dict(d)
        assert c2.field == "field"
        assert c2.operator == "regex"
        assert c2.value == r"\d+"
        assert c2.negate is True


# ────────────────────────────────────────────────────────────────────
# PolicyRule
# ────────────────────────────────────────────────────────────────────

class TestPolicyRule:
    def test_and_conditions(self):
        r = PolicyRule("test", conditions=[
            RuleCondition("a", "eq", 1),
            RuleCondition("b", "eq", 2),
        ], match_all=True)
        assert r.evaluate({"a": 1, "b": 2})
        assert not r.evaluate({"a": 1, "b": 3})

    def test_or_conditions(self):
        r = PolicyRule("test", conditions=[
            RuleCondition("a", "eq", 1),
            RuleCondition("b", "eq", 2),
        ], match_all=False)
        assert r.evaluate({"a": 1, "b": 99})
        assert r.evaluate({"a": 99, "b": 2})
        assert not r.evaluate({"a": 99, "b": 99})

    def test_disabled_rule(self):
        r = PolicyRule("test", conditions=[RuleCondition("a", "eq", 1)], enabled=False)
        assert not r.evaluate({"a": 1})

    def test_custom_evaluator(self):
        r = PolicyRule("custom", custom_evaluator=lambda d: d.get("x", 0) > 10)
        assert r.evaluate({"x": 20})
        assert not r.evaluate({"x": 5})

    def test_no_conditions(self):
        r = PolicyRule("empty")
        assert not r.evaluate({"anything": 1})

    def test_compliance_refs(self):
        r = PolicyRule("data_encrypt", compliance_refs=[ComplianceFramework.GDPR,
                                                        ComplianceFramework.SOC2])
        assert ComplianceFramework.GDPR in r.compliance_refs

    def test_to_from_dict(self):
        r = PolicyRule("test_rule", description="desc",
                       conditions=[RuleCondition("f", "eq", "val")],
                       action=EnforcementAction.DENY, severity=Severity.CRITICAL,
                       remediation="Fix it")
        d = r.to_dict()
        r2 = PolicyRule.from_dict(d)
        assert r2.name == "test_rule"
        assert r2.action == EnforcementAction.DENY
        assert r2.severity == Severity.CRITICAL


# ────────────────────────────────────────────────────────────────────
# PolicyDefinition
# ────────────────────────────────────────────────────────────────────

class TestPolicyDefinition:
    def test_to_json(self):
        p = PolicyDefinition(name="Test", domain="security", rules=[
            PolicyRule("r1", conditions=[RuleCondition("f", "eq", 1)])
        ])
        s = p.to_json()
        d = json.loads(s)
        assert d["name"] == "Test"
        assert len(d["rules"]) == 1

    def test_from_json(self):
        p = PolicyDefinition(name="Test", domain="privacy")
        s = p.to_json()
        p2 = PolicyDefinition.from_json(s)
        assert p2.name == "Test"
        assert p2.domain == "privacy"

    def test_to_yaml(self):
        # Will skip if yaml not installed
        try:
            import yaml
            p = PolicyDefinition(name="Test", domain="security")
            s = p.to_yaml()
            assert "name: Test" in s
        except ImportError:
            pytest.skip("PyYAML not installed")

    def test_from_yaml(self):
        try:
            import yaml
            p = PolicyDefinition(name="YAML Test", domain="org")
            s = p.to_yaml()
            p2 = PolicyDefinition.from_yaml(s)
            assert p2.name == "YAML Test"
        except ImportError:
            pytest.skip("PyYAML not installed")

    def test_enabled_rules(self):
        p = PolicyDefinition(name="T", rules=[
            PolicyRule("r1", enabled=True, conditions=[RuleCondition("f", "eq", 1)]),
            PolicyRule("r2", enabled=False, conditions=[RuleCondition("f", "eq", 1)]),
        ])
        assert len(p.enabled_rules) == 1

    def test_add_remove_rule(self):
        p = PolicyDefinition(name="T")
        r = PolicyRule("r1")
        p.add_rule(r)
        assert len(p.rules) == 1
        assert p.remove_rule(r.rule_id) is True
        assert len(p.rules) == 0
        assert p.remove_rule("nonexistent") is False


# ────────────────────────────────────────────────────────────────────
# Audit Logger
# ────────────────────────────────────────────────────────────────────

class TestAuditLogger:
    @pytest.fixture
    def audit(self):
        return AuditLogger()

    def test_log_entry(self, audit):
        entry = audit.log("evaluate", policy_id="p1", rule_id="r1",
                          action="warn", severity="HIGH", message="Test")
        assert entry.event_type == "evaluate"
        assert entry.policy_id == "p1"
        assert len(audit) == 1

    def test_query_by_event_type(self, audit):
        audit.log("deny", policy_id="p1")
        audit.log("allow", policy_id="p2")
        results = audit.query(event_type="deny")
        assert len(results) == 1
        assert results[0].event_type == "deny"

    def test_query_by_severity(self, audit):
        audit.log("violation", severity="HIGH", policy_id="p1")
        audit.log("violation", severity="LOW", policy_id="p2")
        results = audit.query(severity="HIGH")
        assert len(results) == 1

    def test_integrity_check(self, audit):
        for i in range(10):
            audit.log("test", message=f"msg{i}")
        assert audit.verify_integrity() is True

    def test_integrity_tampered(self, audit):
        audit.log("test", message="original")
        # Tamper with an entry
        audit._entries[0].message = "tampered!"
        assert audit.verify_integrity() is False

    def test_export(self, audit):
        audit.log("test", message="hello")
        exported = audit.export()
        assert len(exported) == 1
        assert exported[0]["message"] == "hello"

    def test_max_entries(self):
        audit = AuditLogger(max_entries=3)
        for i in range(5):
            audit.log("test", message=f"msg{i}")
        assert len(audit) == 3

    def test_clear(self, audit):
        audit.log("test")
        audit.clear()
        assert len(audit) == 0


# ────────────────────────────────────────────────────────────────────
# Conflict Detector
# ────────────────────────────────────────────────────────────────────

class TestConflictDetector:
    @pytest.fixture
    def detector(self):
        return ConflictDetector()

    def test_opposite_action_conflict(self, detector):
        p1 = PolicyDefinition(name="P1", policy_id="p1", rules=[
            PolicyRule("r1", conditions=[RuleCondition("f", "eq", 1)],
                       action=EnforcementAction.ALLOW)
        ])
        p2 = PolicyDefinition(name="P2", policy_id="p2", rules=[
            PolicyRule("r2", conditions=[RuleCondition("f", "eq", 1)],
                       action=EnforcementAction.DENY)
        ])
        conflicts = detector.detect([p1, p2])
        assert len(conflicts) > 0
        assert any(c.conflict_type == "opposite_action" for c in conflicts)

    def test_redundant_rules(self, detector):
        p1 = PolicyDefinition(name="P1", policy_id="p1", rules=[
            PolicyRule("r1", conditions=[RuleCondition("f", "eq", 1)],
                       action=EnforcementAction.DENY)
        ])
        p2 = PolicyDefinition(name="P2", policy_id="p2", rules=[
            PolicyRule("r2", conditions=[RuleCondition("f", "eq", 1)],
                       action=EnforcementAction.DENY)
        ])
        conflicts = detector.detect([p1, p2])
        assert any(c.conflict_type == "redundant" for c in conflicts)

    def test_overlapping_scope(self, detector):
        p1 = PolicyDefinition(name="P1", policy_id="p1", rules=[
            PolicyRule("r1", conditions=[RuleCondition("f", "eq", 1),
                                         RuleCondition("g", "eq", 2)])
        ])
        p2 = PolicyDefinition(name="P2", policy_id="p2", rules=[
            PolicyRule("r2", conditions=[RuleCondition("f", "eq", 1)])
        ])
        conflicts = detector.detect([p1, p2])
        assert any(c.conflict_type == "overlapping_scope" for c in conflicts)

    def test_no_conflicts(self, detector):
        p1 = PolicyDefinition(name="P1", policy_id="p1", rules=[
            PolicyRule("r1", conditions=[RuleCondition("a", "eq", 1)])
        ])
        p2 = PolicyDefinition(name="P2", policy_id="p2", rules=[
            PolicyRule("r2", conditions=[RuleCondition("b", "eq", 2)])
        ])
        conflicts = detector.detect([p1, p2])
        assert len(conflicts) == 0

    def test_disabled_policy_ignored(self, detector):
        p1 = PolicyDefinition(name="P1", policy_id="p1", enabled=False, rules=[
            PolicyRule("r1", conditions=[RuleCondition("f", "eq", 1)],
                       action=EnforcementAction.ALLOW)
        ])
        p2 = PolicyDefinition(name="P2", policy_id="p2", rules=[
            PolicyRule("r2", conditions=[RuleCondition("f", "eq", 1)],
                       action=EnforcementAction.DENY)
        ])
        conflicts = detector.detect([p1, p2])
        # Only p2 is enabled, so no conflict
        assert all(c.policy_a_id != "p1" for c in conflicts)
        assert all(c.policy_b_id != "p1" for c in conflicts)


# ────────────────────────────────────────────────────────────────────
# Compliance Mapper
# ────────────────────────────────────────────────────────────────────

class TestComplianceMapper:
    @pytest.fixture
    def mapper(self):
        m = ComplianceMapper()
        m.register(ComplianceMapping(
            policy_id="p1", framework=ComplianceFramework.GDPR,
            control_ids=["GDPR-Art.5", "GDPR-Art.32"]
        ))
        m.register(ComplianceMapping(
            policy_id="p2", framework=ComplianceFramework.GDPR,
            control_ids=["GDPR-Art.32", "GDPR-Art.35"]
        ))
        return m

    def test_covered_controls(self, mapper):
        covered = mapper.get_covered_controls(ComplianceFramework.GDPR)
        assert "GDPR-Art.5" in covered
        assert "GDPR-Art.32" in covered
        assert "GDPR-Art.35" in covered

    def test_gap_analysis(self, mapper):
        gap = mapper.gap_analysis(ComplianceFramework.GDPR)
        assert gap["framework"] == "GDPR"
        assert gap["covered"] >= 3
        assert gap["total_controls"] > 0
        assert "coverage_pct" in gap
        assert "missing_controls" in gap

    def test_export(self, mapper):
        exp = mapper.export()
        assert "GDPR" in exp
        assert "SOC2" in exp
        assert "HIPAA" in exp
        assert "PCI-DSS" in exp


# ────────────────────────────────────────────────────────────────────
# Policy Set
# ────────────────────────────────────────────────────────────────────

class TestPolicySet:
    def test_add_and_list(self):
        ps = PolicySet()
        p = PolicyDefinition(name="Test", policy_id="p1")
        ps.add(p)
        assert ps.get("p1") is not None
        assert len(ps.list_all()) == 1

    def test_remove(self):
        ps = PolicySet()
        p = PolicyDefinition(name="T", policy_id="p1")
        ps.add(p)
        assert ps.remove("p1") is True
        assert ps.remove("p1") is False

    def test_list_enabled(self):
        ps = PolicySet()
        ps.add(PolicyDefinition(name="E1", policy_id="e1", enabled=True))
        ps.add(PolicyDefinition(name="E2", policy_id="e2", enabled=False))
        assert len(ps.list_enabled()) == 1

    def test_list_by_domain(self):
        ps = PolicySet()
        ps.add(PolicyDefinition(name="S", policy_id="s1", domain="security"))
        ps.add(PolicyDefinition(name="P", policy_id="p1", domain="privacy"))
        assert len(ps.list_by_domain("security")) == 1

    def test_detect_conflicts(self):
        ps = PolicySet()
        ps.add(PolicyDefinition(name="P1", policy_id="p1", rules=[
            PolicyRule("r1", conditions=[RuleCondition("f", "eq", 1)],
                       action=EnforcementAction.ALLOW)
        ]))
        ps.add(PolicyDefinition(name="P2", policy_id="p2", rules=[
            PolicyRule("r2", conditions=[RuleCondition("f", "eq", 1)],
                       action=EnforcementAction.DENY)
        ]))
        conflicts = ps.detect_conflicts()
        assert len(conflicts) > 0

    def test_serialization_roundtrip(self):
        ps = PolicySet(name="test_set", version="2.0.0")
        ps.add(DataPrivacyPreset.create())
        d = ps.to_dict()
        ps2 = PolicySet.from_dict(d)
        assert ps2.name == "test_set"
        assert ps2.version == "2.0.0"
        assert len(ps2.list_all()) == 1


# ────────────────────────────────────────────────────────────────────
# Policy Enforcer
# ────────────────────────────────────────────────────────────────────

class TestPolicyEnforcer:
    @pytest.fixture
    def enforcer(self):
        ps = PolicySet()
        ps.add(DataPrivacyPreset.create())
        ps.add(SecurityPreset.create())
        return PolicyEnforcer(policy_set=ps)

    def test_enforce_clean_data(self, enforcer):
        result = enforcer.enforce({"content": "This is a clean document with no issues."})
        assert result.allowed is True

    def test_enforce_email_detection(self, enforcer):
        result = enforcer.enforce({"content": "Contact us at user@example.com for details."})
        assert len(result.violations) >= 1
        assert any("Email" in v.rule_name for v in result.violations)

    def test_enforce_sql_injection(self, enforcer):
        result = enforcer.enforce({"content": "SELECT * FROM users; DROP TABLE users;"})
        assert result.allowed is False

    def test_enforce_xss(self, enforcer):
        result = enforcer.enforce({"content": "<script>alert('xss')</script>"})
        assert result.allowed is False

    def test_enforce_ssn(self, enforcer):
        result = enforcer.enforce({"content": "SSN: 123-45-6789"})
        assert result.allowed is False

    def test_enforce_credit_card(self, enforcer):
        result = enforcer.enforce({"content": "Card: 4111-1111-1111-1111"})
        assert result.allowed is False

    def test_enforce_domain_filter(self, enforcer):
        result = enforcer.enforce({"content": "user@example.com"}, domains=["privacy"])
        assert len(result.violations) >= 1  # email in privacy domain

    def test_enforce_policy_id_filter(self, enforcer):
        # Only enforce security policy — email is in privacy, so no violation
        ps = enforcer.policy_set
        sec_pol = [p for p in ps.list_all() if p.domain == "security"]
        if sec_pol:
            result = enforcer.enforce({"content": "user@example.com"},
                                      policy_ids=[sec_pol[0].policy_id])
            # Email is not a security violation
            email_violations = [v for v in result.violations if "Email" in v.rule_name]
            assert len(email_violations) == 0

    def test_max_severity(self, enforcer):
        result = enforcer.enforce({"content": "SELECT * FROM users; SSN: 123-45-6789"})
        assert result.has_critical is True
        assert result.max_severity == Severity.CRITICAL

    def test_enforcement_result_to_dict(self, enforcer):
        result = enforcer.enforce({"content": "Clean text"})
        d = result.to_dict()
        assert d["allowed"] is True
        assert "run_id" in d
        assert "violations" in d

    def test_enforce_with_redaction(self, enforcer):
        result, redacted = enforcer.enforce_with_redaction(
            {"content": "user@example.com", "secret": "my-api-key"},
            redact_fields=["secret"]
        )
        assert redacted["secret"] == "[REDACTED]"
        assert "user@example.com" in redacted["content"]

    def test_hooks(self, enforcer):
        calls = []

        def pre_hook(data):
            calls.append("pre")
            return data

        def post_hook(result):
            calls.append("post")

        enforcer.add_hook("pre", pre_hook)
        enforcer.add_hook("post", post_hook)
        enforcer.enforce({"content": "clean"})
        assert "pre" in calls
        assert "post" in calls

    def test_default_action(self):
        enforcer = PolicyEnforcer(default_action=EnforcementAction.DENY)
        result = enforcer.enforce({"content": "clean"})
        assert result.allowed is True  # no DENY rules triggered


# ────────────────────────────────────────────────────────────────────
# Presets
# ────────────────────────────────────────────────────────────────────

class TestPresets:
    def test_data_privacy(self):
        p = DataPrivacyPreset.create()
        assert p.domain == "privacy"
        assert len(p.rules) == 7
        assert any("Email" in r.name for r in p.rules)

    def test_security(self):
        p = SecurityPreset.create()
        assert p.domain == "security"
        assert len(p.rules) == 5
        assert any("SQL" in r.name for r in p.rules)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])