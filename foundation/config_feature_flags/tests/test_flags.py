"""
Tests for FeatureFlagManager.
"""

import pytest

import sys
from pathlib import Path

_project_root = Path(__file__).resolve().parents[5]
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from enterprise.foundation.config_feature_flags.flags import (
    FeatureFlagManager,
    Flag,
    FlagEvaluationContext,
    FlagEvaluationResult,
    FlagTargetingRule,
    FlagType,
    TargetOperator,
    validate_flag_dependencies,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

@pytest.fixture
def mgr():
    """Return a fresh FeatureFlagManager."""
    return FeatureFlagManager()


@pytest.fixture
def basic_flag():
    """A simple boolean flag."""
    return Flag(
        name="test-flag",
        description="A test flag",
        enabled=True,
    )


@pytest.fixture
def user_context():
    """A typical user evaluation context."""
    return FlagEvaluationContext(
        user_id="user-abc-123",
        user_attributes={"country": "US", "plan": "premium", "age": 30},
        environment="production",
    )


# ---------------------------------------------------------------------------
# Registration tests
# ---------------------------------------------------------------------------

class TestRegistration:
    """Tests for flag registration and retrieval."""

    def test_register_flag(self, mgr, basic_flag):
        mgr.register(basic_flag)
        assert mgr.get_flag("test-flag") is not None

    def test_register_updates_existing(self, mgr, basic_flag):
        mgr.register(basic_flag)
        flag2 = Flag(name="test-flag", enabled=False)
        mgr.register(flag2)
        assert mgr.get_flag("test-flag").enabled is False

    def test_unregister_flag(self, mgr, basic_flag):
        mgr.register(basic_flag)
        mgr.unregister("test-flag")
        assert mgr.get_flag("test-flag") is None

    def test_list_flags(self, mgr):
        mgr.register(Flag(name="a"))
        mgr.register(Flag(name="b"))
        assert len(mgr.list_flags()) == 2

    def test_get_active_flags(self, mgr):
        mgr.register(Flag(name="a", enabled=True))
        mgr.register(Flag(name="b", enabled=False))
        mgr.register(Flag(name="c", enabled=True, kill_switch=True))
        active = mgr.get_active_flags()
        assert len(active) == 1
        assert active[0].name == "a"


# ---------------------------------------------------------------------------
# Basic evaluation tests
# ---------------------------------------------------------------------------

class TestBasicEvaluation:
    """Tests for basic flag evaluation."""

    def test_flag_not_found(self, mgr, user_context):
        result = mgr.evaluate("nonexistent", user_context)
        assert result.value is False
        assert "not found" in result.reason

    def test_enabled_flag_returns_true(self, mgr, user_context):
        mgr.register(Flag(name="my-flag", enabled=True))
        result = mgr.evaluate("my-flag", user_context)
        assert result.value is True

    def test_disabled_flag_returns_default(self, mgr, user_context):
        mgr.register(Flag(name="my-flag", enabled=False, default_value=False))
        result = mgr.evaluate("my-flag", user_context)
        assert result.value is False
        assert "disabled" in result.reason.lower()

    def test_is_enabled_convenience(self, mgr, user_context):
        mgr.register(Flag(name="my-flag", enabled=True))
        assert mgr.is_enabled("my-flag", user_context) is True

        mgr.register(Flag(name="off-flag", enabled=False))
        assert mgr.is_enabled("off-flag", user_context) is False


# ---------------------------------------------------------------------------
# Kill switch tests
# ---------------------------------------------------------------------------

class TestKillSwitch:
    """Tests for kill switch behavior."""

    def test_kill_switch_overrides_enabled(self, mgr, user_context):
        mgr.register(Flag(name="feature", enabled=True, kill_switch=True))
        result = mgr.evaluate("feature", user_context)
        assert result.value is False  # default_value
        assert "kill-switch" in result.reason.lower()

    def test_set_kill_switch(self, mgr, user_context):
        mgr.register(Flag(name="feature", enabled=True))
        assert mgr.evaluate("feature", user_context).value is True

        mgr.set_kill_switch("feature", True)
        assert mgr.evaluate("feature", user_context).value is False

        mgr.set_kill_switch("feature", False)
        assert mgr.evaluate("feature", user_context).value is True

    def test_kill_switch_nonexistent_flag(self, mgr):
        with pytest.raises(KeyError):
            mgr.set_kill_switch("ghost", True)


# ---------------------------------------------------------------------------
# Targeting rule tests
# ---------------------------------------------------------------------------

class TestTargetingRules:
    """Tests for targeting rule evaluation."""

    def test_equals_match(self, mgr, user_context):
        mgr.register(Flag(
            name="premium-feature",
            enabled=True,
            targeting_rules=[
                FlagTargetingRule("plan", TargetOperator.EQUALS, "premium"),
            ],
        ))
        result = mgr.evaluate("premium-feature", user_context)
        assert result.value is True
        assert result.matched is True

    def test_not_equals_match(self, mgr, user_context):
        mgr.register(Flag(
            name="non-enterprise",
            enabled=True,
            targeting_rules=[
                FlagTargetingRule("plan", TargetOperator.NOT_EQUALS, "enterprise"),
            ],
        ))
        result = mgr.evaluate("non-enterprise", user_context)
        assert result.value is True

    def test_in_operator(self, mgr, user_context):
        mgr.register(Flag(
            name="geo-feature",
            enabled=True,
            targeting_rules=[
                FlagTargetingRule("country", TargetOperator.IN, ["US", "CA", "UK"]),
            ],
        ))
        result = mgr.evaluate("geo-feature", user_context)
        assert result.value is True

    def test_not_in_operator(self, mgr, user_context):
        mgr.register(Flag(
            name="non-eu-feature",
            enabled=True,
            targeting_rules=[
                FlagTargetingRule("country", TargetOperator.NOT_IN, ["DE", "FR", "ES"]),
            ],
        ))
        result = mgr.evaluate("non-eu-feature", user_context)
        assert result.value is True

    def test_contains_operator(self, mgr):
        ctx = FlagEvaluationContext(
            user_id="u1",
            user_attributes={"email": "user@example.com"},
        )
        mgr.register(Flag(
            name="example-domain",
            enabled=True,
            targeting_rules=[
                FlagTargetingRule("email", TargetOperator.CONTAINS, "@example"),
            ],
        ))
        assert mgr.evaluate("example-domain", ctx).value is True

    def test_starts_with(self, mgr, user_context):
        mgr.register(Flag(
            name="us-users",
            enabled=True,
            targeting_rules=[
                FlagTargetingRule("country", TargetOperator.STARTS_WITH, "U"),
            ],
        ))
        assert mgr.evaluate("us-users", user_context).value is True

    def test_ends_with(self, mgr, user_context):
        mgr.register(Flag(
            name="s-end",
            enabled=True,
            targeting_rules=[
                FlagTargetingRule("country", TargetOperator.ENDS_WITH, "S"),
            ],
        ))
        assert mgr.evaluate("s-end", user_context).value is True

    def test_greater_than(self, mgr, user_context):
        mgr.register(Flag(
            name="adult",
            enabled=True,
            targeting_rules=[
                FlagTargetingRule("age", TargetOperator.GREATER_THAN, 18),
            ],
        ))
        assert mgr.evaluate("adult", user_context).value is True

    def test_less_than(self, mgr, user_context):
        mgr.register(Flag(
            name="young",
            enabled=True,
            targeting_rules=[
                FlagTargetingRule("age", TargetOperator.LESS_THAN, 50),
            ],
        ))
        assert mgr.evaluate("young", user_context).value is True

    def test_regex_match(self, mgr, user_context):
        mgr.register(Flag(
            name="regex-flag",
            enabled=True,
            targeting_rules=[
                FlagTargetingRule("country", TargetOperator.REGEX, r"^U[S]$"),
            ],
        ))
        assert mgr.evaluate("regex-flag", user_context).value is True

    def test_no_match_returns_default(self, mgr, user_context):
        mgr.register(Flag(
            name="unreachable",
            enabled=True,
            default_value=False,
            targeting_rules=[
                FlagTargetingRule("plan", TargetOperator.EQUALS, "enterprise"),
            ],
        ))
        result = mgr.evaluate("unreachable", user_context)
        assert result.value is False
        assert result.matched is False

    def test_missing_attribute_no_match(self, mgr, user_context):
        mgr.register(Flag(
            name="missing-attr",
            enabled=True,
            targeting_rules=[
                FlagTargetingRule("nonexistent_attr", TargetOperator.EQUALS, "value"),
            ],
        ))
        result = mgr.evaluate("missing-attr", user_context)
        assert result.value is False

    def test_rule_weights_order(self, mgr, user_context):
        # Higher weight rule should win
        mgr.register(Flag(
            name="weighted",
            enabled=True,
            targeting_rules=[
                FlagTargetingRule("plan", TargetOperator.EQUALS, "free", weight=100),
                FlagTargetingRule("plan", TargetOperator.EQUALS, "premium", weight=1),
            ],
        ))
        result = mgr.evaluate("weighted", user_context)
        # The free rule (weight 100) is evaluated first but doesn't match
        # The premium rule (weight 1) matches
        assert result.value is True
        assert "premium" in result.reason


# ---------------------------------------------------------------------------
# Percentage rollout tests
# ---------------------------------------------------------------------------

class TestPercentageRollout:
    """Tests for percentage-based rollout."""

    def test_0_percent(self, mgr, user_context):
        """0% percentage means no rollout restriction; flag is just on."""
        mgr.register(Flag(name="f", enabled=True, percentage=0))
        result = mgr.evaluate("f", user_context)
        assert result.value is True

    def test_100_percent(self, mgr, user_context):
        mgr.register(Flag(name="f", enabled=True, percentage=100))
        result = mgr.evaluate("f", user_context)
        assert result.value is True

    def test_hashing_is_consistent(self, mgr):
        ctx = FlagEvaluationContext(user_id="user-42")
        mgr.register(Flag(name="f", enabled=True, percentage=50))
        r1 = mgr.evaluate("f", ctx)
        r2 = mgr.evaluate("f", ctx)
        assert r1.value == r2.value

    def test_rollout_distribution(self, mgr):
        """Statistical smoke test: ~50% of users get True at 50% rollout."""
        mgr.register(Flag(name="fifty", enabled=True, percentage=50))
        true_count = 0
        n = 1000
        for i in range(n):
            ctx = FlagEvaluationContext(
                user_id=f"user-{i}",
                user_attributes={},
                environment="prod",
            )
            if mgr.evaluate("fifty", ctx).value:
                true_count += 1
        # Allow generous tolerance
        ratio = true_count / n
        assert 0.40 < ratio < 0.60, f"Rollout ratio {ratio:.3f} outside [0.40, 0.60]"

    def test_percentage_invalid(self):
        with pytest.raises(ValueError):
            Flag(name="bad", percentage=101)
        with pytest.raises(ValueError):
            Flag(name="bad", percentage=-1)


# ---------------------------------------------------------------------------
# Environment targeting tests
# ---------------------------------------------------------------------------

class TestEnvironmentTargeting:
    """Tests for environment-based flag restrictions."""

    def test_env_allowed(self, mgr):
        ctx = FlagEvaluationContext(user_id="u1", environment="staging")
        mgr.register(Flag(
            name="staging-only", enabled=True, environments={"staging", "dev"}
        ))
        assert mgr.evaluate("staging-only", ctx).value is True

    def test_env_not_allowed(self, mgr):
        ctx = FlagEvaluationContext(user_id="u1", environment="production")
        mgr.register(Flag(
            name="staging-only", enabled=True, environments={"staging", "dev"}
        ))
        result = mgr.evaluate("staging-only", ctx)
        assert result.value is False
        assert "environment" in result.reason.lower()

    def test_empty_environments_means_all(self, mgr):
        ctx = FlagEvaluationContext(user_id="u1", environment="production")
        mgr.register(Flag(name="anywhere", enabled=True, environments=set()))
        assert mgr.evaluate("anywhere", ctx).value is True


# ---------------------------------------------------------------------------
# Dependency tests
# ---------------------------------------------------------------------------

class TestDependencies:
    """Tests for flag dependency resolution."""

    def test_dependency_not_met(self, mgr, user_context):
        mgr.register(Flag(name="parent", enabled=False))
        mgr.register(Flag(name="child", enabled=True, dependencies={"parent"}))
        result = mgr.evaluate("child", user_context)
        assert result.value is False
        assert "dependency" in result.reason.lower()

    def test_dependency_met(self, mgr, user_context):
        mgr.register(Flag(name="parent", enabled=True))
        mgr.register(Flag(name="child", enabled=True, dependencies={"parent"}))
        result = mgr.evaluate("child", user_context)
        assert result.value is True

    def test_dependency_nonexistent(self, mgr, user_context):
        mgr.register(Flag(
            name="orphan", enabled=True, dependencies={"ghost"}
        ))
        result = mgr.evaluate("orphan", user_context)
        assert result.value is False

    def test_validate_dependencies(self):
        flags = {
            "a": Flag(name="a"),
            "b": Flag(name="b", dependencies={"a"}),
            "c": Flag(name="c", dependencies={"a", "b"}),
        }
        errors = validate_flag_dependencies(flags)
        assert len(errors) == 0

    def test_validate_missing_dependency(self):
        flags = {
            "a": Flag(name="a", dependencies={"nonexistent"}),
        }
        errors = validate_flag_dependencies(flags)
        assert len(errors) == 1
        assert "does not exist" in errors[0]

    def test_validate_circular_dependency(self):
        flags = {
            "a": Flag(name="a", dependencies={"b"}),
            "b": Flag(name="b", dependencies={"a"}),
        }
        errors = validate_flag_dependencies(flags)
        assert any("circular" in e.lower() for e in errors)


# ---------------------------------------------------------------------------
# Multivariate flags tests
# ---------------------------------------------------------------------------

class TestMultivariateFlags:
    """Tests for multivariate flag variants."""

    def test_variant_selection(self, mgr):
        mgr.register(Flag(
            name="button-color",
            enabled=True,
            flag_type=FlagType.MULTIVARIATE,
            variants={"blue": "#0000FF", "green": "#00FF00", "red": "#FF0000"},
            default_value="#0000FF",
        ))
        ctx = FlagEvaluationContext(user_id="user-1")
        result = mgr.evaluate("button-color", ctx)
        assert result.value in ("#0000FF", "#00FF00", "#FF0000")

    def test_variant_consistency(self, mgr):
        mgr.register(Flag(
            name="color",
            enabled=True,
            flag_type=FlagType.MULTIVARIATE,
            variants={"a": 1, "b": 2, "c": 3},
        ))
        ctx = FlagEvaluationContext(user_id="consistent-user")
        r1 = mgr.evaluate("color", ctx)
        r2 = mgr.evaluate("color", ctx)
        assert r1.value == r2.value

    def test_no_variants_returns_default(self, mgr):
        mgr.register(Flag(
            name="empty-variants",
            enabled=True,
            flag_type=FlagType.MULTIVARIATE,
            variants={},
            default_value="fallback",
        ))
        ctx = FlagEvaluationContext(user_id="u1")
        result = mgr.evaluate("empty-variants", ctx)
        assert result.value == "fallback"


# ---------------------------------------------------------------------------
# Evaluate all
# ---------------------------------------------------------------------------

class TestEvaluateAll:
    """Tests for evaluate_all."""

    def test_evaluate_all(self, mgr):
        mgr.register(Flag(name="a", enabled=True))
        mgr.register(Flag(name="b", enabled=False))
        ctx = FlagEvaluationContext(user_id="u1")
        results = mgr.evaluate_all(ctx)
        assert len(results) == 2
        assert results["a"].value is True
        assert results["b"].value is False


# ---------------------------------------------------------------------------
# TargetOperator edge cases
# ---------------------------------------------------------------------------

class TestTargetOperatorCoverage:
    """Cover all TargetOperator branches."""

    def test_equals(self):
        rule = FlagTargetingRule("x", TargetOperator.EQUALS, 5)
        assert rule.evaluate({"x": 5}) is True
        assert rule.evaluate({"x": 6}) is False

    def test_not_equals(self):
        rule = FlagTargetingRule("x", TargetOperator.NOT_EQUALS, 5)
        assert rule.evaluate({"x": 6}) is True
        assert rule.evaluate({"x": 5}) is False

    def test_in(self):
        rule = FlagTargetingRule("x", TargetOperator.IN, [1, 2, 3])
        assert rule.evaluate({"x": 2}) is True
        assert rule.evaluate({"x": 4}) is False

    def test_in_scalar_value(self):
        rule = FlagTargetingRule("x", TargetOperator.IN, 1)
        assert rule.evaluate({"x": 1}) is True
        assert rule.evaluate({"x": 2}) is False

    def test_not_in(self):
        rule = FlagTargetingRule("x", TargetOperator.NOT_IN, [1, 2])
        assert rule.evaluate({"x": 3}) is True
        assert rule.evaluate({"x": 1}) is False

    def test_contains(self):
        rule = FlagTargetingRule("x", TargetOperator.CONTAINS, "hello")
        assert rule.evaluate({"x": "hello world"}) is True
        assert rule.evaluate({"x": "goodbye"}) is False

    def test_starts_with(self):
        rule = FlagTargetingRule("x", TargetOperator.STARTS_WITH, "pre")
        assert rule.evaluate({"x": "prefix"}) is True
        assert rule.evaluate({"x": "suffix"}) is False

    def test_ends_with(self):
        rule = FlagTargetingRule("x", TargetOperator.ENDS_WITH, "fix")
        assert rule.evaluate({"x": "suffix"}) is True
        assert rule.evaluate({"x": "latin"}) is False

    def test_greater_than(self):
        rule = FlagTargetingRule("x", TargetOperator.GREATER_THAN, 10)
        assert rule.evaluate({"x": 11}) is True
        assert rule.evaluate({"x": 9}) is False

    def test_less_than(self):
        rule = FlagTargetingRule("x", TargetOperator.LESS_THAN, 10)
        assert rule.evaluate({"x": 9}) is True
        assert rule.evaluate({"x": 11}) is False

    def test_regex(self):
        rule = FlagTargetingRule("x", TargetOperator.REGEX, r"^[a-z]+$")
        assert rule.evaluate({"x": "abc"}) is True
        assert rule.evaluate({"x": "ABC"}) is False

    def test_none_attribute(self):
        rule = FlagTargetingRule("x", TargetOperator.EQUALS, 1)
        assert rule.evaluate({}) is False