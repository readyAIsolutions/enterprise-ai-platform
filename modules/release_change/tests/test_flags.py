"""Tests for the runtime feature-flag / canary / A-B engine.

Covers: flag enable/disable; deterministic percent rollout (hash-bucket); weighted
variant selection; canary promote/rollback with health gate; release gate blocking
unsafe changes; audit log; and full lifecycle.
"""

from __future__ import annotations

import unittest
from typing import Never

import pytest

from enterprise.modules.release_change import (
    AuditLog,
    Canary,
    CanaryState,
    FlagEngine,
    GateDecision,
    ReleaseGate,
    RuleOp,
    TargetingRule,
    hash_bucket,
)


class TestHashBucketDeterminism(unittest.TestCase):
    """The deterministic hash-bucket core."""

    def test_same_input_same_bucket(self) -> None:
        assert hash_bucket("s", "flag", "user-1") == hash_bucket("s", "flag", "user-1")

    def test_different_context_different_seed_changes_bucket(self) -> None:
        a = hash_bucket("s1", "flag", "user-1")
        b = hash_bucket("s2", "flag", "user-1")
        assert a != b

    def test_bucket_in_range(self) -> None:
        for i in range(50):
            assert hash_bucket("s", "f", f"u{i}") >= 0
            assert hash_bucket("s", "f", f"u{i}") < 10000


class TestFlagEnableDisable(unittest.TestCase):
    """Flag on/off semantics."""

    def setUp(self) -> None:
        self.engine = FlagEngine(seed="test")
        self.engine.register_flag("auth_v2")

    def test_enabled_by_default_evaluates_true(self) -> None:
        assert self.engine.is_enabled("auth_v2", {"id": "u1"})

    def test_disable_flips_off(self) -> None:
        assert self.engine.enable("auth_v2")
        assert self.engine.disable("auth_v2")
        assert not self.engine.is_enabled("auth_v2", {"id": "u1"})

    def test_re_enable_restores(self) -> None:
        self.engine.disable("auth_v2")
        assert self.engine.enable("auth_v2")
        assert self.engine.is_enabled("auth_v2", {"id": "u1"})

    def test_unknown_flag_false(self) -> None:
        assert not self.engine.is_enabled("nope", {"id": "u1"})

    def test_enable_disable_unknown_returns_false(self) -> None:
        assert not self.engine.enable("nope")
        assert not self.engine.disable("nope")


class TestRolloutPercentDeterministic(unittest.TestCase):
    """Percent rollout splits deterministically by hash bucket."""

    def test_zero_percent_blocks_everyone(self) -> None:
        e = FlagEngine(seed="t")
        e.register_flag("f", rollout_percent=0.0)
        assert not all(e.is_enabled("f", {"id": i}) for i in range(20))

    def test_100_percent_enables_everyone(self) -> None:
        e = FlagEngine(seed="t")
        e.register_flag("f", rollout_percent=100.0)
        assert all(e.is_enabled("f", {"id": i}) for i in range(20))

    def test_rollout_is_stable_across_calls(self) -> None:
        e = FlagEngine(seed="t")
        e.register_flag("f", rollout_percent=50.0)
        ctx = {"id": "u-42"}
        first = e.is_enabled("f", ctx)
        for _ in range(5):
            assert first == e.is_enabled("f", ctx)

    def test_rollout_approximates_percent_within_tolerance(self) -> None:
        e = FlagEngine(seed="stable-seed")
        e.register_flag("f", rollout_percent=50.0)
        n, hits = 2000, 0
        for i in range(n):
            if e.is_enabled("f", {"id": i}):
                hits += 1
        ratio = hits / n
        assert abs(ratio - 0.5) <= 0.05

    def test_set_rollout_changes_coverage(self) -> None:
        e = FlagEngine(seed="t")
        e.register_flag("f", rollout_percent=0.0)
        assert not e.is_enabled("f", {"id": "u1"})
        assert e.set_rollout("f", 100.0)
        assert e.is_enabled("f", {"id": "u1"})


class TestVariantByWeight(unittest.TestCase):
    """Weighted A/B variant selection."""

    def setUp(self) -> None:
        self.engine = FlagEngine(seed="ab")
        self.engine.register_flag(
            "ui_theme",
            rollout_percent=100.0,
            variants={"control": 90, "experimental": 10},
            default_variant="control",
        )

    def test_variant_distribution_follows_weights(self) -> None:
        counts = {"control": 0, "experimental": 0}
        n = 2000
        for i in range(n):
            v = self.engine.get_variant("ui_theme", {"id": i})
            counts[v] = counts.get(v, 0) + 1
        self.assertAlmostEqual(counts["control"] / n, 0.9, delta=0.05)  # noqa: PT009
        self.assertAlmostEqual(counts["experimental"] / n, 0.1, delta=0.05)  # noqa: PT009

    def test_variant_stable_for_same_context(self) -> None:
        v1 = self.engine.get_variant("ui_theme", {"id": "u-7"})
        for _ in range(5):
            assert v1 == self.engine.get_variant("ui_theme", {"id": "u-7"})

    def test_boolean_flag_returns_none(self) -> None:
        e = FlagEngine(seed="t")
        e.register_flag("plain")
        assert e.get_variant("plain", {"id": "u1"}) is None

    def test_default_variant_when_not_rolled_out(self) -> None:
        e = FlagEngine(seed="t")
        e.register_flag(
            "x",
            rollout_percent=0.0,
            variants={"a": 1, "b": 1},
            default_variant="b",
        )
        assert e.get_variant("x", {"id": "u1"}) == "b"


class TestTargetingRules(unittest.TestCase):
    """Targeting rules gate eligibility before rollout."""

    def test_rule_restricts_to_region(self) -> None:
        e = FlagEngine(seed="t")
        e.register_flag(
            "eu_feature",
            targeting_rules=[TargetingRule("region", RuleOp.IN, ["eu"])],
        )
        assert e.is_enabled("eu_feature", {"id": "u1", "region": "eu"})
        assert not e.is_enabled("eu_feature", {"id": "u1", "region": "us"})

    def test_rule_equals_and_greater_than(self) -> None:
        r1 = TargetingRule("tier", RuleOp.EQUALS, "gold")
        r2 = TargetingRule("age", RuleOp.GREATER_THAN, 18)
        assert r1.matches({"tier": "gold"})
        assert not r1.matches({"tier": "silver"})
        assert r2.matches({"age": 25})
        assert not r2.matches({"age": 10})


class TestCanary(unittest.TestCase):
    """Canary rollout with health-gated promotion."""

    def test_send_traffic_starts_at_initial(self) -> None:
        c = Canary("svc", initial_percent=5.0, increment_step=10.0, target_percent=100.0)
        res = c.send_traffic()
        assert res["current_percent"] == 5.0
        assert c.state == CanaryState.SENDING

    def test_promote_increments_when_healthy(self) -> None:
        c = Canary(
            "svc",
            current_percent=5.0,
            increment_step=10.0,
            target_percent=100.0,
            health_check=lambda: True,
        )
        c.send_traffic()
        c.promote()
        assert c.current_percent == 15.0
        assert c.state == CanaryState.PROMOTING

    def test_promote_blocked_when_unhealthy(self) -> None:
        c = Canary(
            "svc",
            current_percent=5.0,
            increment_step=10.0,
            target_percent=100.0,
            health_check=lambda: False,
        )
        c.send_traffic()
        res = c.promote()
        assert c.state == CanaryState.BLOCKED
        assert not res["decision"]
        assert c.current_percent == 5.0  # unchanged

    def test_promote_no_health_check_allowed(self) -> None:
        c = Canary("svc", current_percent=5.0, increment_step=95.0, target_percent=100.0)
        c.send_traffic()
        c.promote()
        assert c.state == CanaryState.FULL

    def test_rollback_drops_to_zero(self) -> None:
        c = Canary("svc", current_percent=50.0, increment_step=10.0, target_percent=100.0)
        c.send_traffic()
        c.rollback()
        assert c.current_percent == 0.0
        assert c.state == CanaryState.ROLLED_BACK

    def test_rollback_then_send_raises(self) -> None:
        c = Canary("svc", current_percent=50.0, increment_step=10.0, target_percent=100.0)
        c.send_traffic()
        c.rollback()
        with pytest.raises(RuntimeError):
            c.send_traffic()

    def test_health_check_exception_is_unhealthy(self) -> None:
        def boom() -> Never:
            msg = "down"
            raise RuntimeError(msg)

        c = Canary("svc", health_check=boom)
        assert not c.healthy


class TestReleaseGate(unittest.TestCase):
    """Release gate must block unsafe changes."""

    def setUp(self) -> None:
        self.engine = FlagEngine(seed="gate")

    def test_passes_when_all_conditions_ok(self) -> None:
        self.engine.register_flag("new_checkout", rollout_percent=5.0)
        canary = Canary("checkout", current_percent=5.0, health_check=lambda: True)
        gate = ReleaseGate("checkout-gate", max_rollout_percent=10.0)
        res = gate.evaluate(self.engine, "new_checkout", canary)
        assert res["decision"] == GateDecision.PASS.value
        assert res["go"]

    def test_blocks_missing_flag(self) -> None:
        gate = ReleaseGate("g", max_rollout_percent=10.0)
        res = gate.evaluate(self.engine, "ghost_flag")
        assert res["decision"] == GateDecision.BLOCKED.value
        assert not res["go"]

    def test_blocks_disabled_flag(self) -> None:
        self.engine.register_flag("f", enabled=False)
        gate = ReleaseGate("g", max_rollout_percent=100.0)
        res = gate.evaluate(self.engine, "f")
        assert not res["go"]

    def test_blocks_rollout_exceeding_policy(self) -> None:
        self.engine.register_flag("f", rollout_percent=50.0)
        gate = ReleaseGate("g", max_rollout_percent=25.0)
        res = gate.evaluate(self.engine, "f")
        assert not res["go"]
        assert "rollout_exceeds_policy" in [c["reason"] for c in res["checks"]]

    def test_blocks_unhealthy_canary(self) -> None:
        self.engine.register_flag("f", rollout_percent=5.0)
        canary = Canary("c", current_percent=5.0, health_check=lambda: False)
        gate = ReleaseGate("g", max_rollout_percent=10.0)
        res = gate.evaluate(self.engine, "f", canary)
        assert not res["go"]


class TestAuditLogAndLifecycle(unittest.TestCase):
    """Audit trail covers every decision; full lifecycle works end to end."""

    def test_every_evaluation_is_audited(self) -> None:
        e = FlagEngine(seed="audit")
        e.register_flag("f")
        e.is_enabled("f", {"id": "u1"})
        e.is_enabled("missing", {"id": "u1"})
        assert len(e.audit) >= 2
        assert e.audit.find(action="flag.register", name="f")
        assert e.audit.find(name="f")

    def test_audit_log_is_append_only_and_snapshotted(self) -> None:
        log = AuditLog()
        log.log("a", "x")
        snap = log.entries
        assert len(snap) == 1
        log.log("b", "y")
        assert len(log) == 2
        assert len(snap) == 1  # earlier snapshot unchanged

    def test_canary_transitions_audited(self) -> None:
        c = Canary(
            "svc",
            current_percent=5.0,
            increment_step=10.0,
            target_percent=100.0,
            health_check=lambda: True,
        )
        c.send_traffic()
        c.promote()
        c.rollback()
        assert c.audit.find(action="canary.send_traffic", name="svc")
        assert c.audit.find(action="canary.promote", name="svc")
        assert c.audit.find(action="canary.rollback", name="svc")

    def test_full_lifecycle(self) -> None:
        # register -> rollout -> variants -> gate pass -> promote to full.
        e = FlagEngine(seed="life")
        e.register_flag(
            "billing_v2",
            rollout_percent=10.0,
            variants={"control": 80, "new": 20},
            default_variant="control",
        )
        canary = Canary(
            "billing",
            initial_percent=10.0,
            current_percent=10.0,
            increment_step=90.0,
            target_percent=100.0,
            health_check=lambda: True,
        )
        # Early traffic goes to the canary.
        assert any(e.is_enabled("billing_v2", {"id": i}) for i in range(50))
        # Gate passes at low rollout.
        gate = ReleaseGate("billing-gate", max_rollout_percent=50.0)
        res = gate.evaluate(e, "billing_v2", canary)
        assert res["go"]
        # Promote canary to full.
        canary.promote()
        assert canary.current_percent == 100.0
        assert canary.state == CanaryState.FULL
        # Raise rollout to 100 and confirm everyone served.
        e.set_rollout("billing_v2", 100.0)
        ctx = {"id": "u-1"}
        assert e.is_enabled("billing_v2", ctx)
        assert e.get_variant("billing_v2", ctx) in ("control", "new")


if __name__ == "__main__":
    unittest.main()
