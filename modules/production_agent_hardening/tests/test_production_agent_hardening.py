"""Tests for production_agent_hardening — demo->production hardening linter.

Grounding: two real JE Van Clief transcripts
  * ezRtp6K6zwE "Two Engineers on Why Your Agent Demo Will Not Survive Production"
  * NWyTsKTKka8 "Systems Thinking for People Who Build With AI"
All tests are pure logic — no network, no I/O.
"""
from __future__ import annotations

import asyncio

from enterprise.modules.production_agent_hardening import (
    CRITICAL,
    PASS,
    WARNING,
    create_production_agent_hardening_module,
    harden_spec,
    run_readiness_check,
    systems_feedback_loop,
)


# ---------------------------------------------------------------------------
# Demo-grade vs production-grade fixtures
# ---------------------------------------------------------------------------

DEMO_SPEC = {
    # the transcript's exact warning: demo shortcuts that don't generalize
    "demo_trap": {"canned_responses": True, "hardcoded_outputs": True},
    "error_handling": {"enabled": False},
    "retries": {},
    "observability": {},
    "secrets": {"hardcoded": True},
    "cost_bounds": {},
    "graceful_failure": {},
    "deterministic": {},
}

PROD_SPEC = {
    "error_handling": {"enabled": True, "fallback": "return partial result + log"},
    "retries": {"max_retries": 3, "policy": "exponential backoff with jitter"},
    "observability": {"logging": True, "tracing": True, "metrics": True},
    "secrets": {"hardcoded": False, "injection": "env var"},
    "cost_bounds": {"max_tokens": 12000, "max_calls": 60},
    "graceful_failure": {"enabled": True, "mode": "degrade to read-only"},
    "deterministic": {"schema": True, "temperature": 0.0},
    "demo_trap": {"canned_responses": False, "hardcoded_outputs": False},
}


# ---------------------------------------------------------------------------
# harden_spec
# ---------------------------------------------------------------------------

def test_harden_demo_spec_is_unshippable():
    report = harden_spec(DEMO_SPEC)
    assert report.score < 50
    assert report.criticals, "demo spec should surface critical blockers"
    assert report.summary, "summary should be populated"
    # secrets + demo_trap + error_handling + graceful_failure are critical
    crit_dims = {f.dimension for f in report.criticals}
    assert {"secrets", "error_handling", "graceful_failure", "demo_trap"} <= crit_dims


def test_harden_prod_spec_passes_and_scores_high():
    report = harden_spec(PROD_SPEC)
    assert report.score >= 70
    assert not report.criticals
    assert report.passed >= 6  # most dims fully satisfied


def test_missing_dimensions_count_as_unmet():
    report = harden_spec({"secrets": {"hardcoded": False, "injection": "env"}})
    # only secrets passes -> score around 15 + partials => well under 70
    assert report.score < 70
    # explicit missing dims surface as critical/warning findings
    assert any(f.dimension == "observability" for f in report.findings)


def test_severity_levels_are_valid():
    assert CRITICAL == "critical"
    assert WARNING == "warning"
    assert PASS == "pass"


def test_harden_returns_dict_compatible_report():
    report = harden_spec(PROD_SPEC)
    d = report.to_dict()
    assert "score" in d and "findings" in d and "criticals_list" in d
    assert isinstance(d["score"], float)


# ---------------------------------------------------------------------------
# run_readiness_check
# ---------------------------------------------------------------------------

def test_readiness_gates_demo_spec():
    r = run_readiness_check(DEMO_SPEC)
    assert r["ready"] is False
    assert r["score"] < 70
    assert "secrets" in r["required_missing"]


def test_readiness_passes_prod_spec():
    r = run_readiness_check(PROD_SPEC)
    assert r["ready"] is True
    assert r["score"] >= 70
    assert not r["required_missing"]


def test_readiness_respects_custom_min_score():
    # A well-harded spec fails a stricter gate and passes a looser one.
    strict = run_readiness_check(PROD_SPEC, min_score=99.0)
    loose = run_readiness_check(PROD_SPEC, min_score=50.0)
    assert strict["ready"] is False
    assert loose["ready"] is True


def test_readiness_required_override():
    # Require an intentionally unmet dim -> not ready even though score is high enough.
    spec = dict(PROD_SPEC)
    spec["retries"] = {}
    r = run_readiness_check(spec, required=["retries"])
    assert r["ready"] is False
    assert "retries" in r["required_missing"]


# ---------------------------------------------------------------------------
# systems_feedback_loop (systems-thinking lens from NWyTsKTKka8)
# ---------------------------------------------------------------------------

def test_feedback_loop_detected():
    spec = {"components": {
        "agent": ["tool", "model"],
        "model": ["agent"],          # closed loop: agent -> model -> agent
        "tool": ["datastore"],
        "datastore": ["tool"],       # closed loop: tool <-> datastore
    }}
    s = systems_feedback_loop(spec)
    assert s["loop_count"] >= 2
    assert s["feedback_loops"], "should return detected loops"
    # every detected loop must be a real closed cycle (first == last component)
    for loop in s["feedback_loops"]:
        assert loop[0] == loop[-1]


def test_acyclic_graph_no_loops():
    spec = {"components": {
        "client": ["agent"],
        "agent": ["tool"],
        "tool": ["datastore"],
    }}
    s = systems_feedback_loop(spec)
    assert s["loop_count"] == 0
    assert not s["feedback_loops"]


def test_no_graph_returns_informative_note():
    s = systems_feedback_loop({"agent": "demo"})
    assert s["loop_count"] == 0
    assert "no component graph" in s["note"].lower()


def test_coupling_reflects_connectedness():
    dense = {"components": {"a": ["b", "c"], "b": ["a", "c"], "c": ["a", "b"]}}
    sparse = {"components": {"a": ["b"], "b": ["c"], "c": []}}
    assert systems_feedback_loop(dense)["coupling"] >= systems_feedback_loop(sparse)["coupling"]


# ---------------------------------------------------------------------------
# Platform module lifecycle
# ---------------------------------------------------------------------------

def test_module_initializes_and_health():
    m = create_production_agent_hardening_module()
    asyncio.run(m.initialize())
    assert asyncio.run(m.health_check()).value == "healthy"
    assert m.default_min_score == 70.0


def test_module_facade_readiness():
    m = create_production_agent_hardening_module()
    asyncio.run(m.initialize())
    assert m.harden(PROD_SPEC)["score"] >= 70
    assert m.readiness(DEMO_SPEC)["ready"] is False
    assert m.readiness(PROD_SPEC)["ready"] is True


def test_module_facade_systems():
    m = create_production_agent_hardening_module()
    asyncio.run(m.initialize())
    out = m.systems({"components": {"a": ["b"], "b": ["a"]}})
    assert out["loop_count"] == 1
