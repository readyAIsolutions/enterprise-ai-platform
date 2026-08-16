"""Unit tests for the production_hardening module (network-free, no fake data).

The core is pure stdlib logic — tests exercise real, deterministic behaviour
derived from the transcript's failure modes:
  * non-determinism / no confidence score
  * the invisible 80% (observability / monitoring / runtime)
  * security, guard rails & human oversight
  * brittle chains (circuit breaker / retry / deterministic fallback)
  * evaluation & right-sizing
  * scaling / local-resource limits
  * one-off demo vs sustained run
"""
from __future__ import annotations

import asyncio

from enterprise.platform_kernel import HealthStatus, _MODULE_REGISTRY

from enterprise.modules.production_hardening import (
    CATEGORIES, CheckOutcome, CircuitState, RiskLevel,
    SystemProfile, assess, assess_answers, default_rules,
    check_deterministic_output, detect_drift, circuit_breaker_state,
    retry_plan, human_escalation_required,
    create_production_hardening_module,
)


# ---------------------------------------------------------------------------
# Fixtures: grounded system profiles
# ---------------------------------------------------------------------------

def _ready_answers() -> dict:
    """Every rule answered PASS — a system that should clear the gate."""
    answers = {}
    for rule in default_rules():
        answers[rule.id] = 1.0
    return answers


def _demo_answers() -> dict:
    """A one-off demo: works once, none of the invisible 80% exists."""
    answers = {}
    for rule in default_rules():
        answers[rule.id] = 0.0
    return answers


def _middle_answers() -> dict:
    """Half-way: some hardening present (PASS), some gaps remain (WARN)."""
    answers = {}
    for i, rule in enumerate(default_rules()):
        answers[rule.id] = 1.0 if i % 2 else 0.4
    return answers


# ---------------------------------------------------------------------------
# Core: readiness scoring
# ---------------------------------------------------------------------------

def test_ready_profile_is_approved_and_production_ready():
    report = assess_answers("Hardened Agent", _ready_answers())
    assert report.gate_verdict == "APPROVED"
    assert report.production_ready is True
    assert report.overall_score >= 0.75


def test_demo_profile_is_blocked():
    report = assess_answers("One-Off Demo", _demo_answers())
    assert report.gate_verdict == "BLOCKED"
    assert report.production_ready is False
    assert report.overall_score < 0.25


def test_middle_profile_is_review():
    report = assess_answers("Half Hardened", _middle_answers())
    assert report.gate_verdict == "REVIEW"
    assert report.production_ready is False
    assert 0.25 <= report.overall_score < 0.75


def test_all_seven_categories_are_reported():
    report = assess_answers("Check Cats", _ready_answers())
    names = {c.name for c in report.categories}
    assert names == set(CATEGORIES)
    assert len(report.categories) == 7
    # A fully-ready system passes every category.
    assert all(c.outcome is CheckOutcome.PASS for c in report.categories)


def test_every_rule_has_a_transcript_reference():
    for rule in default_rules():
        assert rule.transcript_ref, f"{rule.id} missing transcript_ref"
        assert rule.category in CATEGORIES


def test_failed_rules_surface_as_top_risks():
    report = assess_answers("Demo", _demo_answers())
    assert len(report.top_risks) > 0
    assert len(report.recommendations) > 0


def test_report_dict_roundtrip_and_markdown():
    report = assess_answers("Doc", _ready_answers())
    d = report.to_dict()
    assert d["gate_verdict"] == "APPROVED"
    assert len(d["categories"]) == 7
    md = report.markdown()
    assert "Production Readiness Report" in md
    assert "APPROVED" in md


# ---------------------------------------------------------------------------
# Run-assurance: deterministic output
# ---------------------------------------------------------------------------

def test_deterministic_output_all_identical_passes():
    res = check_deterministic_output(["yes", "yes", "yes", "yes", "yes"])
    assert res.outcome is CheckOutcome.PASS
    assert res.consistent is True
    assert res.distinct_outputs == 1
    assert res.stable_ratio == 1.0


def test_deterministic_output_scattered_fails():
    res = check_deterministic_output(["a", "b", "c", "d", "e"])
    assert res.outcome is CheckOutcome.FAIL
    assert res.consistent is False


def test_deterministic_output_partial_warns():
    res = check_deterministic_output(["x", "x", "x", "y", "z"])
    assert res.outcome is CheckOutcome.WARN
    assert res.stable_ratio < 1.0


def test_deterministic_output_empty_warns():
    res = check_deterministic_output([])
    assert res.outcome is CheckOutcome.WARN


# ---------------------------------------------------------------------------
# Run-assurance: drift detection stub
# ---------------------------------------------------------------------------

def test_drift_within_threshold_passes():
    res = detect_drift(reference_mean=100.0, current_mean=101.0,
                       reference_std=5.0, threshold_std=2.0)
    assert res.outcome is CheckOutcome.PASS
    assert res.drifted is False
    assert res.z_score <= 2.0


def test_drift_large_fails():
    res = detect_drift(reference_mean=100.0, current_mean=150.0,
                       reference_std=5.0, threshold_std=2.0)
    assert res.outcome is CheckOutcome.FAIL
    assert res.drifted is True


def test_drift_approaching_warns():
    res = detect_drift(reference_mean=100.0, current_mean=112.0,
                       reference_std=5.0, threshold_std=2.0)
    assert res.outcome is CheckOutcome.WARN


# ---------------------------------------------------------------------------
# Run-assurance: circuit breaker + retry
# ---------------------------------------------------------------------------

def test_circuit_breaker_closed_within_budget():
    dec = circuit_breaker_state(failures_in_window=2, max_failures=5)
    assert dec.state is CircuitState.CLOSED
    assert dec.allows_traffic is True


def test_circuit_breaker_opens_after_budget_exceeded():
    dec = circuit_breaker_state(failures_in_window=7, max_failures=5)
    assert dec.state is CircuitState.OPEN
    assert dec.allows_traffic is False


def test_circuit_breaker_half_open_after_cooldown_probe():
    dec = circuit_breaker_state(failures_in_window=7, max_failures=5,
                                cooldown_remaining=0, allow_probe=True)
    assert dec.state is CircuitState.HALF_OPEN


def test_circuit_breaker_stays_open_during_cooldown():
    dec = circuit_breaker_state(failures_in_window=7, max_failures=5,
                                cooldown_remaining=3, allow_probe=False)
    assert dec.state is CircuitState.OPEN


def test_retry_plan_allowed_then_exhausted():
    first = retry_plan(attempt=1, max_retries=3)
    assert first.allowed is True
    last = retry_plan(attempt=4, max_retries=3)
    assert last.allowed is False
    assert last.reason == "retry budget exhausted"


def test_retry_plan_backoff_grows():
    a1 = retry_plan(attempt=1, max_retries=3).backoff_seconds
    a3 = retry_plan(attempt=3, max_retries=3).backoff_seconds
    assert a3 > a1


# ---------------------------------------------------------------------------
# Run-assurance: human escalation gate
# ---------------------------------------------------------------------------

def test_high_risk_requires_human():
    dec = human_escalation_required(RiskLevel.CRITICAL)
    assert dec.human_required is True
    dec2 = human_escalation_required(RiskLevel.HIGH)
    assert dec2.human_required is True


def test_low_risk_no_human():
    dec = human_escalation_required(RiskLevel.LOW)
    assert dec.human_required is False


# ---------------------------------------------------------------------------
# Platform module wrapper
# ---------------------------------------------------------------------------

def test_module_is_registered():
    assert "production_hardening" in _MODULE_REGISTRY
    assert _MODULE_REGISTRY["production_hardening"].__name__ == \
        "ProductionHardeningModule"


async def test_platform_module_lifecycle():
    m = create_production_hardening_module()
    assert m.name == "production_hardening"
    assert m.version == "1.0.0"
    await m.initialize()
    assert m.status is HealthStatus.HEALTHY
    health = await m.health_check()
    assert health is HealthStatus.HEALTHY
    await m.shutdown()
    assert m.status is HealthStatus.UNKNOWN


async def test_module_facade_returns_real_report():
    m = create_production_hardening_module()
    await m.initialize()
    report = m.assess_answers("Facade Agent", _ready_answers())
    assert report.production_ready is True
    assert m.categories().keys() == set(CATEGORIES)
    assert len(m.rules()) == len(default_rules())


async def test_module_escalation_facade():
    m = create_production_hardening_module()
    await m.initialize()
    dec = m.escalation(RiskLevel.CRITICAL)
    assert dec.human_required is True


async def test_set_event_bus_publishes_and_guards_when_none():
    class FakeBus:
        def __init__(self):
            self.published = []

        def publish(self, event):
            self.published.append(event)

    bus = FakeBus()
    m = create_production_hardening_module()
    await m.initialize()

    # No bus set yet -> publishing must be a no-op (guarded, no crash).
    m.assess_answers("No Bus", _ready_answers())
    assert bus.published == []

    # With a bus set -> assessment event is published.
    m.set_event_bus(bus)
    m.assess_answers("With Bus", _ready_answers())
    assert len(bus.published) == 1
    assert bus.published[0].topic == "production_hardening.assessment"
    assert bus.published[0].payload["production_ready"] is True

    # Escalation also publishes.
    m.escalation(RiskLevel.CRITICAL)
    assert bus.published[-1].topic == "production_hardening.escalation"
    assert bus.published[-1].payload["human_required"] is True
