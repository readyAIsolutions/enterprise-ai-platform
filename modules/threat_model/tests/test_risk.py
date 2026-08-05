#!/usr/bin/env python3
"""Tests for the ENI Threat Model master-class risk layer (risk.py).

Covers: severity scoring bounds, the SQLite risk register (add/get/update/
status/filter/persistence), mitigation planning per STRIDE category, the
prioritized assessment facade, the overall risk score and the risk lifecycle.
"""

import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from enterprise.modules.threat_model.risk import (  # noqa: E402
    STATUS_CLOSED,
    STATUS_MITIGATED,
    STATUS_OPEN,
    STRIDE_MITIGATIONS,
    MitigationPlanner,
    Risk,
    RiskRegister,
    SeverityBand,
    SeverityScore,
    ThreatAssessment,
    ThreatEntry,
)

# ---------------------------------------------------------------------------
# SeverityScore — formula bounds & bands
# ---------------------------------------------------------------------------


def test_score_minimum_and_maximum_bounds() -> None:
    lo = SeverityScore(impact=0, likelihood=0).score()
    hi = SeverityScore(impact=10, likelihood=10).score()
    assert lo == pytest.approx(0.0)
    assert hi == pytest.approx(10.0)
    assert 0.0 <= lo <= 10.0
    assert 0.0 <= hi <= 10.0


def test_score_always_within_zero_to_ten() -> None:
    for impact in (0, 2.5, 5, 7.5, 10, 99):
        for likelihood in (0, 3, 6, 9, 10):
            s = SeverityScore(impact=impact, likelihood=likelihood).score()
            assert 0.0 <= s <= 10.0


def test_impact_dominates_score() -> None:
    high_impact = SeverityScore(impact=9, likelihood=3).score()
    low_impact = SeverityScore(impact=2, likelihood=3).score()
    assert high_impact > low_impact


def test_likelihood_increases_score() -> None:
    low_like = SeverityScore(impact=6, likelihood=2).score()
    high_like = SeverityScore(impact=6, likelihood=9).score()
    assert high_like > low_like


def test_attack_vector_ordering() -> None:
    network = SeverityScore(likelihood=8, attack_vector="network").score()
    local = SeverityScore(likelihood=8, attack_vector="local").score()
    physical = SeverityScore(likelihood=8, attack_vector="physical").score()
    assert network > local > physical


def test_privilege_level_ordering() -> None:
    no_priv = SeverityScore(likelihood=8, privilege_level="none").score()
    high_priv = SeverityScore(likelihood=8, privilege_level="high").score()
    assert no_priv > high_priv


def test_band_boundaries() -> None:
    assert SeverityBand.from_score(9.5) is SeverityBand.CRITICAL
    assert SeverityBand.from_score(7.5) is SeverityBand.HIGH
    assert SeverityBand.from_score(4.5) is SeverityBand.MEDIUM
    assert SeverityBand.from_score(1.0) is SeverityBand.LOW
    assert SeverityScore(impact=10, likelihood=10).band() is SeverityBand.CRITICAL


def test_score_to_dict_is_serialisable() -> None:
    d = SeverityScore(impact=8, likelihood=7).to_dict()
    assert set(d) >= {"score", "band", "impact", "likelihood"}
    assert isinstance(d["score"], float)
    assert d["band"] in {b.value for b in SeverityBand}


# ---------------------------------------------------------------------------
# RiskRegister — add / get / update / status / filter
# ---------------------------------------------------------------------------


def test_register_add_and_get() -> None:
    reg = RiskRegister()
    risk = reg.add("R-1", "Prompt injection", "Spoofing", 8.5, owner="alice")
    assert isinstance(risk, Risk)
    fetched = reg.get("R-1")
    assert fetched is not None
    assert fetched.id == "R-1"
    assert fetched.title == "Prompt injection"
    assert fetched.category == "Spoofing"
    assert fetched.severity == pytest.approx(8.5)
    assert fetched.owner == "alice"
    assert fetched.status == STATUS_OPEN
    assert reg.get("missing") is None


def test_register_rejects_duplicate_id() -> None:
    reg = RiskRegister()
    reg.add("R-1", "t", "Tampering", 5.0)
    with pytest.raises(ValueError, match="already exists"):
        reg.add("R-1", "t2", "Tampering", 6.0)


def test_register_update() -> None:
    reg = RiskRegister()
    reg.add("R-1", "old", "Spoofing", 5.0, owner="a")
    updated = reg.update("R-1", title="new", severity=9.0, owner="b")
    assert updated.title == "new"
    assert updated.severity == pytest.approx(9.0)
    assert updated.owner == "b"
    # untouched fields retained
    assert updated.category == "Spoofing"
    with pytest.raises(KeyError):
        reg.update("nope", title="x")


def test_register_status_lifecycle() -> None:
    reg = RiskRegister()
    reg.add("R-1", "t", "Spoofing", 6.0)
    assert reg.get("R-1").status == STATUS_OPEN
    reg.set_status("R-1", STATUS_MITIGATED)
    assert reg.get("R-1").status == STATUS_MITIGATED
    reg.close("R-1")
    assert reg.get("R-1").status == STATUS_CLOSED
    with pytest.raises(ValueError, match="invalid status"):
        reg.set_status("R-1", "bogus")


def test_register_filter_by_status_and_severity() -> None:
    reg = RiskRegister()
    reg.add("R-1", "a", "Spoofing", 9.0, status=STATUS_OPEN)
    reg.add("R-2", "b", "Tampering", 3.0, status=STATUS_CLOSED)
    reg.add("R-3", "c", "Spoofing", 6.0, status=STATUS_MITIGATED)
    # filter by status
    assert [r.id for r in reg.filter(status=STATUS_OPEN)] == ["R-1"]
    assert [r.id for r in reg.filter(status=STATUS_MITIGATED)] == ["R-3"]
    # filter by severity range (inclusive)
    assert [r.id for r in reg.filter(severity_min=6.0)] == ["R-1", "R-3"]
    assert [r.id for r in reg.filter(severity_max=6.0)] == ["R-3", "R-2"]
    assert [r.id for r in reg.filter(severity_min=5.0, severity_max=7.0)] == ["R-3"]
    # filter by category
    assert [r.id for r in reg.filter(category="Spoofing")] == ["R-1", "R-3"]
    # combined
    assert [r.id for r in reg.filter(status=STATUS_OPEN, severity_min=8.0)] == ["R-1"]

    # ordering is severity desc
    assert [r.id for r in reg.list()] == ["R-1", "R-3", "R-2"]


def test_register_persistence_across_reopen() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "risks.db"
        reg = RiskRegister(str(db))
        reg.add("P-1", "persisted", "Repudiation", 7.0, status=STATUS_OPEN)
        reg.close_db()
        # reopen from the same file
        reg2 = RiskRegister(str(db))
        fetched = reg2.get("P-1")
        assert fetched is not None
        assert fetched.title == "persisted"
        assert fetched.severity == pytest.approx(7.0)
        assert reg2.count() == 1
        reg2.close_db()


def test_register_delete_and_count() -> None:
    reg = RiskRegister()
    reg.add("R-1", "a", "Spoofing", 5.0)
    reg.add("R-2", "b", "Tampering", 5.0)
    assert reg.count() == 2
    assert reg.delete("R-1") is True
    assert reg.count() == 1
    assert reg.get("R-1") is None
    assert reg.delete("R-1") is False


# ---------------------------------------------------------------------------
# MitigationPlanner — STRIDE suggestions & tracking
# ---------------------------------------------------------------------------


def test_mitigation_suggestion_per_stride() -> None:
    planner = MitigationPlanner()
    spoof = planner.suggest("Spoofing")
    assert spoof
    assert any("authent" in m.lower() for m in spoof)
    assert planner.suggest("Tampering")
    assert planner.suggest("Repudiation")
    assert planner.suggest("Information Disclosure")
    assert planner.suggest("Denial of Service")
    assert planner.suggest("Elevation of Privilege")
    # unknown category yields no invented controls
    assert planner.suggest("Unknown Category") == []


def test_mitigation_category_mapping_coverage() -> None:
    assert STRIDE_MITIGATIONS["spoofing"]
    assert STRIDE_MITIGATIONS["tampering"]
    assert STRIDE_MITIGATIONS["repudiation"]
    assert STRIDE_MITIGATIONS["information_disclosure"]
    assert STRIDE_MITIGATIONS["denial_of_service"]
    assert STRIDE_MITIGATIONS["elevation_of_privilege"]


def test_mitigation_plan_and_tracking() -> None:
    planner = MitigationPlanner()
    suggested = planner.plan("R-1", "Spoofing")
    assert suggested
    status = planner.status("R-1")
    assert all(v == "proposed" for v in status.values())
    assert planner.coverage("R-1") == pytest.approx(0.0)
    # apply one, coverage rises
    planner.apply("R-1", suggested[0])
    assert planner.status("R-1")[suggested[0]] == "applied"
    assert planner.coverage("R-1") > 0.0
    # verify one
    planner.verify("R-1", suggested[1])
    assert planner.status("R-1")[suggested[1]] == "verified"
    # application is idempotent for already-applied
    with pytest.raises(KeyError):
        planner.mark("R-1", "not suggested", "applied")


# ---------------------------------------------------------------------------
# ThreatAssessment facades — prioritization & overall risk
# ---------------------------------------------------------------------------


def make_assessment() -> ThreatAssessment:
    return ThreatAssessment(
        register=RiskRegister(),
        planner=MitigationPlanner(),
    )


def test_assessment_prioritized_order() -> None:
    assess = make_assessment()
    assess.assess(
        [
            ThreatEntry(
                name="Data exfil", category="Information Disclosure", impact=9, likelihood=8
            ),
            ThreatEntry(name="Prompt injection", category="Spoofing", impact=7, likelihood=6),
            ThreatEntry(
                name="Minor leak", category="Information Disclosure", impact=2, likelihood=2
            ),
        ]
    )
    ordered = assess.prioritized()
    assert [r["id"] for r in ordered] == [
        r["id"] for r in sorted(ordered, key=lambda r: r["severity"], reverse=True)
    ]
    # most severe first
    assert ordered[0]["severity"] >= ordered[1]["severity"] >= ordered[2]["severity"]
    assert ordered[0]["title"] == "Data exfil"
    assert ordered[-1]["title"] == "Minor leak"


def test_assessment_top_n() -> None:
    assess = make_assessment()
    assess.assess(
        [
            ThreatEntry(name="A", category="Spoofing", impact=8, likelihood=8),
            ThreatEntry(name="B", category="Tampering", impact=5, likelihood=5),
            ThreatEntry(name="C", category="Spoofing", impact=3, likelihood=3),
        ]
    )
    top2 = assess.top_n(2)
    assert len(top2) == 2
    assert top2[0]["severity"] >= top2[1]["severity"]
    assert assess.risk_count() == 3


def test_assessment_enriches_with_mitigations() -> None:
    assess = make_assessment()
    assess.assess([ThreatEntry(name="Spoof it", category="Spoofing", impact=8, likelihood=8)])
    risks = assess.prioritized()
    assert risks
    assert risks[0]["mitigations"]
    assert "coverage" in risks[0]
    # every risk is open by default
    assert risks[0]["status"] == STATUS_OPEN


def test_assessment_overall_risk_score() -> None:
    assess = make_assessment()
    # empty -> zero
    assert assess.overall_risk() == pytest.approx(0.0)
    assess.assess(
        [
            ThreatEntry(name="low", category="Tampering", impact=2, likelihood=2),
            ThreatEntry(name="high", category="Spoofing", impact=10, likelihood=10),
        ]
    )
    overall = assess.overall_risk()
    # equals the worst single risk ceiling
    severities = [r["severity"] for r in assess.prioritized()]
    assert overall == pytest.approx(max(severities))


def test_assessment_idempotent_reassessment() -> None:
    assess = make_assessment()
    t = ThreatEntry(name="Re", category="Spoofing", impact=6, likelihood=6)
    assess.assess([t])
    assert assess.risk_count() == 1
    # re-assessing the same threat updates rather than duplicating
    t2 = ThreatEntry(name="Re", category="Spoofing", impact=9, likelihood=9)
    assess.assess([t2])
    assert assess.risk_count() == 1
    assert assess.register.get("re_any").severity == pytest.approx(
        SeverityScore(impact=9, likelihood=9).score()
    )


def test_full_risk_lifecycle_with_planner() -> None:
    assess = make_assessment()
    assess.assess(
        [ThreatEntry(name="X", category="Elevation of Privilege", impact=8, likelihood=7)]
    )
    risk = assess.register.get("x_any")
    assert risk is not None
    risk_id = risk.id
    # apply all suggested mitigations -> full coverage
    for m in assess.planner.status(risk_id):
        assess.planner.apply(risk_id, m)
    assert assess.planner.coverage(risk_id) == pytest.approx(1.0)
    # mitigate + close lifecycle
    assess.register.set_status(risk_id, STATUS_MITIGATED)
    assert assess.register.get(risk_id).status == STATUS_MITIGATED
    assess.register.close(risk_id)
    assert assess.register.get(risk_id).status == STATUS_CLOSED
