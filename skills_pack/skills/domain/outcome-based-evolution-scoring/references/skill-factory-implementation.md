# skill_factory evolution.py — canonical implementation (2026)

Concrete, verified-green implementation of the outcome-based evolution pattern
in `enterprise/modules/skill_factory/evolution.py`. All 90 module tests passed
(72 pre-existing + 18 new). stdlib only: `sqlite3` / `math` / `datetime`.

## Scoring constants (tuned, deterministic, documented)

```
PRIOR_STRENGTH      = 4.0     success shrink: (s+0.5*p)/(n+p)
CONFIDENCE_PRIOR    = 5.0     confidence = n/(n+p)
LATENCY_NORM        = 5.0     latency_score = 1/(1+avg_lat/5)   # seconds
ITER_NORM           = 5.0     iter_score    = 1/(1+avg_iter/5)
RECENCY_HALF_LIFE   = 7*86400 # seconds; recency = exp(-age/half_life)
W_SUCCESS=0.40 W_FEEDBACK=0.25 W_EFFICIENCY=0.20 W_RECENCY=0.15  # sum=1
DEFAULT_PROMOTE_THRESHOLD = 35.0   # weight < this => promote for refinement
```

Weight = `(Σ w_i*comp_i) * confidence * 100`, rounded 2dp. Confidence grows
`1-e`-style effectively via `n/(n+5)`: n=1→0.167, n=20→0.8.

## SQLite schema

```sql
CREATE TABLE outcomes (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  skill TEXT NOT NULL, result TEXT NOT NULL,
  score REAL NOT NULL DEFAULT 0.0, latency REAL NOT NULL DEFAULT 0.0,
  iterations INTEGER NOT NULL DEFAULT 1, feedback INTEGER,
  timestamp TEXT NOT NULL
);
CREATE INDEX idx_outcomes_skill ON outcomes(skill);
```

`record_outcome` normalises result (`success|true|1|pass|succeeded` →
"success", else "fail") and clamps feedback to [0,10] (None = absent → neutral
0.5 in scoring). `all_skills()` = `SELECT DISTINCT skill`.

## Public surface (exported from `skill_factory/__init__.py`)

`SkillFeedbackStore`, `SkillScore`, `EvolutionEngine`, `compute_evolution_score`,
`RESULT_SUCCESS`, `RESULT_FAIL`, `DEFAULT_PROMOTE_THRESHOLD`. `SkillScore` =
weights config + `compute(skill, outcomes, now=None) -> dict` including the
`weight`. `SkillScore(weights...)` normalises weights by their total and raises
if total ≤ 0.

## Repo / test environment gotchas (this enterprise repo)

- The `enterprise` package is NOT importable from repo cwd. Tests bootstrap it:
  `sys.path.insert(0, str(Path(__file__).resolve().parents[4]))` — parents[0]=
  tests dir, [1]=module dir, [2]=modules, [3]=repo root (`enterprise`),
  [4]=parent that makes `enterprise` resolve.
- Run with `python3 -m pytest modules/skill_factory -q -p no:cacheprovider`.
- **ENI read-side compression:** `read_file`/big `grep` on this repo's source
  returns a `<ENI-COMPRESSED ... carrier=...png>` head/tail stub, not full
  content. Read in ≤~55-line chunks (`read_file(offset, limit)`) or `grep -n
  "def |class "` for signatures. NEVER overwrite a file you only saw
  compressed — re-read small first, use `patch` with anchored strings.

## Deterministic test recipe

- Fixed reference: `_NOW_EPOCH = datetime.fromisoformat(_T).timestamp()` with
  `_T="2026-08-04T00:00:00+00:00"`. Seed with `_ts(day)` =
  `f"2026-08-{day:02d}T00:00:00+00:00"`.
- Pass `now=_NOW_EPOCH` to `score.compute` / `update_score` / `rank_skills` /
  `identify_top/bottom` / `promote` / `refresh` so recency is fixed.
- Line-up test seeds: "good" = 20×success fb10 lat0 it1; "bad" = 12×fail fb0
  lat8 it8; "mid" = 15×(10 success/5 fail) fb5. Ordering good > mid > bad.

## Verification invariant worth keeping

`steady(20 successes, 100%)` ≈ 76.0 vs `lucky(1 success, 100%)` ≈ 13.7 →
identical raw success but >3x weight gap because confidence + shrink prevent
over-weighting. Assert `steady["weight"] > lucky["weight"] * 3`.
