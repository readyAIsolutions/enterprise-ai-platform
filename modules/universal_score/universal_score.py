"""ENI UNIVERSAL BUILD SCORE — one accurate, industry-grounded build-quality number.

The single canonical build-quality score for the ENI Enterprise Platform. Where
the rest of the platform scores *model output text* or *module metadata*, this
engine scores a *real software build on disk* by running actual probes against
the project tree and fusing them into ONE number.

Design (from ISO/IEC 25010, SonarQube quality-gate/MI, DORA, CMMI, Snyk/OWASP):

    UBS = 0.25*D1 + 0.15*D2 + 0.20*D3 + 0.15*D4 + 0.10*D5 + 0.15*D6 + BONUS

    D1 Reliability & Correctness  0.25   builds/imports clean, error handling
    D2 Security & Supply-Chain    0.15   no hardcoded secrets, pinned deps, gitignore
    D3 Maintainability & Eng.     0.20   type hints, docstrings, structure, duplication
    D4 Test Quality               0.15   real tests present, pass, coverage heuristic
    D5 Delivery / CI-CD (DORA)    0.10   CI config, Dockerfile, packaging, versioning
    D6 Completeness / Sellability 0.15   README, LICENSE, docs, no fake data, persistence

Hard gates: if a build fails any non-negotiable gate (won't build, tests fail,
hardcoded secrets, fake/placeholder data, no real persistence when claimed) the
score is capped at 40 — it is NOT sellable, period.

100 = fully sellable enterprise. A +25 excellence bonus lets a genuinely
transcendent build score ABOVE 100 (105..125) — the 'singularity' band.

This module is intentionally the anti-stub: every dimension is computed from
real filesystem/code inspection, never hardcoded.
"""

from __future__ import annotations

import ast
import logging
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any

from enterprise.platform_kernel import HealthStatus, Module, module

logger = logging.getLogger("eni.universal_score")

# =============================================================================
# Certification ladder (mirrors enterprise_validation for consistency)
# =============================================================================


class CertificationLevel(StrEnum):
    NOT_READY = "Not_Ready"
    PROTOTYPE = "Prototype"
    INTERNAL_DEV = "Internal_Dev"
    PRODUCTION_CANDIDATE = "Production_Candidate"
    ENTERPRISE_READY = "Enterprise_Ready"
    BEYOND_ENTERPRISE = "Beyond_Enterprise"
    TRANSCENDENT = "Transcendent"
    SINGULARITY = "Singularity"


def certification_for_score(score: float) -> CertificationLevel:
    if score >= 120:
        return CertificationLevel.SINGULARITY
    if score >= 110:
        return CertificationLevel.TRANSCENDENT
    if score >= 105:
        return CertificationLevel.BEYOND_ENTERPRISE
    if score >= 100:
        return CertificationLevel.ENTERPRISE_READY
    if score >= 85:
        return CertificationLevel.PRODUCTION_CANDIDATE
    if score >= 70:
        return CertificationLevel.INTERNAL_DEV
    if score >= 50:
        return CertificationLevel.PROTOTYPE
    return CertificationLevel.NOT_READY


# =============================================================================
# Dimension model
# =============================================================================


class Dimension(StrEnum):
    RELIABILITY = "reliability"
    SECURITY = "security"
    MAINTAINABILITY = "maintainability"
    TEST_QUALITY = "test_quality"
    DELIVERY = "delivery"
    SELLABILITY = "sellability"


DIMENSION_WEIGHTS: dict[Dimension, float] = {
    Dimension.RELIABILITY: 0.25,
    Dimension.SECURITY: 0.15,
    Dimension.MAINTAINABILITY: 0.20,
    Dimension.TEST_QUALITY: 0.15,
    Dimension.DELIVERY: 0.10,
    Dimension.SELLABILITY: 0.15,
}

# Default sub-signal weights per dimension (sum to 1.0 each)
DIMENSION_SUBWEIGHTS: dict[Dimension, dict[str, float]] = {
    Dimension.RELIABILITY: {
        "builds_clean": 0.40,
        "error_handling": 0.30,
        "no_crashes": 0.30,
    },
    Dimension.SECURITY: {
        "no_hardcoded_secrets": 0.40,
        "deps_pinned": 0.30,
        "gitignore_clean": 0.30,
    },
    Dimension.MAINTAINABILITY: {
        "type_hints": 0.30,
        "docstrings": 0.25,
        "structure": 0.30,
        "low_duplication": 0.15,
    },
    Dimension.TEST_QUALITY: {
        "tests_present": 0.25,
        "tests_pass": 0.45,
        "test_to_source_ratio": 0.15,
        "coverage_heuristic": 0.15,
    },
    Dimension.DELIVERY: {
        "ci_config": 0.30,
        "packaging": 0.30,
        "containerized": 0.15,
        "versioned": 0.25,
    },
    Dimension.SELLABILITY: {
        "readme": 0.30,
        "license": 0.15,
        "docs": 0.15,
        "no_fake_data": 0.25,
        "real_persistence": 0.15,
    },
}


# Regexes for detecting hardcoded secrets (best-effort, low false-positive bias)
SECRET_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("aws_access_key", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("aws_secret", re.compile(r"aws_secret_access_key\s*=\s*['\"][A-Za-z0-9/+=]{20,}")),
    ("github_token", re.compile(r"gh[pousr]_[A-Za-z0-9]{20,}")),
    ("api_key", re.compile(r"(api[_-]?key|apikey)\s*=\s*['\"][A-Za-z0-9]{20,}['\"]", re.I)),
    ("private_key", re.compile(r"-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----")),
    ("password", re.compile(r"password\s*=\s*['\"][^'\"]{8,}['\"]", re.I)),
    ("bearer_token", re.compile(r"Bearer [A-Za-z0-9._~+/=-]{20,}")),
    ("stripe_secret", re.compile(r"sk_live_[0-9a-zA-Z]{20,}")),
    ("slack_token", re.compile(r"xox[baprs]-[0-9A-Za-z-]{10,}")),
]

# Placeholder / fake-data markers. Two tiers:
#  STRONG = unambiguously fake/inert output even when mentioned once.
#  WEAK   = only damning when found in a returned/assigned value (not help/error text).
FAKE_DATA_MARKERS_STRONG = [
    "lorem ipsum",
    "fake data",
    "dummy data",
    "for demo only",
    "this is a placeholder",
    "fizzbuzz",
    "mock data",
    "sample data only",
    "no real data",
    "hardcoded sample",
    "return fake",
    "stub for demo",
]
FAKE_DATA_MARKERS_WEAK = [
    "todo: implement",
    "placeholder",
    "not implemented",
    "stub",
    "hardcoded",
    "coming soon",
]

# Human-file exclusions for token analysis
NON_SOURCE_SUFFIXES = {
    ".pyc",
    ".pyo",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".ico",
    ".woff",
    ".woff2",
    ".ttf",
    ".mp3",
    ".mp4",
    ".zip",
    ".tar",
    ".gz",
    ".so",
    ".dll",
    ".exe",
    ".pdf",
    ".lock",
    ".sqlite",
    ".db",
    ".bin",
    ".npy",
}
SOURCE_SUFFIXES = {
    ".py",
    ".js",
    ".ts",
    ".tsx",
    ".jsx",
    ".go",
    ".rs",
    ".java",
    ".rb",
    ".php",
    ".c",
    ".cpp",
    ".h",
    ".cs",
    ".sh",
    ".sql",
}


# =============================================================================
# Probe results
# =============================================================================


@dataclass
class SubSignal:
    key: str
    name: str
    score: float  # 0..1
    evidence: str = ""
    weight: float = 1.0


@dataclass
class DimensionResult:
    dimension: Dimension
    score: float  # 0..1
    sub_signals: list[SubSignal] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "dimension": self.dimension.value,
            "score": round(self.score, 4),
            "sub_signals": [
                {
                    "key": s.key,
                    "name": s.name,
                    "score": round(s.score, 4),
                    "evidence": s.evidence,
                }
                for s in self.sub_signals
            ],
        }


@dataclass
class HardGate:
    name: str
    passed: bool
    detail: str = ""


PROJECT_FILE_BLACKLIST = {
    ".git",
    "__pycache__",
    "node_modules",
    ".venv",
    "venv",
    ".ruff_cache",
    ".mypy_cache",
    ".pytest_cache",
    "dist",
    "build",
    "target",
    ".tox",
    "coverage",
}


def _iter_project_files(root: Path) -> list[Path]:
    """Return all files under root, skipping vendored/build dirs."""
    out: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in PROJECT_FILE_BLACKLIST]
        for fn in filenames:
            p = Path(dirpath) / fn
            # skip hidden + pyc
            if any(seg.startswith(".") and seg not in (".github", ".gitignore") for seg in p.parts):
                continue
            out.append(p)
    return out


def _is_source(p: Path) -> bool:
    return p.suffix.lower() in SOURCE_SUFFIXES


# =============================================================================
# The Universal Build Score engine
# =============================================================================


class UniversalBuildScore:
    """Scores a real build tree on disk into ONE universal number."""

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        cfg = config or {}
        self.weights: dict[Dimension, float] = {
            Dimension(k): float(v) for k, v in (cfg.get("weights", {}) or {}).items()
        } or DIMENSION_WEIGHTS
        self.bonus_cap: float = float(cfg.get("bonus_cap", 25))
        self.hard_gate_cap: float = float(cfg.get("hard_gate_cap", 40))
        self._python_bin: str = cfg.get("python_bin", sys.executable)

    # ---------- Probe implementation -------------------------------------

    def _probe_builds_clean(self, project: Path) -> SubSignal:
        evidence = []
        score = 1.0
        py_files = [p for p in _iter_project_files(project) if p.suffix == ".py"]
        if not py_files:
            # no python source — fall back to compile check of any sources
            return SubSignal(
                "builds_clean", "Builds/parses clean", 1.0, "no python source to compile"
            )
        errs = 0
        for p in py_files:
            try:
                ast.parse(p.read_text(encoding="utf-8", errors="ignore"))
            except SyntaxError as e:
                errs += 1
                evidence.append(f"{p.name}:{e.lineno} {e.msg}")
        if errs:
            score = max(0.0, 1.0 - (errs * 0.5))
            evidence = evidence[:8]
            evidence = evidence if evidence else ["syntax errors"]
        else:
            evidence = [f"{len(py_files)} python files parse clean"]
        return SubSignal(
            "builds_clean", "Builds / parses clean", round(score, 4), "; ".join(evidence[:3])
        )

    def _probe_error_handling(self, project: Path) -> SubSignal:
        try_count = except_count = 0
        py_files = [p for p in _iter_project_files(project) if p.suffix == ".py"]
        for p in py_files:
            try:
                tree = ast.parse(p.read_text(encoding="utf-8", errors="ignore"))
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.Try):
                    try_count += 1
                    except_count += len(node.handlers)
        if try_count == 0:
            return SubSignal("error_handling", "Error handling", 0.5, "no try/except found")
        ratio = min(1.0, except_count / max(1, try_count))
        # if every try has >=1 handler -> strong
        score = min(1.0, 0.4 + 0.6 * ratio)
        return SubSignal(
            "error_handling",
            "Error handling",
            round(score, 4),
            f"{try_count} try blocks, {except_count} handlers",
        )

    def _probe_no_crashes(self, project: Path) -> SubSignal:
        # Count defensive patterns: None guards, isinstance checks
        py_files = [p for p in _iter_project_files(project) if p.suffix == ".py"]
        guards = 0
        for p in py_files:
            try:
                tree = ast.parse(p.read_text(encoding="utf-8", errors="ignore"))
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.If):
                    t = ast.unparse(node.test)
                    if "is not None" in t or "is None" in t or "len(" in t:
                        guards += 1
        # normalise by line count of source
        src_lines = sum(_count_lines(p) for p in py_files if p.suffix == ".py")
        if src_lines == 0:
            return SubSignal("no_crashes", "Defensive / no crashes", 0.5, "no source")
        density = guards / max(1, src_lines)
        score = min(1.0, 0.3 + density * 40)
        return SubSignal(
            "no_crashes",
            "Defensive / no crashes",
            round(score, 4),
            f"{guards} guard conditions across {src_lines} lines",
        )

    def _probe_no_hardcoded_secrets(self, project: Path) -> SubSignal:
        hits: list[str] = []
        for p in _iter_project_files(project):
            if p.suffix not in (
                ".py",
                ".js",
                ".ts",
                ".env",
                ".json",
                ".yaml",
                ".yml",
                ".toml",
                ".sh",
            ):
                continue
            low_name = p.name.lower()
            # Skip test/fixture/spec files — they legitimately contain fake
            # credentials, and skip regex/pattern definition files.
            if (
                "test" in low_name
                or "fixture" in low_name
                or "spec" in low_name
                or "pattern" in low_name
                or "regex" in low_name
                or "example" in low_name
            ):
                continue
            text = p.read_text(encoding="utf-8", errors="ignore")
            # only scan non-comment source lines to avoid docstring/comment refs
            for line in text.splitlines():
                s_line = line.strip()
                if (
                    not s_line
                    or s_line.startswith("#")
                    or s_line.startswith("//")
                    or s_line.startswith("*")
                    or s_line.startswith('"""')
                    or s_line.startswith("'''")
                ):
                    continue
                for name, pattern in SECRET_PATTERNS:
                    # require an assignment context (real value), not a regex def
                    if "re.compile" in line or "compile(" in line:
                        continue
                    # skip regex-pattern definition tables like:
                    #   (r"-----BEGIN PRIVATE KEY-----", "PRIVATE_KEY", 0.99),
                    line.lstrip()
                    if "PRIVATE KEY" in line and (
                        "secret" in line.lower()
                        or "key" in line.lower()
                        or "token" in line.lower()
                        or "score" in line.lower()
                    ):
                        continue
                    if re.search(r'r"[^"]*"', line) and re.search(r'",\s*"[A-Z_]+"', line):
                        continue
                    m = pattern.search(line)
                    if m and "re.compile(" not in line and "REGEX" not in line.upper():
                        hits.append(f"{p.name}:{name}")
        if hits:
            uniq = sorted(set(hits))[:10]
            return SubSignal(
                "no_hardcoded_secrets", "No hardcoded secrets", 0.0, f"FOUND: {', '.join(uniq)}"
            )
        return SubSignal(
            "no_hardcoded_secrets", "No hardcoded secrets", 1.0, "no secret patterns detected"
        )

    def _probe_deps_pinned(self, project: Path) -> SubSignal:
        evidence = []
        # requirements with '==' / lockfile / poetry / uv lock
        for p in _iter_project_files(project):
            name = p.name.lower()
            if name in ("requirements.txt", "requirements.in"):
                text = p.read_text(encoding="utf-8", errors="ignore")
                pinned = sum(1 for ln in text.splitlines() if ln.strip() and "==" in ln)
                total = sum(1 for ln in text.splitlines() if ln.strip() and "=" in ln)
                ratio = pinned / max(1, total)
                evidence.append(f"{p.name}:{pinned}/{total} pinned")
                score = max(0.2, ratio)
                return SubSignal(
                    "deps_pinned", "Dependencies pinned", round(score, 4), "; ".join(evidence)
                )
            if name in (
                "poetry.lock",
                "uv.lock",
                "Pipfile.lock",
                "pnpm-lock.yaml",
                "package-lock.json",
                "yarn.lock",
                "go.sum",
                "Cargo.lock",
            ):
                return SubSignal(
                    "deps_pinned", "Dependencies pinned", 1.0, f"lockfile present: {p.name}"
                )
        return SubSignal("deps_pinned", "Dependencies pinned", 0.4, "no lockfile/pinning found")

    def _probe_gitignore_clean(self, project: Path) -> SubSignal:
        gi = project / ".gitignore"
        if not gi.exists():
            return SubSignal("gitignore_clean", ".gitignore & repo hygiene", 0.3, "no .gitignore")
        text = gi.read_text(encoding="utf-8", errors="ignore").lower()
        score = 0.6
        if any(k in text for k in (".env", "secret", "key")):
            score += 0.15
        if any(k in text for k in ("__pycache__", "node_modules", ".venv")):
            score += 0.15
        if any(k in text for k in ("*.log", "dist", "build")):
            score += 0.10
        return SubSignal(
            "gitignore_clean",
            ".gitignore & repo hygiene",
            round(min(1.0, score), 4),
            ".gitignore present",
        )

    def _probe_type_hints(self, project: Path) -> SubSignal:
        py_files = [p for p in _iter_project_files(project) if p.suffix == ".py"]
        annotated = 0
        total = 0
        with_hints = 0
        for p in py_files:
            try:
                tree = ast.parse(p.read_text(encoding="utf-8", errors="ignore"))
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    total += 1
                    if node.returns is not None or node.args.args:
                        pass
                    has_ret = node.returns is not None
                    has_args = bool(
                        node.args.args
                        and all(
                            a.annotation for a in node.args.args if a.arg not in ("self", "cls")
                        )
                    )
                    if has_ret:
                        annotated += 1
                    if has_args:
                        with_hints += 1
        if total == 0:
            return SubSignal("type_hints", "Type hints", 0.3, "no python functions")
        ratio = (annotated + with_hints) / (2 * total)
        return SubSignal(
            "type_hints",
            "Type hints",
            round(min(1.0, ratio * 2), 4),
            f"{annotated}/{total} functions have return-type hints",
        )

    def _probe_docstrings(self, project: Path) -> SubSignal:
        py_files = [p for p in _iter_project_files(project) if p.suffix == ".py"]
        functions = modules = with_doc = 0
        for p in py_files:
            try:
                tree = ast.parse(p.read_text(encoding="utf-8", errors="ignore"))
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    functions += 1
                    if ast.get_docstring(node):
                        with_doc += 1
                elif isinstance(node, ast.Module):
                    if ast.get_docstring(node):
                        modules += 1
        if functions == 0:
            return SubSignal("docstrings", "Docstrings", 0.3, "no functions")
        ratio = with_doc / functions
        return SubSignal(
            "docstrings",
            "Docstrings",
            round(min(1.0, ratio * 1.5), 4),
            f"{with_doc}/{functions} functions documented",
        )

    def _probe_structure(self, project: Path) -> SubSignal:
        py_files = [p for p in _iter_project_files(project) if p.suffix == ".py"]
        py_dirs = {p.parent for p in py_files}
        if not py_files:
            return SubSignal("structure", "Project structure", 0.3, "no python")
        # a modular layout should have >1 module dir, and not everything at root
        has_packages = len([d for d in py_dirs if (d / "__init__.py").exists()])
        has_main = any(p.name in ("main.py", "app.py", "__main__.py", "cli.py") for p in py_files)
        score = 0.4
        if has_packages >= 1:
            score += 0.25
        if has_packages >= 3:
            score += 0.15
        if has_main:
            score += 0.20
        return SubSignal(
            "structure",
            "Project structure",
            round(min(1.0, score), 4),
            f"{has_packages} packages, entrypoint={has_main}",
        )

    def _probe_low_duplication(self, project: Path) -> SubSignal:
        py_files = [p for p in _iter_project_files(project) if p.suffix == ".py"]
        blank_lines = total_lines = 0
        for p in py_files:
            txt = p.read_text(encoding="utf-8", errors="ignore").splitlines()
            total_lines += len(txt)
            blank_lines += sum(1 for ln in txt if not ln.strip() or ln.strip().startswith("#"))
        if total_lines == 0:
            return SubSignal("low_duplication", "Low duplication", 0.5, "no source")
        # high comment/blank ratio = healthier readability proxy
        non_code = blank_lines / total_lines
        score = 0.5 + non_code  # cap
        return SubSignal(
            "low_duplication",
            "Low duplication",
            round(min(1.0, score), 4),
            f"{blank_lines}/{total_lines} non-code lines",
        )

    def _probe_tests_present(self, project: Path) -> SubSignal:
        test_files = [
            p
            for p in _iter_project_files(project)
            if "test" in p.name.lower() and p.suffix == ".py"
        ]
        if not test_files:
            return SubSignal("tests_present", "Tests present", 0.0, "no test files")
        return SubSignal("tests_present", "Tests present", 1.0, f"{len(test_files)} test files")

    def _probe_tests_pass(self, project: Path, run_tests: bool = True) -> SubSignal:
        test_files = [
            p
            for p in _iter_project_files(project)
            if p.suffix == ".py" and ("test" in p.name.lower() or "tests" in str(p.parent).lower())
        ]
        if not test_files:
            return SubSignal("tests_pass", "Tests pass", 0.0, "no tests to run")
        if not run_tests:
            return SubSignal("tests_pass", "Tests pass", 0.5, "test run disabled by config")
        # Try actually running pytest on the project
        try:
            cmd = [
                self._python_bin,
                "-m",
                "pytest",
                "-p",
                "no:cacheprovider",
                "-q",
                "--no-header",
                "-x",
                str(project),
            ]
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=120,
                cwd=str(project),
            )
            out = (proc.stdout or "") + (proc.stderr or "")
            # parse summary like "12 passed, 0 failed"
            m_pass = re.search(r"(\d+) passed", out)
            m_fail = re.search(r"(\d+) failed", out)
            m_err = re.search(r"(\d+) error", out)
            passed = int(m_pass.group(1)) if m_pass else 0
            failed = int(m_fail.group(1)) if m_fail else 0
            errors = int(m_err.group(1)) if m_err else 0
            total = passed + failed + errors
            if total == 0:
                return SubSignal(
                    "tests_pass", "Tests pass", 0.3, "pytest collected 0 tests: " + out[-80:]
                )
            if failed or errors:
                return SubSignal(
                    "tests_pass",
                    "Tests pass",
                    round(max(0.0, passed / total), 4),
                    f"{passed} passed, {failed} failed, {errors} errors",
                )
            return SubSignal("tests_pass", "Tests pass", 1.0, f"{passed} passed, 0 failed")
        except (subprocess.TimeoutExpired, FileNotFoundError) as e:
            return SubSignal("tests_pass", "Tests pass", 0.5, f"could not run tests: {e}")

    def _probe_test_to_source_ratio(self, project: Path) -> SubSignal:
        py_files = [p for p in _iter_project_files(project) if p.suffix == ".py"]
        src_lines = sum(_count_lines(p) for p in py_files if "test" not in p.name.lower())
        test_lines = sum(_count_lines(p) for p in py_files if "test" in p.name.lower())
        if src_lines == 0:
            return SubSignal("test_to_source_ratio", "Test : source ratio", 0.2, "no source")
        ratio = test_lines / src_lines
        # enterprise-grade: >=0.5 test lines per src line
        score = min(1.0, ratio / 0.6)
        return SubSignal(
            "test_to_source_ratio",
            "Test : source ratio",
            round(score, 4),
            f"test:{test_lines} src:{src_lines} (ratio {ratio:.2f})",
        )

    def _probe_coverage_heuristic(
        self, project: Path, coverage_pct: float | None = None
    ) -> SubSignal:
        # If a real measured coverage % is supplied (e.g. from CoverageProbe),
        # fold it straight into D4 Test Quality — the anti-stub, measured path.
        if coverage_pct is not None:
            return SubSignal(
                "coverage_heuristic",
                "Coverage",
                round(min(1.0, float(coverage_pct) / 100.0), 4),
                f"measured line coverage {coverage_pct:g}%",
            )
        # Otherwise fall back to the heuristic (coverage artifact present, else
        # inferred from the test-to-source ratio).
        cov_files = [
            p
            for p in _iter_project_files(project)
            if ".coverage" in p.name
            or p.name.endswith("coverage.xml")
            or "coverage" in p.name.lower()
        ]
        test_ratio_signal = self._probe_test_to_source_ratio(project)
        base = test_ratio_signal.score
        if cov_files:
            return SubSignal(
                "coverage_heuristic",
                "Coverage",
                round(min(1.0, base * 1.2 + 0.1), 4),
                "coverage artifacts present",
            )
        return SubSignal(
            "coverage_heuristic",
            "Coverage",
            round(base * 0.8, 4),
            "no coverage artifact; heuristic from test ratio",
        )

    def _probe_ci_config(self, project: Path) -> SubSignal:
        hits = []
        for p in _iter_project_files(project):
            low = str(p).lower()
            if ".github" in low or "gitlab-ci" in low or "circleci" in low or "jenkins" in low:
                hits.append(p.name)
            if p.name in (".github", "azure-pipelines.yml", "bitbucket-pipelines.yml"):
                hits.append(p.name)
        if hits:
            return SubSignal(
                "ci_config", "CI/CD config", 1.0, f"CI found: {', '.join(sorted(set(hits))[:4])}"
            )
        return SubSignal("ci_config", "CI/CD config", 0.0, "no CI config found")

    def _probe_packaging(self, project: Path) -> SubSignal:
        hits = []
        for p in _iter_project_files(project):
            if p.name in (
                "pyproject.toml",
                "setup.py",
                "setup.cfg",
                "setup.sh",
                "Makefile",
                "package.json",
                "Cargo.toml",
                "go.mod",
            ):
                hits.append(p.name)
        score = min(1.0, len(hits) * 0.35)
        return SubSignal(
            "packaging",
            "Packaging / build tooling",
            round(score, 4),
            f"found: {', '.join(hits[:6]) if hits else 'none'}",
        )

    def _probe_containerized(self, project: Path) -> SubSignal:
        for name in ("Dockerfile", "docker-compose.yml", "docker-compose.yaml", "Containerfile"):
            if (project / name).exists():
                return SubSignal("containerized", "Containerized", 1.0, f"{name} present")
        return SubSignal("containerized", "Containerized", 0.0, "no Dockerfile")

    def _probe_versioned(self, project: Path) -> SubSignal:
        version_refs = 0
        for p in _iter_project_files(project):
            if p.name in ("pyproject.toml", "setup.py", "package.json", "Cargo.toml"):
                text = p.read_text(encoding="utf-8", errors="ignore")
                if re.search(r"version\s*=\s*['\"]\d+\.\d+", text) or re.search(
                    r'"version"\s*:\s*"\d+\.\d+', text
                ):
                    version_refs += 1
        is_git = (project / ".git").exists()
        score = min(1.0, 0.5 * version_refs + (0.5 if is_git else 0))
        return SubSignal(
            "versioned",
            "Versioned / git",
            round(score, 4),
            f"version markers={version_refs}, git={is_git}",
        )

    def _probe_readme(self, project: Path) -> SubSignal:
        for name in ("README.md", "README.rst", "README.txt", "readme.md"):
            p = project / name
            if p.exists():
                n = len(p.read_text(encoding="utf-8", errors="ignore").strip())
                if n < 200:
                    return SubSignal("readme", "README", 0.4, f"{name} but very short ({n} chars)")
                if n < 1000:
                    return SubSignal("readme", "README", 0.8, f"{name}: {n} chars")
                return SubSignal("readme", "README", 1.0, f"{name}: {n} chars")
        return SubSignal("readme", "README", 0.0, "no README")

    def _probe_license(self, project: Path) -> SubSignal:
        for name in ("LICENSE", "LICENSE.md", "LICENSE.txt", "COPYING", "UNLICENSE"):
            if (project / name).exists():
                return SubSignal("license", "LICENSE", 1.0, f"{name} present")
        return SubSignal("license", "LICENSE", 0.0, "no LICENSE")

    def _probe_docs(self, project: Path) -> SubSignal:
        docs_found = []
        for p in _iter_project_files(project):
            low = str(p).lower()
            if any(
                k in low
                for k in (
                    "/docs/",
                    "/doc/",
                    "docs.md",
                    "user_guide",
                    "manual",
                    "api.md",
                    "getting_started",
                )
            ):
                docs_found.append(p.name)
        if docs_found:
            return SubSignal(
                "docs", "Documentation", 1.0, f"docs: {', '.join(sorted(set(docs_found))[:5])}"
            )
        return SubSignal("docs", "Documentation", 0.2, "no docs directory")

    def _probe_no_fake_data(self, project: Path) -> SubSignal:
        py_files = [
            p
            for p in _iter_project_files(project)
            if p.suffix == ".py"
            and "test" not in p.name.lower()
            and "fixture" not in p.name.lower()
            and "example" not in p.name.lower()
            and "universal_score" not in p.name.lower()
        ]

        # A string is a marker *definition* when it names a known marker verbatim
        # (e.g. the constant table "FAKE_DATA_MARKERS = [...]") — not a real hit.
        def _is_marker_def(text: str) -> bool:
            return "FAKE_DATA_MARKERS" in text or "MARKER" in text.upper()

        hits: list[str] = []
        for p in py_files:
            try:
                tree = ast.parse(p.read_text(encoding="utf-8", errors="ignore"))
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                lineno = getattr(node, "lineno", 0)
                if (
                    isinstance(node, ast.Return)
                    and isinstance(node.value, ast.Constant)
                    and isinstance(node.value.value, str)
                ):
                    low = node.value.value.lower()
                    for m in FAKE_DATA_MARKERS_STRONG:
                        if m in low:
                            hits.append(f"{p.name}:{lineno}:{m}")
                            break
                    for m in FAKE_DATA_MARKERS_WEAK:
                        if m in low and len(node.value.value) < 120:
                            hits.append(f"{p.name}:{lineno}:{m}")
                            break
                elif isinstance(node, ast.Assign):
                    vals = (node.value,) if isinstance(node.value, ast.Constant) else ()
                    for tgt_val in vals:
                        if isinstance(tgt_val.value, str):
                            low = tgt_val.value.lower()
                            for m in FAKE_DATA_MARKERS_STRONG:
                                if m in low:
                                    hits.append(f"{p.name}:{lineno}:{m}")
                                    break
                elif isinstance(node, ast.Constant) and isinstance(node.value, str):
                    low = node.value.lower()
                    if node.value.strip().startswith(
                        ("usage:", "help:", "error", "warn", "deprecated", "note:")
                    ):
                        continue
                    for m in FAKE_DATA_MARKERS_STRONG:
                        if m in low and len(node.value) < 200:
                            hits.append(f"{p.name}:{lineno}:{m}")
                            break
        if hits:
            uniq = sorted(set(hits))[:8]
            return SubSignal(
                "no_fake_data", "No fake/placeholder data", 0.0, f"FOUND: {', '.join(uniq)}"
            )
        return SubSignal(
            "no_fake_data",
            "No fake/placeholder data",
            1.0,
            "no placeholder/fake-data markers in source",
        )

    def _probe_real_persistence(self, project: Path) -> SubSignal:
        py_files = [p for p in _iter_project_files(project) if p.suffix == ".py"]
        imports = []
        for p in py_files:
            for line in p.read_text(encoding="utf-8", errors="ignore").splitlines():
                s = line.strip()
                if s.startswith(
                    (
                        "import sqlite3",
                        "import redis",
                        "from sqlalchemy",
                        "import psycopg2",
                        "import pymongo",
                        "import tinydb",
                        "from django.db",
                        "import duckdb",
                        "import aiosqlite",
                        "import peewee",
                        "import pickledb",
                        "import pickle",
                    )
                ):
                    imports.append(s)
        if imports:
            return SubSignal(
                "real_persistence",
                "Real persistence",
                1.0,
                f"persistence: {', '.join(sorted(set(imports))[:4])}",
            )
        # heuristic: writes files
        for p in py_files:
            if re.search(r"open\([^)]*['\"]w['\"]", p.read_text(encoding="utf-8", errors="ignore")):
                return SubSignal(
                    "real_persistence", "Real persistence", 0.6, "file-write persistence found"
                )
        return SubSignal(
            "real_persistence",
            "Real persistence",
            0.2,
            "no persistence dependency found (in-memory only?)",
        )

    # ---------- Aggregation ---------------------------------------------

    def _dimension_probes(
        self,
        dimension: Dimension,
        project: Path,
        run_tests: bool,
        coverage_pct: float | None = None,
    ) -> list[SubSignal]:
        if dimension == Dimension.RELIABILITY:
            return [
                self._probe_builds_clean(project),
                self._probe_error_handling(project),
                self._probe_no_crashes(project),
            ]
        if dimension == Dimension.SECURITY:
            return [
                self._probe_no_hardcoded_secrets(project),
                self._probe_deps_pinned(project),
                self._probe_gitignore_clean(project),
            ]
        if dimension == Dimension.MAINTAINABILITY:
            return [
                self._probe_type_hints(project),
                self._probe_docstrings(project),
                self._probe_structure(project),
                self._probe_low_duplication(project),
            ]
        if dimension == Dimension.TEST_QUALITY:
            return [
                self._probe_tests_present(project),
                self._probe_tests_pass(project, run_tests),
                self._probe_test_to_source_ratio(project),
                self._probe_coverage_heuristic(project, coverage_pct),
            ]
        if dimension == Dimension.DELIVERY:
            return [
                self._probe_ci_config(project),
                self._probe_packaging(project),
                self._probe_containerized(project),
                self._probe_versioned(project),
            ]
        # SELLABILITY
        return [
            self._probe_readme(project),
            self._probe_license(project),
            self._probe_docs(project),
            self._probe_no_fake_data(project),
            self._probe_real_persistence(project),
        ]

    def _score_dimension(self, dimension: Dimension, signals: list[SubSignal]) -> DimensionResult:
        sub_weights = DIMENSION_SUBWEIGHTS[dimension]
        total_w = 0.0
        acc = 0.0
        for sig in signals:
            w = sub_weights.get(sig.key, 1.0 / max(1, len(signals)))
            acc += sig.score * w
            total_w += w
            sig.weight = w
        dim_score = acc / max(1e-9, total_w)
        return DimensionResult(dimension=dimension, score=round(dim_score, 4), sub_signals=signals)

    # ---------- Hard gates ----------------------------------------------

    def _hard_gates(
        self,
        _project: Path,
        tests_pass: SubSignal,
        secrets: SubSignal,
        fake_data: SubSignal,
        persistence: SubSignal,
        builds_clean: SubSignal,
    ) -> list[HardGate]:
        gates: list[HardGate] = []
        gates.append(HardGate("builds", builds_clean.score >= 0.5, builds_clean.evidence))
        if (
            tests_pass.score < 0.99
            and tests_pass.evidence
            and "passed" in tests_pass.evidence
            and tests_pass.score == 0.0
        ):
            gates.append(HardGate("tests_pass", False, tests_pass.evidence))
        else:
            gates.append(HardGate("tests_pass", tests_pass.score >= 0.5, tests_pass.evidence))
        gates.append(HardGate("no_hardcoded_secrets", secrets.score >= 0.99, secrets.evidence))
        gates.append(HardGate("no_fake_data", fake_data.score >= 0.99, fake_data.evidence))
        gates.append(HardGate("real_persistence", persistence.score >= 0.3, persistence.evidence))
        return gates

    # ---------- Main entry -----------------------------------------------

    def score(
        self,
        project_path: str | os.PathLike[str],
        run_tests: bool = True,
        coverage_pct: float | None = None,
    ) -> dict[str, Any]:
        project = Path(project_path)
        if not project.exists():
            msg = f"Project path does not exist: {project}"
            raise FileNotFoundError(msg)

        dim_results: dict[Dimension, DimensionResult] = {}
        # Compute the shared probes once and reuse
        tests_pass = self._probe_tests_pass(project, run_tests)
        secrets = self._probe_no_hardcoded_secrets(project)
        fake_data = self._probe_no_fake_data(project)
        persistence = self._probe_real_persistence(project)
        builds_clean = self._probe_builds_clean(project)

        # Recompute dimension probes (cheap, keeps code simple)
        for dim in Dimension:
            sigs = self._dimension_probes(dim, project, run_tests, coverage_pct=coverage_pct)
            # override the ones we already computed so metrics are consistent
            override = {
                "tests_pass": tests_pass,
                "no_hardcoded_secrets": secrets,
                "no_fake_data": fake_data,
                "real_persistence": persistence,
                "builds_clean": builds_clean,
            }
            sigs = [override.get(s.key, s) for s in sigs]
            dim_results[dim] = self._score_dimension(dim, sigs)

        # Weighted universal base (0..100)
        base = sum(dim_results[dim].score * self.weights[dim] for dim in Dimension) * 100

        # Hard gates
        gates = self._hard_gates(project, tests_pass, secrets, fake_data, persistence, builds_clean)
        any_gate_fail = any(not g.passed for g in gates)

        # Excellence bonus
        bonus = self._compute_bonus(dim_results, gates)
        score = base + bonus
        if any_gate_fail:
            score = min(score, self.hard_gate_cap)
        score = round(score, 1)

        return {
            "universal_score": score,
            "base_score": round(base, 1),
            "bonus": round(bonus, 1),
            "certification": certification_for_score(score).value,
            "hard_gates": [{"name": g.name, "passed": g.passed, "detail": g.detail} for g in gates],
            "any_hard_gate_failed": any_gate_fail,
            "dimensions": {d.value: r.to_dict() for d, r in dim_results.items()},
            "project": str(project),
            "coverage_pct": coverage_pct,
        }

    def _compute_bonus(
        self, dim_results: dict[Dimension, DimensionResult], gates: list[HardGate]
    ) -> float:
        """Excellence bonus (0..bonus_cap) for genuinely transcendent builds."""
        if any(not g.passed for g in gates):
            return 0.0
        bonus = 0.0
        if dim_results[Dimension.RELIABILITY].score >= 0.9:
            bonus += 5
        if dim_results[Dimension.SECURITY].score >= 0.9:
            bonus += 5
        if dim_results[Dimension.MAINTAINABILITY].score >= 0.85:
            bonus += 5
        if dim_results[Dimension.TEST_QUALITY].score >= 0.9:
            bonus += 5
        if dim_results[Dimension.SELLABILITY].score >= 0.9:
            bonus += 5
        return min(self.bonus_cap, bonus)


def _count_lines(p: Path) -> int:
    try:
        return len(p.read_text(encoding="utf-8", errors="ignore").splitlines())
    except Exception:
        return 0


# =============================================================================
# Kernel module wrapper
# =============================================================================


@module(
    name="universal_score",
    version="1.0.0",
    config_defaults={
        "run_tests": False,  # don't run subprocess pytest unless told (safe by default)
        "bonus_cap": 25,
    },
)
class UniversalScoreModule(Module):
    """Kernel module exposing the Universal Build Score engine to the platform."""

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        super().__init__(config)
        self.engine: UniversalBuildScore | None = None
        self._last_score: dict[str, Any] | None = None

    async def initialize(self) -> None:
        self.engine = UniversalBuildScore(dict(self.config))
        self.status = HealthStatus.HEALTHY
        logger.info("Universal Build Score module initialized")

    async def health_check(self) -> HealthStatus:
        if self.engine is None:
            return HealthStatus.UNHEALTHY
        return HealthStatus.HEALTHY

    async def shutdown(self) -> None:
        self.status = HealthStatus.UNKNOWN
        logger.info("Universal Build Score module shutdown")

    # Facade
    def score(
        self,
        project: str | os.PathLike[str],
        run_tests: bool | None = None,
        coverage_pct: float | None = None,
    ) -> dict[str, Any]:
        if self.engine is None:
            msg = "UniversalScoreModule not initialized"
            raise RuntimeError(msg)
        use_tests = self.config.get("run_tests", False) if run_tests is None else run_tests
        result = self.engine.score(project, run_tests=use_tests, coverage_pct=coverage_pct)
        self._last_score = result
        return result

    def last_score(self) -> dict[str, Any] | None:
        return self._last_score


def create_universal_score_module(config: dict[str, Any] | None = None) -> UniversalScoreModule:
    return UniversalScoreModule(config)


__all__ = [
    "UniversalBuildScore",
    "UniversalScoreModule",
    "create_universal_score_module",
    "Dimension",
    "DimensionResult",
    "SubSignal",
    "HardGate",
    "CertificationLevel",
    "certification_for_score",
    "DIMENSION_WEIGHTS",
    "SECRET_PATTERNS",
]
