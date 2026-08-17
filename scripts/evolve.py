#!/usr/bin/env python3
"""C3 — Outcome-Based Evolution CLI.

Given a directory of skills (default ``modules/skill_factory`` or
``skills_pack/skills``) and a *success-log* JSON file, this ranks the skills by
their observed success rate and marks each as ``promote`` or ``regress``
against a threshold.  It prints a ranking table and appends a one-line
recommendation to an evolution log.

Success-log format (a JSON list of records):
    [
      {"skill": "git-flow",     "success": 8, "fail": 2},
      {"skill": "rust-tooling", "success": 3, "fail": 6}
    ]
Each record maps a skill name to its observed success/fail counts.  Skills in
the directory with no success-log record are listed as ``no-data`` and are not
promoted or regressed (we never guess an outcome we did not observe).

Decision rule (deterministic):
    success_rate = success / (success + fail)
    promote if success_rate >= threshold (and success + fail > 0)
    regress otherwise

Usage:
    python3 scripts/evolve.py
    python3 scripts/evolve.py --skills-dir skills_pack/skills \
        --success-log data/success_log.json --threshold 0.7

Exit status: 0 on success.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent

DEFAULT_THRESHOLD = 0.7
#: default success-log written/read next to the repo data dir
DEFAULT_SUCCESS_LOG = REPO_ROOT / "data" / "success_log.json"
#: recommendation log (appended)
DEFAULT_RECOMMEND_LOG = REPO_ROOT / "data" / "evolution_recommendations.log"

DEFAULT_SKILLS_DIR = None  # resolved in script: skill_factory or skills_pack/skills


def default_skills_dir() -> Path:
    """Pick the default skills directory: skill_factory fallback layout."""
    skill_factory = REPO_ROOT / "modules" / "skill_factory"
    skills_pack = REPO_ROOT / "skills_pack" / "skills"
    return skills_pack if skills_pack.is_dir() else skill_factory


def discover_skills(skills_dir: Path) -> list[str]:
    """Return the sorted list of skill names under *skills_dir*.

    A skill is a subdirectory.  If *skills_dir* does not exist or is not a
    directory on a readable path, an empty list is returned (caller notes it).
    """
    if skills_dir is None or not skills_dir.exists() or not skills_dir.is_dir():
        return []
    try:
        names = [
            e.name for e in skills_dir.iterdir()
            if e.is_dir() and not e.name.startswith(".")
        ]
    except OSError:
        return []
    return sorted(names)


def load_success_log(path: Path) -> dict[str, dict[str, int]]:
    """Load the success-log JSON and normalise it to ``{skill: {success, fail}}``.

    Missing / unreadable / malformed files yield an empty dict (never crash).
    """
    out: dict[str, dict[str, int]] = {}
    if path is None or not path.exists():
        return out
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return out
    if isinstance(raw, dict):
        raw = [raw]
    if not isinstance(raw, list):
        return out
    for rec in raw:
        if not isinstance(rec, dict):
            continue
        skill = rec.get("skill")
        if not skill:
            continue
        try:
            success = max(0, int(rec.get("success", 0)))
            fail = max(0, int(rec.get("fail", 0)))
        except (TypeError, ValueError):
            continue
        out[str(skill)] = {"success": success, "fail": fail}
    return out


def success_rate(rec: dict[str, int]) -> float:
    """Observed success rate; 0.0 when there is no data."""
    total = rec["success"] + rec["fail"]
    return (rec["success"] / total) if total > 0 else 0.0


def rank_skills(skills: list[str], log: dict[str, dict[str, int]], threshold: float) -> list[dict[str, Any]]:
    """Rank *skills* by success rate and mark promote/regress.

    Only skills present in the success log are ranked (they have real outcome
    data).  Skills with no record are appended with status ``no-data``.
    Returns a list of dicts, highest rate first.
    """
    ranked: list[dict[str, Any]] = []
    no_data: list[dict[str, Any]] = []
    for skill in skills:
        rec = log.get(skill)
        if rec is None:
            no_data.append({"skill": skill, "status": "no-data",
                            "success": 0, "fail": 0, "rate": None})
            continue
        rate = success_rate(rec)
        status = "promote" if rate >= threshold else "regress"
        ranked.append({"skill": skill, "status": status,
                       "success": rec["success"], "fail": rec["fail"],
                       "rate": rate})
    ranked.sort(key=lambda r: r["rate"], reverse=True)
    return ranked + no_data


def render_ranking(ranked: list[dict[str, Any]], threshold: float, skills_dir: Path) -> str:
    """Render the ranking table for *ranked* skills."""
    lines = [
        "Skill Evolution Ranking",
        "-----------------------",
        f"Skills dir : {skills_dir}",
        f"Threshold  : {threshold}  (rate >= threshold => promote)",
        "",
        f"{'SKILL':<24}{'RATE':>7}  {'SUCCESS':>8}{'FAIL':>6}  STATUS",
        "-" * 62,
    ]
    if not ranked:
        lines.append("(no skills discovered / ranked)")
    for r in ranked:
        if r["rate"] is None:
            rate_str = "  n/a"
            lines.append(
                f"{r['skill']:<24}{rate_str:>7}{r['success']:>8}{r['fail']:>6}  "
                f"{r['status']} (no outcome data)"
            )
        else:
            lines.append(
                f"{r['skill']:<24}{r['rate']:>7.3f}{r['success']:>8}{r['fail']:>6}  "
                f"{r['status']}"
            )
    return "\n".join(lines)


def build_recommendation_line(ranked: list[dict[str, Any]], threshold: float) -> str:
    """One-line recommendation based on the ranked outcomes."""
    with_data = [r for r in ranked if r["rate"] is not None]
    if not with_data:
        rec = "recommendation: insufficient outcome data; collect success/fail before evolving."
    else:
        best = max(with_data, key=lambda r: r["rate"])
        worst = min(with_data, key=lambda r: r["rate"])
        promotes = [r for r in with_data if r["status"] == "promote"]
        regresses = [r for r in with_data if r["status"] == "regress"]
        rec = (
            f"recommendation: promote {len(promotes)} skill(s) top '{best['skill']}' "
            f"({best['rate']:.3f}); regress {len(regresses)} skill(s) bottom "
            f"'{worst['skill']}' ({worst['rate']:.3f}); threshold={threshold}."
        )
    return rec


def append_recommendation(line: str, log_path: Path) -> bool:
    """Append a timestamped recommendation line to *log_path*.

    Returns False (without error) if the log path cannot be written.
    """
    if log_path is None:
        return False
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        with log_path.open("a", encoding="utf-8") as fh:
            fh.write(f"{ts} {line}\n")
        return True
    except OSError:
        return False


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="evolve",
        description="C3 outcome-based skill evolution CLI.",
    )
    parser.add_argument("--skills-dir", type=str, default=str(default_skills_dir()),
                        help="directory of skills (default: skill_factory or skills_pack/skills)")
    parser.add_argument("--success-log", type=str, default=str(DEFAULT_SUCCESS_LOG),
                        help="path to success-log JSON (default: data/success_log.json)")
    parser.add_argument("--recommend-log", type=str, default=str(DEFAULT_RECOMMEND_LOG),
                        help="path to append recommendation lines to")
    parser.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD,
                        help=f"success-rate threshold for promote (default: {DEFAULT_THRESHOLD})")
    args = parser.parse_args(argv)

    skills = discover_skills(Path(args.skills_dir))
    log = load_success_log(Path(args.success_log))
    if not skills:
        print("note: no skills discovered (directory missing/empty); ranking empty.")
    if not log:
        print("note: no success-log data; no skill will be promoted or regressed.")
    ranked = rank_skills(skills, log, args.threshold)
    print(render_ranking(ranked, args.threshold, Path(args.skills_dir)))
    line = build_recommendation_line(ranked, args.threshold)
    print("\n" + line)
    append_recommendation(line, Path(args.recommend_log))
    return 0


if __name__ == "__main__":
    sys.exit(main())
