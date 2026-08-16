# Stdlib-only statistical hypothesis testing + experiment registry

Session: upgraded `modules/innovation_rd` to a master-class experiment surface
(baseline 146 green -> 169 green, +23 tests). NO scipy/numpy — pure Python
stdlib (`statistics`, `math`, `sqlite3`, `random`, `json`, `datetime`). Pattern
generalizes to any Enterprise module that needs to A/B-test / score a change
with real statistics and a durable registry.

## Real p-values without scipy (the core trick)

`statistics` has no t-distribution CDF, so compute the two-sided Student-t
p-value by hand:

- **Student-t identity**: two-sided p for statistic t with df is
  `p = I_{df/(df+t^2)}(df/2, 0.5)` where I is the regularized incomplete beta.
- Implement `_log_gamma` via the Lanczos approximation (`math.log` +
  coefficients + reflection formula for x<0.5).
- Implement `_betacf` (Numerical-Recipes continued fraction, capped at ~200
  iters, EPS ~3e-12, FPMIN ~1e-300 for underflow) and `_betainc(a,b,x)` that
  picks the series vs the continued-fraction branch on `x < (a+1)/(a+b+2)`.
- `student_t_two_sided_p(t, df)`: `x = df/(df+t*t)`; `_betainc(df/2, 0.5, x)`.
- **Welch's t-test** (`welch_t_test(before, after)`) returns `(t, df, p)`:
  `t = (m2-m1)/se`, `df` via Welch-Satterthwaite
  `(v1/n1+v2/n2)^2 / ((v1/n1)^2/(n1-1)+(v2/n2)^2/(n2-1))`. Guard degenerate
  cases: both variances 0 or se==0 => `(0, inf, 1.0)`; non-finite df falls back
  to `n1+n2-2`. Note in the docstring that the Welch df correction is itself an
  approximation. (Verify: fully-separated 5v5 sample => p~2e-05 significant;
  overlapping samples => p~0.89 not significant.)

## Deterministic permutation / bootstrap (no scipy)

- `permutation_test(before, after, n=10000, seed=None)`: pool, `random.Random(seed)`,
  shuffle labels, count how often `|permuted mean diff| >= |observed diff|`,
  return `(count+1)/(n+1)` (the `+1` keeps it > 0).
- `bootstrap_p_value(...)`: resample-with-replacement under a centered null.
- **Determinism rule**: use a private `random.Random(seed)` created per call
  (seed passed in), NOT globals — same seed => bit-identical p-value. This is
  what makes the "seed determinism" test pass.
- `assess(before, after, alpha=0.05, fallback_to_bootstrap=False, seed=None)`:
  default prefers Welch; falls back to permutation for tiny inputs
  (`len<2` per group) or when `fallback_to_bootstrap=True`. Return an
  `AssessmentResult(p_value, significant, method, alpha, t_stat, df,
  effect_size)` with a `conclusion()` string. Welch's is "method=welch",
  fallback is "method=permutation" (tests assert the method string).

## SQLite experiment registry lifecycle (no stubs)

Never break the in-memory/default path. Constructor:
`ExperimentRegistry(db_path=None)` -> temp-file DB when None, still fully
functional. Full lifecycle persisted at every step:

`register_experiment(hypothesis, id)` -> `start(id)` (draft->running) ->
`record_metric_before/after(id, value)` (append to JSON list columns) ->
`finish`/`conclude(id, alpha=..., fallback_to_bootstrap=..., seed=...)`
(runs `assess`, stores p_value/significance/conclusion/method) -> `fail(id)`.

- Store metrics as JSON text columns; store `significance` as INTEGER
  (None stays NULL). Rehydrate with a `_row_to_experiment` static.
- `_row_factory = sqlite3.Row` for name access; RLock around all writes;
  `INSERT OR REPLACE` for register; `UPDATE ... WHERE id=?` for transitions.
- **Persistence round-trip test**: write, `close()`, reopen a NEW registry on
  the same db_path, assert experiment + status + metrics + p_value survived.
- Keep an alias method (`conclude` == `finish`) for API ergonomics; tests
  exercise both names.
- Context-manager (`__enter__/__exit__` -> close) + `count()`/`list()`/`get()`.

## Guarded ExperimentRunner

- `ExperimentRunner(registry, alpha, seed, fallback_to_bootstrap)`.
- `run(experiment_id, fn_before, fn_after)`: `start()` if not running, call
  both callables, coerce each return (number or sequence -> list[float]),
  record every metric, `finish()`. On ANY exception: `registry.fail(id,
  message="Runner error: ...")` then re-raise — never write a partial
  conclusion. Test: a raising `fn_after` leaves status "failed" and conclusion
  contains "Runner error".
- `run_new(hypothesis, fn_before, fn_after)`: register + run in one shot.
- Unregistered id raises KeyError (test asserts it).

## Export surface / naming collisions

The module already had an `Experiment` class in `experiment.py`. The new
`Experiment` in `experiments.py` MUST NOT clobber it. Import with an alias:
`from .experiments import Experiment as StatisticalExperiment` (plus the
registry/runner/HypothesisTest/assess/welch_t_test/permutation_test/
bootstrap_p_value) and add each to `__all__` under a "# Statistical
experiments" comment. This preserves the existing public API while exposing the
new surface. Flag the alias explicitly in the final report.

## Tests to hit (aim 12-18)
p-value significant & not-significant; is_significant(alpha) thresholds; the
three-tuple shape of welch_t_test; constant-groups p==1.0; permutation &
bootstrap seed-determinism; assess fallback uses permutation (method string)
vs default welch; registry register/get; lifecycle transitions; persistence
round-trip; conclude significant (separated) vs not (overlapping); runner
records before+after; runner concludes significance; runner guard marks failed;
run_new; unregistered KeyError.

## Pitfalls hit
1. Paid-model transport compressed tool results into PNG carriers — see
   `eni-omega-compress-paid` skill's `scripts/decode_carrier.py` to recover full
   source before editing.
2. Pyright flags `Optional` narrowing (`.get()` can return None, p_value is
   float|None) — static-only nits, ignore; runtime is fine.
3. Verify seed-determinism and real p-values with a quick REPL sanity check
   BEFORE writing the whole test file.
4. Run the WHOLE module suite at the end (baseline count -> total after) to
   prove no regression of the pre-existing 100+ tests.
