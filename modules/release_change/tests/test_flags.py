"""Tests for the runtime feature-flag / canary / A-B engine.

Covers: flag enable/disable; deterministic percent rollout (hash-bucket); weighted
variant selection; canary promote/rollback with health gate; release gate blocking
unsafe changes; audit log; and full lifecycle.
"""
from __future__ import annotations

import unittest

from enterprise.modules.release_change import (
    RuleOp,
    TargetingRule,
    FeatureFlag,
    FlagEngine,
    CanaryState,
    Canary,
    GateDecision,
    ReleaseGate,
    AuditLog,
    hash_bucket,
)


class TestHashBucketDeterminism(unittest.TestCase):
    """The deterministic hash-bucket core."""

    def test_same_input_same_bucket(self):
        self.assertEqual(hash_bucket("s", "flag", "user-1"),
                         hash_bucket("s", "flag", "user-1"))

    def test_different_context_different_seed_changes_bucket(self):
        a = hash_bucket("s1", "flag", "user-1")
        b = hash_bucket("s2", "flag", "user-1")
        self.assertNotEqual(a, b)

    def test_bucket_in_range(self):
        for i in range(50):
            self.assertGreaterEqual(hash_bucket("s", "f", f"u{i}"), 0)
            self.assertLess(hash_bucket("s", "f", f"u{i}"), 10_000)


class TestFlagEnableDisable(unittest.TestCase):
    """Flag on/off semantics."""

    def setUp(self):
        self.engine = FlagEngine(seed="test")
        self.engine.register_flag("auth_v2")

    def test_enabled_by_default_evaluates_true(self):
        self.assertTrue(self.engine.is_enabled("auth_v2", {"id": "u1"}))

    def test_disable_flips_off(self):
        self.assertTrue(self.engine.enable("auth_v2"))
        self.assertTrue(self.engine.disable("auth_v2"))
        self.assertFalse(self.engine.is_enabled("auth_v2", {"id": "u1"}))

    def test_re_enable_restores(self):
        self.engine.disable("auth_v2")
        self.assertTrue(self.engine.enable("auth_v2"))
        self.assertTrue(self.engine.is_enabled("auth_v2", {"id": "u1"}))

    def test_unknown_flag_false(self):
        self.assertFalse(self.engine.is_enabled("nope", {"id": "u1"}))

    def test_enable_disable_unknown_returns_false(self):
        self.assertFalse(self.engine.enable("nope"))
        self.assertFalse(self.engine.disable("nope"))


class TestRolloutPercentDeterministic(unittest.TestCase):
    """Percent rollout splits deterministically by hash bucket."""

    def test_zero_percent_blocks_everyone(self):
        e = FlagEngine(seed="t")
        e.register_flag("f", rollout_percent=0.0)
        self.assertFalse(all(e.is_enabled("f", {"id": i}) for i in range(20)))

    def test_100_percent_enables_everyone(self):
        e = FlagEngine(seed="t")
        e.register_flag("f", rollout_percent=100.0)
        self.assertTrue(all(e.is_enabled("f", {"id": i}) for i in range(20)))

    def test_rollout_is_stable_across_calls(self):
        e = FlagEngine(seed="t")
        e.register_flag("f", rollout_percent=50.0)
        ctx = {"id": "u-42"}
        first = e.is_enabled("f", ctx)
        for _ in range(5):
            self.assertEqual(first, e.is_enabled("f", ctx))

    def test_rollout_approximates_percent_within_tolerance(self):
        e = FlagEngine(seed="stable-seed")
        e.register_flag("f", rollout_percent=50.0)
        n, hits = 2000, 0
        for i in range(n):
            if e.is_enabled("f", {"id": i}):
                hits += 1
        ratio = hits / n
        self.assertAlmostEqual(ratio, 0.5, delta=0.05)

    def test_set_rollout_changes_coverage(self):
        e = FlagEngine(seed="t")
        e.register_flag("f", rollout_percent=0.0)
        self.assertFalse(e.is_enabled("f", {"id": "u1"}))
        self.assertTrue(e.set_rollout("f", 100.0))
        self.assertTrue(e.is_enabled("f", {"id": "u1"}))


class TestVariantByWeight(unittest.TestCase):
    """Weighted A/B variant selection."""

    def setUp(self):
        self.engine = FlagEngine(seed="ab")
        self.engine.register_flag(
            "ui_theme",
            rollout_percent=100.0,
            variants={"control": 90, "experimental": 10},
            default_variant="control",
        )

    def test_variant_distribution_follows_weights(self):
        counts = {"control": 0, "experimental": 0}
        n = 2000
        for i in range(n):
            v = self.engine.get_variant("ui_theme", {"id": i})
            counts[v] = counts.get(v, 0) + 1
        self.assertAlmostEqual(counts["control"] / n, 0.9, delta=0.05)
        self.assertAlmostEqual(counts["experimental"] / n, 0.1, delta=0.05)

    def test_variant_stable_for_same_context(self):
        v1 = self.engine.get_variant("ui_theme", {"id": "u-7"})
        for _ in range(5):
            self.assertEqual(v1, self.engine.get_variant("ui_theme", {"id": "u-7"}))

    def test_boolean_flag_returns_none(self):
        e = FlagEngine(seed="t")
        e.register_flag("plain")
        self.assertIsNone(e.get_variant("plain", {"id": "u1"}))

    def test_default_variant_when_not_rolled_out(self):
        e = FlagEngine(seed="t")
        e.register_flag(
            "x", rollout_percent=0.0,
            variants={"a": 1, "b": 1}, default_variant="b",
        )
        self.assertEqual(e.get_variant("x", {"id": "u1"}), "b")


class TestTargetingRules(unittest.TestCase):
    """Targeting rules gate eligibility before rollout."""

    def test_rule_restricts_to_region(self):
        e = FlagEngine(seed="t")
        e.register_flag(
            "eu_feature",
            targeting_rules=[TargetingRule("region", RuleOp.IN, ["eu"])],
        )
        self.assertTrue(e.is_enabled("eu_feature", {"id": "u1", "region": "eu"}))
        self.assertFalse(e.is_enabled("eu_feature", {"id": "u1", "region": "us"}))

    def test_rule_equals_and_greater_than(self):
        r1 = TargetingRule("tier", RuleOp.EQUALS, "gold")
        r2 = TargetingRule("age", RuleOp.GREATER_THAN, 18)
        self.assertTrue(r1.matches({"tier": "gold"}))
        self.assertFalse(r1.matches({"tier": "silver"}))
        self.assertTrue(r2.matches({"age": 25}))
        self.assertFalse(r2.matches({"age": 10}))


class TestCanary(unittest.TestCase):
    """Canary rollout with health-gated promotion."""

    def test_send_traffic_starts_at_initial(self):
        c = Canary("svc", initial_percent=5.0, increment_step=10.0, target_percent=100.0)
        res = c.send_traffic()
        self.assertEqual(res["current_percent"], 5.0)
        self.assertEqual(c.state, CanaryState.SENDING)

    def test_promote_increments_when_healthy(self):
        c = Canary("svc", current_percent=5.0, increment_step=10.0,
                   target_percent=100.0, health_check=lambda: True)
        c.send_traffic()
        c.promote()
        self.assertEqual(c.current_percent, 15.0)
        self.assertEqual(c.state, CanaryState.PROMOTING)

    def test_promote_blocked_when_unhealthy(self):
        c = Canary("svc", current_percent=5.0, increment_step=10.0,
                   target_percent=100.0, health_check=lambda: False)
        c.send_traffic()
        res = c.promote()
        self.assertEqual(c.state, CanaryState.BLOCKED)
        self.assertFalse(res["decision"])
        self.assertEqual(c.current_percent, 5.0)  # unchanged

    def test_promote_no_health_check_allowed(self):
        c = Canary("svc", current_percent=5.0, increment_step=95.0, target_percent=100.0)
        c.send_traffic()
        c.promote()
        self.assertEqual(c.state, CanaryState.FULL)

    def test_rollback_drops_to_zero(self):
        c = Canary("svc", current_percent=50.0, increment_step=10.0, target_percent=100.0)
        c.send_traffic()
        c.rollback()
        self.assertEqual(c.current_percent, 0.0)
        self.assertEqual(c.state, CanaryState.ROLLED_BACK)

    def test_rollback_then_send_raises(self):
        c = Canary("svc", current_percent=50.0, increment_step=10.0, target_percent=100.0)
        c.send_traffic()
        c.rollback()
        with self.assertRaises(RuntimeError):
            c.send_traffic()

    def test_health_check_exception_is_unhealthy(self):
        def boom():
            raise RuntimeError("down")
        c = Canary("svc", health_check=boom)
        self.assertFalse(c.healthy)


class TestReleaseGate(unittest.TestCase):
    """Release gate must block unsafe changes."""

    def setUp(self):
        self.engine = FlagEngine(seed="gate")

    def test_passes_when_all_conditions_ok(self):
        self.engine.register_flag("new_checkout", rollout_percent=5.0)
        canary = Canary("checkout", current_percent=5.0, health_check=lambda: True)
        gate = ReleaseGate("checkout-gate", max_rollout_percent=10.0)
        res = gate.evaluate(self.engine, "new_checkout", canary)
        self.assertEqual(res["decision"], GateDecision.PASS.value)
        self.assertTrue(res["go"])

    def test_blocks_missing_flag(self):
        gate = ReleaseGate("g", max_rollout_percent=10.0)
        res = gate.evaluate(self.engine, "ghost_flag")
        self.assertEqual(res["decision"], GateDecision.BLOCKED.value)
        self.assertFalse(res["go"])

    def test_blocks_disabled_flag(self):
        self.engine.register_flag("f", enabled=False)
        gate = ReleaseGate("g", max_rollout_percent=100.0)
        res = gate.evaluate(self.engine, "f")
        self.assertFalse(res["go"])

    def test_blocks_rollout_exceeding_policy(self):
        self.engine.register_flag("f", rollout_percent=50.0)
        gate = ReleaseGate("g", max_rollout_percent=25.0)
        res = gate.evaluate(self.engine, "f")
        self.assertFalse(res["go"])
        self.assertIn("rollout_exceeds_policy",
                      [c["reason"] for c in res["checks"]])

    def test_blocks_unhealthy_canary(self):
        self.engine.register_flag("f", rollout_percent=5.0)
        canary = Canary("c", current_percent=5.0, health_check=lambda: False)
        gate = ReleaseGate("g", max_rollout_percent=10.0)
        res = gate.evaluate(self.engine, "f", canary)
        self.assertFalse(res["go"])


class TestAuditLogAndLifecycle(unittest.TestCase):
    """Audit trail covers every decision; full lifecycle works end to end."""

    def test_every_evaluation_is_audited(self):
        e = FlagEngine(seed="audit")
        e.register_flag("f")
        e.is_enabled("f", {"id": "u1"})
        e.is_enabled("missing", {"id": "u1"})
        self.assertGreaterEqual(len(e.audit), 2)
        self.assertTrue(e.audit.find(action="flag.register", name="f"))
        self.assertTrue(e.audit.find(name="f"))

    def test_audit_log_is_append_only_and_snapshotted(self):
        log = AuditLog()
        log.log("a", "x")
        snap = log.entries
        self.assertEqual(len(snap), 1)
        log.log("b", "y")
        self.assertEqual(len(log), 2)
        self.assertEqual(len(snap), 1)  # earlier snapshot unchanged

    def test_canary_transitions_audited(self):
        c = Canary("svc", current_percent=5.0, increment_step=10.0,
                   target_percent=100.0, health_check=lambda: True)
        c.send_traffic()
        c.promote()
        c.rollback()
        self.assertTrue(c.audit.find(action="canary.send_traffic", name="svc"))
        self.assertTrue(c.audit.find(action="canary.promote", name="svc"))
        self.assertTrue(c.audit.find(action="canary.rollback", name="svc"))

    def test_full_lifecycle(self):
        # register -> rollout -> variants -> gate pass -> promote to full.
        e = FlagEngine(seed="life")
        e.register_flag("billing_v2", rollout_percent=10.0,
                        variants={"control": 80, "new": 20}, default_variant="control")
        canary = Canary("billing", initial_percent=10.0, current_percent=10.0,
                        increment_step=90.0, target_percent=100.0,
                        health_check=lambda: True)
        # Early traffic goes to the canary.
        self.assertTrue(any(e.is_enabled("billing_v2", {"id": i}) for i in range(50)))
        # Gate passes at low rollout.
        gate = ReleaseGate("billing-gate", max_rollout_percent=50.0)
        res = gate.evaluate(e, "billing_v2", canary)
        self.assertTrue(res["go"])
        # Promote canary to full.
        canary.promote()
        self.assertEqual(canary.current_percent, 100.0)
        self.assertEqual(canary.state, CanaryState.FULL)
        # Raise rollout to 100 and confirm everyone served.
        e.set_rollout("billing_v2", 100.0)
        ctx = {"id": "u-1"}
        self.assertTrue(e.is_enabled("billing_v2", ctx))
        self.assertIn(e.get_variant("billing_v2", ctx), ("control", "new"))


if __name__ == "__main__":
    unittest.main()