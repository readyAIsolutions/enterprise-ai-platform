"""
Developer Experience — Golden-Path Validation & Delivery Metrics
=================================================================
Master-class validation layer for the Developer Experience OS.

Two complementary concerns:

1. **Golden-path validation** — checks a project/repo directory against a
   checklist of DX standards (README, tests, CI, lint config, type hints,
   .gitignore, LICENSE, semantic versioning) and produces a compliance
   percentage, a letter grade, and actionable failure recommendations.

2. **Delivery metrics (DORA)** — aggregates deployment frequency, lead time
   for changes, change failure rate, and MTTR into per-metric bands
   (Elite / High / Medium / Low) following the DORA framework, and exposes
   an overall delivery performance level.

A ``DXScore`` facade combines path-compliance and delivery metrics into a
single 0-100 score with an A-F letter grade, giving teams one number that
captures both "is the repo following the golden path?" and "how well are we
delivering?".

Stdlib only.
"""

from __future__ import annotations

import logging
import statistics
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Sequence

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Letter grading (shared by validator and score facade)
# ---------------------------------------------------------------------------


def letter_grade(percentage: float) -> str:
    """Map a 0-100 score to an A-F letter grade."""
    if percentage >= 90:
        return "A"
    if percentage >= 80:
        return "B"
    if percentage >= 70:
        return "C"
    if percentage >= 60:
        return "D"
    return "F"


# ---------------------------------------------------------------------------
# Golden Path — a checklist of DX standards
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class GoldenCheck:
    """A single golden-path standard.

    Attributes:
        id: stable machine-readable identifier (e.g. ``has_readme``).
        description: human-readable explanation of the standard.
        grade: the DX tier this check belongs to
            (``essential``, ``recommended``, ``excellent``).
        weight: relative contribution to the compliance score (default 1.0).
        matcher: optional callable ``fn(Path) -> bool`` used to decide
            whether the project satisfies the check. When ``None`` the check
            falls back to ``present_files`` existence semantics.
        present_files: one or more relative file/dir names that, if present,
            satisfy the check (used when ``matcher`` is ``None``).
        remediation: human advice shown when the check fails.
    """

    id: str
    description: str
    grade: str
    weight: float = 1.0
    matcher: Any | None = None
    present_files: tuple[str, ...] = ()
    remediation: str = ""

    def __post_init__(self) -> None:
        if isinstance(self.present_files, str):
            object.__setattr__(self, "present_files", (self.present_files,))
        if self.weight <= 0:
            object.__setattr__(self, "weight", 1.0)


class GoldenPath:
    """A checklist of DX standards applied to a project directory.

    Provides factory helpers for the canonical enterprise golden path as well
    as the ability to build custom paths. Each check carries an
    ``id``/``description``/``grade`` and a strategy for verification.
    """

    def __init__(
        self, name: str = "enterprise-dx", checks: Sequence[GoldenCheck] | None = None
    ) -> None:
        self.name = name
        self.checks: list[GoldenCheck] = list(checks) if checks is not None else []

    # -- registration -------------------------------------------------------
    def add(self, check: GoldenCheck) -> GoldenPath:
        """Add a check to the path."""
        self.checks.append(check)
        return self

    def get(self, check_id: str) -> GoldenCheck | None:
        """Return a check by id or None."""
        for check in self.checks:
            if check.id == check_id:
                return check
        return None

    def ids(self) -> list[str]:
        """Return the ordered check ids."""
        return [c.id for c in self.checks]

    def by_grade(self, grade: str) -> list[GoldenCheck]:
        """Return checks belonging to a given grade tier."""
        return [c for c in self.checks if c.grade == grade]

    # -- canonical path -----------------------------------------------------
    @classmethod
    def enterprise_dx(cls) -> GoldenPath:
        """The canonical enterprise developer-experience golden path."""
        return cls(
            name="enterprise-dx",
            checks=[
                GoldenCheck(
                    id="has_readme",
                    description="Project has a README documenting purpose and usage.",
                    grade="essential",
                    weight=2.0,
                    present_files=("README.md", "README.rst", "README.txt", "README"),
                    remediation="Add a README.md at the repo root describing the project, quick start, and usage.",
                ),
                GoldenCheck(
                    id="has_tests",
                    description="Project contains an automated test suite.",
                    grade="essential",
                    weight=2.0,
                    present_files=("tests", "test", "spec"),
                    remediation="Add a tests/ directory with unit tests and wire them into your build.",
                ),
                GoldenCheck(
                    id="has_ci",
                    description="Project is wired to a continuous-integration pipeline.",
                    grade="essential",
                    weight=2.0,
                    present_files=(
                        ".github/workflows",
                        ".gitlab-ci.yml",
                        ".circleci",
                        "Jenkinsfile",
                        ".azure-pipelines.yml",
                    ),
                    remediation="Add a CI pipeline (e.g. .github/workflows/ci.yml) that runs tests on every push.",
                ),
                GoldenCheck(
                    id="has_lint_config",
                    description="Project ships a lint/format configuration.",
                    grade="recommended",
                    weight=1.0,
                    present_files=(
                        ".flake8",
                        ".pylintrc",
                        "pyproject.toml",
                        "setup.cfg",
                        ".eslintrc",
                        ".eslintrc.json",
                        ".rubocop.yml",
                        ".golangci.yml",
                    ),
                    remediation="Add a lint configuration (e.g. .flake8 or a ruff section in pyproject.toml).",
                ),
                GoldenCheck(
                    id="has_type_hints",
                    description="Project enforces/declares type hints.",
                    grade="recommended",
                    weight=1.0,
                    present_files=(
                        "mypy.ini",
                        "py.typed",
                        ".mypy.ini",
                        "pyrightconfig.json",
                        "tsconfig.json",
                    ),
                    remediation="Add mypy.ini (or py.typed for a library) and annotate public APIs.",
                ),
                GoldenCheck(
                    id="has_gitignore",
                    description="Project ignores build artifacts and local files.",
                    grade="essential",
                    weight=1.0,
                    present_files=(".gitignore",),
                    remediation="Add a .gitignore covering build output, virtualenvs, caches and IDE files.",
                ),
                GoldenCheck(
                    id="has_license",
                    description="Project includes a software license.",
                    grade="recommended",
                    weight=1.0,
                    present_files=("LICENSE", "LICENSE.txt", "LICENSE.md", "COPYING"),
                    remediation="Add a LICENSE file (pick an OSI-approved license appropriate for the project).",
                ),
                GoldenCheck(
                    id="is_versioned",
                    description="Project declares a semantic version.",
                    grade="essential",
                    weight=2.0,
                    matcher=_check_versioned,
                    remediation="Declare a version (e.g. __version__ in your package or version= in pyproject.toml).",
                ),
            ],
        )


def _check_versioned(project_dir: Path) -> bool:
    """Return True if the project declares a version somewhere."""
    if not project_dir.is_dir():
        return False
    # package.json
    pkg = project_dir / "package.json"
    if pkg.is_file():
        try:
            import json as _json

            data = _json.loads(pkg.read_text(encoding="utf-8", errors="ignore"))
            if data.get("version"):
                return True
        except Exception:  # pragma: no cover - defensive
            pass
    # pyproject.toml / setup.cfg
    for cfg in ("pyproject.toml", "setup.cfg"):
        cfgp = project_dir / cfg
        if cfgp.is_file():
            try:
                txt = cfgp.read_text(encoding="utf-8", errors="ignore")
                if "version" in txt and ("=" in txt or ":" in txt):
                    return True
            except Exception:  # pragma: no cover - defensive
                pass
    # __version__ anywhere in a python file (shallow scan)
    for py in list(project_dir.glob("*.py"))[:50]:
        try:
            txt = py.read_text(encoding="utf-8", errors="ignore")
            if "__version__" in txt:
                return True
        except Exception:  # pragma: no cover - defensive
            pass
    return False


# ---------------------------------------------------------------------------
# Validation result types
# ---------------------------------------------------------------------------


@dataclass
class CheckResult:
    """Outcome of validating a single golden-path check."""

    check_id: str
    description: str
    grade: str
    passed: bool
    weight: float = 1.0
    evidence: str = ""
    remediation: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "check_id": self.check_id,
            "description": self.description,
            "grade": self.grade,
            "passed": self.passed,
            "weight": self.weight,
            "evidence": self.evidence,
            "remediation": self.remediation,
        }


@dataclass
class ValidationReport:
    """Full report of a golden-path validation run."""

    project_dir: str
    path_name: str
    results: list[CheckResult] = field(default_factory=list)

    def passed(self) -> list[CheckResult]:
        return [r for r in self.results if r.passed]

    def failures(self) -> list[CheckResult]:
        return [r for r in self.results if not r.passed]

    def compliance_percent(self) -> float:
        """Weighted compliance percentage over all checks."""
        total = sum(r.weight for r in self.results)
        if total == 0:
            return 0.0
        earned = sum(r.weight for r in self.results if r.passed)
        return round(earned / total * 100.0, 1)

    def letter_grade(self) -> str:
        return letter_grade(self.compliance_percent())

    def recommendations(self) -> list[str]:
        return [r.remediation for r in self.failures() if r.remediation]

    def to_dict(self) -> dict[str, Any]:
        return {
            "project_dir": self.project_dir,
            "path_name": self.path_name,
            "compliance_percent": self.compliance_percent(),
            "letter_grade": self.letter_grade(),
            "passed_count": len(self.passed()),
            "failed_count": len(self.failures()),
            "results": [r.to_dict() for r in self.results],
            "recommendations": self.recommendations(),
        }


class GoldenPathValidator:
    """Validate a project directory against a :class:`GoldenPath`.

    Each check is resolved against the on-disk layout of ``project_dir``.
    Checks with an explicit ``matcher`` use it; otherwise the check passes
    when any of its ``present_files`` exist.
    """

    def __init__(self, path: GoldenPath | None = None) -> None:
        self.path = path or GoldenPath.enterprise_dx()

    def validate(self, project_dir: Path) -> ValidationReport:
        """Run every check in the path against ``project_dir``."""
        project_dir = Path(project_dir)
        results: list[CheckResult] = []
        for check in self.path.checks:
            passed, evidence = self._run_check(check, project_dir)
            results.append(
                CheckResult(
                    check_id=check.id,
                    description=check.description,
                    grade=check.grade,
                    passed=passed,
                    weight=check.weight,
                    evidence=evidence,
                    remediation=check.remediation,
                )
            )
        return ValidationReport(
            project_dir=str(project_dir),
            path_name=self.path.name,
            results=results,
        )

    def _run_check(self, check: GoldenCheck, project_dir: Path) -> tuple[bool, str]:
        """Return (passed, evidence) for a single check."""
        if not project_dir.is_dir():
            return False, "project directory does not exist"
        if check.matcher is not None:
            try:
                ok = bool(check.matcher(project_dir))
            except Exception as exc:  # pragma: no cover - defensive
                logger.debug("matcher failed for %s: %s", check.id, exc)
                ok = False
            return ok, ("matched by custom logic" if ok else "custom matcher did not pass")
        for name in check.present_files:
            candidate = project_dir / name
            if candidate.exists():
                return True, f"found {name}"
        return False, "none of " + ", ".join(check.present_files) + " found"


# ---------------------------------------------------------------------------
# DORA delivery metrics
# ---------------------------------------------------------------------------


class DeliveryBand(Enum):
    """DORA performance bands."""

    ELITE = "elite"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass
class DeployEvent:
    """A single deployment / change event used to derive delivery metrics."""

    timestamp: datetime = field(default_factory=datetime.utcnow)
    success: bool = True
    lead_time_hours: float = 0.0
    recovery_minutes: float = 0.0
    team: str = ""


class DeliveryMetrics:
    """DORA-style delivery aggregator.

    Records deployment events and aggregates the four core DORA metrics:

    * **deployment frequency** — deploys per day
    * **lead time for changes** — mean + p50/p95 hours from commit to prod
    * **change failure rate** — % of deploys that failed
    * **MTTR** — mean time to recovery in minutes

    Each metric is also classified into a DORA band
    (Elite / High / Medium / Low) using canonical thresholds.
    """

    def __init__(self, team: str = "", lookback_days: int = 90) -> None:
        self.team = team
        self.lookback_days = lookback_days
        self.events: list[DeployEvent] = []

    # -- recording ----------------------------------------------------------
    def record_deploy_event(
        self,
        success: bool = True,
        lead_time_hours: float = 0.0,
        recovery_minutes: float = 0.0,
        timestamp: datetime | None = None,
    ) -> DeliveryMetrics:
        """Record a deployment/change event.

        Args:
            success: whether the deployment was successful.
            lead_time_hours: hours from commit merged to production.
            recovery_minutes: time to restore service after a failure
                (only meaningful for failed deployments / incidents).
            timestamp: event time; defaults to now.
        """
        self.events.append(
            DeployEvent(
                timestamp=timestamp or datetime.utcnow(),
                success=success,
                lead_time_hours=lead_time_hours,
                recovery_minutes=recovery_minutes,
                team=self.team,
            )
        )
        return self

    # convenient aliases ----------------------------------------------------
    def record_success(
        self, lead_time_hours: float = 0.0, timestamp: datetime | None = None
    ) -> DeliveryMetrics:
        return self.record_deploy_event(
            success=True, lead_time_hours=lead_time_hours, timestamp=timestamp
        )

    def record_failure(
        self,
        lead_time_hours: float = 0.0,
        recovery_minutes: float = 0.0,
        timestamp: datetime | None = None,
    ) -> DeliveryMetrics:
        return self.record_deploy_event(
            success=False,
            lead_time_hours=lead_time_hours,
            recovery_minutes=recovery_minutes,
            timestamp=timestamp,
        )

    # -- aggregation --------------------------------------------------------
    def _recent_events(self) -> list[DeployEvent]:
        cutoff = datetime.utcnow() - timedelta(days=self.lookback_days)
        return [e for e in self.events if e.timestamp >= cutoff]

    def deployment_frequency_per_day(self) -> float:
        """Mean deploys per day across the lookback window."""
        events = self._recent_events()
        if not events:
            return 0.0
        span = max(
            (max(e.timestamp for e in events) - min(e.timestamp for e in events)).total_seconds()
            / 86400.0,
            1e-9,
        )
        return round(len(events) / span, 3)

    def lead_time_stats(self) -> dict[str, float]:
        """Mean / p50 / p95 lead time (hours) across successful deployments."""
        events = self._recent_events()
        times = sorted(e.lead_time_hours for e in events)
        if not times:
            return {"mean_hours": 0.0, "p50_hours": 0.0, "p95_hours": 0.0}
        return {
            "mean_hours": round(statistics.mean(times), 2),
            "p50_hours": round(statistics.median(times), 2),
            "p95_hours": round(self._percentile(times, 95), 2),
        }

    def change_failure_rate_percent(self) -> float:
        """Percentage of deploys that resulted in failure."""
        events = self._recent_events()
        if not events:
            return 0.0
        failures = sum(1 for e in events if not e.success)
        return round(failures / len(events) * 100.0, 1)

    def mean_time_to_recovery_minutes(self) -> float:
        """Mean recovery time in minutes for failed deployments."""
        events = [e for e in self._recent_events() if not e.success and e.recovery_minutes > 0]
        if not events:
            return 0.0
        return round(statistics.mean(e.recovery_minutes for e in events), 1)

    @staticmethod
    def _percentile(sorted_values: Sequence[float], pct: float) -> float:
        if not sorted_values:
            return 0.0
        if len(sorted_values) == 1:
            return float(sorted_values[0])
        k = (len(sorted_values) - 1) * (pct / 100.0)
        lower = int(k)
        upper = min(lower + 1, len(sorted_values) - 1)
        frac = k - lower
        return float(sorted_values[lower] + frac * (sorted_values[upper] - sorted_values[lower]))

    # -- DORA band classification ------------------------------------------
    @staticmethod
    def band_deployment_frequency(deploys_per_day: float) -> str:
        """DORA band for deployment frequency (per day)."""
        if deploys_per_day >= 1.0:
            return "elite"  # on-demand, multiple per day
        if deploys_per_day >= (1.0 / 7.0):
            return "high"  # between once per day and once per week
        if deploys_per_day >= (1.0 / 30.0):
            return "medium"  # between once per week and once per month
        return "low"

    @staticmethod
    def band_lead_time(mean_hours: float) -> str:
        """DORA band for lead time for changes (mean hours)."""
        if mean_hours < 1.0:
            return "elite"  # less than one hour
        if mean_hours < 24.0:
            return "high"  # less than one day
        if mean_hours < 168.0:
            return "medium"  # less than one week
        return "low"

    @staticmethod
    def band_change_failure_rate(cfr_percent: float) -> str:
        """DORA band for change failure rate (percent)."""
        if cfr_percent < 5.0:
            return "elite"
        if cfr_percent < 10.0:
            return "high"
        if cfr_percent < 15.0:
            return "medium"
        return "low"

    @staticmethod
    def band_mttr(recovery_minutes: float) -> str:
        """DORA band for mean time to recovery (minutes)."""
        if recovery_minutes < 60.0:
            return "elite"  # less than one hour
        if recovery_minutes < 1440.0:
            return "high"  # less than one day
        if recovery_minutes < 4320.0:
            return "medium"  # less than three days
        return "low"

    def bands(self) -> dict[str, str]:
        """Per-metric DORA bands."""
        if not self._recent_events():
            return {
                "deployment_frequency": "low",
                "lead_time": "low",
                "change_failure_rate": "low",
                "mttr": "low",
            }
        return {
            "deployment_frequency": self.band_deployment_frequency(
                self.deployment_frequency_per_day()
            ),
            "lead_time": self.band_lead_time(self.lead_time_stats()["mean_hours"]),
            "change_failure_rate": self.band_change_failure_rate(
                self.change_failure_rate_percent()
            ),
            "mttr": self.band_mttr(self.mean_time_to_recovery_minutes()),
        }

    def overall_band(self) -> str:
        """Overall DORA level from the four metric bands (Elite/High/Medium/Low)."""
        order = {band.value: score for score, band in enumerate(DeliveryBand)}
        scores = [order[b] for b in self.bands().values()]
        if not scores:
            return "low"
        avg = sum(scores) / len(scores)
        # higher score = worse; avg 0.0 -> all elite
        if avg <= 0.5:
            return "elite"
        if avg <= 1.5:
            return "high"
        if avg <= 2.5:
            return "medium"
        return "low"

    def to_dict(self) -> dict[str, Any]:
        return {
            "team": self.team,
            "lookback_days": self.lookback_days,
            "events": len(self._recent_events()),
            "deployment_frequency_per_day": self.deployment_frequency_per_day(),
            "lead_time": self.lead_time_stats(),
            "change_failure_rate_percent": self.change_failure_rate_percent(),
            "mttr_minutes": self.mean_time_to_recovery_minutes(),
            "bands": self.bands(),
            "overall_band": self.overall_band(),
        }


# ---------------------------------------------------------------------------
# DXScore — combined facade
# ---------------------------------------------------------------------------


class DXScore:
    """Combine golden-path compliance and DORA delivery into one 0-100 score.

    Score composition:

    * 60% golden-path compliance (``compliance_percent``)
    * 40% DORA delivery quality (mapped from the overall band and the
      individual metric bands to a 0-100 sub-score)

    Produces a weighted 0-100 total and an A-F letter grade.
    """

    COMPLIANCE_WEIGHT = 0.6
    DELIVERY_WEIGHT = 0.4

    def __init__(
        self,
        validator: GoldenPathValidator | None = None,
        metrics: DeliveryMetrics | None = None,
    ) -> None:
        self.validator = validator or GoldenPathValidator(GoldenPath.enterprise_dx())
        self.metrics = metrics or DeliveryMetrics()

    # -- delivery sub-score -------------------------------------------------
    def delivery_score(self) -> float:
        """Map DORA bands to a 0-100 delivery sub-score."""
        band_values = self.metrics.bands().values()
        if not band_values:
            return 0.0
        order = {band.value: i for i, band in enumerate(DeliveryBand)}  # elite=0..low=3
        avg_index = sum(order[b] for b in band_values) / len(band_values)
        # avg_index 0 -> 100; avg_index 3 -> 0
        return round(100.0 - (avg_index / 3.0) * 100.0, 1)

    # -- aggregate ----------------------------------------------------------
    def score(self, project_dir: Path) -> dict[str, Any]:
        """Compute the combined DX score for ``project_dir``."""
        report = self.validator.validate(project_dir)
        compliance = report.compliance_percent()
        delivery = self.delivery_score()
        total = round(compliance * self.COMPLIANCE_WEIGHT + delivery * self.DELIVERY_WEIGHT, 1)
        return {
            "project_dir": str(project_dir),
            "compliance_percent": compliance,
            "compliance_grade": report.letter_grade(),
            "delivery_score": delivery,
            "delivery_band": self.metrics.overall_band(),
            "dx_score": total,
            "dx_grade": letter_grade(total),
            "recommendations": report.recommendations(),
        }
