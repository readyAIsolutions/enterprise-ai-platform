"""
Tests for the Config & Feature Flag System module.

Covers:
  - Flag CRUD (create, read, update, delete)
  - Boolean and multivariate flag evaluation
  - Targeting rules (user, tenant, attribute-based)
  - Percentage rollouts with consistent bucketing
  - Kill switches and flag state management
  - Flag dependencies
  - Config versioning and rollback
  - Audit logging
  - Cache invalidation
"""

import time
from unittest.mock import MagicMock, patch

import pytest

from enterprise.orchestration.feature_flags import (
    FeatureFlagEngine,
    ConfigVersionStore,
    AuditLogger,
    FlagDefinition,
    TargetRule,
    TargetingRuleSet,
    AuditEntry,
    ConfigSnapshot,
    FlagType,
    FlagState,
    TargetOperator,
    AuditAction,
    FeatureFlagError,
    FlagNotFoundError,
    FlagDependencyError,
    FlagValidationError,
    ConfigVersionError,
    create_engine,
)


# ---------------------------------------------------------------------------
# Targeting Rules Tests
# ---------------------------------------------------------------------------

class TestTargetRule:
    """Tests for individual targeting rules."""

    def test_equals_match(self):
        rule = TargetRule("country", TargetOperator.EQUALS, "US")
        assert rule.evaluate({"country": "US"})
        assert not rule.evaluate({"country": "CA"})

    def test_not_equals(self):
        rule = TargetRule("plan", TargetOperator.NOT_EQUALS, "free")
        assert rule.evaluate({"plan": "premium"})
        assert not rule.evaluate({"plan": "free"})

    def test_in_operator(self):
        rule = TargetRule("role", TargetOperator.IN, ["admin", "superadmin"])
        assert rule.evaluate({"role": "admin"})
        assert rule.evaluate({"role": "superadmin"})
        assert not rule.evaluate({"role": "user"})

    def test_not_in_operator(self):
        rule = TargetRule("team", TargetOperator.NOT_IN, ["blocked_a", "blocked_b"])
        assert rule.evaluate({"team": "engineering"})
        assert not rule.evaluate({"team": "blocked_a"})

    def test_contains_operator(self):
        rule = TargetRule("tags", TargetOperator.CONTAINS, "beta")
        assert rule.evaluate({"tags": ["alpha", "beta", "gamma"]})
        assert not rule.evaluate({"tags": ["alpha", "gamma"]})

    def test_starts_with(self):
        rule = TargetRule("email", TargetOperator.STARTS_WITH, "admin@")
        assert rule.evaluate({"email": "admin@company.com"})
        assert not rule.evaluate({"email": "user@company.com"})

    def test_ends_with(self):
        rule = TargetRule("email", TargetOperator.ENDS_WITH, "@partner.com")
        assert rule.evaluate({"email": "user@partner.com"})
        assert not rule.evaluate({"email": "user@corp.com"})

    def test_greater_than(self):
        rule = TargetRule("score", TargetOperator.GREATER_THAN, 90)
        assert rule.evaluate({"score": 95})
        assert not rule.evaluate({"score": 85})

    def test_greater_equal(self):
        rule = TargetRule("score", TargetOperator.GREATER_EQUAL, 90)
        assert rule.evaluate({"score": 90})
        assert rule.evaluate({"score": 91})

    def test_less_than(self):
        rule = TargetRule("latency", TargetOperator.LESS_THAN, 100)
        assert rule.evaluate({"latency": 50})
        assert not rule.evaluate({"latency": 200})

    def test_regex(self):
        rule = TargetRule("hostname", TargetOperator.REGEX, r"^prod-[a-z]+-\d+$")
        assert rule.evaluate({"hostname": "prod-web-01"})
        assert not rule.evaluate({"hostname": "dev-web-01"})

    def test_exists(self):
        rule = TargetRule("feature_tier", TargetOperator.EXISTS, None)
        assert rule.evaluate({"feature_tier": "pro"})
        assert not rule.evaluate({"other": "val"})

    def test_not_exists(self):
        rule = TargetRule("deprecated_flag", TargetOperator.NOT_EXISTS, None)
        assert rule.evaluate({"active": True})
        assert not rule.evaluate({"deprecated_flag": True})


class TestTargetingRuleSet:
    """Tests for the TargetingRuleSet (rule collections + rollout)."""

    def test_no_rules_matches_all(self):
        trs = TargetingRuleSet(default_serve=True)
        matched, value = trs.evaluate({"user_id": "u1"})
        assert matched
        assert value is True

    def test_rule_priority(self):
        trs = TargetingRuleSet(
            rules=[
                TargetRule("country", TargetOperator.EQUALS, "US", weight=10),
                TargetRule("country", TargetOperator.EQUALS, "CA", weight=5),
            ],
            default_serve=False,
        )
        # US should match the higher-weight rule
        matched, value = trs.evaluate({"country": "US"})
        assert matched

    def test_rollout_bucket_consistency(self):
        trs = TargetingRuleSet(
            rollout_percentage=50.0,
            rollout_salt="test-salt",
            default_serve=True,
        )
        # Same user always gets same result
        ctx = {"user_id": "user-123"}
        results = [trs.evaluate(ctx)[0] for _ in range(20)]
        assert all(r == results[0] for r in results)

    def test_rollout_0_percent(self):
        trs = TargetingRuleSet(
            rollout_percentage=0.0,
            rollout_salt="salt",
            default_serve=True,
        )
        # With 0% and no targeted rules, the rollout check prevents serving
        # Actually the code: if rollout_percentage < 100.0, check bucket.
        # If no rules match and bucket > percentage, returns (False, default)
        trs = TargetingRuleSet(
            rules=[],
            rollout_percentage=0.0,
            rollout_salt="salt",
            default_serve=True,
        )
        matched, _ = trs.evaluate({"user_id": "test"})
        # Almost certainly not matched at 0%
        assert matched is False


# ---------------------------------------------------------------------------
# Shared fixture
# ---------------------------------------------------------------------------

@pytest.fixture
def engine():
    return create_engine(cache_ttl=0)


# ---------------------------------------------------------------------------
# Feature Flag Engine Tests
# ---------------------------------------------------------------------------

class TestFeatureFlagEngine:
    """Comprehensive tests for the FeatureFlagEngine."""

    # ---- Flag CRUD ----

    def test_create_boolean_flag(self, engine):
        flag = engine.create_flag("test-flag", FlagType.BOOLEAN, enabled=True,
                                  description="Test boolean flag")
        assert flag.name == "test-flag"
        assert flag.enabled is True
        assert flag.state == FlagState.ACTIVE

    def test_create_duplicate_raises(self, engine):
        engine.create_flag("unique")
        with pytest.raises(FlagValidationError, match="already exists"):
            engine.create_flag("unique")

    def test_create_multivariate_flag(self, engine):
        flag = engine.create_flag(
            "theme",
            FlagType.MULTIVARIATE,
            value="dark",
            variations=["light", "dark", "auto"],
        )
        assert flag.flag_type == FlagType.MULTIVARIATE
        assert flag.value == "dark"

    def test_create_multivariate_invalid_value(self, engine):
        with pytest.raises(FlagValidationError, match="not in allowed variations"):
            engine.create_flag(
                "bad-var",
                FlagType.MULTIVARIATE,
                value="invalid",
                variations=["a", "b"],
            )

    def test_get_flag(self, engine):
        engine.create_flag("readable")
        flag = engine.get_flag("readable")
        assert flag.name == "readable"

    def test_get_flag_not_found(self, engine):
        with pytest.raises(FlagNotFoundError):
            engine.get_flag("nonexistent")

    def test_update_flag(self, engine):
        engine.create_flag("updatable", enabled=False, description="old")
        engine.update_flag("updatable", enabled=True, description="new",
                           reason="testing update")
        flag = engine.get_flag("updatable")
        assert flag.enabled is True
        assert flag.description == "new"

    def test_update_nonexistent_raises(self, engine):
        with pytest.raises(FlagNotFoundError):
            engine.update_flag("ghost")

    def test_delete_flag(self, engine):
        engine.create_flag("deletable")
        engine.delete_flag("deletable")
        with pytest.raises(FlagNotFoundError):
            engine.get_flag("deletable")

    def test_delete_flag_with_dependents_raises(self, engine):
        engine.create_flag("base")
        engine.create_flag("dependent", dependencies=["base"])
        with pytest.raises(FlagDependencyError):
            engine.delete_flag("base")

    def test_list_flags(self, engine):
        engine.create_flag("f1", tags={"alpha"})
        engine.create_flag("f2", tags={"beta"})
        engine.create_flag("f3", tags={"alpha"})

        all_flags = engine.list_flags()
        assert len(all_flags) == 3

        alpha_flags = engine.list_flags(tag="alpha")
        assert len(alpha_flags) == 2

    # ---- Flag Evaluation ----

    def test_is_enabled_simple(self, engine):
        engine.create_flag("feature-x", enabled=True)
        assert engine.is_enabled("feature-x") is True

        engine.create_flag("feature-y", enabled=False)
        assert engine.is_enabled("feature-y") is False

    def test_get_value_boolean(self, engine):
        engine.create_flag("bool-flag", FlagType.BOOLEAN, enabled=True)
        assert engine.get_value("bool-flag") is True

    def test_get_value_multivariate(self, engine):
        engine.create_flag(
            "color", FlagType.MULTIVARIATE,
            value="blue", variations=["red", "blue", "green"],
        )
        assert engine.get_value("color") == "blue"

    def test_get_value_default_on_error(self, engine):
        result = engine.get_value("nonexistent", default="fallback")
        assert result == "fallback"

    def test_targeting_by_user(self, engine):
        engine.create_flag(
            "beta-feature",
            enabled=True,
            targeting=TargetingRuleSet(
                rules=[
                    TargetRule("user_id", TargetOperator.IN, ["beta-user-1", "beta-user-2"]),
                ],
                default_serve=False,
                rollout_percentage=0.0,
            ),
        )

        assert engine.is_enabled("beta-feature", {"user_id": "beta-user-1"}) is True
        assert engine.is_enabled("beta-feature", {"user_id": "regular-user"}) is False

    def test_targeting_by_tenant(self, engine):
        engine.create_flag(
            "enterprise-feature",
            enabled=True,
            targeting=TargetingRuleSet(
                rules=[
                    TargetRule("tenant", TargetOperator.EQUALS, "enterprise-corp"),
                ],
                default_serve=False,
            ),
        )

        assert engine.is_enabled("enterprise-feature", {"tenant": "enterprise-corp"}) is True
        assert engine.is_enabled("enterprise-feature", {"tenant": "startup-inc"}) is False

    def test_percentage_rollout(self, engine):
        engine.create_flag(
            "gradual-feature",
            enabled=True,
            targeting=TargetingRuleSet(
                rollout_percentage=100.0,
                rollout_salt="test-salt",
                default_serve=True,
            ),
        )
        assert engine.is_enabled("gradual-feature", {"user_id": "anyone"}) is True

    # ---- Kill Switch ----

    def test_kill_flag(self, engine):
        engine.create_flag("killable", enabled=True)
        assert engine.is_enabled("killable") is True

        engine.kill_flag("killable", reason="emergency")
        assert engine.is_enabled("killable") is False
        assert engine.get_flag("killable").state == FlagState.KILLED

    def test_restore_flag(self, engine):
        engine.create_flag("restorable")
        engine.kill_flag("restorable")
        engine.restore_flag("restorable")
        assert engine.get_flag("restorable").state == FlagState.ACTIVE

    def test_archive_flag(self, engine):
        engine.create_flag("old-feature", enabled=True)
        engine.archive_flag("old-feature")
        flag = engine.get_flag("old-feature")
        assert flag.state == FlagState.ARCHIVED
        # Archived flags return false for boolean
        assert engine.is_enabled("old-feature") is False

    # ---- Targeting Rules CRUD ----

    def test_add_targeting_rule(self, engine):
        engine.create_flag("with-rules")
        engine.add_targeting_rule(
            "with-rules", "country", TargetOperator.EQUALS, "US", weight=10
        )
        flag = engine.get_flag("with-rules")
        assert len(flag.targeting.rules) == 1
        assert flag.targeting.rules[0].attribute == "country"

    def test_clear_targeting_rules(self, engine):
        engine.create_flag("clearable")
        engine.add_targeting_rule("clearable", "x", TargetOperator.EQUALS, 1)
        engine.clear_targeting_rules("clearable")
        flag = engine.get_flag("clearable")
        assert len(flag.targeting.rules) == 0

    def test_set_rollout(self, engine):
        engine.create_flag("rollout-flag")
        engine.set_rollout("rollout-flag", 42.0, salt="my-salt")
        flag = engine.get_flag("rollout-flag")
        assert flag.targeting.rollout_percentage == 42.0
        assert flag.targeting.rollout_salt == "my-salt"

    # ---- Flag Dependencies ----

    def test_flag_dependency_satisfied(self, engine):
        engine.create_flag("base-feature", enabled=True)
        engine.create_flag("dependent-feature", enabled=True, dependencies=["base-feature"])
        assert engine.is_enabled("dependent-feature") is True

    def test_flag_dependency_not_satisfied(self, engine):
        engine.create_flag("base-feature", enabled=False)
        engine.create_flag("dependent-feature", enabled=True, dependencies=["base-feature"])
        assert engine.is_enabled("dependent-feature") is False

    # ---- Dynamic Config ----

    def test_set_get_config(self, engine):
        engine.set_config("max_tokens", 4096)
        assert engine.get_config("max_tokens") == 4096
        assert engine.get_config("unknown", "default") == "default"

    def test_delete_config(self, engine):
        engine.set_config("temp", "value")
        engine.delete_config("temp")
        assert engine.get_config("temp") is None

    def test_get_all_config(self, engine):
        engine.set_config("a", 1)
        engine.set_config("b", 2)
        config = engine.get_all_config()
        assert config == {"a": 1, "b": 2}


# ---------------------------------------------------------------------------
# Config Version Store Tests
# ---------------------------------------------------------------------------

class TestConfigVersionStore:
    """Tests for config versioning and rollback."""

    def test_snapshot_and_get(self):
        store = ConfigVersionStore()
        flags = {"flag1": FlagDefinition("flag1")}
        v = store.snapshot(flags, "initial")
        assert v == 1

        snap = store.get_version(1)
        assert snap is not None
        assert "flag1" in snap.flags

    def test_current_version_increments(self):
        store = ConfigVersionStore()
        store.snapshot({}, "v1")
        store.snapshot({}, "v2")
        assert store.current_version == 2

    def test_get_nonexistent_version(self):
        store = ConfigVersionStore()
        assert store.get_version(999) is None

    def test_rollback(self):
        store = ConfigVersionStore()

        v1 = store.snapshot({"a": FlagDefinition("a", enabled=True)}, "v1")
        v2 = store.snapshot({"a": FlagDefinition("a", enabled=False)}, "v2")

        restored = store.rollback_to(v1)
        assert restored["a"].enabled is True
        # rollback creates a new version
        assert store.current_version == 3

    def test_list_versions(self):
        store = ConfigVersionStore()
        store.snapshot({}, "first")
        store.snapshot({}, "second")
        versions = store.list_versions()
        assert len(versions) == 2
        assert versions[0].version == 1
        assert versions[1].version == 2

    def test_max_versions_bounded(self):
        store = ConfigVersionStore(max_versions=5)
        for i in range(10):
            store.snapshot({}, f"v{i}")
        assert len(store.list_versions()) == 5
        # oldest versions dropped
        assert store.list_versions()[0].version > 1


# ---------------------------------------------------------------------------
# Audit Logger Tests
# ---------------------------------------------------------------------------

class TestAuditLogger:
    """Tests for the audit logging system."""

    def test_log_and_query(self):
        logger = AuditLogger()
        logger.log(AuditAction.FLAG_CREATED, flag_name="test-flag",
                   actor="admin", reason="new feature")

        entries = logger.query(flag_name="test-flag")
        assert len(entries) == 1
        assert entries[0].action == AuditAction.FLAG_CREATED
        assert entries[0].actor == "admin"

    def test_query_with_filters(self):
        logger = AuditLogger()
        logger.log(AuditAction.FLAG_CREATED, flag_name="a", actor="alice")
        logger.log(AuditAction.FLAG_UPDATED, flag_name="b", actor="bob")
        logger.log(AuditAction.FLAG_KILLED, flag_name="a", actor="alice")

        alice_entries = logger.query(actor="alice")
        assert len(alice_entries) == 2

        killed = logger.query(action=AuditAction.FLAG_KILLED)
        assert len(killed) == 1

    def test_get_history(self):
        logger = AuditLogger()
        logger.log(AuditAction.FLAG_CREATED, flag_name="history-flag")
        logger.log(AuditAction.FLAG_UPDATED, flag_name="history-flag")
        logger.log(AuditAction.FLAG_UPDATED, flag_name="other")

        history = logger.get_history("history-flag")
        assert len(history) == 2

    def test_clear(self):
        logger = AuditLogger()
        logger.log(AuditAction.FLAG_CREATED, flag_name="x")
        logger.clear()
        assert len(logger) == 0
        assert len(logger.query()) == 0

    def test_max_entries(self):
        logger = AuditLogger(max_entries=3)
        for i in range(5):
            logger.log(AuditAction.FLAG_CREATED, flag_name=f"f{i}")
        assert len(logger.query(limit=10)) == 3


# ---------------------------------------------------------------------------
# Engine-Level Audit and Rollback
# ---------------------------------------------------------------------------

class TestEngineAuditRollback:
    """End-to-end tests for audit + versioning within the engine."""

    def test_audit_trail_on_operations(self, engine):
        engine.create_flag("audit-test", actor="tester", owner="qa")
        engine.update_flag("audit-test", enabled=True, actor="tester",
                           reason="enable for test")
        engine.kill_flag("audit-test", actor="admin", reason="emergency")

        history = engine.audit.get_history("audit-test")
        assert len(history) == 3
        actions = [e.action for e in history]
        assert AuditAction.FLAG_KILLED in actions
        assert AuditAction.FLAG_UPDATED in actions
        assert AuditAction.FLAG_CREATED in actions

    def test_engine_rollback(self, engine):
        engine.create_flag("stable", enabled=True)
        engine.update_flag("stable", enabled=False)
        engine.update_flag("stable", enabled=True)

        # rollback to version 1 (just after create)
        engine.rollback(1)
        flag = engine.get_flag("stable")
        assert flag.enabled is True

    def test_engine_rollback_invalid(self, engine):
        with pytest.raises(ConfigVersionError, match="not found"):
            engine.rollback(999)