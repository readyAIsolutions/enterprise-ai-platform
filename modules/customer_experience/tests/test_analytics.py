"""
Tests for the Customer Experience analytics layer.

Covers funnel conversion math, per-stage drop-off, NPS banding + formula,
churn-risk weighting, the JourneyAnalytics facade report, SQLite persistence
round-trips and component lifecycles. Pure stdlib analytics tests.
"""
from __future__ import annotations

import math
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from analytics import (
    FunnelAnalyst,
    StageConversion,
    NPS,
    NPSBand,
    ChurnRisk,
    ChurnRiskLevel,
    JourneyAnalytics,
)

STAGES = ["awareness", "evaluation", "purchase", "setup"]


# ---------------------------------------------------------------------------
# Funnel
# ---------------------------------------------------------------------------

def test_funnel_conversion_math():
    fa = FunnelAnalyst(STAGES)
    for _ in range(100):
        fa.feed("awareness", "visit")
    for _ in range(60):
        fa.feed("evaluation", "trial")
    for _ in range(30):
        fa.feed("purchase", "buy")
    for _ in range(10):
        fa.feed("setup", "complete")

    reach = fa.reach()
    assert reach["awareness"] == 100
    assert reach["setup"] == 10

    convs = fa.conversions()
    assert len(convs) == 3
    # awareness -> evaluation
    assert convs[0].rate == pytest.approx(60 / 100)
    # evaluation -> purchase
    assert convs[1].rate == pytest.approx(30 / 60)
    # purchase -> setup
    assert convs[2].rate == pytest.approx(10 / 30)

    assert fa.overall_conversion() == pytest.approx(10 / 100)


def test_funnel_dropoff_at_each_stage():
    fa = FunnelAnalyst(STAGES)
    for _ in range(100):
        fa.feed("awareness", "visit")
    for _ in range(60):
        fa.feed("evaluation", "trial")
    for _ in range(30):
        fa.feed("purchase", "buy")

    convs = fa.conversions()
    # awar -> eval: 40 lost, rate 0.4
    assert convs[0].dropoff == 40
    assert convs[0].dropoff_rate == pytest.approx(0.4)
    # eval -> purchase: 30 lost, rate 0.5
    assert convs[1].dropoff == 30
    assert convs[1].dropoff_rate == pytest.approx(0.5)
    # purchase -> setup: 30 lost (no setup events), rate 1.0
    assert convs[2].dropoff == 30
    assert convs[2].dropoff_rate == pytest.approx(1.0)

    drops = fa.dropoffs()
    assert drops["awareness -> evaluation"] == 40
    assert drops["evaluation -> purchase"] == 30


def test_funnel_distinct_customer_dedup():
    fa = FunnelAnalyst(["awareness", "evaluation"])
    # c1 re-enters awareness; should only count once per stage.
    fa.feed("awareness", "visit", customer_id="c1")
    fa.feed("awareness", "visit", customer_id="c1")
    fa.feed("awareness", "visit2", customer_id="c1")
    fa.feed("awareness", "visit", customer_id="c2")
    fa.feed("evaluation", "trial", customer_id="c1")
    fa.feed("evaluation", "trial", customer_id="c2")

    reach = fa.reach()
    assert reach["awareness"] == 2
    assert reach["evaluation"] == 2
    assert fa.overall_conversion() == pytest.approx(1.0)


def test_funnel_unknown_stage_rejected():
    fa = FunnelAnalyst(STAGES)
    with pytest.raises(ValueError):
        fa.feed("nonexistent", "x")


def test_funnel_empty_and_zero_guards():
    fa = FunnelAnalyst(STAGES)
    assert fa.overall_conversion() == 0.0
    assert fa.reach() == {s: 0 for s in STAGES}
    assert fa.conversions()[0].rate == 0.0
    with pytest.raises(ValueError):
        FunnelAnalyst([])


def test_funnel_report_structure():
    fa = FunnelAnalyst(STAGES)
    for _ in range(10):
        fa.feed("awareness", "visit")
    rep = fa.funnel_report()
    assert rep["name"] == "customer_funnel"
    assert rep["stages"] == STAGES
    assert rep["overall_conversion"] == 0.0
    assert len(rep["conversions"]) == 3
    assert rep["total_events"] == 10


# ---------------------------------------------------------------------------
# NPS
# ---------------------------------------------------------------------------

def test_nps_band_boundaries():
    assert NPS.band(0) is NPSBand.DETRACTOR
    assert NPS.band(6) is NPSBand.DETRACTOR
    assert NPS.band(7) is NPSBand.PASSIVE
    assert NPS.band(8) is NPSBand.PASSIVE
    assert NPS.band(9) is NPSBand.PROMOTER
    assert NPS.band(10) is NPSBand.PROMOTER


def test_nps_invalid_score_rejected():
    nps = NPS()
    with pytest.raises(ValueError):
        nps.record(-1)
    with pytest.raises(ValueError):
        nps.record(11)


def test_nps_formula():
    nps = NPS()
    # 3 promoters, 1 passive, 1 detractor -> NPS = 60 - 20 = 40
    for s in (9, 10, 10, 8, 5):
        nps.record(s)
    assert nps.sample_count() == 5
    assert nps.promoters == 3
    assert nps.passives == 1
    assert nps.detractors == 1
    assert nps.percentages()[NPSBand.PROMOTER] == pytest.approx(60.0)
    assert nps.percentages()[NPSBand.PASSIVE] == pytest.approx(20.0)
    assert nps.percentages()[NPSBand.DETRACTOR] == pytest.approx(20.0)
    assert nps.nps() == pytest.approx(40.0)


def test_nps_negative_score_and_empty():
    nps = NPS()
    # all detractors -> -100
    for _ in range(3):
        nps.record(3)
    assert nps.nps() == pytest.approx(-100.0)

    fresh = NPS()
    assert fresh.nps() == 0.0
    assert fresh.sample_count() == 0
    assert fresh.percentages()[NPSBand.PROMOTER] == 0.0


def test_nps_report_and_reset():
    nps = NPS()
    nps.record(10)
    nps.record(2)
    rep = nps.report()
    assert rep["nps"] == pytest.approx(50.0 - 50.0)
    assert rep["sample_count"] == 2
    assert rep["mean_score"] == pytest.approx(6.0)
    nps.reset()
    assert nps.sample_count() == 0
    assert nps.nps() == 0.0


# ---------------------------------------------------------------------------
# Churn risk
# ---------------------------------------------------------------------------

def test_churn_risk_saturation_top_score():
    cr = ChurnRisk()
    # all signals at cap -> normalized to 1.0 each -> score 100
    score = cr.update("c1", support_tickets=5, negative_feedback=3, inactivity_days=90)
    assert score == pytest.approx(100.0)
    assert cr.risk_level(score) is ChurnRiskLevel.HIGH


def test_churn_risk_weighting():
    # Default weights: tickets .30, feedback .30, inactivity .40
    cr = ChurnRisk()
    # only tickets at cap -> 100 * .30 = 30
    assert cr.update("t_only", support_tickets=5) == pytest.approx(30.0)
    # only inactivity at cap -> 100 * .40 = 40
    assert cr.update("i_only", inactivity_days=90) == pytest.approx(40.0)
    # only feedback at cap -> 100 * .30 = 30
    assert cr.update("f_only", negative_feedback=3) == pytest.approx(30.0)


def test_churn_risk_linear_scaling():
    cr = ChurnRisk()
    score = cr.update(
        "c1", support_tickets=2, negative_feedback=1, inactivity_days=30
    )
    # tickets_norm=.4, feedback_norm=1/3, inactivity_norm=1/3
    expected = 100 * (0.30 * 0.4 + 0.30 * (1 / 3) + 0.40 * (1 / 3))
    assert score == pytest.approx(expected, abs=0.01)


def test_churn_risk_levels():
    cr = ChurnRisk()
    assert cr.risk_level(10) is ChurnRiskLevel.LOW
    assert cr.risk_level(45) is ChurnRiskLevel.MEDIUM
    assert cr.risk_level(85) is ChurnRiskLevel.HIGH


def test_churn_risk_breakdown_and_unknown():
    cr = ChurnRisk()
    assert cr.score("missing") == 0.0
    cr.update("c1", support_tickets=5)
    bd = cr.signal_breakdown("c1")
    assert bd["signals"]["support_tickets"] == 5
    assert bd["score"] == pytest.approx(30.0)
    assert bd["risk_level"] == "medium"
    assert cr.signal_breakdown("missing") is None


# ---------------------------------------------------------------------------
# JourneyAnalytics facade
# ---------------------------------------------------------------------------

def test_journey_analytics_report_aggregate():
    ja = JourneyAnalytics(STAGES)
    # funnel
    for _ in range(10):
        ja.record_event("awareness", "visit")
    for _ in range(5):
        ja.record_event("purchase", "buy")
    # nps
    ja.record_nps(10)
    ja.record_nps(9)
    ja.record_nps(4)
    # churn
    ja.update_churn("c1", support_tickets=5, inactivity_days=90)

    rep = ja.report()
    assert rep["funnel"]["overall_conversion"] == pytest.approx(0.0)
    assert rep["nps"]["sample_count"] == 3
    assert rep["funnel"]["total_events"] == 15
    assert rep["summary"]["nps_samples"] == 3
    assert rep["summary"]["total_funnel_events"] == 15
    assert rep["summary"]["tracked_customers"] == 1
    assert "generated_at" in rep
    assert "session_started_at" in rep


def test_journey_analytics_churn_aggregate():
    ja = JourneyAnalytics(STAGES)
    # a: 0.30 (tickets) + 0.40 (inactivity) = 70 -> high
    ja.update_churn("a", support_tickets=5, inactivity_days=90)
    # b: 0.40 (inactivity only) = 40 -> medium
    ja.update_churn("b", inactivity_days=90)
    # c: 0.30 * 0.2 (1 ticket normalized) = 6 -> low
    ja.update_churn("c", support_tickets=1)
    churn = ja.report()["churn_risk"]
    assert churn["customer_count"] == 3
    assert churn["risk_bands"]["high"] == 1
    assert churn["risk_bands"]["medium"] == 1
    assert churn["risk_bands"]["low"] == 1
    assert churn["avg_score"] == pytest.approx((70 + 40 + 6) / 3, abs=0.01)


# ---------------------------------------------------------------------------
# Persistence round-trips
# ---------------------------------------------------------------------------

def test_funnel_sqlite_roundtrip(tmp_path):
    db = str(tmp_path / "funnel.db")
    fa = FunnelAnalyst(STAGES)
    for i in range(6):
        fa.feed("awareness", "visit", customer_id=f"c{i}")
        fa.feed("purchase", "buy", customer_id=f"c{i}")
    fa.save_sqlite(db)

    loaded = FunnelAnalyst.load_sqlite(db, STAGES)
    assert loaded.reach() == fa.reach()
    assert loaded.overall_conversion() == fa.overall_conversion()
    assert loaded.event_count() == fa.event_count()


def test_nps_sqlite_roundtrip(tmp_path):
    db = str(tmp_path / "nps.db")
    nps = NPS()
    for s in (9, 10, 7, 7, 3, 1):
        nps.record(s, customer_id=f"c{s}")
    nps.save_sqlite(db)

    loaded = NPS.load_sqlite(db)
    assert loaded.sample_count() == 6
    assert loaded.nps() == pytest.approx(nps.nps())
    assert loaded.detractors == nps.detractors


def test_churn_sqlite_roundtrip(tmp_path):
    db = str(tmp_path / "churn.db")
    cr = ChurnRisk()
    cr.update("a", support_tickets=4, negative_feedback=2, inactivity_days=60)
    cr.update("b", inactivity_days=90)
    cr.save_sqlite(db)

    loaded = ChurnRisk.load_sqlite(db)
    assert loaded.score("a") == pytest.approx(cr.score("a"))
    assert loaded.score("b") == pytest.approx(cr.score("b"))
    assert loaded.customers() == ["a", "b"]


def test_journey_analytics_sqlite_roundtrip(tmp_path):
    db = str(tmp_path / "ja.db")
    ja = JourneyAnalytics(STAGES)
    for _ in range(10):
        ja.record_event("awareness", "visit")
    for _ in range(4):
        ja.record_event("setup", "done")
    for s in (9, 10, 9, 5, 3):
        ja.record_nps(s)
    ja.update_churn("x", support_tickets=3, negative_feedback=2)
    ja.save_sqlite(db)

    loaded = JourneyAnalytics.load_sqlite(db, STAGES)
    assert loaded.funnel.overall_conversion() == pytest.approx(4 / 10)
    assert loaded.nps.sample_count() == 5
    assert loaded.nps.nps() == pytest.approx(ja.nps.nps())
    assert loaded.churn.score("x") == pytest.approx(ja.churn.score("x"))


def test_journey_analytics_lifecycle():
    ja = JourneyAnalytics(STAGES)
    rep = ja.report()
    assert rep["summary"]["total_funnel_events"] == 0
    assert rep["summary"]["nps_samples"] == 0

    ja.record_event("awareness", "visit")
    ja.record_nps(10)
    assert ja.funnel.event_count() == 1
    assert ja.nps.sample_count() == 1

    ja.nps.reset()
    assert ja.nps.sample_count() == 0
