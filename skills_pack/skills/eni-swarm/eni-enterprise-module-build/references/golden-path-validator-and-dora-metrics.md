# Master-class golden-path validator + DORA delivery metrics (DXScore)

Session: rebuilt the `developer_experience` module's validation layer into a real
golden-path validator + DORA delivery-metrics aggregator + DXScore facade
(baseline 183 green -> 190 green, +25 new tests in `test_validation.py`).
Reusable pattern for any "add a validation / grading / delivery-metrics
subsystem to an OS module" task in this codebase. Stdlib-only.

## 1. Golden-path validator (DX standards checklist)

- **`GoldenCheck` dataclass** with `id` / `description` / `grade` / `weight` /
  `matcher` / `present_files` / `remediation`. `grade` in
  `{essential, recommended, excellent}`; `weight` (>0) drives the compliance
  percentage. In `__post_init__`, coerce a bare string `present_files` into a
  tuple, and clamp non-positive weights to 1.0.
- **`GoldenPath`** = ordered list of checks. Canonical factory
  `GoldenPath.enterprise_dx()` ships the 8 required standards: `has_readme`,
  `has_tests`, `has_ci`, `has_lint_config`, `has_type_hints`, `has_gitignore`,
  `has_license`, `is_versioned`. Each check has TWO verification strategies:
  - a callable `matcher(Path) -> bool` for semantic checks (e.g. `is_versioned`
    scans package.json / pyproject.toml / setup.cfg / any `__version__`),
  - otherwise a `present_files` existence list (any one present = pass).
- **`GoldenPathValidator.validate(project_dir)`** resolves every check against
  the REAL filesystem and returns a `ValidationReport` with:
  - per-check `CheckResult` (check_id, description, grade, passed, weight,
    `evidence` like `"found .flake8"`, remediation),
  - `compliance_percent()` = weighted % = `sum(passed weight)/sum(all weight)`,
  - `letter_grade()` via shared 90/80/70/60 -> A/B/C/D/F,
  - `recommendations()` = remediations of failed checks.
  Always guard `not project_dir.is_dir()` -> all checks fail (never crash on a
  missing path).

## 2. DORA delivery metrics aggregator

- **`DeliveryMetrics`** records `DeployEvent` objects
  (`timestamp / success / lead_time_hours / recovery_minutes / team`) via
  `record_deploy_event`, plus `record_success`/`record_failure` convenience
  wrappers. **Pass `timestamp` through to the wrappers** (an early bug: the
  wrappers dropped it, so tests setting back-dated timestamps got
  `TypeError: unexpected keyword argument 'timestamp'`).
- **Lookback window** (`lookback_days`, default 90) filters events before
  aggregation. Every public accessor recomputes from `_recent_events()`.
- Aggregates the four DORA metrics:
  - `deployment_frequency_per_day()` = `n_events / span_days` (span clamped to a
    small epsilon so it never divides by zero),
  - `lead_time_stats()` = mean / p50 / p95 hours (p95 via linear-interpolated
    percentile on sorted values),
  - `change_failure_rate_percent()` = `failures / n * 100`,
  - `mean_time_to_recovery_minutes()` = mean of `recovery_minutes` over failed
    events only.
- **Band classification** via static methods using canonical DORA thresholds:
  - deploy freq/day: `>=1` elite, `>=1/7` high, `>=1/30` medium, else low,
  - lead time mean hrs: `<1` elite, `<24` high, `<168` medium, else low,
  - CFR%: `<5` elite, `<10` high, `<15` medium, else low,
  - MTTR min: `<60` elite, `<1440` high, `<4320` medium, else low.
  `bands()` returns per-metric band; `overall_band()` averages the band scores.
- **Empty-state correctness:** `bands()` MUST return all-`low` when there are no
  recent events. A naive version returned `elite` for lead-time/CFR/MTTR because
  their aggregate defaults (0.0) fell in the elite range — wrong for "no data".

## 3. DXScore facade (combined 0-100)

Combine two axes into one number: 60% golden-path compliance + 40% DORA delivery.
`delivery_score()` maps the average band index to 0-100 (`100 - avg/3*100`).
`score(project_dir)` returns dict with `compliance_percent`, `compliance_grade`,
`delivery_score`, `delivery_band`, `dx_score`, `dx_grade`, `recommendations`.

## 4. Name-collision handling when extending a module's __init__ exports

`golden_paths.py` ALREADY exported a class named `GoldenPath`. Adding a checklist
class also named `GoldenPath` in `validation.py` is fine at module scope, but in
`__init__.py` you must NOT clobber the existing export. Fix: import it aliased —
`from ...validation import GoldenPath as GoldenPathChecklist` — and add
`GoldenPathChecklist` (not `GoldenPath`) to `__all__`. Then a test asserts BOTH
the preserved `dx.GoldenPath` (from golden_paths) and the new exports exist.

## Pitfalls that bit (and their fixes)

- **`test_validation.py` helper used `**files` kwargs:** keys like `.gitignore`,
  `.github/workflows/ci.yml`, `pyproject.toml` are NOT valid Python identifier
  kwargs — `SyntaxError: expression cannot contain assignment`. Change the helper
  to accept a plain `dict` arg (`make_project(tmp_path, files_dict)`) and pass
  `**{...}` / the dict directly.
- **Fixture reused one directory name** (`tmp_path/"proj"`) across tests. When
  one test wrote `pyproject.toml` and a later test wrote only `README.md` into the
  SAME dir, the stale versioned file leaked in and `_check_versioned` wrongly
  returned True. Use separate subdirs per logical project
  (`tmp_path/"v1"`, `tmp_path/"v2"`).
- **DORA band test math must respect the lookback window AND the event span.**
  `deployment_frequency` = `n / span` where span is between the MIN and MAX event
  timestamp. 2 deploys 30 days apart = medium (2/30 >= 1/30), NOT low. To get a
  genuine `low`, spread the two events >60 days apart AND keep both inside the
  90-day lookback (e.g. success at day -80, failure at day -1). An event placed
  exactly at the lookback boundary (day -90) can fall OUTSIDE the window and
  silently flip the CFR assertion (100% instead of 50%).
- **Empty metrics default to 0.0** which maps to elite for lead-time/CFR/MTTR —
  special-case "no events" to all-low (see section 2).

## Workflow that keeps it green

1. Capture the baseline FIRST: `pytest modules/<mod> -q -p no:cacheprovider`
   before edits.
2. Read the existing `__init__.py` export block and `__all__` to know what names
   are already taken before adding imports.
3. Build the new module, add the test file, then re-run the WHOLE module (not
   just new tests) to prove zero regression.
4. Report real numbers: baseline + new, total passed/failed, and the explicit
   "I did NOT touch <other worker's files>" confirmation (verify via
   `git status --short`).
