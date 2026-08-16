# D3D backend test-suite: Python 3.14 asyncio regression + test-vs-source

Verified 2026-07-12 while clearing 22 pre-existing failures across
`test_fleet_history`, `test_fleet_snapshot`, `test_job_dispatch_gate`,
`test_print_job_manager`, `test_retry`, `test_support_estimator`,
`test_thermal_watch`.

## Symptom signature
- `RuntimeError: There is no current event loop in thread 'MainThread'` raised
  from inside a test that does `asyncio.get_event_loop().run_until_complete(coro)`.
- `Failed: async def functions are not natively supported` for any `async def test_*`.

## Root cause (two independent facts)
1. This box's `python3` is **3.14**. `asyncio.get_event_loop()` no longer
   auto-creates a loop when none is running in the current thread (deprecated
   and removed). It now raises if there is no current loop.
2. `pytest-asyncio` is **NOT installed**. PEP 668 marks the system python
   externally-managed, so `pip install pytest-asyncio` is refused (and we will
   NOT pass `--break-system-packages` on LO's box). Without the plugin, pytest
   collects `async def test_*` but cannot run them.

There is NO network/pip workaround that is safe here — fix the tests instead.

## Fix recipe (no new dependency)

### A. The `get_event_loop().run_until_complete` swap
Every occurrence in a test:
```python
# BEFORE (breaks on 3.14)
hist = asyncio.get_event_loop().run_until_complete(fh.analyze_printer(...))
# AFTER
hist = asyncio.run(fh.analyze_printer(...))
```
`asyncio.run` creates a fresh loop per call — correct for these one-shot tests.

### B. The `async def test_*` wrapper
If a test is defined as `async def test_foo():` and you cannot easily inline it,
rename the coroutine to a private helper and drive it from a sync test:
```python
# BEFORE
async def test_with_retry_success_first_try():
    out = await with_retry(fn, sleep=_sleep_zero)
    assert out == "ok"

# AFTER
async def _coro_with_retry_success_first_try():
    out = await with_retry(fn, sleep=_sleep_zero)
    assert out == "ok"

def test_with_retry_success_first_try():
    asyncio.run(_coro_with_retry_success_first_try())
```
The `_coro_*` name is NOT collected by pytest (no `test_` prefix), so the
"async def not supported" error disappears and the sync wrapper runs it.

## TEST-VS-SOURCE diagnosis rule (decide before editing)
A failing backend test is either a BUGGY SOURCE or a WRONG TEST. Tell them apart:

- **Fix the TEST** when the failure contradicts the module's own documented
  contract AND its sibling tests (the module is internally coherent):
  - `thermal_watch.classify_printer`: hot+uncommanded = `HOT_IDLE` is the
    docstring contract and is confirmed by `test_classify_hot_idle_warning`,
    `test_classify_hot_idle_bed_only`, `test_classify_cold`, etc. The lone
    `test_classify_cooling` (ext=120°C/bed=50°C, both above warn thresholds,
    target 0) expects `COOLING` — but `COOLING` is UNREACHABLE dead code given
    the classifier (step 3 returns `HOT_IDLE` for any hot+uncommanded, step 5
    `COOLING` can never trigger). → align the test to `HOT_IDLE` + `warn True`.
    Do NOT "fix" the classifier — it is the safety-correct behaviour.
  - `support_estimator.estimate_support`: volume `= support_area * vol_per_mm²`
    where `vol_per_mm² = (line_width / pitch) * layer_height * span` and
    `pitch = line_width / density`. The `line_width` cancels, so volume is
    `∝ density` and **nozzle-independent** (a wider bead is spaced wider → same
    plastic per area). `test_nozzle_scales_volume` assumes wide > thin; they are
    equal by design. → assert `wide == pytest.approx(thin)` (or remove the
    scaling claim). The model is validated by 9 other support tests.

- **Fix the SOURCE** when the test encodes the real contract and the source
  diverges (these were genuine bugs):
  - `demiurge.util.retry.with_retry`: makes `max_attempts + 1` calls (one
    extra call after the budget is spent). Restructure the loop to check
    `budget.can_retry` BEFORE invoking `fn()` and `advance()` after a caught
    transient failure, so exactly `max_attempts` attempts occur. Keeps all
    params/semantics; only removes the off-by-one.
  - `demiurge.util.retry.is_transient`: body fragment list has `"timeout"` but
    real text is `"504 Gateway Time-out"` (hyphen). The scan misses it. → add
    `"time-out"` to `_TRANSIENT_BODY_FRAGMENTS` (or normalize `-`→`` in the scan
    text). Do NOT weaken the test.
  - `forge.support_estimator.compare_orientations`: ranks `rows` by cost into
    `ranked` and uses `ranked` for `best_name`/`worst_name`, but returns the
    UNsorted `rows` under `"candidates"`. `test_compare_all_candidates_ranked`
    expects `cmp["candidates"]` sorted by cost. → return `ranked` as
    `"candidates"`.

## General principle
When a backend test fails, grep the module's other tests + docstring FIRST.
A single outlier test that fights a coherent, documented module is almost
always the wrong one. Fixing a validated source to satisfy a mistaken test
silently degrades the product (e.g. gutting the thermal safety classifier).
Conversely, when the test IS the contract, fix the source and keep the test
as the regression anchor.
