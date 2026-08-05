"""Tests for the ENI fleet-wide line-coverage engine.

Hermetic by design: :class:`CoverageProbe` is exercised against a tiny fixture
project with an INJECTED fake subprocess runner (no slow real coverage run in
the unit tests). The only test that triggers a genuinely real ``coverage``
subprocess is a light smoke over the tiny fixture, and it is skipped when the
``coverage`` package is absent (``pytest.importorskip``).

Verifies: CoverageProbe computes per-file + global %, CoverageReport grade
bounds / bottom-files / per-package aggregation, the optional ``coverage_pct``
slotting into D4 Test Quality, and the report-writing fleet script.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import pytest
from enterprise.modules.universal_score.coverage_fleet import (
    CoverageError,
    CoverageProbe,
    CoverageReport,
    _Proc,
    run_fleet_coverage,
)
from enterprise.modules.universal_score.tests.test_universal_score import (
    make_good_project,
)
from enterprise.modules.universal_score.universal_score import UniversalBuildScore

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "covproj"


# ---------------------------------------------------------------------------
# Canned coverage JSON (shape of `coverage report --format=json`)
# ---------------------------------------------------------------------------
def _summary(percent: float, stmts: int, covered: int) -> dict[str, Any]:
    return {
        "percent_covered": percent,
        "num_statements": stmts,
        "covered_lines": covered,
        "missing_lines": max(0, stmts - covered),
        "num_branches": 0,
        "covered_branches": 0,
        "missing_branches": 0,
    }


def _payload(total_pct: float = 75.0) -> dict[str, Any]:
    return {
        "meta": {"format": 2, "version": "7.15.3"},
        "files": {
            "app/mod1.py": {"summary": _summary(100.0, 10, 10)},
            "app/mod2.py": {"summary": _summary(50.0, 10, 5)},
        },
        "totals": {
            "percent_covered": total_pct,
            "num_statements": 20,
            "covered_lines": 15,
            "missing_lines": 5,
        },
    }


class FakeRunner:
    """Injectable subprocess runner: returns canned JSON for the report step,
    a no-op for the pytest/run step. Records every command it saw."""

    def __init__(self, payload: dict[str, Any], rc: int = 0) -> None:
        self.payload = payload
        self.rc = rc
        self.calls: list = []

    def __call__(self, command: list[str], cwd: str, timeout: int) -> _Proc:  # noqa: ARG002
        self.calls.append(list(command))
        if "json" in command:
            return _Proc(json.dumps(self.payload), self.rc)
        return _Proc("", self.rc)


class BadRunner:
    """Subprocess runner that always fails (nonzero return code)."""

    def __call__(self, _command: list[str], cwd: str, timeout: int) -> _Proc:  # noqa: ARG002
        return _Proc("", 1)


# ---------------------------------------------------------------------------
# CoverageProbe
# ---------------------------------------------------------------------------
class TestCoverageProbe:
    def test_probe_measures_per_file_and_global(self) -> None:
        runner = FakeRunner(_payload())
        probe = CoverageProbe(FIXTURE, runner=runner)
        data = probe.measure()
        assert data["files"]["app/mod1.py"]["summary"]["percent_covered"] == 100.0
        assert probe.global_pct(data) == pytest.approx(75.0)

    def test_probe_rejects_missing_root(self) -> None:
        with pytest.raises(FileNotFoundError):
            CoverageProbe(FIXTURE / "does_not_exist", runner=FakeRunner(_payload()))

    def test_probe_raises_on_failed_subprocess(self) -> None:
        probe = CoverageProbe(FIXTURE, runner=BadRunner())
        with pytest.raises(CoverageError):
            probe.measure()

    def test_probe_reads_source_relative_paths(self) -> None:
        runner = FakeRunner(_payload())
        probe = CoverageProbe(FIXTURE, runner=runner)
        data = CoverageReport(probe, probe.measure())
        assert "app/mod2.py" in data.per_file

    def test_probe_report_command_uses_json_output(self) -> None:
        runner = FakeRunner(_payload())
        CoverageProbe(FIXTURE, runner=runner).measure()
        report_call = [c for c in runner.calls if "json" in c][-1]
        assert "-o" in report_call


# ---------------------------------------------------------------------------
# CoverageReport aggregation + grade
# ---------------------------------------------------------------------------
class TestCoverageReport:
    def _report(self, payload: dict[str, Any]) -> CoverageReport:
        probe = CoverageProbe(FIXTURE, runner=FakeRunner(payload))
        return CoverageReport(probe, payload)

    def test_global_percent(self) -> None:
        assert self._report(_payload(75.0)).global_pct == pytest.approx(75.0)
        assert self._report(_payload(99.9)).global_pct == pytest.approx(99.9)

    def test_global_percent_rounds(self) -> None:
        assert self._report(_payload(12.345)).global_pct == pytest.approx(12.3)

    def test_bottom_files_lowest_first(self) -> None:
        report = self._report(_payload())
        assert report.bottom_files[0] == ("app/mod2.py", 50.0)
        assert report.bottom_files[1] == ("app/mod1.py", 100.0)

    def test_bottom_files_at_most_ten(self) -> None:
        many = {"meta": {}, "files": {}, "totals": {"percent_covered": 50.0}}
        for i in range(15):
            many["files"][f"pkg/f{i}.py"] = {"summary": _summary(float(i), 10, i)}
        report = self._report(many)
        assert len(report.bottom_files) <= 10

    def test_per_package_statement_weighted(self) -> None:
        report = self._report(_payload())
        # app: (10 covered + 5 covered) / (10 + 10 stmts) = 75%
        assert report.per_package["app"] == pytest.approx(75.0)

    def test_grade_bounds(self) -> None:
        grade = CoverageReport._grade
        assert grade(95) == "A"
        assert grade(90) == "A"
        assert grade(85) == "B"
        assert grade(80) == "B"
        assert grade(75) == "C"
        assert grade(70) == "C"
        assert grade(65) == "D"
        assert grade(60) == "D"
        assert grade(40) == "F"

    def test_to_dict_shape(self) -> None:
        d = self._report(_payload()).to_dict()
        assert set(d) == {
            "global_pct",
            "grade",
            "per_package",
            "bottom_files",
            "n_files",
            "tests_exit_code",
        }


# ---------------------------------------------------------------------------
# coverage_pct slots into D4 Test Quality
# ---------------------------------------------------------------------------
class TestCoveragePctSlotIn:
    def test_zero_coverage_slots_into_score(self) -> None:
        s = UniversalBuildScore()
        result = s.score(
            make_good_project(Path(__import__("tempfile").mkdtemp())),
            run_tests=False,
            coverage_pct=0.0,
        )
        assert result["coverage_pct"] == 0.0

    def test_higher_coverage_raises_test_quality(self, tmp_path: Path) -> None:
        s = UniversalBuildScore()
        low = s.score(make_good_project(tmp_path / "a"), run_tests=False, coverage_pct=5.0)
        high = s.score(make_good_project(tmp_path / "b"), run_tests=False, coverage_pct=95.0)
        low_d4 = low["dimensions"]["test_quality"]["score"]
        high_d4 = high["dimensions"]["test_quality"]["score"]
        assert high_d4 > low_d4
        assert high["coverage_pct"] == 95.0

    def test_coverage_pct_none_backward_compatible(self, tmp_path: Path) -> None:
        s = UniversalBuildScore()
        result = s.score(make_good_project(tmp_path), run_tests=False)
        assert result["coverage_pct"] is None


# ---------------------------------------------------------------------------
# run_fleet_coverage report writer
# ---------------------------------------------------------------------------
class TestRunFleetCoverage:
    def test_writes_report_file_hermetically(self, tmp_path: Path) -> None:
        probe = CoverageProbe(FIXTURE, runner=FakeRunner(_payload(75.0)))
        out = tmp_path / "COVERAGE_REPORT.md"
        rep = run_fleet_coverage(root=FIXTURE, report_path=out, probe=probe)
        assert rep.global_pct == pytest.approx(75.0)
        text = out.read_text(encoding="utf-8")
        assert "Global line coverage: 75%" in text
        assert "Grade: C" in text
        assert "app/mod2.py" in text

    def test_report_covers_lowest_files_section(self, tmp_path: Path) -> None:
        probe = CoverageProbe(FIXTURE, runner=FakeRunner(_payload()))
        out = tmp_path / "COVERAGE_REPORT.md"
        run_fleet_coverage(root=FIXTURE, report_path=out, probe=probe)
        assert "Lowest-coverage files" in out.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Light smoke: real coverage subprocess over the TINY fixture only (fast),
# skipped when the `coverage` package is unavailable.
# ---------------------------------------------------------------------------
class TestFleetScriptRealSmoke:
    def test_real_tiny_fixture_coverage(self, tmp_path: Path) -> None:
        pytest.importorskip("coverage")
        probe = CoverageProbe(FIXTURE, python_bin=sys.executable, source_dirs=("app",), timeout=120)
        out = tmp_path / "COVERAGE_REPORT.md"
        try:
            rep = run_fleet_coverage(root=FIXTURE, report_path=out, probe=probe)
        except CoverageError as e:
            # The coverage package may live in a different interpreter than the
            # one pytest invokes the subprocess with; skip rather than fail.
            pytest.skip(f"coverage subprocess not available in this environment: {e}")
        assert isinstance(rep.global_pct, float)
        assert out.exists()
        # Bigger than zero and bounded <= 100
        assert 0.0 <= rep.global_pct <= 100.0
