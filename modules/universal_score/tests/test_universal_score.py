"""Tests for the ENI Universal Build Score engine.

Verifies the one-number build-quality scorer genuinely discriminates between
good, sellable builds and weak/fake builds, across all six weighted dimensions,
hard gates, and the excellence bonus (allowing >100).
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import pytest

from enterprise.modules.universal_score.universal_score import (
    CertificationLevel,
    Dimension,
    UniversalBuildScore,
    UniversalScoreModule,
    certification_for_score,
    create_universal_score_module,
)


# ---------------------------------------------------------------------------
# Fabricated project trees
# ---------------------------------------------------------------------------


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


GOOD_CODE = '''
class Service:
    """A well-typed, documented service with persistence."""

    def __init__(self, db_path: str = "data.db") -> None:
        self._db_path = db_path

    def connect(self) -> None:
        """Connect to sqlite storage."""
        import sqlite3
        try:
            self._conn = sqlite3.connect(self._db_path)
        except Exception as exc:
            raise RuntimeError(f"connect failed: {exc}") from exc
        return None

    def get(self, key: str) -> Optional[str]:
        """Retrieve a value by key, or None."""
        if self._conn is not None:
            cur = self._conn.execute("SELECT v FROM kv WHERE k = ?", (key,))
            row = cur.fetchone()
            if row is not None and len(row) > 0:
                return str(row[0])
        return None
'''


def make_good_project(root: Path) -> Path:
    """A fully sellable-looking project."""
    proj = root / "goodproj"
    _write(proj / "app" / "__init__.py", "")
    _write(proj / "app" / "service.py", GOOD_CODE)
    _write(proj / "app" / "main.py", "def main() -> int:\n    return 0\n")
    _write(proj / "tests" / "test_service.py",
           "import pytest\n\ndef test_connect() -> None:\n    assert 1 == 1\n"
           "def test_get() -> None:\n    assert True\n")
    _write(proj / "README.md",
           "# GoodProj\n\nA real sellable project with real persistence, "
           "tests, docs, and security hygiene.\n\n" + "docs " * 40)
    _write(proj / "LICENSE", "MIT License\n" + "terms " * 50)
    _write(proj / ".gitignore", ".env\n__pycache__\nnode_modules\n*.log\n")
    _write(proj / "requirements.txt", "sqlite3==0.1.0\npytest==8.0.0\n")
    _write(proj / ".github" / "workflows" / "ci.yml", "name: CI\non: [push]\n")
    _write(proj / "pyproject.toml", '[tool.poetry]\nname = "goodproj"\nversion = "1.2.3"\n')
    _write(proj / "docs" / "user_guide.md", "# User Guide\n\nstep 1\nstep 2\n")
    _write(proj / "Dockerfile", "FROM python:3.11\n")
    _write(proj / "Makefile", "test:\n\tpytest\n")
    (proj / ".git").mkdir(exist_ok=True)
    return proj


def make_bad_project(root: Path) -> Path:
    """A fake, non-sellable project: no tests, hardcoded secrets, no README,
    fake data, no persistence."""
    proj = root / "badproj"
    _write(proj / "main.py",
           "AKIAIOSFODNN7EXAMPLE\n"
           "password = 'supersecret123'\n"
           "def main():\n    return 'lorem ipsum placeholder stub'\n")
    # main.py has a syntax error to also fail the builds_clean gate
    _write(proj / "broken.py", "def oops(:\n    pass\n")
    _write(proj / "requirements.txt", "flask\n")  # unpinned
    return proj


def make_medium_project(root: Path) -> Path:
    """Decent but missing polish: tests pass, some docs, no secrets, but no
    license, no CI, no packaging, in-memory only."""
    proj = root / "medproj"
    _write(proj / "core.py",
           "class Core:\n    def __init__(self):\n        self._data = {}\n"
           "    def put(self, k, v):\n        self._data[k] = v\n"
           "    def get(self, k):\n        if k in self._data:\n            return self._data[k]\n        return None\n")
    _write(proj / "tests" / "test_core.py",
           "def test_put_get():\n    c = Core()\n    c.put('a', 1)\n    assert c.get('a') == 1\n")
    _write(proj / "README.md", "# MedProj\n\nA decent little project. " + "text " * 30)
    return proj


# ---------------------------------------------------------------------------
# Score separation
# ---------------------------------------------------------------------------


class TestUniversalScoreDiscrimination:
    def test_good_project_scores_enterprise(self, tmp_path):
        s = UniversalBuildScore()
        result = s.score(make_good_project(tmp_path), run_tests=False)
        assert result["universal_score"] >= 80, result
        assert result["certification"] in ("Enterprise_Ready", "Beyond_Enterprise",
                                           "Transcendent", "Singularity",
                                           "Production_Candidate")
        assert not result["any_hard_gate_failed"]

    def test_bad_project_scores_low_and_fails_gates(self, tmp_path):
        s = UniversalBuildScore()
        result = s.score(make_bad_project(tmp_path), run_tests=False)
        assert result["any_hard_gate_failed"] is True, result
        assert result["universal_score"] <= 40, result  # hard-gate cap
        assert result["certification"] in ("Not_Ready", "Prototype", "Internal_Dev")

    def test_good_beats_bad_clearly(self, tmp_path):
        s = UniversalBuildScore()
        good = s.score(make_good_project(tmp_path), run_tests=False)["universal_score"]
        bad = s.score(make_bad_project(tmp_path), run_tests=False)["universal_score"]
        assert good >= bad + 40, (good, bad)

    def test_medium_is_between(self, tmp_path):
        s = UniversalBuildScore()
        good = s.score(make_good_project(tmp_path), run_tests=False)["universal_score"]
        med = s.score(make_medium_project(tmp_path), run_tests=False)["universal_score"]
        bad = s.score(make_bad_project(tmp_path), run_tests=False)["universal_score"]
        assert bad < med < good, (bad, med, good)


# ---------------------------------------------------------------------------
# Dimension / sub-signal behavior
# ---------------------------------------------------------------------------


class TestDimensionSignals:
    def test_six_dimensions_present(self, tmp_path):
        s = UniversalBuildScore()
        result = s.score(make_good_project(tmp_path), run_tests=False)
        assert set(result["dimensions"].keys()) == {d.value for d in Dimension}

    def test_secrets_probe_flags_bad(self, tmp_path):
        s = UniversalBuildScore()
        proj = make_bad_project(tmp_path)
        sig = s._probe_no_hardcoded_secrets(proj)
        assert sig.score == 0.0
        assert "AKIA" in sig.evidence or sig.evidence

    def test_secrets_probe_clean_good(self, tmp_path):
        s = UniversalBuildScore()
        sig = s._probe_no_hardcoded_secrets(make_good_project(tmp_path))
        assert sig.score == pytest.approx(1.0)

    def test_fake_data_probe_flags(self, tmp_path):
        s = UniversalBuildScore()
        proj = make_bad_project(tmp_path)
        # The bad project has placeholder/lorem markers
        sig = s._probe_no_fake_data(proj)
        assert sig.score == 0.0

    def test_readme_probe(self, tmp_path):
        s = UniversalBuildScore()
        assert s._probe_readme(make_good_project(tmp_path)).score >= 0.8
        assert s._probe_readme(make_bad_project(tmp_path)).score == 0.0

    def test_persistence_probe(self, tmp_path):
        s = UniversalBuildScore()
        assert s._probe_real_persistence(make_good_project(tmp_path)).score >= 0.6
        assert s._probe_real_persistence(make_bad_project(tmp_path)).score < 0.5

    def test_tests_present(self, tmp_path):
        s = UniversalBuildScore()
        assert s._probe_tests_present(make_good_project(tmp_path)).score == 1.0
        assert s._probe_tests_present(make_bad_project(tmp_path)).score == 0.0


# ---------------------------------------------------------------------------
# Hard gates
# ---------------------------------------------------------------------------


class TestHardGates:
    def test_bad_build_capped_by_gate(self, tmp_path):
        s = UniversalBuildScore()
        result = s.score(make_bad_project(tmp_path), run_tests=False)
        names = [g["name"] for g in result["hard_gates"] if not g["passed"]]
        assert any("secret" in n or "fake" in n or "build" in n for n in names), names
        assert result["universal_score"] == pytest.approx(min(
            result["universal_score"], s.hard_gate_cap))

    def test_good_build_no_gate_failures(self, tmp_path):
        s = UniversalBuildScore()
        result = s.score(make_good_project(tmp_path), run_tests=False)
        assert not result["any_hard_gate_failed"]


# ---------------------------------------------------------------------------
# Certification ladder
# ---------------------------------------------------------------------------


class TestCertification:
    def test_ladder_bounds(self):
        assert certification_for_score(125) == CertificationLevel.SINGULARITY
        assert certification_for_score(112) == CertificationLevel.TRANSCENDENT
        assert certification_for_score(106) == CertificationLevel.BEYOND_ENTERPRISE
        assert certification_for_score(100) == CertificationLevel.ENTERPRISE_READY
        assert certification_for_score(90) == CertificationLevel.PRODUCTION_CANDIDATE
        assert certification_for_score(75) == CertificationLevel.INTERNAL_DEV
        assert certification_for_score(55) == CertificationLevel.PROTOTYPE
        assert certification_for_score(20) == CertificationLevel.NOT_READY


# ---------------------------------------------------------------------------
# Module lifecycle
# ---------------------------------------------------------------------------


class TestModule:
    def test_module_lifecycle(self):
        import asyncio
        mod = create_universal_score_module()
        asyncio.run(mod.initialize())
        assert mod.status.value == "healthy"
        # health check
        from enterprise.platform_kernel import HealthStatus
        assert asyncio.run(mod.health_check()) == HealthStatus.HEALTHY
        assert mod.engine is not None

    def test_module_score_facade(self, tmp_path):
        import asyncio
        mod = create_universal_score_module()
        asyncio.run(mod.initialize())
        result = mod.score(make_good_project(tmp_path), run_tests=False)
        assert "universal_score" in result
        assert mod.last_score() is result

    def test_module_score_before_init_raises(self):
        mod = create_universal_score_module()
        with pytest.raises(RuntimeError):
            mod.score("/tmp/nonexistent")

    def test_module_registered_name(self):
        mod = create_universal_score_module()
        assert mod.name == "universal_score"
        assert mod.version == "1.0.0"


# ---------------------------------------------------------------------------
# Bonus capability (>100)
# ---------------------------------------------------------------------------


class TestBonus:
    def test_bonus_can_exceed_100(self):
        from enterprise.modules.universal_score.universal_score import (
            DimensionResult, Dimension, SubSignal, HardGate, UniversalBuildScore)
        s = UniversalBuildScore({"bonus_cap": 25})
        # fabricate near-perfect dimension results
        dim_results = {}
        for dim in Dimension:
            sig = SubSignal(dim.value, dim.value, 0.95, "near perfect")
            dim_results[dim] = DimensionResult(dimension=dim, score=0.95,
                                               sub_signals=[sig])
        bonus = s._compute_bonus(dim_results, [HardGate("g", True)])
        assert bonus == pytest.approx(min(25.0, bonus)) and bonus >= 20
