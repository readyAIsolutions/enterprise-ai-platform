"""
Tests for the developer_experience validation layer.

Covers the golden-path checklist, the project validator, DORA delivery
metrics, and the combined DXScore facade. All checks are real filesystem
validations (no stubs).
"""

import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, "/home/hunter/Desktop/Enterprise Builder")

from enterprise.modules.developer_experience.validation import (
    GoldenCheck,
    GoldenPath,
    GoldenPathValidator,
    ValidationReport,
    CheckResult,
    DeliveryBand,
    DeliveryMetrics,
    DXScore,
    letter_grade,
)


def make_project(tmp_path: Path, files: dict) -> Path:
    """Create a project directory populated with the given files."""
    project = tmp_path / "proj"
    project.mkdir(parents=True, exist_ok=True)
    for name, content in files.items():
        p = project / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    return project


COMPLETE = {
    "README.md": "# Proj\n",
    "tests/test_x.py": "def test_x():\n    assert True\n",
    ".github/workflows/ci.yml": "name: CI\non: [push]\n",
    ".flake8": "[flake8]\nmax-line-length = 100\n",
    "py.typed": "",
    ".gitignore": "__pycache__/\n",
    "LICENSE": "MIT\n",
    "pyproject.toml": "[project]\nversion = \"1.2.3\"\n",
}


# ---------------------------------------------------------------------------
# GoldenPath checklist structure
# ---------------------------------------------------------------------------

def test_golden_path_enterprise_dx_has_expected_checks():
    path = GoldenPath.enterprise_dx()
    ids = path.ids()
    assert "has_readme" in ids
    assert "has_tests" in ids
    assert "has_ci" in ids
    assert "has_lint_config" in ids
    assert "has_type_hints" in ids
    assert "has_gitignore" in ids
    assert "has_license" in ids
    assert "is_versioned" in ids
    assert len(ids) >= 8


def test_golden_path_check_has_id_description_grade():
    path = GoldenPath.enterprise_dx()
    for check in path.checks:
        assert check.id
        assert check.description
        assert check.grade in ("essential", "recommended", "excellent")
        assert check.weight > 0


def test_golden_path_get_and_by_grade():
    path = GoldenPath.enterprise_dx()
    assert path.get("has_readme") is not None
    assert path.get("does_not_exist") is None
    essential = path.by_grade("essential")
    assert all(c.grade == "essential" for c in essential)
    assert any(c.id == "has_readme" for c in essential)


def test_golden_check_accepts_string_present_files():
    check = GoldenCheck(
        id="x", description="d", grade="essential",
        present_files="README.md",
    )
    assert check.present_files == ("README.md",)


# ---------------------------------------------------------------------------
# GoldenPathValidator
# ---------------------------------------------------------------------------

def test_validator_complete_project_100_percent(tmp_path):
    project = make_project(tmp_path, COMPLETE)
    report = GoldenPathValidator().validate(project)
    assert isinstance(report, ValidationReport)
    assert report.compliance_percent() == 100.0
    assert report.letter_grade() == "A"
    assert report.failures() == []
    assert len(report.passed()) == len(report.results)


def test_validator_empty_project_zero_compliance(tmp_path):
    project = make_project(tmp_path, {})
    report = GoldenPathValidator().validate(project)
    assert report.compliance_percent() == 0.0
    assert report.letter_grade() == "F"
    assert report.failures() == report.results
    assert len(report.passed()) == 0


def test_validator_partial_project_letter_grade(tmp_path):
    project = make_project(tmp_path, {"README.md": "# Proj\n", ".gitignore": "x\n"})
    report = GoldenPathValidator().validate(project)
    pct = report.compliance_percent()
    assert 0.0 < pct < 100.0
    assert report.letter_grade() in ("A", "B", "C", "D", "F")
    assert len(report.passed()) == 2


def test_validator_missing_directory_fails(tmp_path):
    missing = tmp_path / "nope"
    report = GoldenPathValidator().validate(missing)
    assert report.failures()
    assert report.compliance_percent() == 0.0


def test_validator_returns_per_check_results(tmp_path):
    project = make_project(tmp_path, COMPLETE)
    report = GoldenPathValidator().validate(project)
    for result in report.results:
        assert isinstance(result, CheckResult)
        assert result.check_id
        assert result.passed is True
        assert result.evidence


def test_validator_failure_recommendations(tmp_path):
    project = make_project(tmp_path, {})
    report = GoldenPathValidator().validate(project)
    recs = report.recommendations()
    assert recs
    # Each failed check that has remediation yields an actionable suggestion.
    for rec in recs:
        assert isinstance(rec, str) and len(rec) > 10


def test_validator_custom_path(tmp_path):
    project = make_project(tmp_path, {"README.md": "x\n"})
    path = GoldenPath(name="custom", checks=[
        GoldenCheck(id="readme", description="has readme", grade="essential",
                    present_files="README.md"),
    ])
    report = GoldenPathValidator(path).validate(project)
    assert report.path_name == "custom"
    assert report.compliance_percent() == 100.0


def test_validator_versioned_check(tmp_path):
    # versioned via pyproject.toml
    project = make_project(tmp_path / "v1", {"pyproject.toml": '[project]\nversion = "1.0.0"\n'})
    check = GoldenPath.enterprise_dx().get("is_versioned")
    from enterprise.modules.developer_experience.validation import _check_versioned
    assert check is not None
    assert _check_versioned(project) is True
    # not versioned
    plain = make_project(tmp_path / "v2", {"README.md": "x\n"})
    assert _check_versioned(plain) is False


# ---------------------------------------------------------------------------
# DeliveryMetrics (DORA)
# ---------------------------------------------------------------------------

def test_delivery_metrics_elite_band():
    metrics = DeliveryMetrics(team="core")
    now = datetime.utcnow()
    for i in range(20):
        metrics.record_success(
            lead_time_hours=0.5,
            timestamp=now - timedelta(hours=i * 2),
        )
    assert metrics.deployment_frequency_per_day() >= 1.0
    assert metrics.lead_time_stats()["mean_hours"] < 1.0
    assert metrics.change_failure_rate_percent() == 0.0
    assert metrics.bands()["deployment_frequency"] == "elite"
    assert metrics.bands()["lead_time"] == "elite"
    assert metrics.bands()["change_failure_rate"] == "elite"
    assert metrics.overall_band() == "elite"


def test_delivery_metrics_low_band():
    metrics = DeliveryMetrics(team="legacy")
    now = datetime.utcnow()
    # 2 deploys spread across 80 days -> less than once a month -> low
    metrics.record_success(lead_time_hours=400, timestamp=now - timedelta(days=80))
    metrics.record_failure(lead_time_hours=300, recovery_minutes=10000,
                           timestamp=now - timedelta(days=1))
    # 50% CFR, slow lead time, huge MTTR
    assert metrics.change_failure_rate_percent() == 50.0
    assert metrics.bands()["deployment_frequency"] == "low"
    assert metrics.bands()["lead_time"] == "low"
    assert metrics.bands()["change_failure_rate"] == "low"
    assert metrics.bands()["mttr"] == "low"
    assert metrics.overall_band() == "low"


def test_delivery_metrics_deploy_freq_band():
    assert DeliveryMetrics.band_deployment_frequency(5.0) == "elite"
    assert DeliveryMetrics.band_deployment_frequency(0.5) == "high"
    assert DeliveryMetrics.band_deployment_frequency(0.1) == "medium"
    assert DeliveryMetrics.band_deployment_frequency(0.001) == "low"


def test_delivery_metrics_lead_time_band():
    assert DeliveryMetrics.band_lead_time(0.1) == "elite"
    assert DeliveryMetrics.band_lead_time(12.0) == "high"
    assert DeliveryMetrics.band_lead_time(72.0) == "medium"
    assert DeliveryMetrics.band_lead_time(400.0) == "low"


def test_delivery_metrics_cfr_and_mttr_band():
    assert DeliveryMetrics.band_change_failure_rate(2.0) == "elite"
    assert DeliveryMetrics.band_change_failure_rate(7.0) == "high"
    assert DeliveryMetrics.band_change_failure_rate(12.0) == "medium"
    assert DeliveryMetrics.band_change_failure_rate(25.0) == "low"
    assert DeliveryMetrics.band_mttr(30.0) == "elite"
    assert DeliveryMetrics.band_mttr(200.0) == "high"
    assert DeliveryMetrics.band_mttr(2000.0) == "medium"
    assert DeliveryMetrics.band_mttr(5000.0) == "low"


def test_delivery_metrics_lead_time_percentiles():
    metrics = DeliveryMetrics()
    now = datetime.utcnow()
    times = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
    for t in times:
        metrics.record_success(lead_time_hours=t, timestamp=now)
    stats = metrics.lead_time_stats()
    assert stats["mean_hours"] == 5.5
    assert stats["p50_hours"] == 5.5
    assert stats["p95_hours"] >= 9.0


def test_delivery_metrics_empty():
    metrics = DeliveryMetrics()
    assert metrics.deployment_frequency_per_day() == 0.0
    assert metrics.change_failure_rate_percent() == 0.0
    assert metrics.mean_time_to_recovery_minutes() == 0.0
    assert metrics.overall_band() == "low"
    assert metrics.bands()["lead_time"] == "low"


def test_delivery_metrics_to_dict():
    metrics = DeliveryMetrics(team="t")
    metrics.record_success(lead_time_hours=0.5)
    data = metrics.to_dict()
    assert data["team"] == "t"
    assert "bands" in data
    assert "overall_band" in data
    assert data["change_failure_rate_percent"] == 0.0


# ---------------------------------------------------------------------------
# DXScore facade
# ---------------------------------------------------------------------------

def test_dxscore_combines_compliance_and_delivery(tmp_path):
    project = make_project(tmp_path, COMPLETE)
    metrics = DeliveryMetrics(team="core")
    now = datetime.utcnow()
    for i in range(10):
        metrics.record_success(lead_time_hours=0.4, timestamp=now - timedelta(hours=i))
    score = DXScore(metrics=metrics).score(project)
    assert score["compliance_percent"] == 100.0
    assert score["delivery_score"] > 90.0
    assert 0 <= score["dx_score"] <= 100
    assert score["dx_grade"] in ("A", "B", "C", "D", "F")
    assert score["dx_score"] >= 95.0


def test_dxscore_poor_project_low_score(tmp_path):
    project = make_project(tmp_path, {})
    metrics = DeliveryMetrics()
    now = datetime.utcnow()
    metrics.record_failure(lead_time_hours=500, recovery_minutes=9000,
                           timestamp=now - timedelta(days=45))
    score = DXScore(metrics=metrics).score(project)
    assert score["compliance_percent"] == 0.0
    assert score["dx_score"] < 40.0
    assert score["dx_grade"] == "F"
    assert score["recommendations"]


def test_letter_grade_boundaries():
    assert letter_grade(95) == "A"
    assert letter_grade(85) == "B"
    assert letter_grade(75) == "C"
    assert letter_grade(65) == "D"
    assert letter_grade(40) == "F"
    assert letter_grade(0) == "F"


# ---------------------------------------------------------------------------
# Lifecycle / to_dict serialization
# ---------------------------------------------------------------------------

def test_validation_report_to_dict(tmp_path):
    project = make_project(tmp_path, COMPLETE)
    report = GoldenPathValidator().validate(project)
    data = report.to_dict()
    assert data["compliance_percent"] == 100.0
    assert data["letter_grade"] == "A"
    assert data["passed_count"] == len(report.results)
    assert data["failed_count"] == 0
    assert isinstance(data["results"], list)
    assert data["project_dir"] == str(project)


def test_exports_available_from_module_package():
    from enterprise.modules import developer_experience as dx
    assert hasattr(dx, "GoldenPathValidator")
    assert hasattr(dx, "GoldenPathChecklist")
    assert hasattr(dx, "DeliveryMetrics")
    assert hasattr(dx, "DXScore")
    assert hasattr(dx, "ValidationReport")
    assert hasattr(dx, "GoldenPath")  # preserved from golden_paths
