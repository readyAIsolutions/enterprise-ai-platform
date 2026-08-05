#!/usr/bin/env python3
"""
Unit tests for the ENI Compliance LIVE EVIDENCE subsystem.

Covers ControlEvidence hashing, the SQLite EvidenceRegister (add/get/dedupe,
tamper-evident hash-chain integrity), and GapAnalysis (pass %, gaps, score,
remediation), plus the assess() / ingest() facades and within-framework
filtering.

Usage:
    python3 -m pytest modules/compliance/tests/test_evidence.py -v --tb=short
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from enterprise.modules.compliance.evidence import (  # noqa: E402
    ControlEvidence,
    EvidenceRegister,
    GapAnalysis,
    assess,
    ingest,
)
from enterprise.modules.compliance.compliance import (  # noqa: E402
    FRAMEWORK_MITRE,
    FRAMEWORK_NIST,
    FRAMEWORK_OWASP,
    STATUS_IMPLEMENTED,
    STATUS_MISSING,
    STATUS_PARTIAL,
    controls_for_framework,
)
from enterprise.modules.compliance import (  # noqa: E402
    ComplianceFacade,
    ComplianceModule,
    create_compliance_module,
)


def _owasp_ids():
    return [c.id for c in controls_for_framework(FRAMEWORK_OWASP)]


@pytest.fixture
def register():
    reg = EvidenceRegister()
    yield reg
    reg.close()


# =============================================================================
# ControlEvidence
# =============================================================================


class TestControlEvidence:
    def test_hash_is_computed_and_stable(self):
        ev = ControlEvidence("LLM01", "owasp", "implemented",
                             source="scanner-a", detail="verified at t0")
        assert ev.evidence_hash == ev.recompute_hash()
        assert len(ev.evidence_hash) == 64

    def test_hash_changes_with_content(self):
        a = ControlEvidence("LLM01", "owasp", "implemented", source="s", detail="x")
        b = ControlEvidence("LLM01", "owasp", "implemented", source="s", detail="y")
        assert a.evidence_hash != b.evidence_hash

    def test_invalid_status_raises(self):
        with pytest.raises(ValueError):
            ControlEvidence("LLM01", "owasp", "bogus")

    def test_missing_control_id_raises(self):
        with pytest.raises(ValueError):
            ControlEvidence("  ", "owasp", "implemented")

    def test_to_dict_from_dict_roundtrip(self):
        ev = ControlEvidence("LLM01", "owasp", "partial", source="s", detail="d")
        d = ev.to_dict()
        ev2 = ControlEvidence.from_dict(d)
        assert ev2.control_id == "LLM01"
        assert ev2.status == STATUS_PARTIAL


# =============================================================================
# EvidenceRegister - add / get / dedupe
# =============================================================================


class TestEvidenceAddGet:
    def test_add_and_get(self, register):
        register.add(ControlEvidence("LLM01", "owasp", "implemented", source="sc1"))
        rows = register.get("LLM01")
        assert len(rows) == 1
        assert rows[0].status == STATUS_IMPLEMENTED
        assert rows[0].source == "sc1"
        assert register.count() == 1

    def test_get_filters_by_source(self, register):
        register.add(ControlEvidence("LLM01", "owasp", "implemented", source="a"))
        register.add(ControlEvidence("LLM01", "owasp", "missing", source="b"))
        assert len(register.get("LLM01", source="a")) == 1
        assert len(register.get("LLM01")) == 2

    def test_dedupe_same_key_updates_in_place(self, register):
        register.add(ControlEvidence("LLM01", "owasp", "implemented", source="s"))
        register.add(ControlEvidence("LLM01", "owasp", "partial", source="s"))
        assert register.count() == 1
        row = register.get("LLM01", source="s")[0]
        assert row.status == STATUS_PARTIAL

    def test_update_method(self, register):
        register.add(ControlEvidence("LLM01", "owasp", "implemented", source="s"))
        register.update("LLM01", "s", status="missing", detail="regressed")
        row = register.get("LLM01", source="s")[0]
        assert row.status == STATUS_MISSING
        assert row.detail == "regressed"

    def test_delete_and_clear(self, register):
        register.add(ControlEvidence("LLM01", "owasp", "implemented", source="s"))
        register.add(ControlEvidence("LLM02", "owasp", "partial", source="s"))
        assert register.delete("LLM01") == 1
        assert register.count() == 1
        register.clear()
        assert register.count() == 0


# =============================================================================
# Tamper-evident integrity
# =============================================================================


class TestIntegrity:
    def test_integrity_valid_after_legit_adds(self, register):
        for i, cid in enumerate(_owasp_ids()):
            register.add(ControlEvidence(cid, "owasp", "implemented", source="scan"))
        check = register.verify_integrity()
        assert check["valid"] is True
        assert check["checked"] == 10

    def test_integrity_detects_content_tamper(self, register):
        register.add(ControlEvidence("LLM01", "owasp", "implemented", source="s"))
        assert register.verify_integrity()["valid"] is True
        # Out-of-band edit of the detail text (bypasses the register API).
        register._conn.execute(
            "UPDATE evidence SET detail = 'forged' WHERE control_id = 'LLM01'"
        )
        register._conn.commit()
        check = register.verify_integrity()
        assert check["valid"] is False
        assert any("content tampered" in p for p in check["problems"])

    def test_integrity_detects_row_deletion(self, register):
        for cid in ["LLM01", "LLM02", "LLM03"]:
            register.add(ControlEvidence(cid, "owasp", "implemented", source="s"))
        # Bypass API: delete a middle row without rebuilding the chain.
        register._conn.execute("DELETE FROM evidence WHERE control_id = 'LLM02'")
        register._conn.commit()
        check = register.verify_integrity()
        assert check["valid"] is False


# =============================================================================
# GapAnalysis - pass %, gaps, score, remediation
# =============================================================================


class TestGapAnalysis:
    def test_all_missing_when_empty_register(self, register):
        report = GapAnalysis(register).analyze(framework=FRAMEWORK_OWASP, top_n=None)
        n = len(_owasp_ids())
        assert report["frameworks"]["owasp"]["missing"] == n
        assert report["gap_count"] == n
        assert report["frameworks"]["owasp"]["score"] == 0.0
        assert all(g["status"] == STATUS_MISSING for g in report["gaps"])

    def test_full_pass_gives_100(self, register):
        for cid in _owasp_ids():
            register.add(ControlEvidence(cid, "owasp", "implemented", source="scan"))
        report = GapAnalysis(register).analyze(framework=FRAMEWORK_OWASP)
        assert report["frameworks"]["owasp"]["pass_pct"] == 100.0
        assert report["gap_count"] == 0
        assert report["frameworks"]["owasp"]["implemented"] == 10

    def test_partial_control_lowers_score(self, register):
        for cid in _owasp_ids():
            register.add(ControlEvidence(cid, "owasp", "implemented", source="scan"))
        register.update("LLM01", "scan", status=STATUS_PARTIAL)
        report = GapAnalysis(register).analyze(framework=FRAMEWORK_OWASP, top_n=None)
        fw = report["frameworks"]["owasp"]
        assert fw["partial"] == 1
        assert fw["implemented"] == 9
        assert fw["pass_pct"] == 90.0
        # LLM01 is a gap (only partial), severity 1.
        llm01 = [g for g in report["gaps"] if g["control_id"] == "LLM01"][0]
        assert llm01["status"] == STATUS_PARTIAL
        assert llm01["severity"] == 1

    def test_half_score(self, register):
        ids = _owasp_ids()
        for cid in ids[:5]:
            register.add(ControlEvidence(cid, "owasp", "implemented", source="scan"))
        report = GapAnalysis(register).analyze(framework=FRAMEWORK_OWASP)
        assert report["frameworks"]["owasp"]["score"] == 50.0

    def test_gap_severity_ordering(self, register):
        # LLM01 missing (sev 2), LLM02 partial (sev 1).
        register.add(ControlEvidence("LLM02", "owasp", "partial", source="scan"))
        report = GapAnalysis(register).analyze(framework=FRAMEWORK_OWASP, top_n=None)
        sevs = [g["severity"] for g in report["gaps"]]
        assert sevs == sorted(sevs, reverse=True)

    def test_remediation_top_n(self, register):
        for cid in _owasp_ids():
            register.add(ControlEvidence(cid, "owasp", "implemented", source="scan"))
        register.update("LLM01", "scan", status=STATUS_MISSING)
        register.update("LLM02", "scan", status=STATUS_PARTIAL)
        register.update("LLM03", "scan", status=STATUS_MISSING)
        report = GapAnalysis(register).analyze(framework=FRAMEWORK_OWASP, top_n=2)
        remediation_ids = [g["control_id"] for g in report["remediation"]]
        assert len(remediation_ids) == 2
        # Missing controls rank above partial.
        assert remediation_ids[0] == "LLM01" or remediation_ids[0] == "LLM03"
        # Gaps complete list still has all 3.
        assert report["gap_count"] == 3


# =============================================================================
# assess / ingest facades + framework filtering + lifecycle
# =============================================================================


class TestFacadesAndLifecycle:
    def test_ingest_bulk_flat(self, register):
        results = {c.id: {"status": "implemented", "source": "scanner"} for c in controls_for_framework(FRAMEWORK_OWASP)}
        n = ingest(results, register, source="scanner")
        assert n == 10
        assert register.count() == 10

    def test_ingest_nested_framework(self, register):
        results = {
            FRAMEWORK_OWASP: {
                "LLM01": {"status": "implemented", "source": "t"},
                "LLM02": "partial",
            }
        }
        n = ingest(results, register)
        assert n == 2
        assert register.get("LLM02")[0].status == STATUS_PARTIAL

    def test_assess_per_framework_facade(self):
        facade = ComplianceFacade()
        for c in controls_for_framework(FRAMEWORK_NIST):
            facade.add_evidence(
                ControlEvidence(c.id, FRAMEWORK_NIST, "implemented", source="audit")
            )
        report = facade.assess(FRAMEWORK_NIST)
        assert report["frameworks"]["nist"]["pass_pct"] == 100.0
        assert report["frameworks"]["nist"]["missing"] == 0
        assert report["integrity"]["valid"] is True

    def test_assess_all_frameworks(self, register):
        for c in controls_for_framework(FRAMEWORK_MITRE):
            register.add(ControlEvidence(c.id, FRAMEWORK_MITRE, "implemented", source="s"))
        report = GapAnalysis(register).analyze(top_n=None)
        assert set(report["scope"]) >= {FRAMEWORK_OWASP, FRAMEWORK_NIST, FRAMEWORK_MITRE}
        # Only MITRE has evidence -> its pass is 100, others 0.
        assert report["frameworks"][FRAMEWORK_MITRE]["pass_pct"] == 100.0
        assert report["frameworks"][FRAMEWORK_OWASP]["pass_pct"] == 0.0

    def test_within_framework_filter(self, register):
        register.add(ControlEvidence("LLM01", "owasp", "implemented", source="s"))
        register.add(ControlEvidence("LLM09", "owasp", "missing", source="s"))
        register.add(ControlEvidence("ATLAS-1", "mitre", "implemented", source="s"))
        owasp = register.list(framework=FRAMEWORK_OWASP)
        assert all(e.framework == FRAMEWORK_OWASP for e in owasp)
        assert len(owasp) == 2
        implemented = register.list(status=STATUS_IMPLEMENTED)
        assert all(e.status == STATUS_IMPLEMENTED for e in implemented)
        assert len(implemented) == 2
        assert len(register.list(status=STATUS_MISSING)) == 1

    def test_search(self, register):
        register.add(ControlEvidence("LLM01", "owasp", "implemented", source="scanner-x", detail="presidio filter active"))
        hits = register.search("presidio")
        assert [h.control_id for h in hits] == ["LLM01"]

    def test_file_lifecycle_persists(self, tmp_path):
        db = tmp_path / "compliance.db"
        r1 = EvidenceRegister(db)
        r1.add(ControlEvidence("LLM01", "owasp", "implemented", source="s"))
        r1.close()
        r2 = EvidenceRegister(db)
        assert r2.count() == 1
        assert r2.get("LLM01")[0].status == STATUS_IMPLEMENTED
        r2.close()

    def test_in_memory_is_ephemeral(self):
        r = EvidenceRegister()
        r.add(ControlEvidence("LLM01", "owasp", "implemented", source="s"))
        assert r.count() == 1
        r.close()

    def test_module_and_factory_expose_evidence(self):
        mod = create_compliance_module({"framework": None})
        assert isinstance(mod, ComplianceModule)
        mod.add_evidence(
            ControlEvidence("LLM01", "owasp", "implemented", source="scan")
        )
        assert mod.assess(FRAMEWORK_OWASP)["frameworks"]["owasp"]["implemented"] >= 1
