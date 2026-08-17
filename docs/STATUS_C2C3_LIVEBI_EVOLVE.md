# STATUS — C2 Live BI + C3 Outcome-Based Evolution

Date: 2026-08-16
Scope: enterprise/ — C2 (live business intelligence) and C3 (outcome-based evolution)
Status: COMPLETE — all tests green

## What shipped

### C2 — scripts/live_bi.py (NEW)
A CLI that reads real telemetry and prints a one-page business snapshot:
  - Build sessions   : counted from subdirectories of data/build_sessions/ named session_*
  - Artifacts        : counted as files inside each session folder (manifest.json excluded, it is metadata)
  - Est tokens/cost  : read from data/cost_meter.json when present ({tokens, cost});
                        otherwise, if artifacts exist, an estimate is shown using a
                        configurable --rate (tokens/artifact) and --cost-per-1k.
No fabrication: when data is missing/empty, metric prints 0 (or an estimate clearly
labelled "estimated") and a Notes: line explains what was missing.

Live run (real telemetry): 12 sessions, 72 artifacts, est. 57,600 tokens / $0.5760 (estimated,
no cost_meter.json present).

### C3 — scripts/evolve.py (NEW)
An outcome-based evolution CLI that:
  - discovers skills from a directory (default: skills_pack/skills, fallback modules/skill_factory)
  - reads a simple success-log JSON we define (list of {skill, success, fail})
  - ranks skills by success rate (descending) and marks each promote (rate >= --threshold, default 0.7)
    or regress; skills with no outcome data are shown as no-data and are never promoted/regressed.
  - prints a ranking table, emits a one-line recommendation, and appends a timestamped
    recommendation line to a log (default data/evolution_recommendations.log).

## Tests (NEW, scripts/tests/)
  - test_live_bi.py — proves live_bi counts sessions/artifacts from a temp telemetry dir, and
    does NOT crash on empty/missing data (reports zeros + a note); also verifies the real
    cost_meter.json path is honored.
  - test_evolve.py  — proves evolve ranks by rate, marks promote/regress against the threshold,
    leaves no-data skills untouched, and appends the recommendation line.

Run:  python3 -m pytest scripts/tests/test_live_bi.py scripts/tests/test_evolve.py
Result: 6 passed in ~0.03s

## Files created
  - enterprise/scripts/live_bi.py
  - enterprise/scripts/evolve.py
  - enterprise/scripts/tests/test_live_bi.py
  - enterprise/scripts/tests/test_evolve.py
  - enterprise/STATUS (this file)

## Constraints honored
  - Did not edit licensing/, cost_meter/, icm/, multiplayer/, or sidebyside.html.
  - Did not modify modules/skill_factory existing code/tests (evolution exists there already;
    this C3 CLI is a standalone outcome-evolution wrapper that could call into it).
  - All tests use temp dirs; no repo/real data was modified.
