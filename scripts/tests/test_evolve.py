"""Minimal tests for the C3 outcome-based evolution CLI.

Verifies that evolve ranks skills by success rate, marks promote/regress
against the threshold, and appends a recommendation line.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
SCRIPTS = REPO / "scripts"

_spec = importlib.util.spec_from_file_location("evolve", SCRIPTS / "evolve.py")
assert _spec and _spec.loader
evolve = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(evolve)


def test_ranks_by_rate_and_marks_promote_regress(tmp_path: Path) -> None:
    skills = tmp_path / "skills"
    for name in ("alpha", "beta", "gamma"):
        (skills / name).mkdir(parents=True)

    log_path = tmp_path / "success_log.json"
    log_path.write_text(
        '[\n'
        '  {"skill": "alpha", "success": 9, "fail": 1},\n'   # 0.9 -> promote
        '  {"skill": "beta",  "success": 2, "fail": 8},\n'    # 0.2 -> regress
        '  {"skill": "gamma", "success": 6, "fail": 4}\n'     # 0.6 -> promote (>=0.6)
        ']',
        encoding="utf-8",
    )

    names = evolve.discover_skills(skills)
    assert set(names) == {"alpha", "beta", "gamma"}

    log = evolve.load_success_log(log_path)
    ranked = evolve.rank_skills(names, log, threshold=0.6)

    by_name = {r["skill"]: r for r in ranked}
    assert by_name["alpha"]["status"] == "promote"
    assert by_name["beta"]["status"] == "regress"
    assert by_name["gamma"]["status"] == "promote"
    # ranking is rate-descending: alpha (0.9) first
    assert ranked[0]["skill"] == "alpha"


def test_no_data_skills_are_not_promoted_or_regressed(tmp_path: Path) -> None:
    skills = tmp_path / "skills"
    (skills / "known").mkdir(parents=True)
    (skills / "unknown").mkdir()

    log_path = tmp_path / "success_log.json"
    log_path.write_text('[{"skill": "known", "success": 8, "fail": 2}]', encoding="utf-8")

    names = evolve.discover_skills(skills)
    log = evolve.load_success_log(log_path)
    ranked = evolve.rank_skills(names, log, threshold=0.7)

    by_name = {r["skill"]: r for r in ranked}
    assert by_name["known"]["status"] == "promote"   # 0.8 >= 0.7
    assert by_name["unknown"]["status"] == "no-data"

    line = evolve.build_recommendation_line(ranked, 0.7)
    assert "recommendation:" in line and "known" in line


def test_appends_recommendation_line(tmp_path: Path) -> None:
    skills = tmp_path / "skills"
    (skills / "alpha").mkdir(parents=True)
    log_path = tmp_path / "success_log.json"
    log_path.write_text('[{"skill": "alpha", "success": 8, "fail": 2}]', encoding="utf-8")

    rec_path = tmp_path / "rec.log"
    names = evolve.discover_skills(skills)
    log = evolve.load_success_log(log_path)
    ranked = evolve.rank_skills(names, log, threshold=0.7)
    line = evolve.build_recommendation_line(ranked, 0.7)

    assert evolve.append_recommendation(line, rec_path) is True
    assert evolve.append_recommendation(line, rec_path) is True  # append twice
    text = rec_path.read_text(encoding="utf-8")
    assert text.count("recommendation:") == 2
