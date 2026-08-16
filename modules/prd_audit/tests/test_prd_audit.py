"""Tests for the prd_audit module (PRD-gated workflow).

Grounded in JEVanClief's "I'm Building a Custom Front End for Claude Code"
(J2GLzkaUrBc): write a PRD markdown first, have a second auditor re-review it,
then gate execution until it clears a threshold before building.
"""
from __future__ import annotations

import pytest

from enterprise.modules.prd_audit.prd_audit import (
    AuditSeverity,
    AuditFinding,
    AuditReport,
    Auditor,
    PrdDocument,
    PrdGate,
    PrdGateBlocked,
    PrdValidator,
    Task,
    SECTIONS,
    audit_prd,
)


# ---------------------------------------------------------------------------
# Real PRD samples (markdown, as Claude would generate them)
# ---------------------------------------------------------------------------

GOOD_PRD = """# Claude Code Front End

## Goals
- Let the user monitor active agents from a web UI.
- Reuse existing open-source front-ends rather than reinventing the wheel.

## Scope
- A web dashboard that lists running Claude sessions.
- A read-only agent activity feed.

## Acceptance criteria
- The dashboard must render within 500ms on a 2020 laptop.
- The activity feed must update within 1 second of an agent event.
- At least 90% of listed sessions must resolve their status correctly.

## Risks
- Browser compatibility across the team's three supported browsers.
- Auth token handling must not leak credentials to the client.

## Tasks
- [ ] Scaffold web app (test: npm run build exits 0)
- [ ] List sessions endpoint (test: GET /sessions returns 200)
- [ ] Activity feed subscription (test: feed delivers an event in < 1s)
- [x] Auth token vault (test: token is never logged)
"""

BAD_PRD = """# Half-Baked Plan

## Scope
- Just make a front end and stuff, plus etc and more as needed.

## Goals
- It should work and be better somehow.
"""


def _good_doc() -> PrdDocument:
    return PrdDocument.from_markdown(GOOD_PRD)


def _bad_doc() -> PrdDocument:
    return PrdDocument.from_markdown(BAD_PRD)


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------


def test_parse_good_prd_all_sections():
    doc = _good_doc()
    assert doc.title == "Claude Code Front End"
    assert len(doc.goals) == 2
    assert len(doc.acceptance_criteria) == 3
    assert len(doc.risks) == 2
    assert len(doc.tasks) == 4
    assert doc.is_complete


def test_parse_task_acceptance_tests():
    doc = _good_doc()
    assert doc.tasks[0].acceptance_test == "npm run build exits 0"
    assert doc.tasks[1].acceptance_test == "GET /sessions returns 200"
    # the done task still carries its test
    assert doc.tasks[3].done is True
    assert doc.tasks[3].has_acceptance_test is True


def test_parse_bad_prd_missing_sections():
    doc = _bad_doc()
    assert "acceptance-criteria" in doc.missing_sections
    assert "risks" in doc.missing_sections
    assert "tasks" in doc.missing_sections
    assert not doc.is_complete


def test_markdown_round_trip():
    doc = _good_doc()
    reparsed = PrdDocument.from_markdown(doc.to_markdown())
    assert reparsed.title == doc.title
    assert reparsed.goals == doc.goals
    assert len(reparsed.acceptance_criteria) == len(doc.acceptance_criteria)
    assert len(reparsed.tasks) == len(doc.tasks)


def test_sections_contract():
    assert SECTIONS == ("goals", "scope", "acceptance-criteria", "risks", "tasks")


# ---------------------------------------------------------------------------
# Auditor completeness / vagueness / scope-creep / tests
# ---------------------------------------------------------------------------


def test_good_prd_passes_audit_clean():
    report = PrdValidator().validate(_good_doc())
    assert report.error_count == 0
    assert report.warning_count == 0
    assert report.score() == 1.0


def test_bad_prd_has_missing_section_errors():
    report = PrdValidator().validate(_bad_doc())
    codes = {f.code for f in report.findings}
    assert "MISSING_SECTION" in codes
    assert "NO_RISKS" in codes
    assert "SCOPE_CREEP" in codes
    assert report.error_count >= 1


def test_vague_criterion_detected():
    doc = _good_doc()
    doc.acceptance_criteria.append("it should be fast and good")
    report = PrdValidator().validate(doc)
    assert any(f.code == "VAGUE_ACCEPTANCE_CRITERION" for f in report.findings)


def test_no_acceptance_tests_detected():
    doc = _good_doc()
    doc.tasks = [Task(id="t1", description="build thing")]  # no tests
    report = PrdValidator().validate(doc)
    assert any(f.code == "NO_ACCEPTANCE_TESTS" for f in report.findings)


def test_scope_creep_detected():
    doc = _good_doc()
    doc.scope.append("and more stuff in the future phase 2")
    report = PrdValidator().validate(doc)
    assert any(f.code == "SCOPE_CREEP" for f in report.findings)


def test_deterministic_findings():
    v = PrdValidator()
    r1 = v.validate(_bad_doc())
    r2 = v.validate(_bad_doc())
    assert [f.code for f in r1.sorted_findings()] == [f.code for f in r2.sorted_findings()]
    assert r1.weighted_score() == r2.weighted_score()


def test_auditor_alias_is_validator():
    assert Auditor is PrdValidator


def test_finding_severity_ordering():
    assert AuditSeverity.INFO < AuditSeverity.WARNING < AuditSeverity.ERROR
    assert AuditSeverity.ERROR.weight > AuditSeverity.WARNING.weight


# ---------------------------------------------------------------------------
# Gate: blocks execution until audit passes
# ---------------------------------------------------------------------------


def test_gate_blocks_bad_prd():
    gate = PrdGate()
    with pytest.raises(PrdGateBlocked):
        gate.enforce_document(_bad_doc())


def test_gate_passes_good_prd():
    gate = PrdGate()
    decision = gate.enforce_document(_good_doc())
    assert decision.approved is True
    assert decision.score == 1.0


def test_gate_evaluate_non_raising():
    gate = PrdGate()
    decision = gate.evaluate(PrdValidator().validate(_bad_doc()))
    assert decision.approved is False
    assert "BLOCKED" in decision.reason


def test_gate_threshold_sensitive():
    doc = _good_doc()
    doc.scope.append("and more stuff in phase 2")  # triggers one SCOPE_CREEP warning
    strict = PrdGate(max_warnings=0)
    lenient = PrdGate(max_warnings=10)
    assert strict.evaluate(PrdValidator().validate(doc)).approved is False
    assert lenient.evaluate(PrdValidator().validate(doc)).approved is True


def test_gate_rejects_invalid_threshold():
    with pytest.raises(ValueError):
        PrdGate(max_errors=-1)
    with pytest.raises(ValueError):
        PrdGate(min_score=1.5)


# ---------------------------------------------------------------------------
# audit_prd convenience + report dict
# ---------------------------------------------------------------------------


def test_audit_prd_convenience():
    report = audit_prd(BAD_PRD)
    assert isinstance(report, AuditReport)
    assert report.error_count >= 1


def test_report_to_dict():
    report = PrdValidator().validate(_bad_doc())
    d = report.to_dict()
    assert d["errors"] == report.error_count
    assert d["warnings"] == report.warning_count
    assert "findings" in d and isinstance(d["findings"], list)
    assert all("severity" in f and "code" in f for f in d["findings"])
