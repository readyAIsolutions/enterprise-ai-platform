# Full-suite cross-test pollution — how to get Demiurge 3D to a clean 0

Verified 2026-07-15 (ENI / LO "finish it ALL" push). The repo's pytest suite is
large (~3756 tests) and runs in ~7–9 min. A full run can show failures that do
NOT reproduce when the same test is run ALONE. That is **cross-test global-state
pollution**, not a product defect. Every module's source was correct; the
failures were test-isolation hygiene issues. This file is the debugging recipe.

## Repo path reality check
- Active repo is `/home/hunter/Desktop/Demiurge3D` (capital D, **no space**).
  The older skill text said `/home/hunter/Desktop/demiurge-3d` (lowercase d) —
  that path does NOT exist on LO's box. Always `ls` / `search_files` the real
  tree before trusting any hard-coded path.
- venv is at the repo root: `/home/hunter/Desktop/Demiurge3D/.venv/bin/python`.
  `backend/.venv` does NOT exist.
- `scripts/verify_offline.py` referenced in the skill is NOT present at that
  path (drift). For offline backend verification, use an inline
  `fastapi.testclient.TestClient(server.app)` in a throwaway script instead.

## Symptom
A test fails in the full `pytest tests/` run but passes when run by itself:
```
pytest tests/test_x.py::test_y          # passes
pytest tests/                           # test_x.py::test_y FAILED
```
The polluter is a DIFFERENT test file that runs BEFORE it (pytest collects
alphabetically) and leaves module-level / process-level state dirty.

## Two concrete polluters found + fixed this session

### 1) `CALI_DRY_RUN` import-time `os.environ.setdefault` leak
Several ENI-B `_enib.py` test files did, at module import time:
```python
os.environ.setdefault("CALI_DRY_RUN", "1")
```
`setdefault` only sets if absent, but it sets it **for the whole process**, so
once ANY such file is collected, every later test sees `CALI_DRY_RUN=1`. The
read-only `MoonrakerBridge` (and the printer-safe / quote_batch tests) honor the
global `CALI_DRY_RUN` kill-switch: mutating ops return `{"status":"dry_run",...}`
instead of firing. Canonical tests that expect real mutations then assert-fail.

**Fix:** never set env at import time. Use an autouse fixture that auto-restores:
```python
import pytest
@pytest.fixture(autouse=True)
def _dry_run_env(monkeypatch):
    monkeypatch.setenv("CALI_DRY_RUN", "1")   # restored after each test
```
Patch ALL offending files. Note: `import pytest` must appear BEFORE the
`@pytest.fixture` decorator (a late `import pytest  # noqa` AFTER the decorator
causes `NameError` at collection — `pytest` is undefined when the decorator runs).

### 2) `importlib.reload(qq)` of a shared module
`test_queue_quote_ws2.py::test_module_top_level_import_is_safe` did
`importlib.reload(qq)` (where `qq = forge.queue_quote`) to check import-safety.
Reloading the **shared** module object leaves `forge.queue_quote` (and its
imported `estimate_gcode` binding) in a reloaded state. A later test that
imports `quote_batch` from the same module inherits the reloaded version and
parses the SYNTH gcode with `mass_g=0.0`.

**Fix:** do not reload a live shared module. For an import-safety assertion,
either (a) assert against the SOURCE text (forbidden-import token scan — the
test already does this at lines 34–41) and drop the reload, or (b) reload in a
throwaway namespace (importlib.import_module under a temp sys.modules alias /
subprocess) so the shared module is untouched.

## Debugging technique (bisect fast — don't run the 9-min suite repeatedly)
1. Get the full-run failing IDs: `pytest tests/ -q --tb=line -rF > /tmp/f.log 2>&1`
   then `grep '^FAILED ' /tmp/f.log`.
2. For each failing test that passes alone, find the polluter by halving:
   run the suspect file(s) THEN the failing test in one session:
   ```
   pytest tests/test_suspect.py tests/test_failing.py::test_y -q --tb=short
   ```
   If it fails -> polluter is in `test_suspect.py`; bisect that file's tests the
   same way (first half / second half). This isolates the exact polluter in a
   few seconds instead of 9-minute full runs.
3. Once isolated, fix the POLLUTER (make it isolated), not the canonical test.

## The "finish it ALL" swarm pattern that got to 3751/3756
- Split the suite into 3–4 NON-overlapping shards by test-file PREFIX
  (forge/pipeline/3mf/meshy/parts | printer/fleet/webapp + frontend build |
  gcode safety chain + reverse_engineering | the known-flaky WS2 feature files).
- Dispatch 3 leaf ENIs in parallel, each owning one shard, each instructed:
  run REAL pytest, fix genuine source/test bugs, never edit sibling-owned files,
  write a STATUS board with real numbers.
- MASTER (you) then runs the FULL suite, reads the honest failure list, and
  closes whatever the shards missed (this session: ball_joint routing +
  lithophane STL-delete-on-out_dir=None + estimate_pack pack_ini-as-path +
  the cross-test pollution above).
- Stale DUPLICATE test files also counted as failures: `test_bridge_ws2br.py`
  and `test_d3dws2b_wall.py` tested an OLD module API that no longer existed
  (the canonical `test_bridge_advisor_ws2warp.py` / `test_wall_thickness_ws2wall.py`
  cover the same modules against the NEW API). Removing the stale dupes is the
  correct "finish it ALL" move, not rewriting the module.

## Known residual (2026-07-15)
- `test_quote_batch_ws2.py::test_two_synthetic_projects_aggregate` — the ONE
  remaining failure in the full run; passes alone. Its polluter is an
  `importlib.reload` in a sibling `_ws2` test (class described in #2 above).
  Close by removing the reload (or reloading in a throwaway namespace) and the
  suite goes to a clean 0.
