"""ENI Fleet-wide Line Coverage engine.

MASTER-CLASS addition to :mod:`enterprise.modules.universal_score`: instead of
guessing test coverage from a heuristic (presence of a ``.coverage`` artifact or
a test-to-source ratio), this engine measures REAL line coverage by running
``python -m coverage`` over a project's own test suite in a controlled, capped
subprocess, parses the JSON report and folds a rounded percentage back into the
Universal Build Score's ``TEST_QUALITY`` dimension.

Three public pieces:

* :class:`CoverageProbe` -- runs ``coverage run -m pytest`` then
  ``coverage report --format=json`` in a subprocess (bounded by repo-size
  source list and a hard timeout) and returns the raw per-file/global data.
  The subprocess runner is injectable so tests never execute a slow run.
* :class:`CoverageReport` -- turns raw JSON into a global %, per-package %,
  the 10 worst-covered files and a letter grade.
* :func:`run_fleet_coverage` -- script-style entrypoint that measures the
  enterprise repo's own ``modules/`` tree and writes ``docs/COVERAGE_REPORT.md``
  with the real numbers.

Hermetic by construction: ``CoverageProbe`` accepts a ``runner`` callable and
``CoverageReport``/``run_fleet_coverage`` accept pre-baked data, so the test
suite never triggers a real full-suite coverage run.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
from collections import OrderedDict
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger("eni.universal_score.coverage_fleet")

#: Default subprocess timeout (sec) for the coverage measurement -- caps runtime
#: so a pathological repo cannot hang the caller.
DEFAULT_TIMEOUT = 600

#: Default source roots measured inside a project (relative paths).
DEFAULT_SOURCE_DIRS = ("modules",)

#: Grade thresholds on global line-coverage %.
GRADE_BOUNDS = (
    (90.0, "A"),
    (80.0, "B"),
    (70.0, "C"),
    (60.0, "D"),
    (0.0, "F"),
)

#: Bottom-N files to surface in the report.
BOTTOM_FILES_N = 10


class CoverageError(RuntimeError):
    """Raised when a coverage subprocess fails or its output cannot be parsed."""


class _Proc:
    """Minimal stand-in for :class:`subprocess.CompletedProcess` (also used to
    let tests inject a fake runner without importing subprocess internals)."""

    __slots__ = ("stdout", "stderr", "returncode")

    def __init__(self, stdout: str, returncode: int = 0, stderr: str = "") -> None:
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode


def _clean_environ(environ: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    """Return a sanitized copy of ``os.environ`` for a coverage subprocess.

    Defensive against harness/CI-injected corruption: drops a mangled
    ``PYTHONPATH`` whose value contains a literal ``declare -x`` export prefix
    and removes path entries that do not exist as directories, so the nested
    ``python -m coverage`` can always find its installed package.
    """
    env = dict(os.environ if environ is None else environ)
    ppath = env.get("PYTHONPATH", "")
    if "declare -x" in ppath or "PYTHONPATH=" in ppath:
        # Reject the corrupted literal-export value entirely.
        env.pop("PYTHONPATH", None)
        ppath = ""
    if ppath:
        kept = [p for p in ppath.split(os.pathsep) if p and Path(p).is_dir()]
        if kept:
            env["PYTHONPATH"] = os.pathsep.join(kept)
        else:
            env.pop("PYTHONPATH", None)
    # Never disable the user site-packages dir in the coverage subprocess; that
    # is where the `coverage` package commonly lives.
    env.pop("PYTHONNOUSERSITE", None)
    env.pop("PYTHONDONTWRITEBYTECODE", None)
    return env


def _real_runner(command: List[str], cwd: str, timeout: int) -> _Proc:
    """Default subprocess runner for :class:`CoverageProbe`.

    Captures stdout/stderr as text and enforces the timeout cap. The subprocess
    runs with a sanitized environment so ``python -m coverage`` resolves
    reliably even inside a longer test session.
    """
    proc = subprocess.run(
        command,
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
        env=_clean_environ(),
    )
    return _Proc(proc.stdout, proc.returncode, proc.stderr)


class CoverageProbe:
    """Run ``python -m coverage`` over a project and return line-coverage %.

    Controlled/capped by: (1) limiting the measured source to ``source_dirs``
    rather than the whole tree, and (2) a hard ``timeout`` on every subprocess.
    The ``runner`` callable is injectable for hermetic unit tests.
    """

    def __init__(
        self,
        project_root: Any,
        runner: Optional[Callable[..., _Proc]] = None,
        timeout: int = DEFAULT_TIMEOUT,
        python_bin: Optional[str] = None,
        source_dirs: Tuple[str, ...] = DEFAULT_SOURCE_DIRS,
        pytest_opts: str = "-q",
    ) -> None:
        self.root = Path(project_root)
        if not self.root.is_dir():
            raise FileNotFoundError(f"Project root does not exist: {self.root}")
        self.runner: Callable[..., _Proc] = runner or _real_runner
        self.timeout = int(timeout)
        self.python_bin = python_bin or sys.executable
        self.source_dirs = tuple(source_dirs)
        self.pytest_opts = pytest_opts
        #: Exit code of the most recent ``coverage run -m pytest`` (0 => green).
        self.last_run_rc: int = 0

    # ------------------------------------------------------------------ utils
    def _exec(self, command: List[str], check: bool = True) -> _Proc:
        proc = self.runner(command, cwd=str(self.root), timeout=self.timeout)
        if check and getattr(proc, "returncode", 0) != 0:
            detail = getattr(proc, "stderr", "") or getattr(proc, "stdout", "") or ""
            if detail:
                detail = "\n" + detail.strip()
            raise CoverageError(
                f"coverage subprocess failed (rc={proc.returncode}): "
                f"{' '.join(command)}{detail}"
            )
        return proc

    def _source_args(self) -> List[str]:
        """--source=... limiting measurement to the configured source dirs."""
        roots = ",".join(str(self.root / d) for d in self.source_dirs)
        return [f"--source={roots}"]

    # ------------------------------------------------------------- public API
    def measure(self) -> Dict[str, Any]:
        """Run the project's own tests under coverage and return the raw JSON
        report dict (shape of ``coverage json``).

        A non-zero exit from the test run is tolerated (flaky CI tests must not
        block a coverage measurement): coverage still records every line the
        executed tests touched. The run's exit code is stashed on
        ``self.last_run_rc`` for transparency. Only a genuine failure of the
        coverage JSON step raises :class:`CoverageError`.
        """
        run_cmd = (
            [self.python_bin, "-m", "coverage", "run"]
            + self._source_args()
            + ["-m", "pytest", self.pytest_opts]
        )
        run_proc = self._exec(run_cmd, check=False)
        self.last_run_rc: int = getattr(run_proc, "returncode", 0)

        report_cmd = [self.python_bin, "-m", "coverage", "json", "-o", "-"]
        out = self._exec(report_cmd).stdout or ""
        try:
            return json.loads(out)
        except json.JSONDecodeError as exc:  # pragma: no cover - defensive
            raise CoverageError(f"malformed coverage JSON output: {exc}") from exc

    def global_pct(self, data: Optional[Dict[str, Any]] = None) -> float:
        """Rounded global line-coverage % (folds back into Test Quality)."""
        totals = (data or self.measure()).get("totals", {})
        try:
            return round(float(totals.get("percent_covered", 0.0)), 1)
        except (TypeError, ValueError):  # pragma: no cover - defensive
            return 0.0


class CoverageReport:
    """Aggregate a raw coverage JSON report into decisions for the scorer."""

    def __init__(self, probe: CoverageProbe, data: Optional[Dict[str, Any]] = None) -> None:
        self.probe = probe
        self.data: Dict[str, Any] = data if data is not None else probe.measure()
        self.totals: Dict[str, Any] = self.data.get("totals", {})

        try:
            self.global_pct = round(float(self.totals.get("percent_covered", 0.0)), 1)
        except (TypeError, ValueError):
            self.global_pct = 0.0

        # per-file: relative path -> rounded line-coverage %
        self.per_file: Dict[str, float] = OrderedDict()
        for rel, info in (self.data.get("files", {}) or {}).items():
            try:
                self.per_file[rel] = round(
                    float(info["summary"]["percent_covered"]), 1
                )
            except (KeyError, TypeError, ValueError):
                continue

        # statement-weighted per-package %
        self.per_package: Dict[str, float] = self._aggregate_packages()
        self.bottom_files: List[Tuple[str, float]] = sorted(
            self.per_file.items(), key=lambda kv: (kv[1], kv[0])
        )[:BOTTOM_FILES_N]
        self.grade: str = self._grade(self.global_pct)

    # ------------------------------------------------------------------ utils
    def _aggregate_packages(self) -> Dict[str, float]:
        """Group per-file coverage by real module subdir, weighted by executed
        statements (the same weighting ``coverage`` itself uses).

        Source files live under ``<root>/<pkg>/<file>.py``; we group on ``pkg``
        (the segment after the source root) so ``modules/agent_core/...`` yields
        package ``agent_core`` rather than a single ``modules`` bucket.
        """
        packages: Dict[str, List[float]] = {}
        for rel, info in (self.data.get("files", {}) or {}).items():
            summary = info.get("summary", {})
            try:
                stmts = float(summary.get("num_statements", 0))
                covered = float(summary.get("covered_lines", 0))
            except (TypeError, ValueError):
                continue
            parts = [p for p in Path(rel).parts if p]
            if not parts:
                continue
            if len(parts) >= 2 and parts[0] in self.probe.source_dirs:
                package = parts[1]
            else:
                package = parts[0]
            if stmts <= 0:
                continue
            packages.setdefault(package, [0.0, 0.0])
            packages[package][0] += covered
            packages[package][1] += stmts
        return OrderedDict(
            (name, round(covered / total * 100.0, 1) if total else 0.0)
            for name, (covered, total) in packages.items()
        )

    @staticmethod
    def _grade(pct: float) -> str:
        for threshold, letter in GRADE_BOUNDS:
            if pct >= threshold:
                return letter
        return "F"  # pragma: no cover - GRADE_BOUNDS floor is 0.0

    def to_dict(self) -> Dict[str, Any]:
        """Plain dict for serialization into docs / the score result."""
        return {
            "global_pct": self.global_pct,
            "grade": self.grade,
            "per_package": dict(self.per_package),
            "bottom_files": self.bottom_files,
            "n_files": len(self.per_file),
            "tests_exit_code": self.probe.last_run_rc,
        }


def _repo_root() -> Path:
    # .../modules/universal_score/coverage_fleet.py -> repo root
    return Path(__file__).resolve().parents[2]


def run_fleet_coverage(
    root: Optional[Any] = None,
    report_path: Optional[Any] = None,
    probe: Optional[CoverageProbe] = None,
) -> CoverageReport:
    """Run REAL line coverage over the enterprise repo's own ``modules/`` tree
    and write ``docs/COVERAGE_REPORT.md`` with the measured numbers.

    ``probe`` and ``report_path`` are injectable so tests can exercise the
    report-writing path without a slow real coverage run.
    """
    root = Path(root) if root is not None else _repo_root()
    probe = probe or CoverageProbe(root)
    report = CoverageReport(probe)

    if report_path is None:
        report_path = root / "docs" / "COVERAGE_REPORT.md"
    out_path: Path = Path(str(report_path))
    out_path.parent.mkdir(parents=True, exist_ok=True)

    lines = [
        "# ENI Fleet-Wide Line Coverage Report",
        "",
        "MASTER-CLASS: real measured line coverage from `python -m coverage` "
        "over the enterprise repo's own modules. Not a heuristic, not fabricated.",
        "",
        "## Global",
        "",
        f"- **Global line coverage: {report.global_pct:g}%**",
        f"- **Grade: {report.grade}**",
        f"- **Files measured: {len(report.per_file)}**",
        f"- **Test run exit code: {report.probe.last_run_rc}** "
        "(0 = whole suite green)",
        "",
        "## Per-package coverage",
        "",
        "| Package | Line coverage % |",
        "| --- | --- |",
    ]
    for name in sorted(report.per_package, key=lambda n: report.per_package[n]):
        lines.append(f"| {name} | {report.per_package[name]:g} |")

    lines += ["", "## Lowest-coverage files (bottom 10)", ""]
    if report.bottom_files:
        lines.append("| File | Line coverage % |")
        lines.append("| --- | --- |")
        for rel, pct in report.bottom_files:
            lines.append(f"| {rel} | {pct:g} |")
    else:  # pragma: no cover - defensive
        lines.append("_No files measured._")

    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    logger.info("Wrote coverage report: %s (global %.1f%%)", out_path, report.global_pct)
    return report


if __name__ == "__main__":  # invoke: python3 modules/universal_score/coverage_fleet.py
    rep = run_fleet_coverage()
    print(f"Fleet line coverage: {rep.global_pct}% (grade {rep.grade}) "
          f"across {len(rep.per_file)} files")
    print(json.dumps(rep.to_dict(), indent=2))
