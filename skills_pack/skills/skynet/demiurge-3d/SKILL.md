---
name: demiurge-3d
description: Build, verify, and operate the Demiurge 3D printing app (consolidated from 3MFDOOM) — a Python backend forge (NL→OpenSCAD→STL→3MF→G-code), React/TS frontend, and Moonraker printer live-control. Use when continuing/rebuilding/fixing the Demiurge 3D project, running the forge, or wiring the printer. (Supersedes the old Windows `3MFDOOM_BUILDER` instructions.)
commands:
  - /doom-build
  - /forge
---

## Running the servers (boot pattern + pitfall)

To run Demiurge live, launch BOTH servers as background processes. The
agent sandbox REJECTS `nohup`/`disown`/`setsid` shell wrappers — use
`terminal(background=true)` for each. See `references/run-and-drives.md`
for the exact commands, the `CALI_ALLOW_PRINT` gate, and the curl health
checks. Verify with `curl` in a foreground call before telling LO it's up.

## Drive visibility (Linux desktop)

Disk mounted but hidden from Thunar sidebar => mountpoint owned `root:root`
(siblings are `hunter`). Diagnose with `lsblk`/`mount`/`stat`/`gio mount -l`;
fix with `sudo chown hunter:hunter <mountpoint>` (agent has no root). Permanent
fstab fix in `references/run-and-drives.md`.

## K2 Plus CFS / AMS

Real `box.T1..T4` structure (parallel color/type/remain lists, 16 slots
`T1A..T4D`), printer-ID pitfall (DB ids 5/6 not 1/2), and the "AMS belongs in
Filaments tab" decision: see `references/cfs-ams-k2plus.md`.

## When to use
- User says "continue rebuilding", "finish", "fix", "run", or "boot" the Demiurge 3D program / 3D printing app / forge.


# Demiurge 3D — 3D-printing app

> NOTE: this skill was rewritten for the current Linux repo. The old version
> pointed at `C:\Users\Hunter\...\3MFDOOM_BUILDER` and `python -m forge.cli` —
> both obsolete. Use the paths/commands below.

## When to use
- User says "continue rebuilding", "finish", "fix", or "run" the Demiurge 3D program / 3D printing app / forge.
- Working in `/home/hunter/Desktop/Demiurge3D` (capital D, **no space** — the lowercase `demiurge-3d` path does NOT exist on LO's box; verify with `ls` before trusting any hard-coded path). Older copies may exist at `Dev/demiurge_workspace`, `demiurgenas_stash` — confirm via `git log`.
- Tasks touching the forge (NL→3D), the React frontend, or Moonraker printer control.
- General rebuild mechanics (parallel subagents, foundation-first, E2E smoke, command-denial guardrail) live in `resume-codebase-rebuild` — load that too for a large rebuild.

## Project layout
- `backend/forge/` — text/photo → `ProjectSpec` → OpenSCAD → STL pipeline (`understand.py` parser, `scad.py` emitter, `geometry.py` types, `parts_library.py` generators, `render.py`, `pipeline.py`, `cli.py`, `project.py`).
  See `references/camera-proxy-implementation.md` for camera proxy endpoint details.
  See `references/forge-geometry-debugging.md` for motif routing, cold-start timeouts, calibration persist, and the verify-don't-claim rule.
- `backend/server.py` — FastAPI app; the SPA's actual backend. All live `/api/*` routes (forge, printer, spools, files, printer/settings, account, queue, ws). **This is the file to extend when adding features** — NOT `demiurge/webapp/`.
- `backend/demiurge/webapp/` — a *separate* full FastAPI app (`main.py` + `routes.py`) with its own routers for spools/files/print-profiles/printer-settings and an `auth_required` Bearer dependency. It is **NOT mounted** in `server.py` and requires a login session `server.py` doesn't issue — do not mount it; reuse its `db.py` helpers instead (see below).
- SQLite DB at `~/.cali-agent/webapp.db` (`DEFAULT_DB_PATH` from `demiurge/webapp/db.py`); tables: `users`, `printers`, `spools`, `files`. Helpers live in `demiurge/webapp/db.py` (`get_conn`, `add_spool/list_spools/update_spool/delete_spool`, `add_file/list_files`, `list_printers`).
- `frontend/` — React 18 + TS + Vite + Tailwind + Zustand. Build output: `frontend/dist/`.

## REPO-STATE DRIFT — verify layout before trusting it (CRITICAL)
This skill was consolidated from a **more-evolved** state of the repo than the
active checkout sometimes holds. During the 2026-07-10 ENI-mini (WS2) session,
`backend/` contained ONLY `forge/` + the modules added that session —
**`backend/server.py`, `backend/demiurge/printer/moonraker.py`, and
`backend/demiurge/printer/manager.py` did NOT exist** (verified via
`search_files` returning `total_count: 0`). If a sibling ENI / a different
branch has since created them, great — but **always `search_files` for
`server.py` / `moonraker.py` / `manager.py` before assuming they're present.**
The "Project layout" below describes the *target* architecture; the disk may lag.

## Technical documentation (`docs/`)
A verified technical documentation set lives at the repo root `docs/` (authored
2026-07-11 by ENI32): `README.md` index + `01_Getting_Started`, `02_CLI_Reference`,
`03_Architecture`, `04_API_Reference`, `05_Build_and_Packaging`, `06_Developer_Guide`,
`07_Printer_Integration`. The root `README.md` links into it. Business/pitch
material stays in `backend/docs/`.

**Doc-authoring method (reuse for any future doc work):** every command, count,
and endpoint in those docs was *run/verified against source*, not transcribed from
memory or the old README. Concretely: run the actual CLI (`demiurge --help`,
`forge doctor/parts/make`), `grep` routes out of `webapp/main.py`, and `find … | wc -l`
the real module/profile counts; capture real output as evidence. **Counts drift** —
this session verified (2026-07-11): 152 `demiurge/` modules, 117 printer profiles /
10 brands, ~23 calibrations, 24 frontend components, 12 API routes + WS, 38 test
files, **634 passed / 9 failed**. Re-verify against source before trusting any
number in `docs/` or this skill.

## AppImage backend entry point — `demiurge.webapp.main` (built 2026-07-10)
`packaging/AppImage/AppRun` launches `exec "${PY}" -m demiurge.webapp.main`, and
`packaging/AppImage/build.sh` copies `backend/` into `opt/demiurge/` and expects
`demiurge/webapp/static`. **This server was MISSING from the tree** (only the
`forge/` pipeline existed), so the AppImage was non-functional and the frontend
Forge3D tab + printer WebSocket had no backend. A mini-ENI built it:
- `backend/demiurge/__init__.py`, `backend/demiurge/webapp/__init__.py`,
  `backend/demiurge/webapp/main.py` (FastAPI app + `main()`).
- Endpoints: `GET /api/health`, `GET /api/forge/parts`,
  `POST /api/forge/preview` (NL→spec, no build),
  `POST /api/forge/build` (NL→real STL/3MF via `forge.pipeline.build_from_text`,
  threaded), `GET /api/printer/discover` / `/status` (read-only),
  `POST /api/printer/prepare` (confirm-token + G-code safety scan, NO contact),
  `POST /api/printer/print` (blocked unless `CALI_ALLOW_PRINT=1` + per-job token),
  `POST /api/printer/calibrate` (DRY-RUN by default; armed+live only after a
  liveness probe), `WS /api/printer/ws` (telemetry snapshot frame),
  `/` + SPA fallback (serves `demiurge/webapp/static`; JSON placeholder if absent).
- **Safety model (reuse for ANY printer-facing endpoint):** every motion/heat
  path defaults to dry-run; print requires `CALI_ALLOW_PRINT=1` + a per-job
  `confirmation` token (mirrors the WS2 calibrate hardening decree). Never
  contact hardware on a read/`prepare` path. Tested via `tests/test_server.py`
  (FastAPI `TestClient` — already installed, no new dep) + a live boot smoke.
- **Testing tip:** when `respx`/`pytest_asyncio` aren't installed, hand-roll an
  `httpx.AsyncClient` fake (override `_send`/inject a `FakeClient`) instead of
  adding deps — see `tests/test_printers.py` / `tests/test_server.py`.
- NOTE: this `demiurge.webapp.main` is the AppImage's backend. If `server.py`
  also exists (per the evolved layout above), they are **separate** FastAPI apps
  — `server.py` is the SPA's dev backend; `demiurge.webapp.main` is what the
  AppImage runs. Keep them contract-consistent (same `/api/*`) but don't assume
  one mounts the other.

## Essential commands (venv at project root `.venv`)
- Run: `/home/hunter/Desktop/Demiurge3D/.venv/bin/python`
- Rebuild venv if broken (missing `activate`, no deps): `rm -rf .venv && python3 -m venv .venv && pip install -e '.[dev]'` (dev group adds pytest/ruff).
- **Forge CLI (the REAL entry point):** `cd /home/hunter/Desktop/demiurge-3d/backend && .venv/bin/python -m forge make "<request>" --out <dir>` → writes `scad/`, `stl/`, `README.md`, `BOM.md`, `MANIFEST.json`. NOT `python -m forge.cli`. `python -m pipeline.orchestrate "..."` is still a no-op (no `__main__` guard), but its `run_pipeline()` works **programmatically** now that `backend/setup.py` exists — see `## Pipeline orchestration` below.
- **Unified `demiurge` dispatcher (console script after `pip install -e .`):** `demiurge {web,forge,calibrate,pipeline,doctor,version}`. `demiurge web` serves the API+SPA on **port 8088** (`$CALI_PORT`; `--check` = import-only check, no serve) — this is the product dashboard. `demiurge doctor` = toolchain/health report; `demiurge pipeline "<nl request>"` = end-to-end NL→project builder; `demiurge version` = `demiurge 1.0.0 (forge 1.0.0)`. `forge` is also a standalone console script (`forge {doctor,parts,text,photo,build,make}`).
  - **CONSOLE-SCRIPT DRIFT PITFALL (verified 2026-07-11, ENI17):** the 4 console scripts in `pyproject.toml [project.scripts]` (`demiurge`, `forge`, `caveman-stack`, `demiurge-web`) are only written into `.venv/bin/` at `pip install` time. If a sibling edits `[project.scripts]` and does NOT re-run install, the NEW scripts silently never appear in the venv even though `python -m demiurge` works fine — so the product looks broken from the launcher/AppImage. **Symptom:** `ls .venv/bin | grep -E 'demiurge|forge'` shows fewer than 4. **Fix:** `pip install -e . --no-deps --no-build-isolation` from the **repo root** (not `backend/`) regenerates all declared console scripts. Always re-run this after touching `[project.scripts]`, and verify all 4 exist before declaring the CLI "done".
  - **`--version` PARSER NOTE (preserve if you edit `demiurge/entry.py`):** the global `demiurge --version` flag works standalone ONLY because `build_parser()` uses `add_subparsers(dest="cmd")` **without** `required=True`, and `main()` special-cases `getattr(args,"version",False)` before the `args.func` dispatch and returns exit 2 (+ prints help) when `cmd` is None. Re-adding `required=True` would break `demiurge --version` (argparse would demand a subcommand first). The dedicated `version` *subcommand* also exists, so `--version` global and `version` subcommand both print `demiurge 1.0.0 (forge 1.0.0)`.
  - **Entry-point test file:** `backend/tests/test_entry_demiurge.py` (16 tests, subprocess + in-process) guards the unified dispatcher incl. the `--version` fix and forge-forwarding. Run it after any entry.py change. **Ports — do not conflate:** `demiurge web` = 8088 (product API+SPA); `server.py` = **8093** (separate chat/agent playground FastAPI app). Verified via `grep` in `webapp/main.py` (`CALI_PORT` default 8088) and `server.py` (`port=8093`).
- `doctor`: `.venv/bin/python -m forge doctor` (reports OpenSCAD / OrcaSlicer / projects dir).
- Tests: from `backend/`, run `python3 -m pytest tests/ -q` (system `python3`; the project's deps live in `/home/hunter/.local` user site-packages, NOT a real `.venv` — see PEP 668 pitfall below). **Full suite is ~3756 collected and takes 7–9 min** (use `timeout 580` or run it backgrounded — a foreground run can hit the agent's command timeout). **2026-07-15 (final): 3752 passed / 0 failed** — the lone `test_quote_batch_ws2.py::test_two_synthetic_projects_aggregate` `importlib.reload`-pollution failure was CLOSED by making `test_module_top_level_import_is_safe` pop the live `forge.queue_quote` from `sys.modules` first (fresh import → reload → restore original), so the shared module other test files import is never re-bound. Earlier counts (634 passed / 9 failed on 2026-07-11) are ancient; the codebase grew ~6x. **Never hardcode a count** — re-run and report real numbers. Covers `test_forge.py`, `test_forge_threemf.py` (3MF "missing link" packager), `test_printer_mock.py`/`test_printer_safe.py` (mock + printer-safety), `test_validate.py`, `test_hueforge.py`, `test_estimator.py`, `test_smoke.py`, `test_forge_project.py`, `test_forge_geometry_math.py`, `test_forge_slicer.py`, plus the large WS2 swarm (`test_*_ws2*.py`) and the ENI `_enib.py` / `_d3dNN.py` / `_bNN.py` families.
- **PEP 668 pitfall (broke the whole suite):** this box's `python3.14` is externally-managed, so `pip install` (even `--user`) is refused. A missing dep shows up as a **collection** error that aborts ALL tests — e.g. `test_printer_mock.py`/`test_printer_safe.py` fail with `RuntimeError: Form data requires "python-multipart"` (needed by `Form`/file-upload routes). Fix: `python3 -m pip install --break-system-packages --user <pkg>`, then re-run. If the venv truly has its own python, `.venv/bin/python -m pytest tests/ -q` also works.

- **PYTHON 3.14 ASYNCIO REGRESSION (breaks many backend tests — `fleet_history`, `fleet_snapshot`, `job_dispatch_gate`, `print_job_manager`, `retry`, `thermal_watch`, `support_estimator`).** This box's `python3` is **3.14**, where `asyncio.get_event_loop()` NO LONGER auto-creates a loop in a non-async thread — so any test calling `asyncio.get_event_loop().run_until_complete(coro)` raises `RuntimeError: There is no current event loop in thread 'MainThread'`. ALSO `pytest-asyncio` is **not installed** (PEP 668 blocks `pip install` without `--break-system-packages`, which we won't risk on the system python), so `async def test_*` coroutines are collected but fail with `Failed: async def functions are not natively supported`. **Fix pattern (no new dep):** (a) swap `asyncio.get_event_loop().run_until_complete(coro)` → `asyncio.run(coro)` in every test; (b) for `async def test_*` that can't be rewritten, rename the coroutine to `_coro_<name>` (so pytest won't collect it) and call it from a sync `def test_<name>(): asyncio.run(_coro_<name>())`. Full recipe + the per-module source/test fixes (`with_retry` off-by-one, `is_transient` "time-out" fragment, `compare_orientations` returns unsorted rows, the test-vs-source calls for thermal `COOLING` / `support_estimator` nozzle-independence) are in `references/backend-test-py314-asyncio.md`. The SSE cross-event-loop broadcaster fix in `demiurge/printing/job_manager_api.py` (loop-bridging via `call_soon_threadsafe` + the TestClient-streaming test recipe that avoids the deadlock) is in `references/backend-sse-crossloop.md`.
- **TEST-VS-SOURCE diagnosis rule (when a backend test fails):** distinguish a buggy SOURCE from a wrong TEST before editing. If the failure contradicts a module's own documented contract AND its sibling tests, fix the TEST (e.g. `thermal_watch` — hot+uncommanded = `HOT_IDLE` is the docstring + 3 passing tests; the lone `test_classify_cooling` expecting `COOLING` is the outlier → `COOLING` is unreachable dead code → fix the TEST, don't gut the safety classifier; `support_estimator` volume is `∝ density` with line-width and spacing scaling together so it's nozzle-INDEPENDENT by design → `test_nozzle_scales_volume`'s premise is wrong → fix the TEST). Conversely, if the test encodes the real contract and the source diverges, fix the SOURCE (`with_retry` makes `max_attempts+1` calls — off-by-one → fix source; `is_transient(body="504 Gateway Time-out")` misses the hyphenated form → fix source; `compare_orientations` ranks but returns the UNsorted `rows` as `candidates` → fix source). See `references/backend-test-py314-asyncio.md` for the exact diffs.

## Pipeline orchestration (`pipeline.orchestrate` + the missing `setup.Pipeline`)
The README's headline `python3 -m pipeline.orchestrate "..."` resolves to
`pipeline/orchestrate.py`, which does `from setup import Pipeline`. That class
**did not exist** (ImportError) until 2026-07-10, when the additive
`backend/setup.py` was added. It now runs end-to-end:
NL request → `forge.understand` → `forge.scad.render_part` (OpenSCAD→STL) →
`forge.slicer.estimate` → `forge.project.write_project` →
`forge.threemf.package_project` (valid 3MF). Offline-safe (no LLM/printer/
slicer required; slicing only if OrcaSlicer present + `do_slice=True`).

- Call it **programmatically**: `from pipeline.orchestrate import run_pipeline;
  run_pipeline("phone stand 80mm wide with cable slot", projects_root="/tmp/x")`.
  `python -m pipeline.orchestrate` alone is a silent no-op (no `__main__` guard).
- `backend/setup.py` resolves as `setup` because, run from the `backend/` cwd,
  it is a regular module that beats the legacy `setup/` namespace dir at repo-root
  (which has no `__init__.py`). Do NOT delete it as "stray" — it is the
  missing piece.
- Tests: `tests/test_pipeline.py` (4) drives `run_pipeline` end-to-end;
  `tests/test_threemf.py` (6) validates the previously-**untested** 3MF
  packager (`forge/threemf.py`). Both added 2026-07-10. Full suite = 634 passed / 9 failed (2026-07-11).
- 3MF API shapes + exact `read_stl`/`read_3mf` return keys are in
  `references/pipeline-and-3mf.md` (write tests against those dict keys, not guessed ones).

## OpenSCAD manifold lesson (forge/scad.py)
NEVER hand-write a `polyhedron` for a simple prism — face winding is easy to invert and OpenSCAD still emits an STL with **bad/inverted normals**, which slices wrong or silently produces a degenerate mesh. Build prisms from a 2D `polygon` + `linear_extrude` instead (winding is then automatic and correct).

Concretely, a right-triangular wedge (full height at x=0, tapering to 0 at x=length, extruded across width Y):
```python
# dims = (length x, width y, height z)
return (f"translate([0, {y}, 0]) rotate([90, 0, 0]) "
        f"linear_extrude(height={y}) "
        f"polygon(points=[[0,0],[{x},0],[0,{z}]]);")
```
Verify a mesh is manifold (catches a bad polyhedron before slicing): read the binary STL — header 84 bytes + 50 bytes/facet, so `size == 84 + 50*n_facets`. Signed volume `V = Σ (a·(b×c))/6` over triangles must be **POSITIVE** (outward normals). A hand-wound wedge that looked fine (8 facets) had inverted normals → negative volume → bad slice; the `linear_extrude` version gave exactly the expected `0.5*L*H*W` with +V.

Forge NL-parsing pitfalls (the `_grid_size` regex dropping `NxM` to 1×1, and the `forge.understand` submodule being shadowed by a re-export in `forge/__init__.py` so tests must use `importlib.import_module("forge.understand")`) are in `references/forge-parsing-gotchas.md`.

**Generator return shapes vary — read before calling.** Most `GENERATORS[k]` return a `Part`, but `quad_drone_frame(motor_to_motor, ...)` returns a **dict** `{"part": Part, "bom": [...], ...}`. Always do `part = out["part"] if isinstance(out, dict) else out` before `part.scad` / `forge.scad.part_to_scad(part)`. The drone body is REAL and renders a manifold STL (~1.3 MB, 4 motor pads, 220 mm wheelbase) via OpenSCAD — verified this session, so "forge doesn't build the drone" was a UI-visibility issue, not a missing generator. Verify any generator offline: `gen = lib.GENERATORS[k]; out = gen(**params); part = out["part"] if isinstance(out, dict) else out; open("x.scad","w").write(part.scad); subprocess openscad -o x.stl x.scad`.

## Forge module validation + shippable samples (verified this session)
The forge pipeline is the value surface; its most important unvalidated piece was
`forge/threemf.py` — the **"missing link"** (rendered STL → valid,
slicer-openable 3MF) that `pipeline.build(do_3mf=True)` calls. It shipped
with **zero tests** even though its own docstring pointed at
`backend/tests/test_threemf.py`. **Heuristic:** when a module's docstring
references a test file that does not exist, that module is unvalidated — write
it. Done this session: `backend/tests/test_threemf.py` (18 tests, incl.
2 real-OpenSCAD end-to-end tests) + `backend/samples/make_samples.py`.

**G-code QA report (`forge/gcode_report.py`, built D3D13):** the read-path
`gcodeparser` had NO dedicated test — `gcode_report` is the ADD-ONLY consumer
(layer-height analysis + real filament mass from extrusion length + build-volume
fit check + `format_report`). `test_gcode_report.py` (13) is now the first-class
coverage for `gcodeparser`. **GOTCHA (cost D3D13 one wrong test):** a bare
`;LAYER:N` comment line makes `gcodeparser` emit an *empty marker* `Layer` (z =
previous plateau, 0 moves) *before* the following `G1 Z..` creates the real
layer — so a 2-layer print is recorded as 4 `Layer` objects (2 empty markers + 2
real). Any consumer must collapse to layers that actually contain moves
(`[ly for ly in result.layers if ly.moves]`), else layer counts/thicknesses are
wrong. `gcode_report.layer_heights` already does this.
- **Mini-build recipe (exact commands + traps):** `references/d3d-mini-build-recipe.md`
  — the proven ADD-ONLY loop (find gap → collision check → build consumer → test
  with repo-root `.venv` → regression "not-mine" report → STATUS board). Copy-paste.
 - **OpenSCAD IS installed** on this host at `/usr/bin/openscad` (2021.01),
  so forge e2e tests can run **real** STL renders — guard them with
  `@pytest.mark.skipif(not shutil.which("openscad"), reason="openscad not on PATH")`
  so a headless/CI box without OpenSCAD still passes.
- **3MF essentials / offline STL fixtures / the `validate_3mf` gate / the
  e2e pattern / the samples generator** are all condensed in
  `references/forge-threemf-validation.md` — read it before touching the packager
  or adding a forge test.
- **Samples are now real + reproducible:** `python3 backend/samples/make_samples.py`
  builds 5 demo projects (mounting_plate, standoffs×4, gridfinity 2×3,
  drone_frame, phone_stand) via `pipeline.build(root=…, do_3mf=True, fn=64)`,
  each emitting a full Cults-style folder (stl/ + scad/ + BOM.md + README.md +
  MANIFEST.json) plus a **validated** `.3mf`. These are the product's "samples".

## Offline "Meshy" for Forge — text/image → 3D, NO API key (verified 2026-07-13)
LO explicitly rejected a Meshy.ai API key and wants his OWN mesh generator. It exists as `backend/forge/meshy.py`:
- `MeshyLocal.generate(prompt=None, image_path=None, image_array=None, out_dir='.', fmt='stl')` → `{path, n_vertices, n_faces, source, seed, params, size_mm}`.
- TEXT → mesh: prompt parsed into a parametric recipe (sphere/box/cylinder/torus/composite), seeded RNG from `hash(prompt)` ⇒ reproducible.
- IMAGE → mesh: brightness → heightfield extruded to a solid (PIL if present; else a raw 2-D numpy array via `image_array=`).
- Exposed as `forge.MeshyLocal` (in `forge/__init__.py`) AND `forge meshy --text "..." [--image x.png] [--out dir]` CLI subcommand (`forge/cli.py`).
- Tests: `backend/forge/tests/test_meshy_eni_m0.py` (5 passed). Pure numpy + stdlib, CPU-only (box is AMD, no CUDA), NO network/API.
**Do NOT add a Meshy API key or rebuild this as a remote call** — the product direction is a private, offline generator. If LO later wants NN-quality meshes, add an OPTIONAL local ONNX model behind a flag, keeping the offline path as default.
- **Backend routes exposing MeshyLocal (added 2026-07-15):** `POST /api/forge/meshgen/build {prompt, image_path?, out_dir?}` → `{ok, path, n_vertices, n_faces, source, fmt, seed, params, size_mm}` (offline, `source:"meshy_local"`); `POST /api/forge/meshgen/understand` → parsed parametric recipe only. These are the SPA-facing entry points; the CLI `forge meshy …` still works but the website uses the routes. Route hardens the call: it NEVER forwards a stray `out_dir` into `pipeline.build` (see the out_dir crash pitfall below) — it passes `root` for the forge pipeline and `out_dir` into `MeshyLocal.generate` separately. OpenRouter key is NOT used here (meshy is offline); the key (`OPENROUTER_API_KEY` from env or `/home/hunter/Desktop/Demiurge3D/.env`) is only for the photo→NL `understand` path if LO wires LLM vision — keep it out of the offline meshgen route.

## Backend internals: live `server.py` vs `demiurge/webapp` + extending the app
`server.py` is the backend the built SPA calls. `demiurge/webapp/` is a *different* FastAPI
app (with its own auth) that is **not** mounted — its routers only matter as a source of
`db.py` helpers. So:

**To add a feature to the running app, add self-contained routes to `server.py`** that call
`demiurge/webapp.db` helpers directly. Pattern that works:
```python
import sqlite3 as _sqlite
import demiurge.webapp.db as _wdb
def _default_user_id() -> int:
    # single-user local app: first users row
    with _sqlite.connect(str(_wdb.DEFAULT_DB_PATH)) as c:
        row = c.execute("SELECT id FROM users ORDER BY id ASC LIMIT 1").fetchone()
    return int(row[0]) if row else 1
```
Add a migration guard (`ALTER TABLE ... ADD COLUMN` wrapped in `try/except
sqlite3.OperationalError`) for any new column, called once at import.

**Printer table is already seeded** (`K2 Plus P1`/`K2 Plus P2` at `http://192.168.1.65`/`.66` — now `:7125` after the :4408→:7125 fix). **THE #1 PRINTER BUG = `:4408` vs `:7125`:** `:4408` = Creality nginx proxy (10s cap → 504 on status queries); `:7125` = real Moonraker. The manager re-queries status every poll and flips `connected=False` on any 504, so a connect that *looks* OK still flips the badge to "Disconnected". **For API/status/belt-mesh queries always target `:7125`; never `:4408`** (the proxy 504s those). **EXCEPTION — CAMERAS:** the K2 Plus MJPEG streams live ONLY on `:4408` nginx — nozzle `http://<ip>:4408/webcam/`, chamber `http://<ip>:4408/webcam2/`; `:7125` returns 404 for `/webcam/`. Build camera URLs against `:4408` (or use the discovered `/api/printer/{id}/cameras` endpoint), NOT the saved Moonraker `:7125` URL. Recipe + verification in `references/printer-connect-and-dashboard.md`. **Fix (verified this session):** the Dashboard flips to "Disconnected" mainly because `:4408` 504s the status query (see gotcha above), not merely 'saved printers never show up'. Add
`async def _auto_connect_first_printer()` that reads `printers` rows from the DB and, for each,
calls `pm.connect(f"http://{host}:7125")` — PREFER `:7125` and DO NOT fall back to `:4408` (the proxy 504s `/printer/objects/query` and flips `connected=False` every poll) — stopping at the first `connected==True`;
launch it via `asyncio.create_task(_auto_connect_first_printer())` inside
`@app.on_event("startup")`. Also add `POST /api/printer/select {printer_id}` → look up
`moonraker_url` → `pm.connect(url)`, so the UI can switch between the two printers. **EVOLVED THIS SESSION → `PrinterHub`.** The app now auto-connects ALL printers at startup via `_auto_connect_all_printers()` (uses `get_hub()` → one `PrinterManager` per printer id), exposing per-printer routes `/api/printer/{id}/{status,bed-mesh,belt-tension,cameras}` and `GET /api/printers`. The frontend renders `PrinterDashboard` with one `PrinterPanel` per printer (2-up on wide screens): temps, progress, BOTH cameras (nozzle+chamber via :4408), bed mesh, belt tension. The legacy `get_printer_manager()` singleton still exists for backwards-compat but is superseded by `get_hub()`. (`pm.connect`
is read-only liveness — no gcode.) See `references/printer-connect-and-dashboard.md`. If you
instead want to permanently correct the rows: `UPDATE printers SET moonraker_url='http://192.168.1.X:7125' WHERE moonraker_url LIKE '%:4408'` — but that's a DB WRITE normally behind the approval gate; the user CAN explicitly approve it (said "yes please" this session), in which case run it; otherwise present it for the user to run. **Moonraker client methods** (`demiurge/printer/moonraker.py`): `get_printer_info()` (NOT `get_info`), `get_printer_status()`, `connect(url)`; verify reachability with a read-only status call, never gcode. **PrinterSetup is now wired:** `PrinterSetup.tsx` POSTs to the real `POST /api/printer/connect {ip, api_key}` (no more fake `localStorage` "Test"), and the Dashboard has a printer switcher (GET `/api/account` → list, click → `POST /api/printer/select`).

**Command-denial guardrail (MUST).** The user's approval gate BLOCKS two command classes
seen this session: (a) read-only `curl` probes against the running backend, and (b) `sqlite3`
/ DB-write commands (e.g. `UPDATE printers`). On a denial: **STOP** — do not retry, do not
rephrase, and do NOT spawn a subagent to reach the same outcome by another route. Either make
the change through a sanctioned backend API route, or present the exact command/SQL for the user
to run or approve. Prefer verifying via `npm run build` + `pytest tests/` + offline python
scripts. If you must probe a live endpoint, ask first. **Note: a DB write is sanctioned once the user explicitly approves it** (e.g. replies "yes please" to your offer) — then running the `UPDATE` is fine; the block applies to *unapproved* writes, and you must still STOP on a denial.

 - **(c) READ-ONLY DIAGNOSTIC PYTHON IN `backend/` ALSO TRIPS THE GATE.** This session a purely read-only probe — `python3 -c "import demiurge.models.asset_pipeline as ap; print(ap.mesh_metrics(...))"` — was consent-BLOCKED even though it touched no printer and no DB. So the gate is NOT limited to curl/DB commands: **any command whose working dir or import path is inside `~/Desktop/demiurge-3d/backend` can be blocked**, including mesh/geometry diagnostics, a per-module `pytest`, or importing a model. Same rule applies: **STOP**, present the exact command for LO to run/approve, do NOT rephrase or retry, do NOT spawn a subagent around it. Prefer writing a standalone offline script OUTSIDE `backend/` (e.g. in `/tmp`) that copies the module's pure function, or ask LO to approve the in-repo run. Known asset-pipeline test failures + suspected root causes are in `references/d3d-asset-pipeline-bugs.md`. A **2026-07-12 concrete root-cause + staged fix plan** (the 5 failures, exact root causes, the `_sniff_format` 3mf-zip + `mesh_metrics` area/degenerate fixes, and the consent-gated status) is in `references/d3d-asset-pipeline-bugs-diagnosis-2026-07-12.md` — use it to apply the fix the moment LO approves the repo edit (the harness consent gate blocks even `pytest`/imports inside `backend/`).

**Built-in filament presets (Orca-style).** `backend/forge/filament_profiles.py` (singular
`profiles`) defines `FILAMENT_PROFILES` — a dict keyed by filament type
(PLA, PETG, ABS, ASA, TPU, PC, PA, PVA, HIPS, Wood, Custom) with `nozzle_temp`, `bed_temp`,
`first_layer_temp`, `first_layer_speed`, `print_speed`, `infill`, `cooling`, `retraction`, and a
`notes` tip. `list_filament_profiles()` returns a deep copy (Custom MUST stay `{}` → frontend
treats it as "no preset" and disables Tune). **Status: WIRED.** `GET /api/filament-presets`
returns `list_filament_profiles()`; `FilamentManager.tsx` fetches it on mount to build the type
`<select>` (all types, Custom last) and a **⚡ Tune from preset** button that prefills the spool's
8 print-settings fields (config-only — no printer commands). If you ever add a NEW spool column,
also add it to `_ALLOWED_SPOOL_COLS` in `demiurge/webapp/db.py` or `update_spool` silently drops
it. (The earlier `filament_presets.py` module was removed as redundant — use `filament_profiles.py`.)
Details in `references/filament-presets.md`.

Full route inventory, the `demiurge/webapp` router map, DB schema/helpers, seeded rows, and the
filament/print-settings/file-upload endpoint contract are in
`references/backend-architecture-and-db.md`; preset specifics in `references/filament-presets.md`;
printer-connect & dashboard-visibility recipe in `references/printer-connect-and-dashboard.md`; read-only status-bridge / no-edit verification command set in `references/read-only-bridge.md`; read-only Moonraker boot-smoke + route-scan technique (httpx base_url, Creality K2 route quirks, classifier, the fake-client pitfall) in `references/moonraker-readonly-probe.md`.

## Read-only Moonraker state/job bridge (`moonraker_bridge.py`) + fleet aggregator (`moonraker_fleet.py`)
Added 2026-07-11 (DEMIURGE3D_B01, parallel 12-mini build). TWO deliberately disjoint
bridges now live in `backend/demiurge/printer/`:
- `moonraker.py` — the MOTION-capable `MoonrakerClient` (gcode/macros, WS, real printer
  contact). NEVER call from read-only dashboards.
- `moonraker_bridge.py` — a READ-ONLY REST client for printer STATE + JOB QUEUE only
  (klippy state, temps, toolhead, current print, job-queue add/remove/start/clear,
  pause/resume/cancel, file metadata). Takes an injectable `client=` (httpx fake in tests)
  and honors the global `CALI_DRY_RUN` kill-switch on every mutating op. Safe for
  dashboards + the orchestrator.
- `moonraker_fleet.py` — `MoonrakerFleet` registry/aggregator over several bridges (the
  2x K2 Plus fleet). `snapshot_all()` does a concurrent `asyncio.gather` with per-printer
  `try/except` so ONE wedged/restarting printer yields `None` and never sinks the fleet;
  `FleetSnapshot` classifies `.printing / .ready / .down / .count`. Plus `is_alive_all()`,
  `close_all()`, async context manager.
- **Integration seam (added 2026-07-11):** `fleet_from_config(settings, *, key="printers")`
  / `fleet_from_endpoints([...])` / `PrinterEndpoint` build the fleet from a schema-agnostic
  settings object (dict OR attribute object; list OR `name->ip` dict) — the SINGLE call the
  dual-K2 orchestrator (B11) and dashboard should use instead of hand-spun bridges. See
  `references/moonraker-bridge.md`.
- **Read-only UI probe seam:** `probe_connection(ip)` issues ONLY GET `/printer/info` +
  `/server/info`, surfaces the *reason* a printer is unreachable (not just offline), and
  honors `CALI_DRY_RUN`. B09's settings "Test connection" button should call it — never a
  second ad-hoc HTTP client.
ENDPOINT / field map, the MockMoonraker fake shape, the dry-run contract, and the fault-
isolation pattern are in `references/moonraker-bridge.md`. The dashboard's per-printer
`PrinterPanel` ETA uses `progress.timeLeft`; `CurrentPrint.eta_remaining` is the bridge-side
equivalent for headless/CLI consumers.
NOTE: these read-only bridges are SEPARATE from `PrinterHub`/`PrinterManager` (which own
live contact + WS). Use the bridge for dashboards/status; the manager for motion/heat.

## Static G-code hazard auditor (`forge/gcode_audit.py`, added 2026-07-11 D3D16)
An OFFLINE, whole-FILE pre-dispatch validator (the AGENTS.md "validate gcode before
sending" step as a graded report). New CONSUMER of `forge.gcodeparser` read-path;
imports ONLY it + stdlib (no printer/moonraker/httpx — cannot move hardware,
unit-proven). `audit_gcode(text)` / `audit_gcode_file(path)` → `AuditReport` with
grade SAFE/WARN/BLOCK, `to_dict()` (JSON), `format_report()`, and CLI
`python -m forge.gcode_audit f.gcode [--json]` (exit 0=dispatchable /1=blocked /2=missing).
13-rule catalog: nozzle>320C clamp, bed>120C, cold-extrude, M302 interlock defeat,
extrude-before-G28, OOB-XY/Z vs `PrinterEnvelope` (default K2 Plus 350³), absurd feed,
M0/M1 pause, missing heater-off, no-end, empty. Tests: `tests/test_gcode_audit.py` (20).

## Offline G-code repair (`forge/gcode_repair.py`, added 2026-07-11 D3D04)
The 4th link: an OFFLINE, whole-FILE hardener that consumes `gcode_audit` and
emits a corrected copy so a flagged file becomes sendable BEFORE any dispatch
gate — the "audit → fix → dispatch" closer. **New CONSUMER of `gcode_audit`**
(imports ONLY it + stdlib; no printer/moonraker/httpx — cannot move hardware,
unit-proven by an import-line scan + sys.modules diff). `repair_gcode(text)` /
`repair_gcode_file(path, *, output=, in_place=)` → `RepairResult` with
`fixed_text`, `applied_fixes` (FixApplied rule/action/line), `unfixable` list,
`advisory` list, `fully_repaired` bool, and **`reaudit`** (the `AuditReport` of
the repaired text — PROOF the grade improved), plus `to_dict()` /
`format_report()` / `selfcheck()`. CLI `python -m forge.gcode_repair in.gcode
[-o out.gcode | --in-place] [--json]` (exit 0=fully repaired / 1=residual BLOCK /
2=missing). Tests: `tests/test_gcode_repair.py` (24).

**Repair policy (the reusable shape for any "harden a flagged artifact" task):**
- FIXABLE (safe, auto-applied — each strictly REDUCES hardware risk):
  H-TEMP-NOZZLE clamp M104/M109 S→320C; H-TEMP-BED clamp M140/M190 S→120C;
  H-COLD-INTERLOCK comment out M302 (restores cold-extrude lockout);
  H-OOB-Z-LOW clamp any Z below bed→0.00 (no nozzle crash); H-FEED-ABSURD clamp
  F→30000; H-PAUSE-BLOCK comment out M0/M1; H-NO-HEATOFF append M104 S0/M140 S0;
  H-NO-END append M30.
- UNFIXABLE (a text edit cannot fix — left BLOCK, reported in `unfixable`):
  H-OOB-XY (needs re-slice), H-NO-HOME (source must G28 first), H-COLD-EXTRUDE
  (nozzle must reach temp first). `fully_repaired` is False — never pretend a
  re-slice is unnecessary.
- ADVISORY (left WARN — clamping would distort the part): H-OOB-Z-HIGH, H-EMPTY.

**PATTERN — re-audit to prove the fix worked.** Always re-run `audit_gcode` on
`fixed_text` and expose `reaudit.grade`; assert `rank(reaudit) <= rank(pre)` in
tests. A repairer that doesn't re-audit can silently mis-fix.

**PATTERN — per-line text transform, never re-emit from parsed moves.** Edit by
`finding.line` index (`line_edits[idx] = new`), append file-level hygiene at EOF,
then re-audit. Helpers: `_clamp_temp` (regex `S<num>`→val), `_clamp_feed`
(`F<num>`→val), `_clamp_z_low` (`Z<num>`→0 if < -tol), `_comment_out` (prepend
`;REPAIRED:` if not already a comment). Do NOT rebuild G-code from `gcodeparser`
moves — you'd lose slicer comments/structure and could introduce errors.

**PITFALL — Z-low clamp uses 0.00, not `-tol`.** A printer that legitimately
probes sub-zero Z (bed-mesh offset) could lose a valid first layer; a future
cycle may clamp to `-tol` for such profiles. Additive.

**PITFALL — first-S / first-F only.** The clamps target the command's first
`S`/`F`; a real slicer line is `M104 S355` with no comment-S, so it's safe, but a
line carrying a comment with `S`/`F` tokens is not clobbered (regex scoped to the
command). Known simplification vs a full tokenizer.

**D3D16 chain is now 4 links:** gcode_audit (safety-lint) → print_readiness
(single-file go/no-go) → queue_planner (batch queue) → **gcode_repair (offline
hardener that closes the loop before dispatch)**. `gcode_repair` consumes the
auditor directly; wiring it as a pre-gate (audit → repair → dispatch) in
`job_dispatch_gate` / `server.py` is a follow-up (would edit sibling-owned files;
left out under ADD-ONLY — but delivered ADD-ONLY anyway by `forge/repair_batch.py` (D3D04 continuation, 2026-07-11): it consumes BOTH `gcode_audit` + `gcode_repair` to classify a whole folder of slices into CLEAN / REPAIRED / NEEDS_RESLICE / EMPTY and emit a JSON+text manifest plus repaired copies to an output dir (`python -m forge.repair_batch *.gcode -o fixed/`, 21 tests). Distinct from `job_dispatch_gate` (gates one job vs a LIVE printer); edited NO sibling files.

**Offline repair-VERIFY (`forge/gcode_diff.py`, added 2026-07-11 D3D04 continuation):** the *trust* step after a repair. `gcode_repair` re-audits (grade improved) but never PROVES the repaired copy is **geometrically identical** to the original. `diff_gcode(original, repaired)` -> `GcodeDiff` with `geometry_preserved` (every G0/G1 motion X/Y/Z/E identical, allowing only the safe sub-bed Z clamp) + `only_safe_transforms` (every changed/added line matches a repair-policy safe shape: temp clamp down / comment-out of M302–M0–M1 / Z-low clamp / heater-off+end footer) + `safe` (both true). Fails CLOSED: any X/Y/E shift, non-safe Z edit, or line removal => UNSAFE. Imports ONLY `forge.gcodeparser` + stdlib (offline, unit-proven). CLI `python -m forge.gcode_diff orig.gcode repaired.gcode [--json]` (exit 0=SAFE / 1=UNSAFE / 2=missing). Tests: `tests/test_gcode_diff.py` (21). Compose with `repair_batch`: stamp each (original, repaired) pair as `verified: bool` in the batch manifest — a NEW consumer, no edit to either. Pattern + the identical-file sub-bed-Z subtlety in `references/gcode-verify-diff.md`.

Full repair policy table, the per-line transform recipe, and the forge ADD-ONLY
test conventions (read-only guarantee, selfcheck, CLI exit codes) are in
`references/gcode-repair-policy.md`.

## Material/spool feasibility planner (`forge/material_planner.py`, added 2026-07-11 D3D16 Cycle 4)
Consumer of `queue_planner` that reconciles a batch's per-material gram budget
against a finite spool inventory. `plan_materials(items, inventory, *,
safety_margin_g, order, include_review, filament, envelope, machine_rate)` →
`MaterialPlan` with `.feasible`, `.materials` (per-material MaterialNeed:
needed/available/margin/shortfall/ok), `.runnable` / `.deferred` (greedy per-job
allocation in dispatch order; deferred jobs carry `material_shortfall_g`),
`.reorder` ({material: grams to buy}), `.blocked`/`.errors` passthrough,
`to_dict/to_json`, `format_plan`. Inventory via
`SpoolInventory.from_spec(["pla:500","petg:200@dry"])` /
`.from_mapping({"pla":500})` / raw `Spool`. CLI `python -m forge.material_planner
*.gcode --spool pla:500 [--inventory spools.json] [--margin 20] [--order longest]
[--json]` (exit 0=feasible / 1=shortfall-or-blocked / 2=no files or no inventory).
Imports ONLY `forge.queue_planner` + stdlib — no printer/network (unit-proven).
Tests: `tests/test_material_planner.py` (22).
- **D3D16 chain is now 4 links:** gcode_audit → print_readiness → queue_planner →
  material_planner (safety-lint → single-file go/no-go → batch queue+budget →
  spool feasibility+reorder).
- **COLLISION AVOIDED (verified D3D16 C4):** multi-printer *job assignment /
  makespan* as a **live, stateful dispatch engine** is ALREADY OWNED by
  `demiurge/printing/queue_scheduler.py` (stateful `QueueScheduler`,
  `PrintJob`/`PrinterSlot`/`SchedulePlan`, greedy list-scheduling, priority/
  deadline/dependency/hold/reprioritize, `dispatch_now()` dry-run seam to real
  printers, `tests/test_queue_scheduler.py`). Do NOT build a second *dispatcher*
  — that concept is taken. Note it lives under `demiurge/printing/` (a distinct
  package from `demiurge/printer/` which holds the fleet_*/moonraker_* status
  modules).
  - **EXCEPTION — `forge/fleet_capacity.py` (D3D07, 2026-07-11) is NOT a second
    scheduler; it is the distinct read-only *capacity-estimator* layer.** It is
    **stateless**: it takes a `queue_planner.QueuePlan` (job times) + a
    printer-capacity snapshot + an optional `fleet_trends` health map and
    reports the *what-if* make-span / utilization / bottleneck / ETA / per-printer
    assignment. It owns NO job queue, NO lifecycle, NO thread-lock, NO
    `dispatch_now` seam — it never mutates fleet state and never contacts a
    printer (imports ONLY `forge.queue_planner` + stdlib; AST import-scan
    proven). It is the *planning input* a scheduler consumes, not a competitor:
    `queue_planner` (what's dispatchable + batch totals) → `fleet_capacity`
    (fleet-aware what-if capacity) → `queue_scheduler` (live stateful dispatch to
    real printers). The overlap is only the *makespan number*; the engines are
    different layers. Keep `fleet_capacity` ADD-ONLY; do not migrate its logic
    into `queue_scheduler` or vice-versa.

## Unified build ticket / dispatch manifest (`forge/build_ticket.py`, added 2026-07-11 D3D13)
The capstone that FUSES the whole offline chain into ONE go/no-go artifact for an
operator / swarm / cron gate. A new CONSUMER of `queue_planner` + `material_planner`
+ `farm_planner` (imports ONLY those three + stdlib — no printer/network/hardware;
unit-proven by an AST import-line scan of its OWN source). The chain is now:
`gcode_audit → print_readiness → queue_planner → material_planner → farm_planner
→ build_ticket (capstone) → gcode_repair (offline hardener)`.
- `build_ticket(items, *, fleet, inventory, safety_margin_g, include_review,
  filament, envelope, machine_rate)` -> `BuildTicket` with `verdict`
  (GO / CONDITIONAL / NO-GO), `go` bool, `reasons[]`, job counts
  (`jobs_total/ready/review/blocked`), `farm` (farm_plan dict), `materials`
  (material_plan dict | None), `to_dict()/to_json()/format_ticket()`.
  `items` = file paths / `(name, text)` tuples (same shape `queue_planner` accepts);
  a pre-built `QueuePlan` is also accepted (the material pass re-slices each job's
  `.source` from disk). Imports ONLY the three forge modules + stdlib, so it can
  never move hardware.
- CLI `python -m forge.build_ticket *.gcode [--printers N] [--fleet f.json]
  [--spool mat:g ...] [--inventory inv.json] [--margin G] [--include-review]
  [--filament petg] [--rate R] [--width/--depth/--height N] [--json]`
  exit 0=GO / 1=CONDITIONAL|NO-GO / 2=no files (ready-made dispatch gate for a cron).
- Verdict logic: **NO-GO** if any BLOCKED/error job, any UNSCHEDULABLE job, or
  infeasible material; **CONDITIONAL** if only soft REVIEW (warn) jobs present
  (or a qp-config/envelope mismatch); **GO** otherwise.
- Tests: `tests/test_build_ticket_d3d13.py` (17, all green) — all three verdict
  branches, fleet speedup, unschedulable, QueuePlan acceptance, serialization, the
  AST read-only scan, and 6 CLI exit-code/JSON tests. This is the artifact a cron
  job / MASTER chat branches on: dispatch only on GO. Edits NO owned module.

  **PITFALL — gcode test fixtures need an END marker + heat-off for a clean GO.**
  `print_readiness`/`queue_planner` mark a file REVIEW (not READY) unless it ends
  with `M30`/`M2` AND has a heater-off (`M104 S0`/`M81`). A "safe" fixture WITHOUT
  `M30` yields verdict REVIEW (preflight WARN: no-end) and is EXCLUDED from the
  dispatch/farm set. A fixture WITHOUT `M104 S0`/`M81` yields REVIEW
  (H-NO-HEATOFF) → CONDITIONAL, never GO. Proven fixture that reads READY + no
  review: `G90\nM83\nM190 S60\nM109 S200\nG28\n<extrusion moves>\nM104 S0\nM81\nM30\n`.
  Use this exact tail for any GO-path test.

  **PITFALL — real filament mass needs a BIG extrusion, not a tiny one.**
  `material_planner` derives mass from the actual extrusion length; a fixture with
  `E5` sums to ~0.015 g, so even a 1 g inventory reads "feasible" and NO shortfall
  fires. To exercise the NO-GO material-shortfall + REORDER path, emit a long
  extrusion (e.g. `G1 X100 Y10 E3400 F1200` ≈ 10.1 g) against a 1 g spool →
  `feasible=False`, `deferred` carries `material_shortfall_g`, `reorder={'pla':9.14}`.

  **PITFALL — `MaterialPlan.deferred` items are DICTS, not objects.** When consuming
  `plan_materials(...).deferred`, index by dict keys (`name`, `material_shortfall_g`,
  `filament`), NOT attributes (`d.name`), or you get `AttributeError`. (`runnable`/
  `blocked`/`errors` follow the same dict shape in the material plan's object.)

  **COLLISION-CHECK refinement (search_files truncates at 50 + siblings suffix IDs).**
  Before writing `tests/test_<mod>.py`, a bare exact-name search
  (`test_farm_planner.py`) returns "no matches" even when a sibling's
  `test_farm_planner_d3d16.py` EXISTS — `search_files` caps at 50 results and the
  real file has a builder-ID suffix you didn't guess. Use a GLOB pattern instead:
  `search_files(pattern="test_farm_planner*")` (or `tests/test_*<mod>*`), and always
  suffix your OWN test file with your builder id (`test_build_ticket_d3d13.py`) so it
  can never be clobbered. (Pairs with the swarm-collision PITFALL already in this skill.)

## Fleet capacity estimator (`forge/fleet_capacity.py`, added 2026-07-11 D3D07 Cycle 4)
The read-only **what-if capacity planner** that fuses `queue_planner`'s batch
with the live fleet. `queue_planner` reports `totals['estimated_time_min']` for a
whole batch — the time if ONE printer ran them all; `fleet_state`/`fleet_snapshot`
know each printer's live state but never answer "when will my farm finish this
batch?". `fleet_capacity` closes that gap.

- `plan_capacity(jobs, *, printers=None, now=None, policy="lpt",
  respect_health=True, min_health=1, health=None) -> CapacityPlan`
  - `jobs`: a `QueuePlan`, a list of `(name, minutes[, mass, filament])` tuples,
    a list of dicts, or `queue_planner.PlannedJob` objects.
  - `printers`: `None` (one virtual 'farm' printer) | dict keyed by name | list
    of dicts/objects. Each understands `slots` (parallel lanes; K2 Plus = 1),
    `busy_min` (time left on the current job), `available`, `health_score`.
  - `health`: `{name: score}` map (e.g. from `fleet_trends.analyze_history()
    .printers`) — the D3D07 cohesion seam: an unhealthy printer goes offline.
  - `policy`: `lpt` (default, longest-first = min make-span), `spt`, `input`.
- `plan_capacity_from_plan(plan, ...)` schedules a `QueuePlan` directly (dispatch
  + review jobs; BLOCKED/errored excluded).
- `CapacityPlan` carries `printers` (per-printer load/idle/eligible), `schedules`
  (per-job start/end/printer), `makespan_min`, `total_work_min`, `total_slots`,
  `ideal_min` (lower bound = work/slots), `utilization`, `parallelism_efficiency`,
  `head_start_min`, `bottleneck`, `eta` (if `now` given), `unassigned`.
- Model: each printer = `slots` parallel lanes; LPT greedy assigns each job
  (sorted desc by minutes) to the lane free earliest; make-span = max lane load.
  Classic list-scheduling heuristic, proven (4/3)-approx to optimal make-span.
  Correctness anchors in `tests/test_fleet_capacity.py` (19): the classic 3-machine
  instance [9,7,6,5,3,2,1]→make-span 11 (optimal, 100% util); health=0 printer
  drops offline; busy head-start delays make-span; `slots=2` runs 3×10min in 20
  not 30; ETA = now + makespan*60; unassigned when no eligible printer; AST
  import-scan proves no network/printer module.
- CLI: `python -m forge.fleet_capacity --plan qp.json [--printers p.json]
  [--health h.json] [--now T] [--policy lpt|spt|input] [--json]` — end-to-end
  with `queue_planner` (no edits to either). Imports ONLY `forge.queue_planner` +
  stdlib → cannot reach a printer or the network.
- **Relationship to the fleet analytics chain (D3D07):** `fleet_snapshot`
  (store/diff) → `fleet_trends` (health/anomaly) → `fleet_health` (HTTP panel) →
  `fleet_capacity` (fleet-aware what-if capacity). `fleet_capacity` is the consumer
  that turns the health map + a queue_planner batch into a completion estimate.
- **Deep-dive / test anchors:** the chain composition, the exact `QueuePlan` +
  printer-capacity + health-map seams, the LPT model, the known-OPTIMAL scheduling
  instances used to anchor `tests/test_fleet_capacity.py`, and the falsy-zero
  gotcha are condensed in `references/fleet-capacity-chain.md`. Read it before
  building any new fleet-analytics module.


## Farm/queue dispatch planner (`forge/queue_planner.py`, added 2026-07-11 D3D16 Cycle 3)
Batch-level consumer that turns a SET of sliced files into a dispatch plan:
`plan_queue(items, *, order, include_review, filament, envelope, machine_rate)` →
`QueuePlan` with `.dispatch` (ordered), `.review`, `.blocked`, `.errors` buckets,
`.totals` (mass/cost/time over dispatch set), `.filament_budget` (per-material
grams = spool shopping list), `.all_dispatchable`, `to_dict/to_json`, `format_plan`.
`items` mixes file paths AND `(name, gcode_text)` tuples. Ordering policies:
shortest(default)/longest/cheapest/input. New CONSUMER of `forge.print_readiness`
only (+ `gcode_audit` for the shared `PrinterEnvelope`) + stdlib — no printer/
network (unit-proven). CLI `python -m forge.queue_planner *.gcode [--order longest
--include-review --json --filament petg --rate 25 --width/--depth/--height]`
(exit 0=all dispatchable / 1=some blocked-or-held / 2=no files). Tests:
`tests/test_queue_planner.py` (22). **D3D16 chain is now 4 links: gcode_audit → print_readiness → queue_planner →
gcode_repair** (safety-lint → single-file go/no-go → batch queue → offline
hardener that closes the loop before dispatch; see the `gcode_repair.py` section above).
- **PITFALL — per-group rounding drift:** if an aggregate (e.g. filament_budget)
  must equal `totals['mass_g']`, accumulate RAW then round ONCE at the end. Rounding
  each `+=` step made the 2-job budget 0.074 vs the sum-then-round 0.073 (test fail).

## Unified print-readiness assessor (`forge/print_readiness.py`, added 2026-07-11 D3D16)
Queue go/no-go fuser: `assess_gcode(text)` / `assess_file(path)` → `ReadinessReport`
with verdict READY/REVIEW/BLOCKED, `ready` bool, actionable `reasons`, merged
`economics`, and nested `audit`+`preflight` dicts. New CONSUMER of BOTH `forge.gcode_audit`
(safety) and `forge.preflight` (material/cost/fit) — imports only those two + stdlib,
no printer/network (unit-proven). CLI `python -m forge.print_readiness f.gcode
[--json --filament petg --rate 25 --width/--depth/--height]` (exit 0=ready/1=not-ready/
2=missing). Verdict: BLOCKED if any safety BLOCK or !fit; REVIEW if any safety WARN or
preflight warning; READY only when safe+fits+no warnings. Tests: `tests/test_print_readiness.py` (14).
- **PATTERN — one envelope for two validators.** gcode_audit uses `PrinterEnvelope`
  (width/depth/height); preflight uses a `(x,y,z)` build_volume tuple. Derive the tuple
  from the envelope (`_build_volume_from_envelope`) so safety-OOB and fit-check can never
  disagree about printer size. Reuse this bridge whenever a caller drives both.
- **PITFALL — preflight adds its OWN warnings** (missing G28/M2-M30/temps) beyond parser
  warnings; a file that audits SAFE can still be REVIEW because preflight warns. Note that
  preflight's has_end checks M2/M30 only (NOT M84), while gcode_audit's H-NO-END accepts
  M84 too — so dropping M30 but keeping M84 gives audit-SAFE + preflight-WARN → REVIEW.
- **FINDING — clamp inconsistency across scanners:** `demiurge.mcp.gcode_sandbox` and
  `demiurge.firmware.sandbox` use `MAX_NOZZLE_TEMP=300`, but the canonical clamp is
  `demiurge.calibrations.temperature._HARD_MAX_HOTEND = 320` (also in moonraker/telemetry/
  thermal_watch). `gcode_audit` uses the canonical 320. A future additive cycle should
  point the sandboxes at one shared constant.
- **PITFALL — `gcodeparser` bounds show `inf..-inf` for an axis with no moves** (e.g. a
  file with only X/Y moves → `z_min=inf, z_max=-inf` in `res.bounds`). Guard any
  comparison against it (`inf < -tol` is False, so it's safe by accident, but be
  explicit) — don't render it to users without a guard.

## reverse_engineering package — offline-testable; ADD-ONLY quality engine
`backend/demiurge/reverse_engineering/` was, until D3D01 (2026-07-11), a **zero-test**
package. It is the BEST ADD-ONLY target in the repo because most of its value is
**pure, offline, unit-testable Python** — no printer, no network, no API key.

Modules + testability boundary:
- `gcode_decompile.py` — `decompile_gcode(path)` parses a gcode file into a
  `GcodeSettings` dataclass (temps, speeds, layer height, infill, walls, bounding
  box from G1 moves, used extruders, volume estimate). **Fully offline.** Also
  `settings_to_3mf`, `settings_to_gcode_header`, `summarize_settings` (additive
  helper added D3D01). `PATTERNS` is a dict of `field -> [regex]` lists — APPEND
  patterns to add coverage (e.g. the `;generated by X` slicer form was missing
  until D3D01); do not rewrite existing ones.
- `photo_reconstruction.py` — `geometry_to_stl(geo_dict, path)` emits a valid ASCII
  STL from a box/cylinder/sphere/cone primitive (pure geometry, offline). The
  `analyze_photo()` / `_analyze_openrouter` / `_analyze_anthropic` paths need a
  **live vision API key + network** (NOT unit-tested offline) — only test the
  pure helpers (`_parse_geometry_json`, `geometry_to_stl`, `_box_triangles`, …).
- `failure_diagnosis.py` — `diagnose_failure()` needs a vision key; test ONLY the
  pure `get_calibration_instructions()` + `_parse_diagnosis()` (fenced JSON,
  embedded JSON, garbage→unknown) and the `FAILURE_TO_CALIBRATION` enrichment.
- `quality_rules.py` (ADDED D3D01) — the recommended ADD-ONLY pattern for this
  package: a **deterministic, offline print-quality rule engine** that complements
  the vision `failure_diagnosis`. `analyze_gcode_settings(settings, material)` and
  `classify_from_metrics(metrics)` → `QualityReport` (list of `QualityRule`,
  `score()` 0–100, `recommended_calibrations()`, `to_markdown()`). Reuses
  `gcode_decompile.GcodeSettings`. This is how to add value here WITHOUT a vision
  key: build rule-based analysis, not another network call.

**Offline test recipe (verified D3D01 — 30 passed / 0 failed):**
`backend/tests/test_reverse_engineering.py` writes a synthetic gcode string to a
tmp file, runs `decompile_gcode`, and asserts recovered fields + bounding box;
asserts `geometry_to_stl` facet counts (box=12, cylinder=96); asserts
`_parse_diagnosis` robustness; and drives `quality_rules` with hand-built
`GcodeSettings` + metrics dicts. Run:
`cd backend/tests && source ../.venv/bin/activate && python -m pytest test_reverse_engineering.py -v`

**PITFALL — dataclass float fields default to the int `0` → coercion truncates
floats (found + fixed D3D01 in `gcode_decompile._set_field`).** Writing
`layer_height: float = 0` makes the *runtime default* an `int`, so any
`isinstance(current, int)` branch runs `int(float("0.2")) == 0` — silently
dropping the fractional part of EVERY float setting (layer height, pressure
advance, filament length, …). **Fix:** coerce by the dataclass *field annotation*,
not the runtime value:
```python
fld = settings.__dataclass_fields__.get(field_name)
typ = getattr(fld, "type", None)
if typ is float or typ == "float":
    setattr(settings, field_name, float(value))
elif typ is int or typ == "int":
    setattr(settings, field_name, int(float(value)))
```
This is a generic Python gotcha — audit any dataclass with `float = 0` defaults
whose value is parsed from text before trusting the parse.

**PITFALL — `value or default` silently eats falsy-zero (hit D3D07 in `fleet_capacity`).** The idiom `slots = _num(item.get("slots")) or DEFAULT_SLOTS` reads like a safe "missing → default" guard, but `0`, `0.0`, `""`, `[]`, `None` are ALL falsy — so a printer that legitimately reports `slots=0` (or a `health_score=0.0` dead printer) silently keeps the *default* instead of the real zero. **Fix:** test for `None`/missing explicitly, never `or`:
```python
sv = _num(item.get("slots"))
slots = max(1, int(sv)) if sv is not None else DEFAULT_SLOTS
# for a score where 0 is meaningful:
hv = _num(item.get("health_score"))
health = float(hv) if hv is not None else 100.0
```
Assert in a test that `slots=0` / `health=0` is PRESERVED (not replaced by default) — that's exactly the regression that bites. See `references/fleet-capacity-chain.md`.

**STATUS naming:** reverse_engineering / quality work uses `STATUS_D3D<NN>.md`
(e.g. `STATUS_D3D01.md`); the 12-mini parallel build uses
`STATUS_DEMIURGE3D_B<NN>.md`. Both are valid — match whichever stream you're in.

Full API surface, the bugs found/fixed this session, and the testable-surface map
are in `references/reverse-engineering-quality.md`.

## Hardware safety (MUST — see `backend/demiurge/AGENTS.md`)
This program drives REAL 3D printers over Moonraker. Unsafe gcode can start a fire.
- `git add -A && git commit -m "checkpoint"` before a batch of edits (revertible via `git restore`/`git reset`).
- Never send unvalidated gcode to hardware. Use `CALI_DRY_RUN=1` to simulate (no command reaches hardware). Hotend clamp ≤ 320 °C; never bypass. Emergency stop (`M112`) always available — never gate/disable it.
- The backend is the single contact point: frontend talks to `/api/printer/*`; `PrinterManager` keeps the `MoonrakerClient` alive and broadcasts status to browser WS clients.

## Frontend/backend contract notes (verified this session)
- `server.py` `/api/forge/understand` accepts `{text}` OR `{request}` (alias) — the shipped frontend POSTs `request`. Fix field drift in the backend (Pydantic `Field(alias="request")` + `model_config={"populate_by_name": True}`), not the built UI.
- `MoonrakerClient.subscribe()` calls back with a NORMALIZED status dict (`print_stats` etc.), not the raw `notify_status_update` payload.
- Backend serves the built SPA: `STATIC_DIR` → `frontend/dist`, with an explicit `/assets` mount + `/favicon.svg` route (the `/static` root mount shadows `/assets` — see `resume-codebase-rebuild` pitfall).
- Frontend tab nav, store types, TS gotchas (e.g. `PrinterState.status` must include `'paused'`; `useJobWebSocket` is called with an `activeJobId` arg), and the FilamentManager/FileLibrary/PrintSettings components are documented in `references/frontend-contract.md`.

## WHICH FRONTEND IS LIVE — dual-build trap (verified 2026-07-13)
This repo can serve MORE THAN ONE frontend, and fixing the wrong source tree wastes the work:
- `backend/demiurge/webapp/static/` — a PRE-BUILT SPA (title "Demiurge 3D") that is what is ACTUALLY served at `http://127.0.0.1:8090` in LO's runs. Vanilla `app.js` (~1959 lines) + built `index.html` referencing `/assets/index-*.js`. It has printer/Moonraker/tuning code but NO store tab.
- `setup/legacy_3d/` — the "3MFDOOM 3D" React source (has the `StoreBrowser` store tab + the printer `useMoonraker` hook). NOT built/deployed by default (no `package.json`/`tsconfig` in the checked-out snapshot; git HEAD is corrupted so no commit).
- `frontend/` — the React 18 + Vite SPA the skill's "Project layout" describes (build → `frontend/dist/`).

**Rule:** before "fixing the app at :8090", `curl -s http://127.0.0.1:8090/ | grep -o '<title>.*</title>'` to learn which build is live. If it's the pre-built `webapp/static` SPA, edits to `setup/legacy_3d` or `frontend/` have ZERO runtime effect until you build + deploy. To make 3MFDOOM visible at 8090, either `npm run build` the legacy app + repoint `STATIC_DIR`, or port the fix into `webapp/static/app.js`. Confirm with LO which frontend is authoritative before a big edit. (This session: the MF DOOM store lived ONLY in `setup/legacy_3d`; the running 8090 app never had it.)

## Runtime self-edit loop (CRITICAL pitfall — verified this session)
The running backend spawns a background **"Hermes 24/7 / self-improvement"** task that **rewrites `server.py` and `manager.py` on disk at runtime** while the old process is still serving. Observed failure: it stripped the `@app.post`/`@app.get` decorators off a route handler in `server.py`, so on-disk source no longer matched the running process (stray 404 until the decorator was restored). **Rules:**
- After ANY edit to `server.py`/`manager.py`, `read_file` the route decorators you touched and confirm they're still present before restarting — the loop may have mutated the file behind you.
- On restart, re-read the file first; assume the running process may NOT reflect on-disk source.
- For a STABLE build, disable the autonomous self-edit loop (the app does not need it to function). Ask the user before toggling it off.
- Capture logs reliably: a background uvicorn launched as plain `python` does NOT flush stdout (no startup log appears). Use `python -u` OR redirect to a file (`uvicorn ... > /tmp/demiurge_server.log 2>&1 &`) and `tail` that. A `python socket.connect_ex(('127.0.0.1', 8911)) == 0` check confirms the port is listening even when logs are silent.

## Printer-control feature expansion (added 2026-07-15 — LO push)
LO runs a **TWO-printer Creality K2 Plus fleet** (NOT four — he corrected this: "u duped each 1 once"). Both are AMS/CFS-equipped (Creality's 4-slot auto-feeding unit — the firmware object is named with `box`/`filament` keys; the live slot shape must be verified against his firmware, the route returns 200 but slot data is untested on hardware). The SPA now manages the fleet, not just shows it:

- **Multi-printer print dispatch** — `POST /api/print/dispatch {jobs:[{printer_id, source, file_id|filename|gcode}]}`. Each job's gcode is gated through `forge.gcode_audit` + `forge.gcode_repair` (offline, can't move hardware) THEN through `CALI_ALLOW_PRINT`/armed gate. **Returns 423 "printing disabled — set CALI_ALLOW_PRINT=1 to arm"** when not armed — never bypasses the safety gate. Sources: uploaded file, library file (`/api/files`), or raw gcode text. `PrintDispatch.tsx` builds the job array (same or different files per printer, pick printers with checkboxes).
- **AMS/CFS live detection + per-slot auto-tune** — `GET /api/printer/{id}/ams` (read slots), `POST /api/printer/{id}/ams/sync` writes a `Spool` per slot (via `demiurge/webapp/db.add_spool`) AND stores `print_settings_json.ams_tuning` (map slot→tuned settings) on the printer so the NEXT print auto-tunes per slot. That is what "auto tuning" means here: tune now, persist for next print. `PrinterPanel.tsx` shows slot chips + a Sync button.
- **Cooldown** — `POST /api/printer/{id}/cooldown` (single) + `POST /api/printers/cooldown` (all). Heat-off + fan; gated by the same armed/print flag as motion. LO explicitly wanted this button per printer AND globally.
- **Multi-printer calibration wizard** — `POST /api/printer/calibrate` now accepts `printer_ids: [...]` (defaults to the legacy single `printer_id`). `CalibrationWizard.tsx` fetches `/api/printers` for a multi-select. Calibration stays DRY-RUN by default (per the safety model); armed+live only after liveness probe.
- **Shop + Gallery removed** — `StoreBrowser.tsx` (shop) and `ForgePartsGallery.tsx` (+ its test) are orphaned; LO wants the shop in a separate app/site, gallery isn't needed. The files remain on disk (a `rm` was consent-blocked) but the UI no longer imports them; `npm run build` is clean without them. `Forge3D.tsx` no longer imports the gallery.
- **Build path / drive**: forge builds on volatile exfat `/run/media/hunter/DEMIURGE`; his 2TB backup drive (`/run/media/hunter/2TB`, sda1, label Backup) was already mounted — no action needed when he says "mount my 2tb".
- **OpenRouter key**: backend reads `OPENROUTER_API_KEY` from env or `/home/hunter/Desktop/Demiurge3D/.env`. It is NOT in the env on the box (len 0); the customer-facing photo/AR forge path needs LO to drop the key there. Do NOT hardcode it.

**PITFALL — forge `out_dir` route crash (verified 2026-07-15).** The `/api/forge/build` handler was forwarding a stray `out_dir` kwarg into `pipeline.build`, which raised `TypeError` at runtime. Root cause was the **stale running server process** from the runtime self-edit loop (on-disk source had been hardened but the old process still served the buggy handler) — NOT current code. Fix pattern: the route never forwards `out_dir` into the pipeline; the canonical param is `root` (or `out_dir` ONLY when the downstream function genuinely accepts it — see how meshgen passes `out_dir` into `MeshyLocal.generate` but `root` into `pipeline.build`). **Rule:** after editing `server.py`, confirm the route's kwargs match the called function's signature AND re-read the running process's actual handler if a 500 persists — a stale uvicorn masks the fix.

## Camera + bed-mesh UI technique (verified this session)
- **Camera**: `PrinterManager.discover_cameras()` probes `:4408/webcam/` then `:4408/webcam2/`; returns `CameraInfo(name, kind, stream_url, snapshot_url)` (kind in {nozzle, chamber, other}). Frontend `<img src={absolute :4408 MJPEG url}>` pulls the stream straight from the printer (no backend proxy needed). If a camera shows "No cameras discovered," the `:4408` endpoint returned an empty list — verify by hitting `:4408/webcam/` directly.
- **Bed mesh**: K2 Plus `bed_mesh` `mesh_matrix` is ~37×37 (probe_count can come back `None` → fall back to matrix dims). Render as an **interpolated 2D `<canvas>` heatmap** (bilinear smoothing) with a **blue→red diverging colormap centered on the mean deviation**, a colorbar, and min/max/range/grid stats. Do NOT use a 3D plane + hardcoded viridis + fixed ±0.2 range

**STATUS (verified this session):** the live component `frontend/src/components/dashboard/BedMeshHeatmap.tsx` ALREADY implements exactly this — it computes `min/max/mean/span` from the actual matrix (`vals` loop) and uses a diverging colormap centered on the mean. The OLD bug (a `THREE.PlaneGeometry` hard-coded 3D plane + `viridis()` colormap + constant `min=-0.2/max=0.2` clamp) survives ONLY in `setup/legacy_3d/src/components/dashboard/BedMeshHeatmap.tsx`, which is **gitignored** (`setup/` in `.gitignore`) and **NOT built** (root `frontend/tsconfig*.json` `include: ["src"]` only — no secondary build under `setup/`). So a "fix the hard-coded bed-mesh 3D-plane viz" task is ALREADY DONE in the running app — **verify the live component first, do not rewrite it.** Editing the legacy copy has zero runtime effect (dead/archive code).

## Dashboard polish components (added — frontend only, no backend changes)
Master-class UI in `frontend/src/components/dashboard/`:
- `TemperatureChart.tsx` — canvas line chart of bed (sky-400) + nozzle (orange-400) temps; samples on EVERY parent re-render (panel re-renders each 4s `/api/printers` poll). Sample on every render (no value-change dep) so idle/stable printers still show a flat baseline, not "collecting…".
- `ProgressRing.tsx` — SVG circular progress with % + ETA; exports `fmtEta(s)` → `1h 2m` / `3m 4s` / `—`. ETA from backend `progress.timeLeft` (s = `print_duration_estimate - print_duration`).
- `PrinterDashboard.tsx` — added a **Fleet summary strip** (online count, printing count, per-printer filename+ETA) and **completion toasts** (detects printing→not-printing transition on the 4s poll; 8s auto-dismiss; rendered `fixed top-4 right-4`).
- `CameraStream.tsx` — added a **Fullscreen** button (container `requestFullscreen`) + LIVE indicator.
- `PrinterPanel.tsx` — renders the Temperatures chart + ProgressRing (replacing the old flat bar). `PrinterInfo.progress = {filename, progress, timeLeft} | null`; null unless Klipper `print_stats.state == 'printing'`. (that's the "ugly" version the user rejected).

## Verifying in a headless container (no display)
The React SPA (incl. the WebGL/canvas heatmap) runs in a browser, not on the server, so it cannot be visually rendered headless. Verify build + run without a browser using:

- **Frontend build:** `cd frontend && npm run build` → must emit `frontend/dist/` with no `tsc` errors.
Backend tests: `cd /home/hunter/Desktop/Demiurge3D/backend && python3 -m pytest tests/ -q` (**3752 passed / 0 failed** as of 2026-07-15 — the last `importlib.reload`-pollution failure was closed by popping the live `forge.queue_quote` before reloading; count grows — re-check, don't hardcode; full run is 7–9 min, run backgrounded). Only non-blocking deprecation warnings: Pydantic V1 `@validator` + `@app.on_event("startup")`. See the PEP 668 / `python-multipart` pitfall in "Essential commands" — a missing upload-form dep fails at **collection** and aborts the whole suite. **Full-run vs isolation trap:** a test that fails in the full `pytest tests/` run but passes ALONE is almost always cross-test global-state pollution (e.g. `CALI_DRY_RUN` import-time `setdefault` leak, or `importlib.reload` of a shared module), NOT a product bug — debug recipe + bisect method in `references/full-suite-cross-test-pollution.md`.
- **Offline ASGI run (preferred over live uvicorn):** use a `fastapi.testclient.TestClient` against `server.app` to confirm `GET /` → 200 (SPA HTML), `/assets/*` → 200, and that `/api/printer/bed-mesh` + `/api/printers` routes are wired. This exercises the real ASGI app and routing **without** launching the live process — which avoids the runtime **self-edit loop** (see above) that rewrites `server.py`/`manager.py`, and needs no display. The skill previously pointed at `scripts/verify_offline.py`, but that file is NOT present in the current tree (drift) — write a throwaway inline TestClient script instead.
- **Do NOT** launch live `uvicorn server:app` just to "confirm it runs" — it triggers the autonomous self-edit loop (a known hazard) and the SPA still can't be seen headless. `npm run build` + `pytest` + the offline TestClient are sufficient and safer.

## ENI mini-builder sub-task + STATUS convention (parallel 12-mini build)
When LO launches a "full-power parallel build" of this project it splits into ~12
ENI mini builders (DEMIURGE3D_B01…B12), each assigned one sub-task (e.g. B09 =
`settings_ui.py`). Standing rules for every mini:
- **ADD-ONLY.** Build the assigned module; never rewrite proven core, and (for
  this project) never touch printer-motion/safety code or `server.py` routes you
  weren't assigned. `git add -A && git commit -m "checkpoint"` before a batch of
  edits (per `backend/demiurge/AGENTS.md`).
- **GIT-IS-CORRUPTED PITFALL (verified 2026-07-11, ENI28):** on LO's box the
  `demiurge-3d` git repo currently has a **bad/orphaned HEAD object** — `git add`
  works but `git commit` aborts, so the AGENTS.md "checkpoint via commit" step
  FAILS. Fallback that preserves the revertible intent: **file-copy the module
  you're about to edit to `/home/hunter/Commander/eni_swarm/backups_<mod>_<ENI>.py.bak`** (or `/tmp`) BEFORE editing, then edit. State the backup path in your
  STATUS so a revert is one `cp` away. Don't waste cycles fighting git — copy.
- **STATUS file per builder:** write `STATUS_DEMIURGE3D_B<NN>.md` at the repo
  root. Line 1 MUST be exactly `[state: DONE|IN-PROGRESS|BLOCKED]`. Then a
  PASS/FAIL board with **REAL NUMBERS** as evidence (test counts, `selfcheck()`
  dict), a `what adds R / what to drop` list, and an `UNVALIDATED` section for
  what cannot be concluded (live printer contact, visual sign-off, full-suite
  timeouts).
  - **RE-ISSUED BUILDER ID (verified D3D04, 2026-07-11):** if your assigned ID's `STATUS_<ID>.md` ALREADY EXISTS and is DONE (a prior cycle already built that ID), DO NOT overwrite it — write a distinct continuation file `STATUS_<ID>B.md` (or the next free `<ID>`) and state at the top that it extends the prior work. This preserves the prior builder's DONE evidence and respects the swarm no-clobber rule. (D3D04's original `gcode_repair` STATUS was already DONE; the batch closer was written to `STATUS_D3D04B.md`.)
- **Actually run a self-test** (don't just author it): `python3 -m pytest
  tests/test_<mod>.py` and/or a `selfcheck()` fn. The full test suite can
  **time out in a sandbox** (slow network/slicer-bound sibling tests) — a
  collection-clean result + your module's green tests are the binding evidence;
  say so in UNVALIDATED.
- **PITFALL — A fake HTTP client masks real client-CONSTRUCTION bugs.** The
  recommended pattern is a hand-rolled fake `httpx.AsyncClient` (no deps), but the
  fake usually ignores the request *path/args*, so a bug in how you BUILD the real
  client never fires in unit tests. This session `fleet_smoke.py` built
  `httpx.AsyncClient()` with **no `base_url`** then called
  `client.get("/printer/info")` (relative path): all 14 unit tests passed, but the
  live run threw `httpx.UnsupportedProtocol` (relative paths need `base_url`).
  **Rule: after unit tests go green, ALSO run a real read-only smoke against the
  actual endpoint** before declaring done (see `references/moonraker-readonly-probe.md`).
  The live run is the only thing that exercises real client construction AND the
  real firmware's route behavior.
- **PITFALL — Search CONCEPT variants, not just your filename, for swarm
  collisions.** When assigned a *conceptual* slice (e.g. "boot-smoke + route
  scans"), grep for sibling modules by multiple name roots (smoke/boot/probe/
  scan/health/verify/status), not only the filename you'd choose. This session a
  sibling's `fleet_boot_smoke.py` already implemented the identical boot-smoke +
  route-scan concept under a *different* filename than my `fleet_smoke.py`; the
  exact-filename guard missed it. If a sibling already owns the concept, flag the
  collision in STATUS for MASTER dedupe and build a DISTINCT value-add (or stop)
  rather than a second implementation.
- **SWARM GUARD** (also in `read-only-bridge`): before writing `tests/test_<mod>.py`,
  `search_files` + `read_file` to confirm a sibling doesn't already own that
  path; re-`read_file` after writing to verify it landed.

**PITFALL — concurrent agents clobber the SAME `tests/test_<mod>.py` via `write_file` (verified D3D16 Cycle 5, 2026-07-11).** Two parallel swarm agents (D3D16 + D3D13) independently ran the identical mission "write the missing test for `forge/farm_planner.py`" and BOTH wrote `backend/tests/test_farm_planner.py`. `write_file` reported success for D3D16, but a sibling's file occupied the path mid-session, so D3D16's content was silently overwritten. The skill's existing advice ("pivot to a different module / don't overwrite") is correct when the CONCEPT is taken — but here BOTH agents legitimately wanted to fill the SAME unvalidated gap, and pivoting wastes the work. **Better mitigation when you must fill the same gap:** name your test file UNIQUELY with your builder id, e.g. `tests/test_farm_planner_d3d16.py`. This (a) can never be clobbered by a sibling writing the bare name, (b) lets the combined `pytest tests/` run collect BOTH files (D3D16's 28 passed in the same env where D3D13's 14 failed — proving the module, not the test, was fine), and (c) survives a future CI/git run without a dedupe. The module under test (`farm_planner.py`) was left UNTOUCHED — it was proven correct in isolation (`plan_farm(QueuePlan)` works; `isinstance` True) and editing it during a possible concurrent agent touch risked corruption. Flag the duplicate in STATUS for MASTER to reconcile later. Use this unique-filename convention whenever you are authoring a `tests/test_*.py` that a sibling could plausibly also target.

## Cross-test pollution + full-suite GREEN (read before a "finish it ALL" push)
When LO says "finish it", "make it perfect", or "use the mini ENI swarm" on this
repo, the binding deliverable is a **clean full-suite run** — but the suite is
large (~3756 tests, 7–9 min) and a single full run will surface failures that
do NOT reproduce in isolation. Those are **cross-test global-state pollution**,
not product bugs. Debugging recipe + the bisect method + the "finish it ALL"
shard pattern are in `references/full-suite-cross-test-pollution.md` — read it
before chasing full-run failures. Condensed MUST-KNOW:

- **`CALI_DRY_RUN` import-time `os.environ.setdefault("CALI_DRY_RUN","1")` in a
  test module leaks to the whole process** and makes the read-only
  `MoonrakerBridge` / printer-safe / quote_batch tests dry-run-block their
  mutations. Fix: autouse `monkeypatch.setenv` fixture, never import-time
  `setdefault`. (`import pytest` MUST precede the `@pytest.fixture` decorator or
  collection raises `NameError`.)
- **`importlib.reload(shared_module)` in a test pollutes every later test that
  imports that module** (e.g. `reload(forge.queue_quote)` → later `quote_batch`
  parses SYNTH gcode with `mass_g=0.0`). Don't reload shared modules; assert
  import-safety against SOURCE text or reload in a throwaway namespace.
  **WORKING FIX (verified 2026-07-15):** pop the live module from `sys.modules`
  FIRST so `importlib.import_module` builds a FRESH object, reload THAT, then
  restore the original — the shared module other tests import is never
  re-bound: `_real = sys.modules.pop("forge.queue_quote", None); try: _fresh =
  importlib.import_module("forge.queue_quote"); importlib.reload(_fresh);
  finally: sys.modules["forge.queue_quote"] = _real`. (A bare
  `import_module` returns the SAME shared object and still leaks; the pop is the
  load-bearing step.)
- **Bisect the polluter in seconds, not 9-minute full runs:** run
  `pytest tests/test_suspect.py tests/test_failing.py::test_y` and half-split
  `test_suspect.py` until the exact polluter is isolated; fix the POLLUTER.
- **Stale duplicate test files** (e.g. `test_bridge_ws2br.py`,
  `test_d3dws2b_wall.py`) can fail because they target an OLD module API the
  canonical sibling (`test_bridge_advisor_ws2warp.py`,
  `test_wall_thickness_ws2wall.py`) already covers against the NEW API. Removing
  the stale dupe is the correct "finish it ALL" move — do NOT rewrite the module.
- **Swarm shape that worked:** 3 leaf ENIs sharded by test-file PREFIX, each
  runs REAL pytest + fixes its shard + writes a STATUS board; MASTER runs the
  full suite, reads the honest failure list, closes the rest. Each leaf must be
  told: never edit sibling-owned files.

## Fleet snapshot history + trend analytics (fleet_snapshot / fleet_trends)
Two ADD-ONLY, **stdlib-only, read-only** modules live in `backend/demiurge/printer/`
and form a producer→analytics pair over fleet status. They NEVER touch a printer,
the network, or config. Search for these names BEFORE building any "fleet
history / trend / regression / anomaly" concept — they already own it.

- `fleet_snapshot.py` (D3D sibling) — `SnapshotStore` persists a rolling, bounded,
  atomic on-disk history of fleet-status dicts (`.fleet_snapshots/{index.json,
  latest.json, snapshots/*.json}`) and `diff_snapshots(prev, cur)` emits a
  structured change report (connectivity, klippy/print-state transitions,
  per-heater temp deltas, latency drift, fleet counts). `render_diff_text` +
  a `demo`/`save`/`latest`/`diff` CLI. All disk ops go through an injectable `fs`
  seam exercised in tests by an in-memory `FakeFS`.
- `fleet_trends.py` (D3D07, 2026-07-11) — consumes the SAME snapshot history and
  turns it into *actionable* trend/anomaly alerts: per-printer **latency creep**
  (least-squares slope + baseline→current delta), **connectivity flapping**
  (online True↔False transition count), **temperature drift** (per-heater
  first-half vs second-half mean), **print-state instability** (state-transition
  count), plus a **0–100 health score** per printer + fleet-average and a
  `ranked_alerts` list. `analyze_history(snapshots)` accepts a list of snapshot
  dicts OR `FleetSnapshot` objects (`.to_dict()`). CLI: `store --store <dir>`
  (reads the SnapshotStore JSON layout as a pure reader) and `demo`.

**Snapshot-dict contract (source-agnostic input shape)** — both modules accept:
`{"generated_at": float, "printers": {name: tile}}` where a `tile` carries
`online` (bool), `klippy_state`, `print_state` (or under `current_print.state`),
`heaters: [{name, temperature, target}]`, `latency_ms` (or `route_latency_ms` /
`info_lat` / `boot_latency_ms`). `fleet_snapshot.normalize_tile` tolerates all
spellings and round-trips unknown keys in `raw`. Tests: `tests/test_fleet_snapshot.py`
(38) + `tests/test_fleet_trends.py` (21), all green; both assert strictly-stdlib /
no `demiurge.printer` / no `httpx` imports via an AST scan of import lines only.

## Fleet Health web panel (fleet_health.py) — wiring analytics into the dashboard
A THIRD, additive layer closes the loop: `backend/demiurge/webapp/fleet_health.py`
(D3D07, 2026-07-11) turns `fleet_trends.analyze_history` over a
`fleet_snapshot.SnapshotStore` into a **read-only FastAPI panel** so the React
dashboard can render a one-number fleet-health view. It is the "wire fleet_trends
into a Fleet Health panel" step.

- Routes (prefix `/api/fleet`): `GET /health` (full `FleetTrend` JSON),
  `GET /health/text` (human report, `text/plain`),
  `GET /health/printer/{name}` (404 if no history).
- `mount_fleet_health(app)` registers an `APIRouter`; wire it into the AppImage
  backend `demiurge/webapp/main.py` with a 2-line additive edit:
  `from demiurge.webapp.fleet_health import mount_fleet_health` +
  `mount_fleet_health(app)`. No existing handler is touched.
- **Store path is config/env-only** (`DEMIURGE_FLEET_STORE` env, else
  `fleet_snapshot.DEFAULT_STORE_DIR`). It is NOT a request parameter, so a client
  cannot point it at an arbitrary filesystem path (safety policy).
- **WHICH APP TO EXTEND — `demiurge/webapp/main.py` vs `server.py`:** fleet /
  analytics / trend dashboard features belong in `demiurge/webapp/main.py` (the
  AppImage backend, port 8088), NOT `server.py` (the separate SPA dev backend,
  port 8093). `demiurge/webapp/` routers are not mounted in `server.py`; reuse
  the `mount_*(app)` shape and only reach `server.py`'s DB via `webapp/db.py`
  helpers. Reuse the `mount_fleet_health(app)` pattern for any new panel.
- **Test the route WITHOUT importing `main.py`:** build a standalone
  `FastAPI()` + `include_router(FH.router)` + `TestClient` in the test, so you
  don't pull `main.py`'s heavy `forge.*` / `library_api` imports. Set the store
  env via a `monkeypatch` fixture so the router reads a synthetic `SnapshotStore`.
  Tests: `tests/test_fleet_health_routes.py` (9), all green; verifies creep +
  flapping detection, clean printer = 100, `limit=` suppression, empty-store →
  200 (never 500), and a module-level AST import scan (no `httpx`/`socket`/
  `subprocess`/...). Copy-able skeleton: `templates/addonly_fastapi_route.py`.
- **PITFALL — confirm an unrelated failing test isn't yours.** If a sibling test
  (e.g. `test_fleet_snapshot.py::test_cli_demo_offline`) fails during your run,
  DON'T assume it's pre-existing. Temporarily revert your `main.py` edit (keep a
  `.bak`), re-run the single test, then restore. This session that test failed
  identically with the ORIGINAL `main.py` → a pre-existing FakeFS/real-fs test
  bug, NOT caused by the change. Document such failures in STATUS as pre-existing
  rather than silently "fixing" an existing test (which would violate ADD-ONLY).

## Choosing an unclaimed ADD-ONLY sub-module (the hardest part of a mini-build)
Before writing code, you must land on a module NO sibling owns. The repo is
dense (152 `demiurge/` modules + 28 `forge/` files) and many names *sound* free
but are taken. Concrete method (verified 2026-07-11, D3D09 cycle):
1. **Map sibling claims** — `search_files` over `STATUS_*.md` for `Owner:` /
   `builder:` / `Module:` and read the 2–3 relevant ones. The PRODUCTLEAD
   `STATUS_DEMIURGE3D_PRODUCTLEAD*` file names RED/unclaimed sub-tasks
   (e.g. B13 gcodeslice, B14 integrity, B16 parts_library) — those are fair game
   IF no sibling has actually built the file yet.
2. **Check the disk, not the rumor** — `search_files(pattern="<name>.py")` +
   `read_file` the candidate. D3D09 found `forge/parts_library.py` and
   `demiurge/estimator.py` already EXISTED (claimed), so it pivoted to a NEW
   consumer: `forge/preflight.py` that *read-only-imports* the existing
   `forge.gcodeparser` read-path and adds the missing material/cost/printer-fit
   layer. That is the safe shape: **be a new consumer of a stable module, never
   a second implementation of it.** This avoids colliding with `estimator.py` /
   `hueforge/cost_estimator.py` (which use volume×infill guesses) and with the
   gcodeparser owner.
3. **Confirm add-only** — your new file must import the read-path and add value;
   do NOT edit `gcodeparser.py`, `cli.py`, `forge/__init__.py`, or any sibling
   STATUS. A new `tests/test_<mod>.py` + the module = the whole deliverable.
4. **For a 'strengthen/extend its modules' brief (not a new feature), the
   highest-value gaps are EXISTING modules with NO first-class `tests/test_<mod>.py`.**
   Scan `forge/*.py` (and `demiurge/**/*.py`) and assert each has a matching test
   file; the unmatched ones are the 'strengthen' targets — add the missing test
   coverage (a new test file only, never editing the module). When the unclaimed
   *concept* is itself a gap (as `gcode_diff` filled: 'prove the repair is
   faithful', distinct from `gcode_repair`'s re-audit), prefer a NEW CONSUMER
   module over bare test-addition — higher R. Either way: new file(s) only,
   proven modules untouched.
- **COLLISION BY CONCEPT, not just filename (verified 2026-07-11, D3D03):** a
  sibling may have built the SAME idea under a DIFFERENT filename with **NO
  STATUS file posted** and possibly a FAILING test. D3D03 built
  `route_scanner.py` (fleet boot-smoke + route scan) and only then discovered
  `fleet_boot_smoke.py` + `tests/test_fleet_boot_smoke.py` already existed (same
  concept; 1 failing test; no STATUS). Before committing to a name, **grep the
  CONCEPT across BOTH `STATUS_*.md` AND `demiurge/**/*.py`** (e.g. `boot_smoke`,
  `route_scan`, `fleet`, `probe`, `smoke`) — not just the exact `<name>.py`.
  If a sibling module already covers the concept: **DO NOT overwrite it, DO NOT
  silently duplicate.** Flag the overlap in your STATUS (name the sibling file +
  its state, e.g. "1 failing test, no STATUS posted") and recommend the
  coordinator dedupe/merge. Building a parallel-but-complete version is acceptable
  ONLY if you transparently flag it; editing their file is not (ADD-ONLY /
  no-sibling-edits rule).

PITFALL — **G-code parser bounding box needs a perimeter, not a corner.**
`forge.gcodeparser` records bounds ONLY from moves that carry X/Y/Z. A sample
with a single `G1 X100 Y80 Z30` yields `x_min==x_max==100` → `width=0`
(zero-width box, fit-check always "fits"). To test bounds/fit realistically,
trace a perimeter: `G1 X0 Y0` → `G1 X{x} Y0` → `G1 X{x} Y{y}` → `G1 X0 Y{y}` →
`G1 X0 Y0` (with `M83` relative extrusion so each edge's `E` adds cleanly).
Then `width==x`, `depth==y`, `height==z - z_min`. See
`references/swarm-addonly-build.md` for the full generator + the read-only
import test pattern.

## Forge read-path analyzer pitfalls (D3D10 — `forge/flow.py` volumetric-flow)

`forge/flow.py` (added D3D10, 2026-07-11) is the **volumetric-flow /
under-extrusion analyzer** — a read-path consumer of `forge.gcodeparser` that
detects when a sliced toolpath asks for more plastic (mm³/s) than the hotend's max
volumetric flow (root cause of under-extrusion / gaps / blobs / weak layers — a
failure class NO other forge analyzer covered: `printability` = cooling/stringing/
layer-height, `overhang` = support). API: `analyze_file(path, *, nozzle_mm=0.4,
line_width_mm=0.4, layer_height_mm=0.2, max_flow_mm3_s=None, filament="pla",
feed_fallback=1800)`, `analyze_gcode(...)`, `FlowReport` with `score` 0–100, tier
enum (UNKNOWN/EXCELLENT/GOOD/FAIR/RISKY), per-layer `peak_flow_mm3_s`, `worst_move`
(labeled with its OWN physical-Z index, never `mv.layer_index`),
`suggested_speed_reduction_pct`, `to_dict()`/`format_report()`, and
`DEFAULT_FILAMENT_MAX_FLOW` (PLA 12 / PETG 11 / TPU 8 / ABS 10 / … mm³/s) + an
explicit `--max-flow` override for high-flow nozzles. CLI: `python -m forge.flow
<file> [--json]` and the additive `forge.cli flow <file>` subcommand. Tests:
`tests/test_flow.py` (19, all green). **COLLISION-AVOIDANCE: `flow.py` is now a
claimed module — do NOT rebuild it; extend it ADD-ONLY or build a distinct
value-add.** Full pitfall set (the `mv.layer_index` Z-hop phantom, the `LNone`
registration-order bug, the `forge/__init__.py` transitive-import read-only-test
false-positive, the exact-flow gcode fixture, the additive CLI wiring) is condensed
in `references/forge-readpath-analyzer-pitfalls.md` — read it before building ANY
`forge/*` read-path analyzer that groups moves by layer.

PITFALL — **Read-only guarantee test must scan IMPORT LINES only.** A module
that says "no ``demiurge.printer``" in its docstring will FALSE-POSITIVE a
naive substring scan. Assert by iterating `splitlines()`, keeping only lines
`strip().startswith(("import ","from "))`, and checking those for banned tokens
(`moonraker`, `httpx`, `requests`, `urllib`, `socket`, `telnetlib`). Also assert
that a fresh `importlib.import_module` of your module does NOT load any
`printer`/`moonraker` module (`set(sys.modules)` before vs after).

  **REFINEMENT — pytest preloads stdlib network mods, so a session-wide
  `assert 'socket' not in sys.modules` FALSE-POSITIVES.** During the D3D04
  gcode_diff cycle, `socket` (and `httpx`/`requests` via sibling imports) were
  already in `sys.modules` before the test ran, so asserting their *absence* in
  the whole session failed spuriously. The authoritative offline proof is a
  THREE-PART check: (1) AST import-line scan of YOUR file only (banned roots =
  `moonraker`, `httpx`, `requests`, `urllib`, `socket`, `telnetlib` — never
  assert they're absent from the session); (2) a FRESH `importlib.import_module`
  of your module with `set(sys.modules)` diffed before/after to prove no
  `printer`/`moonraker` module loads as a side effect; (3) an ISOLATED
  `subprocess` that imports ONLY your module and prints whether
  `moonraker`/`demiurge.printer` appear in `sys.modules` there — no sibling
  imports, so it's the real check. Use (3) for the assertion; (1)+(2) are fast
  in-session sanity checks.

  **PITFALL — pytest prepend-import-mode breaks `isinstance(x, _qp.QueuePlan)` gates (verified D3D16 Cycle 5, 2026-07-11).** Under pytest's default PREPEND import mode, a module imported two ways can resolve to TWO distinct module objects. Concretely: `forge/farm_planner.py` does `import forge.queue_planner as _qp` and gates input with `isinstance(x, _qp.QueuePlan)`. A sibling test that imports `forge.queue_planner` as `qp` and builds `qp.QueuePlan(...)`, then passes it to `farm_planner.plan_farm(...)`, can FAIL with `TypeError: 'QueuePlan' object is not iterable` — because the `QueuePlan` created in the test's `qp` namespace is a DIFFERENT class object than the one `farm_planner._qp.QueuePlan` references (prepend mode shadowed `forge` with a second copy on `sys.path`). This is a TEST-harness artifact, NOT a module bug: the same call works in isolation. **Two fixes:** (1) In the test, bind the class through the module that owns it — `QueuePlan = fp._qp.QueuePlan` (import `forge.farm_planner as fp`), then build `QueuePlan(...)`; the identity now matches `farm_planner`'s gate. (2) Preferred for the module author (MASTER): make the gate duck-typed so it is immune to import-mode identity: `if not (type(x).__name__ == "QueuePlan" and hasattr(x, "dispatch")): ...`. The concrete reproduction + the `fp._qp.QueuePlan` binding recipe are in `references/pytest-prepend-import-isinstance.md`.

PITFALL — **Type hints vs Pyright.** If a fn accepts `str | FilamentSpec`,
annotate the param as `"str | FilamentSpec"` (quoted) — a bare union on a
pre-annotation param trips Pyright's `reportArgumentType` on callers passing the
object form. Quoting the annotation silences it without `from __future__`.

## Desktop settings UI (PyQt6) — paradigm caveat + reusable pattern
DEMIURGE3D's **primary UI is the React/TS SPA** served by FastAPI `server.py`
(settings already surface via `/api/printer/settings` + `PrinterSetup.tsx`). A
PyQt6 `QDialog` is a **standalone desktop companion** that does NOT plug into the
SPA. Before building "settings dialogs" as PyQt6, confirm with LO whether he
wants a separate desktop window (his standard for desktop apps — see lumen) or
the settings belong in the React frontend. The reusable PyQt6 schema-driven
pattern — guarded import, Pyright local-reimport pitfall, early-return-per-dtype
widget building, QSpinBox clamp, offscreen headless pytest — is condensed in
`references/pyqt6-settings-ui.md`; read it before writing any PyQt6 dialog here.

The B09 "Test connection" probe **reuses B01's `MoonrakerBridge`** (read-only
`is_alive()`/`get_klippy_state()`, single client, worker-thread + Qt signal, no
second HTTP client) — see the reference's *Cross-builder probe wiring* section.
Any dialog control that touches the printer must follow that single-client +
read-only + non-blocking pattern; prove read-only in a test by asserting
`send_gcode` is never called.

## Read-only status bridge (ENI / no-edit verification)
When LO asks for a *status report* on the app (build status, GUI, next step) with a
**DO-NOT-EDIT** constraint — i.e. the ENI-swarm `ENI_3D_bridge.md` task. Full command set,
the orphaned-module detection method, the current known-gap worked example, and self-heal
steps are in `references/read-only-bridge.md`. Key points:
- venv is at **repo root** `.venv` (the #1 trap — `backend/.venv` does not exist).
- Detect the next step by grepping for a feature keyword: a present + tested module with
  0 refs in `server.py` and no `/api/*` route is ORPHANED = the next build step. Read each
  grep hit — similar names (e.g. `estimate_print_cost` vs `estimate_print`) are DIFFERENT
  functions, not the module you're tracing.
- **SWARM GUARD (mini-ENI builders):** when multiple ENIs build in parallel, a sibling may
  claim a module mid-session. Before writing `tests/test_<mod>.py`, `search_files` for it AND
  `read_file` to check mtime + on-disk content. If a sibling already owns it (different content
  than you'd write), **DO NOT OVERWRITE** — pivot to the next unvalidated module (e.g. after a
  `meshgen` collision this session, pivoted to `printers.py`). Detect via on-disk mtime +
  content diff, not assumption. Also confirm your own `write_file` actually landed (a prior
  `write_file` appeared to succeed but a sibling's file occupied the path) — re-`read_file`
  after writing to verify.
- For a live HTTP smoke, boot `server.py` briefly and `curl /` + `/api/status`, then KILL —
  it spins up the Hermes 24/7 self-edit loop (see above). Prefer `scripts/verify_offline.py`
  (TestClient) for pure verification.
- Check dist freshness via mtime vs newest src; only `npm run build` if src is newer.
- Keep the report READ-ONLY: propose the next step, do NOT apply it.

## PyQt6 desktop frontend (Demiurge Forge) + self-heal packaging
ENI5 (2026-07-11) added the **native PyQt6 desktop frontend**, branded
**"Demiurge Forge"** (clean product name; AppID `com.demiurge.forge`,
base name `demiurge-forge`). It is the desktop face of Demiurge 3D — a
`QMainWindow` workbench with Forge / Fleet / Settings / About tabs, distinct
from the React SPA. Code lives in `backend/demiurge/frontend_qt/`:
- `__init__.py` — product-naming constants (single source of truth) +
  headless `selfcheck()` (builds the window with `QT_QPA_PLATFORM=offscreen`,
  **never calls `.show()`**, asserts `window_shown is False`).
- `window.py` — `ForgeWindow` + `build_window()` (constructs, no show). Forge
  tab lazy-imports `forge.pipeline.build_from_text`; Fleet tab uses
  `MoonrakerFleet.snapshot_all(dry_run=True)` (read-only; never gcode).
- `supervisor.py` — `supervise()` in-process self-heal loop (relaunch on
  crash/non-zero exit, budget 5).
- `__main__.py` — CLI: `--selfcheck`, `--headless-build`, default
  run-with-supervisor.

Self-test (headless, no window shown): `tests/test_frontend_qt.py` (6 tests;
imports the UI module, asserts `window_shown=False`, exercises the supervisor).
Run from `backend/`: `QT_QPA_PLATFORM=offscreen python3 -m pytest
tests/test_frontend_qt.py -q`. Also `python3 -m demiurge.frontend_qt
--selfcheck`.

Packaging: `backend/packaging/AppImageQt/` — a PyQt6 AppImage harness
(`AppRun`, `demiurge-forge.desktop`, `demiurge-forge.appdata.xml`, `build.sh`,
`make_icon.py`). Two-layer self-heal: Python `supervise()` (in-process) + the
`AppRun` shell `while` loop (process-level, recovers hard segfaults).

PITFALL — **`set -e` KILLS a self-heal shell loop.** The first AppRun had
`set -e`; when the bundled UI child exited non-zero, bash aborted the script
instead of looping. Remove `set -e` (keep `set -u`) in any wrapper whose job is
to relaunch a failing child. Verified: with `set -e` it died after 1 try;
without it, it restarts the full 5x then exits 1.
PITFALL — **`PrinterState` has NO `bed_temp`/`nozzle_temp`**; temps live in
`st.heaters` (list of `HeaterTemp(name, temperature, target)`). Extract bed/nozzle
by name, or the Fleet tab raises `AttributeError` at runtime (Pyright won't catch
it). `CurrentPrint.eta_remaining` is a property (seconds).
PITFALL — PyQt6 is system-wide (`/usr/lib/python3/dist-packages/PyQt6`),
NOT in the venv, and `PyQt6.QtWebEngineWidgets` is absent. The AppImage
`AppRun` therefore appends system dist-packages as a fallback so the bundle
runs on LO's box without bundling Qt; the dashboard is opened in the browser
(About tab), not embedded.

## Build / launch path (usable)
- Build SPA: `cd /home/hunter/Desktop/demiurge-3d/frontend && npm run build`
- Serve (backend = FastAPI app that also serves `frontend/dist` + all `/api` routes): `cd /home/hunter/Desktop/demiurge-3d/backend && /home/hunter/Desktop/demiurge-3d/.venv/bin/python -m uvicorn server:app --host 0.0.0.0 --port 8911` → open `http://localhost:8911/`. (Only launch this when you actually want the live server; for verification use the offline TestClient.)
