#!/usr/bin/env python3
"""
Comprehensive unit tests for the Enterprise Compliance Module.

Covers the control catalogue (OWASP LLM Top 10, NIST AI RMF, MITRE ATLAS),
the ComplianceEvaluator (coverage / risk / PASS-FAIL), GapAnalyzer,
ComplianceReport, the ComplianceFacade, and the kernel Module lifecycle.

Usage:
    python3 -m pytest modules/compliance/tests/test_compliance.py -v --tb=short
"""

from __future__ import annotations

import asyncio
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from enterprise.modules.compliance.compliance import (  # noqa: E402
    BUILTIN_CONTROLS,
    DEFAULT_TARGET,
    FRAMEWORK_MITRE,
    FRAMEWORK_NIST,
    FRAMEWORK_OWASP,
    STATUS_IMPLEMENTED,
    STATUS_MISSING,
    STATUS_NOT_APPLICABLE,
    STATUS_PARTIAL,
    CompControl,
    ComplianceEvaluator,
    ComplianceFacade,
    ComplianceModule,
    ComplianceReport,
    Control,
    GapAnalyzer,
    controls_for_framework,
)

try:  # pragma: no cover
    from enterprise.platform_kernel import EventBus, HealthStatus
except Exception:  # pragma: no cover
    EventBus = None
    HealthStatus = None


def _owasp_all(status: str):
    """Return a status map marking every OWASP control with the given status."""
    return {c.id: status for c in controls_for_framework(FRAMEWORK_OWASP)}


# =============================================================================
# Control catalogue
# =============================================================================


class TestControlCatalogue:
    def test_builtin_controls_nonempty(self):
        assert len(BUILTIN_CONTROLS) > 0

    def test_control_ids_unique(self):
        ids = [c.id for c in BUILTIN_CONTROLS]
        assert len(ids) == len(set(ids))

    def test_owasp_catalogue_has_all_ten(self):
        owasp = [c for c in BUILTIN_CONTROLS if c.framework == FRAMEWORK_OWASP]
        assert len(owasp) == 10
        expected_ids = {f"LLM{str(i).zfill(2)}" for i in range(1, 11)}
        assert [c.id for c in owasp] == sorted(
            [c.id for c in owasp], key=lambda s: int(s[3:])
        )
        assert expected_ids == {c.id for c in owasp}
        assert expected_ids <= {c.id for c in controls_for_framework(FRAMEWORK_OWASP)}

    def test_owasp_control_titles(self):
        by_id = {c.id: c for c in controls_for_framework(FRAMEWORK_OWASP)}
        assert by_id["LLM01"].title == "Prompt Injection"
        assert by_id["LLM02"].title == "Sensitive Information Disclosure"
        assert by_id["LLM06"].title == "Excessive Agency"
        assert by_id["LLM10"].title == "Unbounded Consumption"

    def test_nist_catalogue_has_four_functions(self):
        nist = controls_for_framework(FRAMEWORK_NIST)
        categories = {c.category for c in nist}
        assert categories == {"GOVERN", "MAP", "MEASURE", "MANAGE"}
        assert all(c.framework == FRAMEWORK_NIST for c in nist)

    def test_mitre_catalogue_populated(self):
        mitre = controls_for_framework(FRAMEWORK_MITRE)
        assert len(mitre) == 4
        assert all(c.framework == FRAMEWORK_MITRE for c in mitre)
        assert all(c.id.startswith("ATLAS-") for c in mitre)

    def test_control_dataclass_fields(self):
        c = Control("X-1", "owasp", "cat", "T", "D", True)
        assert c.id == "X-1"
        assert c.required is True
        d = c.to_dict()
        assert d["id"] == "X-1"
        assert d["framework"] == "owasp"
        assert d["required"] is True

    def test_framework_filter_case_insensitive(self):
        assert len(controls_for_framework("OWASP")) == 10
        assert len(controls_for_framework("Nist")) == 4

    def test_controls_for_none_returns_all(self):
        assert set(controls_for_framework(None)) == set(BUILTIN_CONTROLS)


# =============================================================================
# CompControl
# =============================================================================


class TestCompControl:
    def test_default_is_missing(self):
        cc = CompControl()
        assert cc.category == STATUS_MISSING
        assert cc.implemented is False

    def test_valid_categories(self):
        for cat in (STATUS_IMPLEMENTED, STATUS_PARTIAL, STATUS_MISSING, STATUS_NOT_APPLICABLE):
            cc = CompControl(category=cat, evidence=["e1"], notes="n")
            assert cc.category == cat
            assert cc.evidence == ["e1"]

    def test_invalid_category_raises(self):
        with pytest.raises(ValueError):
            CompControl(category="bogus")

    def test_risk_weight(self):
        assert CompControl(STATUS_IMPLEMENTED).risk_weight == 0.0
        assert CompControl(STATUS_PARTIAL).risk_weight == 0.5
        assert CompControl(STATUS_MISSING).risk_weight == 1.0
        assert CompControl(STATUS_NOT_APPLICABLE).risk_weight == 0.0


# =============================================================================
# ComplianceEvaluator
# =============================================================================


class TestComplianceEvaluator:
    def test_all_implemented_passes(self):
        ev = ComplianceEvaluator().evaluate(_owasp_all(STATUS_IMPLEMENTED), FRAMEWORK_OWASP)
        assert ev.coverage == 100.0
        assert ev.risk_score == 0.0
        assert ev.passed is True
        assert ev.implemented == 10
        assert ev.missing == 0
        assert ev.partial == 0

    def test_missing_lowers_coverage_and_fails(self):
        sm = _owasp_all(STATUS_IMPLEMENTED)
        sm["LLM01"] = STATUS_MISSING
        sm["LLM02"] = STATUS_MISSING
        sm["LLM03"] = STATUS_MISSING
        ev = ComplianceEvaluator().evaluate(sm, FRAMEWORK_OWASP)
        assert ev.coverage == 70.0
        assert ev.risk_score == 30.0
        assert ev.missing == 3
        assert ev.implemented == 7
        assert ev.passed is False

    def test_partial_produces_risk_but_counts_toward_coverage(self):
        sm = _owasp_all(STATUS_IMPLEMENTED)
        sm["LLM01"] = STATUS_PARTIAL
        ev = ComplianceEvaluator().evaluate(sm, FRAMEWORK_OWASP)
        assert ev.coverage == 100.0  # partial still counts as covered
        assert ev.risk_score == 5.0
        assert ev.passed is False  # require_all_implemented rejects partial

    def test_mixed_metrics(self):
        sm = _owasp_all(STATUS_IMPLEMENTED)
        for cid in ("LLM01", "LLM02", "LLM03"):
            sm[cid] = STATUS_PARTIAL
        for cid in ("LLM04", "LLM05"):
            sm[cid] = STATUS_MISSING
        ev = ComplianceEvaluator().evaluate(sm, FRAMEWORK_OWASP)
        assert ev.implemented == 5
        assert ev.partial == 3
        assert ev.missing == 2
        assert ev.coverage == 80.0
        assert ev.risk_score == 35.0

    def test_omitted_controls_default_to_missing(self):
        ev = ComplianceEvaluator().evaluate({}, FRAMEWORK_OWASP)
        assert ev.coverage == 0.0
        assert ev.risk_score == 100.0
        assert ev.missing == 10
        assert ev.passed is False

    def test_not_applicable_excluded_from_denominator(self):
        sm = _owasp_all(STATUS_NOT_APPLICABLE)
        sm["LLM01"] = STATUS_IMPLEMENTED
        ev = ComplianceEvaluator().evaluate(sm, FRAMEWORK_OWASP)
        assert ev.not_applicable == 9
        assert ev.total_applicable == 1
        assert ev.coverage == 100.0
        assert ev.risk_score == 0.0
        assert ev.passed is True

    def test_invalid_status_defaults_to_missing(self):
        sm = _owasp_all(STATUS_IMPLEMENTED)
        sm["LLM01"] = "not-a-real-status"
        ev = ComplianceEvaluator().evaluate(sm, FRAMEWORK_OWASP)
        assert ev.missing == 1
        assert ev.implemented == 9
        assert ev.coverage == 90.0

    def test_compcontrol_evidence_captured(self):
        sm = _owasp_all(STATUS_IMPLEMENTED)
        sm["LLM01"] = CompControl(
            STATUS_IMPLEMENTED, evidence=["audit-1", "audit-2"], notes="verified"
        )
        ev = ComplianceEvaluator().evaluate(sm, FRAMEWORK_OWASP)
        llm01 = next(r for r in ev.results if r.control.id == "LLM01")
        assert llm01.evidence == ["audit-1", "audit-2"]
        assert llm01.notes == "verified"

    def test_per_control_status_in_results(self):
        sm = _owasp_all(STATUS_IMPLEMENTED)
        sm["LLM10"] = STATUS_MISSING
        ev = ComplianceEvaluator().evaluate(sm, FRAMEWORK_OWASP)
        statuses = {r.control.id: r.status for r in ev.results}
        assert statuses["LLM10"] == STATUS_MISSING
        assert statuses["LLM09"] == STATUS_IMPLEMENTED
        assert len(ev.results) == 10

    def test_framework_filtering(self):
        sm = _owasp_all(STATUS_IMPLEMENTED)
        ev = ComplianceEvaluator().evaluate(sm, FRAMEWORK_NIST)
        # OWASP statuses are irrelevant to NIST controls -> all default missing.
        assert len(ev.results) == 4
        assert all(r.status == STATUS_MISSING for r in ev.results)
        assert ev.coverage == 0.0

    def test_number_target_coverage_threshold(self):
        sm = _owasp_all(STATUS_IMPLEMENTED)
        sm["LLM01"] = STATUS_MISSING
        sm["LLM02"] = STATUS_MISSING
        sm["LLM03"] = STATUS_MISSING  # coverage 70
        ev = ComplianceEvaluator()
        assert ev.passes(sm, FRAMEWORK_OWASP, target=70.0) is True
        assert ev.passes(sm, FRAMEWORK_OWASP, target=80.0) is False

    def test_no_missing_target_allows_partial(self):
        sm = _owasp_all(STATUS_IMPLEMENTED)
        sm["LLM01"] = STATUS_PARTIAL
        ev = ComplianceEvaluator()
        assert ev.passes(sm, FRAMEWORK_OWASP, target="no_missing") is True
        assert ev.passes(sm, FRAMEWORK_OWASP, target="require_all_implemented") is False

    def test_compute_helpers(self):
        sm = _owasp_all(STATUS_IMPLEMENTED)
        sm["LLM01"] = STATUS_MISSING
        ev = ComplianceEvaluator()
        assert ev.compute_coverage(sm, FRAMEWORK_OWASP) == 90.0
        assert ev.compute_risk(sm, FRAMEWORK_OWASP) == 10.0

    def test_default_target_is_require_all_implemented(self):
        assert DEFAULT_TARGET == "require_all_implemented"


# =============================================================================
# GapAnalyzer
# =============================================================================


class TestGapAnalyzer:
    def setup_method(self):
        self.analyzer = GapAnalyzer()

    def test_no_gaps_when_all_implemented(self):
        assert self.analyzer.find_missing(_owasp_all(STATUS_IMPLEMENTED), FRAMEWORK_OWASP) == []

    def test_returns_only_missing(self):
        sm = _owasp_all(STATUS_IMPLEMENTED)
        sm["LLM01"] = STATUS_MISSING
        sm["LLM02"] = STATUS_MISSING
        sm["LLM03"] = STATUS_PARTIAL
        gaps = self.analyzer.find_missing(sm, FRAMEWORK_OWASP)
        assert {g.id for g in gaps} == {"LLM01", "LLM02"}
        assert all(g.framework == FRAMEWORK_OWASP for g in gaps)

    def test_omitted_controls_are_gaps(self):
        gaps = self.analyzer.find_missing({}, FRAMEWORK_OWASP)
        assert len(gaps) == 10

    def test_find_partial(self):
        sm = _owasp_all(STATUS_IMPLEMENTED)
        sm["LLM07"] = STATUS_PARTIAL
        partial = self.analyzer.find_partial(sm, FRAMEWORK_OWASP)
        assert [c.id for c in partial] == ["LLM07"]


# =============================================================================
# ComplianceReport
# =============================================================================


class TestComplianceReport:
    def test_report_fields(self):
        facade = ComplianceFacade()
        sm = _owasp_all(STATUS_IMPLEMENTED)
        sm["LLM01"] = STATUS_MISSING
        report = facade.report(sm, FRAMEWORK_OWASP)
        assert isinstance(report, ComplianceReport)
        assert report.framework == FRAMEWORK_OWASP
        assert report.coverage == 90.0
        assert 0.0 < report.risk_score < 100.0
        assert report.passed is False
        assert [g.id for g in report.gaps] == ["LLM01"]
        assert len(report.controls) == 10
        assert isinstance(report.timestamp, datetime)
        assert report.timestamp.tzinfo is not None

    def test_report_passes_when_clean(self):
        facade = ComplianceFacade()
        report = facade.report(_owasp_all(STATUS_IMPLEMENTED), FRAMEWORK_OWASP)
        assert report.passed is True
        assert report.gaps == []
        assert report.coverage == 100.0

    def test_report_to_dict(self):
        facade = ComplianceFacade()
        report = facade.report(_owasp_all(STATUS_IMPLEMENTED), FRAMEWORK_OWASP)
        d = report.to_dict()
        assert d["framework"] == FRAMEWORK_OWASP
        assert d["coverage"] == 100.0
        assert d["passed"] is True
        assert d["gaps"] == []
        assert isinstance(d["timestamp"], str)


# =============================================================================
# ComplianceFacade
# =============================================================================


class TestComplianceFacade:
    def setup_method(self):
        self.facade = ComplianceFacade()

    def test_list_controls_all(self):
        assert len(self.facade.list_controls()) == len(BUILTIN_CONTROLS)

    def test_list_controls_filtered(self):
        assert len(self.facade.list_controls(FRAMEWORK_NIST)) == 4

    def test_facade_evaluate(self):
        ev = self.facade.evaluate(_owasp_all(STATUS_IMPLEMENTED), FRAMEWORK_OWASP)
        assert ev.coverage == 100.0
        assert ev.passed is True

    def test_facade_gap_analysis(self):
        sm = _owasp_all(STATUS_IMPLEMENTED)
        sm["LLM05"] = STATUS_MISSING
        result = self.facade.gap_analysis(sm, FRAMEWORK_OWASP)
        assert [c.id for c in result["missing"]] == ["LLM05"]
        assert result["partial"] == []

    def test_facade_report(self):
        mitre_all = {c.id: STATUS_IMPLEMENTED for c in controls_for_framework(FRAMEWORK_MITRE)}
        report = self.facade.report(mitre_all, FRAMEWORK_MITRE)
        assert report.framework == FRAMEWORK_MITRE
        assert report.passed is True
        assert report.coverage == 100.0

    def test_facade_evaluator_property(self):
        assert isinstance(self.facade.evaluator, ComplianceEvaluator)


# =============================================================================
# Module lifecycle
# =============================================================================


class TestComplianceModule:
    def setup_method(self):
        self.module = ComplianceModule({})

    def test_module_name_version(self):
        assert self.module.name == "compliance"
        assert self.module.version == "1.0.0"

    def test_lifecycle(self):
        async def run():
            await self.module.initialize()
            assert self.module._status.value == "healthy"
            health = await self.module.health_check()
            assert health == HealthStatus.HEALTHY
            await self.module.shutdown()
            assert self.module._status.value == "healthy"

        asyncio.run(run())

    def test_health_unhealthy_before_initialize(self):
        async def run():
            assert await self.module.health_check() == HealthStatus.UNHEALTHY

        asyncio.run(run())

    def test_set_event_bus(self):
        if EventBus is None:
            pytest.skip("platform_kernel not importable")
        bus = EventBus()
        self.module.set_event_bus(bus)
        assert self.module._event_bus is bus

    def test_module_facade_after_initialize(self):
        async def run():
            await self.module.initialize()
            ev = self.module.evaluate(
                _owasp_all(STATUS_IMPLEMENTED), FRAMEWORK_OWASP
            )
            assert ev.passed is True
            assert self.module.facade is not None

        asyncio.run(run())

    def test_module_gap_analysis_and_report(self):
        sm = _owasp_all(STATUS_IMPLEMENTED)
        sm["LLM09"] = STATUS_MISSING
        result = self.module.gap_analysis(sm, FRAMEWORK_OWASP)
        assert [c.id for c in result["missing"]] == ["LLM09"]
        report = self.module.report(sm, FRAMEWORK_OWASP)
        assert report.passed is False
