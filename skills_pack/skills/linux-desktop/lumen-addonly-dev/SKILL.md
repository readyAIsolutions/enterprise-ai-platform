---
name: lumen-addonly-dev
description: >
  Build ADD-ONLY sub-modules for the LUMEN PyQt6/WebGL wallpaper engine during
  ENI swarm passes. Covers the CODE-ONLY hard leash (NEVER launch the GUI / X /
  WebGL — it has crashed LO's AMD RX 5700 XT box), picking an UNCLAIMED module,
  headless pytest/flake8/mypy verification, the `--self-test` liveness probe,
  and the required STATUS_<NAME>.md contract (state line + PASS/FAIL board with
  real numbers + what-adds-R/what-to-drop + UNVALIDATED). Use whenever assigned
  a LUMEN swarm-builder task ("You are swarm builder LMxx, workspace N,
  project LUMEN ... pick ONE add-only sub-module ... write STATUS_LMxx.md").
---

# LUMEN Add-Only Swarm Module Development

Swarm-builder missions arrive as:
> "You are swarm builder LMxx, workspace N, project LUMEN. ... Pick ONE concrete
> add-only sub-module not already claimed by a sibling, build it, RUN its
> self-test/smoke, fix errors, then write STATUS_LMxx.md with [state: ...], a
> PASS/FAIL board with REAL numbers, a 'what adds R / what to drop' list, and an
> UNVALIDATED section. Keep ADD-ONLY; never touch core or sibling files."

## HARD LEASH (SAFETY-CRITICAL — do NOT violate)
- CODE-ONLY. NEVER run `python -m lumen`, NEVER open the GUI/PyQt app, NEVER let
  it grab the X display or a WebGL/GPU context. In the past this has CRASHED and
  REBOOTED LO's AMD RX 5700 XT multi-monitor box.
- ALLOWED: edit/fix/harden modules, `pytest`, `flake8`, `mypy`, import-smoke ONLY.
  The app stays CLOSED.
- Safe liveness check: `python -m lumen.<mod> --self-test` — a headless probe
  returning exit 0 = PASS / 1 = FAIL, never touching X/WebGL or LO's config.

## WORKFLOW
1. ORIENT — find an UNCLAIMED module.
   - Read every `STATUS_*.md` in the repo root to see which sub-modules siblings
     claimed (snapshot in `references/lumen_swarm_notes.md`, but RE-CHECK live —
     the map drifts as the swarm progresses).
   - FIRST read the MASTER `STATUS_LUMEN.md`: it names the headline product risk
     (for LUMEN: "Lumen reboots LO's AMD box"). Ask which DEFENCE LAYER for that
     risk is ABSENT, then grep the `lumen/` package for that missing *logic*
     layer (config keys with no consumer, referenced-but-missing engine hooks).
     Targeting the missing layer of the #1 risk beats random gap-grepping; the
     existing layers are mapped in `references/headless_safety_and_mypy.md`.
   - Pick a module that is PURE (no PyQt/QWebEngine/X11/WebGL import) so it is
     fully headless-testable. If rendering is involved, isolate the pure logic.
2. BUILD — new file only, ADD-ONLY.
   - NEVER edit core/sibling files (`engine.py`, `shader.py`, `web.py`,
     `window.py`, `model.py`, `config.py`, `app.py`, `safety.py`,
     `lumen/__main__.py`, sibling `STATUS_*.md`, or another builder's module).
     Add new files: `lumen/<mod>.py` + `tests/test_<mod>.py`.
   - Make every time-dependent method accept an explicit `now` (seconds) and every
     RNG seeded, so tests are deterministic and never read the wall clock
     (`time.monotonic()` only inside the live path, never the test path).
   - Expose `self_test() -> (bool, str)` and a CLI
     `python -m lumen.<mod> --self-test` (see Pitfall #2 — test the exit code
     IN-PROCESS, not via subprocess).
   - For governor/action modules, separate the PURE decision (`govern(snap) ->
     List[Action]`) from a PURE effect-simulation (`apply_plan(snap, actions) ->
     Snapshot`) so idempotency `govern(apply(govern(x))) == []` and a CLI dry-run
     are both testable headlessly. Wrap noisy signals in a hysteresis
     `AutoTuner(window=N)` that acts only after N consecutive hits but acts at
     once on critical — patterns in `references/headless_safety_and_mypy.md`.
3. TEST — headless only.
   - `pytest tests/test_<mod>.py` green; `flake8` clean; `mypy` clean.
   - Run the FULL suite once (`pytest -q`) and confirm you ADDED tests with ZERO
     regressions. Attribute any pre-existing failures to siblings; do NOT fix
     core (that needs a master-sanctioned push).
4. STATUS — write `STATUS_<YOURNAME>.md` (contract in `templates/status_lm_template.md`):
   - Line 1: `[state: DONE|IN-PROGRESS|BLOCKED]`
   - PASS/FAIL board with REAL numbers as evidence (counts, exit codes, durations).
   - "what adds R / what to drop" list.
   - UNVALIDATED section for anything needing LO's real desktop (live GUI/WebGL).
   - Validate with `scripts/check_status.py STATUS_<YOURNAME>.md`.
5. LOOP — advance, re-test, update STATUS until DONE.

## PITFALLS (detail + fix recipes in `references/lumen_swarm_notes.md`)
- **Half-open interval overlap**: shared boundaries ABUT, they do NOT overlap
  (`06:00-12:00` and `12:00-18:00` are adjacent, not overlapping). Detect overlap
  with a minute-intersection, NOT endpoint-in-range (endpoint equality falsely
  fires). See the fixed `_overlaps` there.
- **CLI self-test exit-code test**: call the module's `_main(["--self-test"])`
  IN-PROCESS after monkeypatching the module global. A `subprocess.run([...,
  "-m", "lumen.<mod>", "--self-test"])` will NOT see the parent's monkeypatch and
  always reports pass. (First attempt at this failed exactly this way.)
- **Determinism**: inject `now` and `seed`; never call `time.time()`/
  `time.monotonic()` inside the test path.
- **Shuffle-bag randomizer > `random.choice`**: guarantees no immediate repeats
  and full coverage per cycle; seed for reproducibility. Pairs with a
  `randomize_now()` engine hook.
- **Conftest's offscreen QApplication makes in-process "no Qt" checks LIE**: the
  repo conftest builds a `QApplication` at session start, so `PyQt6` is ALREADY
  in `sys.modules` during any pytest run. An in-process "assert no PyQt loaded"
  test fails even for a pure module. Prove Qt-freeness in a FRESH subprocess
  instead (the `QT []` pattern) — recipe in `references/headless_safety_and_mypy.md`.
- **mypy fails on sibling type errors**: `from lumen import perf` drags the
  sibling into mypy's descent; a pre-existing gap in `perf.py` (or any sibling)
  shows up as YOUR error. Use `--follow-imports=silent` to bill your own file
  clean — recipe in `references/headless_safety_and_mypy.md`. Do NOT patch a
  sibling file (ADD-ONLY).
- **Collision avoidance — claims drift, re-check BOTH sources (and mid-session)**: before
  picking a gap, read every `STATUS_*.md` AND grep `lumen/*.py` for
  capability — a sibling may already own the "obvious" module. ALSO check whether CORE or a sibling ALREADY IMPLEMENTS the capability end-to-end — e.g. `config.py` has `migrate()` (schema upgrade) so a standalone `migration.py` would DUPLICATE core, and `manifest_lint.lint_library()` already lints every folder so a naive "library audit" wrapping it adds nothing. Pick a DISTINCT GAP (the UNRENDERABLE/EMPTY/ORPHAN catch, not a re-skin of lint). This cycle
  LM08 already owned `wallpaper_index.py` (= search / query / filter over
  the library), so building a "search engine" would have collided. Pick a
  DISTINCT gap. Dedup (`library_dedup.py`) was the pick — unclaimed,
  high-value, headless, zero core edits.
- **The map drifts WHILE you work (live swarm)**: other minis create files
  mid-session. Re-scan `lumen/*.py` and `tests/*.py` right before committing
  to a module — a candidate that "didn't exist 10 min ago" (e.g. another mini
  just created `library_dedup.py`, or `tests/test_hotkeys.py` appears
  mid-build) is now OWNED; pick a different gap. Use the full-suite failure
  list as a live "who is building what" signal:
  `pytest -q 2>&1 | grep -E "^(FAILED|ERROR)" | sed -E 's#tests/test_([a-z_]+)\.py.*#\1#' | sort | uniq -c`
  Any module there is actively touched — do NOT also edit it, and do NOT "fix"
  its failures. Confirm YOUR change adds ZERO failures
  (`grep -i <yourmod> /tmp/failures.txt` => empty); attribute the rest to
  siblings/concurrent swarm and report them. Do NOT fix core.
- **`write_file` to an EXISTING path SILENTLY SUCCEEDS (sandbox ADD-ONLY guard) — always `stat` + symbol-check before trusting a "new" file**: the agent sandbox enforces ADD-ONLY by REFUSING to overwrite an existing file, but `write_file`/the harness returns `success` WITHOUT changing the on-disk file (no error raised). If you pick a module name a sibling already owns, your `write_file` reports success while the disk still holds THEIR version — and your later `import`/tests import their symbols (this cycle: I wrote `lumen/preflight.py` but `from lumen.preflight import ModuleCheck` → `ImportError`, because the on-disk file was LM16's different AMD-safety-gate module). Fix/avoid: (1) BEFORE writing, `search_files` the repo for the target filename — if it EXISTS, the name is TAKEN; pick a DISTINCT name (pivoted to `benchmark.py`). (2) AFTER writing a possibly-existing path, `stat lumen/<mod>.py` and confirm size/mtime changed; if unchanged, the write was refused. (3) Sanity-import a symbol UNIQUE to your module (`from lumen.<mod> import <YourUniqueClass>`) and assert it resolves — if it raises, the file on disk isn't yours. This caught a phantom-file build before any damage.
- **Content-hash dedup: exclude the unique-id manifest + DON'T use a media
  whitelist**: when fingerprinting a wallpaper folder for duplicates, hash
  EVERY renderable file EXCEPT `lumen.json`/`project.json` (the manifest
  carries the unique `id`, so including it makes a renamed re-import hash
  DIFFERENTLY from the original — a false negative) and `preview.gif`
  (shared placeholder, causes false positives). A media-extension whitelist
  (`png/mp4/...`) MISSES shader entries (`.html`/`.glsl`), so enumerate
  all files and skip only the manifest + placeholder. See
  `references/dedup_content_hashing.md` for the recipe + deterministic tests.
- **`scan_library()` reads a MODULE-GLOBAL, not `config.LIBRARY_DIR`**: any
  module that WRITES into the library (creator/asset-ingest) and whose tests
  assert "created wallpaper shows up in `scan_library()`" must patch
  `lumen.wallpaper.model.LIBRARY_DIR` (module global), NOT
  `lumen.config.LIBRARY_DIR`. The latter does nothing — `scan_library` never
  re-reads config. See `references/creator_module_pattern.md`.
- **`.format()` + CSS/JS braces = `KeyError`**: when emitting an HTML/GLSL
  wrapper, `str.format(url=...)` chokes on literal braces like
  `body { margin: 0 }` -> `KeyError: 'margin'`. For a user URL, use the
  NATIVE URL entry (`kind="web", entry=url, is_url=True`) so the engine loads
  the URL directly — no local index.html. If you must template, escape braces
  as `{{`/`}}` or switch to `string.Template`. See
  `references/creator_module_pattern.md`.
- **Every produced wallpaper MUST be `is_renderable()`**: in a creator/asset
  module's `self_test()`, assert `wp.is_renderable()` for every generated
  `references/dedup_content_hashing.md` for the recipe + deterministic tests.

- **Read-only safety/boot-guard access — NEVER construct `BootGuard()`**: its
  `__init__` calls `_save()` and writes `~/.config/lumen/boot_guard.json`. To read
  safe-mode state, parse `GUARD_FILE` (from `lumen.safety`) directly with `json`.
  Conversely, calling sibling `lumen.safe_mode.self_test()` is SAFE to aggregate —
  it redirects `safety.GUARD_FILE` to a temp file and restores it in `finally`, so
  it never touches LO's real guard. Recipe in `references/diagnostics_module_pattern.md`.
- **`ProfileStore.load()` requires an explicit path**: calling it with no args is a
  `TypeError` (no default). For read-only access pass `str(DATA_DIR /
  "profiles.json")`; a missing file yields an empty store, never raises. Recipe in
  `references/diagnostics_module_pattern.md`.
- **Lazy `PyQt6` probe is leash-safe but breaks `ast.walk` Qt checks**: a
  best-effort `from PyQt6.QtCore import QT_VERSION_STR` INSIDE a function loads
  PyQt6 but does NOT open a display — allowed. A test that scans `ast.walk(tree)`
  for Qt imports will FALSE-POSITIVELY flag it; scan `tree.body` (top-level only).
  Snippet in `references/diagnostics_module_pattern.md`.
- **Config-drift guard test is a false positive**: `tests/test_config.py::
  test_no_config_key_drift_*` regex matches a LOCAL `cfg.get(...)` inside sibling
  `to_config()`/`from_config()` (scheduler.py, library_stats.py) — nested dicts,
  NOT app config. Not real schema drift; do NOT edit those siblings. Report under
  PRE-EXISTING, attribute to the config/core owner.

- **`lumen.wallpaper.model` transitively imports Qt — NEVER import it at
  module top**: `import lumen.wallpaper` (the package `__init__`) pulls in the
  engine, so `from lumen.wallpaper.model import Wallpaper, LIBRARY_DIR,
  scan_library` at top level loads ALL of PyQt6 + QtWebEngine + Xlib and FAILS
  the leash subprocess probe (`QT/XLIB:True`). Verified this cycle:
  `import lumen` and `import lumen.config` are clean, but `import
  lumen.wallpaper` is not. Fix: lazy-import the model INSIDE the one
  function that needs it (e.g. a renderability helper). The module then imports
  Qt-free; only that function pulls Qt at call time (fine under the offscreen
  conftest). See `references/library_integrity_repair.md`.
- **Hidden lint/mypy config — discover via terminal, not `search_files`**:
  LUMEN's `.flake8` is a HIDDEN file (narrow rules F821/F822/F823/F831/E9 +
  line-length <=100 convention) and mypy flags live in `pyproject.toml`
  (`--follow-imports=skip`). `search_files` does NOT index dotfiles, so a
  grep-for-config sweep returns nothing and you'll ship a 120-char line that
  "passes" your local check but the repo gate would fail. Read both via the
  terminal before assuming the lint rules.
- **Import-smoke: assert the EXACT `PULLED_QT:[]` token, not just "no PyQt"**:
  the basic leash probe prints `QT:False`, but a future sibling edit could add
  a lazy top-level `import Xlib` that slips past a weak check. Print the
  ACTUAL list of pulled top-level modules (blocked set `PyQt6/PySide6/Xlib/
  PySide2/PyQt5`) and `assert "PULLED_QT:[]" in stdout` from a fresh
  subprocess. See `references/safe_archive_transfer.md`.
- **Symlink fixtures for a library-scanning module must target OUTSIDE the
  library root**: a recursive `scan_entries`/library walk DOUBLE-COUNTS a
  symlinked subfolder whose real target lives INSIDE the root. Put the real
  target at `root.parent / "_real_..."` and symlink into it; also `mkdir(
  parents=True, exist_ok=True)` in fixtures (a bare `mkdir()` on a nested path
  is a `FileNotFoundError` that fails most tests). See
  `references/safe_archive_transfer.md`.
- **`Wallpaper(root, meta)` lies about renderability on the wrong root**: when
  you build `Wallpaper(root, meta)` for an `is_renderable()` check, pass the
  REAL scan root (not the global `LIBRARY_DIR`) and force `meta["id"] =
  folder.name`, otherwise `folder` / `preview_path` / `entry_path` resolve
  against the wrong directory and you get FALSE `non_renderable` findings on
  temp / non-library paths. `LIBRARY_DIR` is only correct for the live library.
- **mypy: `a or b` over `Optional` stays `Path | None`**: even after an
  earlier `if a is None and b is None: continue`, mypy cannot prove the later
  `x.read_text()` is safe, so it errors `union-attr`. Fix: after the
  `continue`, add an explicit `if manifest_path is None: continue` (or an
  `assert`) so the type narrows to `Path`.
- **Dataclass field/method NAME COLLISION (silent runtime corruption, no test
  catches it)**: if a dataclass declares BOTH a field and a method with the
  same public name (e.g. `max_webgl_surfaces: int = 1` AND
  `def max_webgl_surfaces(self)`), the METHOD overwrites the field's default
  slot — `__init__` stores the FUNCTION as the instance attribute. Call sites
  then either raise `"missing 1 required positional argument: 'self'"` or,
  worse, SILENTLY return the bound method (a callable) instead of the value,
  corrupting every downstream consumer. This shipped in `lumen/perfmon.py` and
  was invisible until a `--self-test` probed it — there were NO tests to catch
  it. Fix: keep the public protocol method names, back the value with a
  PRIVATE `_`-backed field, and have the method `return self._field`; for a
  SyntheticSource-style test double, accept the public kwargs via a custom
  `__init__` (so call sites are unchanged). General Python gotcha — scan any
  untested dataclass module for same-named field+method pairs before trusting
  it.
- **Importer/ingest modules WRITE via their OWN `LIBRARY_DIR` binding — patch THAT, not config's**: a module that does `from lumen.config import LIBRARY_DIR` binds the global into its OWN namespace (`lumen.<mod>.LIBRARY_DIR`), so redirecting `lumen.config.LIBRARY_DIR` or `lumen.wallpaper.model.LIBRARY_DIR` does NOTHING for it. In tests, `monkeypatch.setattr(lumen.<mod>, "LIBRARY_DIR", tmp)` (or `patch.object(imp, "LIBRARY_DIR", tmp)`). Verified this cycle with `lumen.importers.wallpaper_engine`: `tests/test_importers.py` patches `imp.LIBRARY_DIR` for exactly this reason. (`scan_library` separately reads `model.LIBRARY_DIR` — a DIFFERENT global; keep the two patch targets straight.)
- **Import modules MUST guarantee `is_renderable()` AND clean up dead entries**: any module that WRITES a library manifest (importer/ingest, not just creator) must, after writing `lumen.json`, build `Wallpaper(root, meta)` and assert `is_renderable()`; on False, `shutil.rmtree(dest)` then raise `ValueError` (or return `None`) so a pathological source can never leave a silent white/black void in the Library. The renderable-guard in `creator.py` is the template; `importers/wallpaper_engine.py` now mirrors it for `import_pkg` / `import_we_project`. Keep `detect_kind()` (a metadata-only quick guess, often test-locked) SEPARATE from the on-disk planner (`_plan_import`) that actually inspects files — do NOT mutate the locked `detect_kind` contract to add scene->shader logic; add a second function instead.
- **Nested pack media -> store RELATIVE posix entry paths**: Wallpaper Engine (and other) packs nest files under a subfolder. Discover media top-level-first then `rglob`, and store `entry`/`preview` as `p.relative_to(dest).as_posix()` (e.g. `"v/clip.mp4"`), so `Wallpaper.entry_path`/`preview_path` resolve it under `folder/`. A bare top-level `p.name` breaks for nested packs (entry resolves to a missing top-level file -> non-renderable).
- **One broken collection aborts the WHOLE suite — isolate with `--ignore`**: another builder's test with an `ImportError` (e.g. `tests/test_preflight.py` importing a symbol `ModuleCheck` that doesn't exist in `lumen.preflight`) makes bare `pytest` error at COLLECT and report 0 real results. To get YOUR regression number, run `pytest -q --ignore=tests/<broken>.py`; confirm the broken test doesn't import your module (`grep -c "<yourmod>" tests/<broken>.py` == 0) and DON'T fix the other builder's module (out of your ADD-ONLY lane, may be in-flight). Report it as EXTERNAL.

- **Hardware-profiling add-only modules (GPU sensor) — funnel ALL probing through ONE `_detect_raw()`, strip DISPLAY from subprocesses, degrade don't crash**: when you build a module that profiles real hardware (e.g. a GPU/WebGL capability profiler feeding the fragment budget into `recommend`/`auto_tune`), keep it 100% displayless + Qt-free. (1) Funnel every read into a single `_detect_raw()` that reads `/sys/class/drm/card*/device/{vendor,device,driver,mem_info_vram_total}` (AMD VRAM) and DRM connectors (`card*/card*-*/status` + `modes` for multi-head pixel load) and runs `lspci -nn` — both are displayless and need no GPU context. (2) **Strip DISPLAY when shelling out**: `subprocess.run([lspci,'-nn'], env={k:v for k,v in os.environ.items() if k!='DISPLAY'})` so even a tool that *could* open a display cannot. (3) Guard every read (`FileNotFoundError`/`PermissionError`/`OSError`/`SubprocessError`) and on a Qt-less/container box return `{}` — then `build_profile({})` degrades to a conservative LOW fallback (never crash, never open a display). (4) Map known GPUs through a capability TABLE → tier (`fragment_budget`, `surface_cap`, `recommended_dpr`, `max_texture_size`, `webgl_version`, `vram_mb`) with per-vendor + last-resort fallback. The headline `fragment_budget` (frag/s) drops straight into `lumen.perf.gpu_fragment_load` / `gpu_budget_report` / `recommend.auto_assign` (same unit) — so the profiler replaces the OLD config-guess budget with a real one. Full recipe in `references/hardware_profiling.md`.

- **`lspci -nn` parsing: the first `[xxxx]` bracket is the PCI CLASS code, not the `[vendor:device]` id**: a VGA line looks like `00:02.0 VGA compatible controller [0300]: ... [1002:731f] (rev c1)`. The leading `[0300]` is the class code (VGA = 0300) and has NO colon; the real PCI id is `[1002:731f]` (has a colon). A naive `line.find('[')` parse grabs `[0300]` and yields a bogus vendor/device. Fix: regex `\[([0-9a-fA-F]{4}):([0-9a-fA-F]{4})\]` to capture the `vid:did` token; for the model name, drop the bus id + the `[vid:did]` token + the `[nnnn]` class code, take the text after the first ':', strip `(rev cN)`, and KEEP the remaining `[...]` brackets (they hold the descriptive name like 'Radeon RX 5700 XT'). Verified on LO's real box: correctly fingerprinted AMD Navi 10 RX 5700 XT (device 0x731f) → HIGH tier, 900M frag/s, 4 surfaces. See `references/hardware_profiling.md`.

- **Additive seam into your OWN module = allowed, low-risk**: to make a new module useful without editing siblings, add a NEW function to a module YOU already own that lazily imports the new module and falls back. Example: `recommend.profile_from_capability()` does `try: from lumen.capability import profile ... except Exception: return profile_from_config(...)` — it feeds the real `capability.fragment_budget`/`surface_cap`/`recommended_dpr` into the `HardwareProfile`, while staying backward-compatible (existing `recommend` API + its 9 tests unchanged). Adding a function to your own module is within ADD-ONLY; editing a SIBLING's module is not.
 - **Headless FPS/verdict modeling — use DELIVERED rate, not the raw vsync-skip counter**: when you simulate a render loop headlessly (benchmark / what-if / preflight / recommend extension), do NOT count "every vsync that fires while a draw is still running" as a drop — a 30fps-on-60Hz wallpaper SKIPS every other vsync BY DESIGN (normal pacing, not a dropped frame), so a naive skip counter reports ~50% "drop rate" for a perfectly smooth asset. Derive the verdict from `delivered_fps = min(target, 1000/draw_cost_ms)` and `drop_rate = (target - delivered)/target` — the metric a user actually feels. Full model (fragment load `w*h*dpr^2*fps`, box throughput T = capacity_surfaces × one 1920×1080@30 surface, `draw_cost_ms <= 1000/fps` SMOOTH rule, `safe_fps = floor(T/(w*h*dpr^2))`, SMOOTH/DEGRADED/UNUSABLE thresholds) in `references/headless_fps_estimator.md`, shipped as `lumen/benchmark.py`.

 - **`python -m lumen.<mod> --self-test` loads the loader as `__main__` (a 2nd copy) — anchor base classes on the plugin module's OWN symbol**: when a loader discovers plugins by `issubclass(attr, Plugin)` using the loader's own `Plugin`, running `python -m lumen.<mod>` imports `lumen.<mod>` TWICE (once as the package, once as `__main__`), so a plugin that does `from lumen.plugin_loader import Plugin` binds a DIFFERENT `Plugin` object than the loader's `__main__.Plugin` — and every valid plugin is REJECTED (the `--self-test` fails ONLY because of how it was invoked, not because the logic is wrong). Fix: anchor the base on `getattr(module, "Plugin", None)` (the symbol the plugin module itself imported) and `cast(Type[Plugin], ...)` for mypy. Verified this cycle on `lumen/plugin_loader.py`: `self_test()` passed on import but FAILED under `python -m`; after the fix `python -m lumen.plugin_loader --self-test` => `RESULT: PASS`. (Distinct from the "CLI self-test exit-code test" pitfall — that one is about subprocess not seeing the parent monkeypatch; this one is about the loader importing a duplicate copy of itself.)

- **Project is now SATURATED — re-scan for real gaps, don't assume one exists**: as of
  2026-07-12 the additive surface is essentially complete — 66–67 gate modules all
  GREEN, 45+ bundled shader samples + web/video samples, and the major missing-link
  orphans (perfmon, library_dedup, capability, autostart, archive_transfer,
  benchmark, hardware-profiling) are all built + tested. Gap-scanning now mostly
  finds (a) already-owned modules, or (b) saturated-sample redundancy. The TWO
  genuinely remaining deploy-gate tasks are: (1) deep BUNDLED-SAMPLE lint — shipped
  as `lumen/sample_health.py` (composes the public `lint_wallpaper`/`lint_manifest`,
  Qt-free at import via lazy lint imports; runs the same deep white-screen check the
  runtime would over every bundled sample; `tests/test_sample_health_integration_ws4.py`
  bakes it into CI); and (2) a MASTER-COORDINATED `lumen.AppImage` rebuild (see rebuild
  pitfall). Before building, confirm a DISTINCT gap still exists — a 46th shader
  sample is clutter, not value.

- **`/tmp` per-user QUOTA (EDQUOT) silently eats the full-suite log**: this box
  enforces a per-user /tmp quota (~257M observed); a full `pytest -q` run writes
  enough to /tmp to hit `Errno 122` and the background-process log is LOST (no
  failures captured — looked like a clean pass). Fix: set `TMPDIR=/home/hunter/.cache/<uniq>`
  AND redirect the run output to a home path, e.g.
  `TMPDIR=/home/hunter/.cache/lumen_test5 .venv/bin/python -m pytest -q 2>&1 | tee /home/hunter/ws4_full.log`.
  Same applies to any pytest run that writes temp files (~400G free under /home/hunter).

- **`headless_gate --self-test` (GREEN) ≠ full `pytest -q` (may show reds)**: the
  deploy gate is `python -m lumen.headless_gate --self-test` — it runs each gate
  module's `self_test()` and reports e.g. `67 passed / 0 failed / 67 total, result
  PASS`. The full `pytest -q` additionally runs every `tests/test_*.py` and WILL show
  RED on SIBLING-OWNED in-flight edits (this session: `test_advisor_assets_cli.py`
  TypeError on a changed AssetCache kwarg, `test_config.py` config-drift guard
  false-positive, `test_library_dedup_report_ws4.py` KeyError on an in-flight sibling
  edit) — these are NOT gate breaks and NOT your regression. Confirm with
  `grep -c <yourmod> tests/test_<failing>.py` == 0 and report them as PRE-EXISTING.
  The gate being GREEN is the authoritative deploy signal.

- **AppImage rebuild is MASTER-COORDINATED, not a solo build**: a fresh `lumen.AppImage`
  needs the network (downloads deps), can spike RAM on this memory-tight box (OOM
  risk), and the build DELETES the live `lumen.AppImage` LO may be actively testing —
  a failed/aborted rebuild leaves LO without a working artifact. The gate is ALREADY
  GREEN (the current 248 MB artifact, built 2026-07-12 ~16:24, boots without reboot),
  so a rebuild is a carry-along to ship new additive modules/samples, NOT a blocker.
  Coordinate with master (ENI_LUMEN) and wait for sibling source mtimes to stabilize
  before rebuilding. Do NOT delete/rebuild the live artifact unilaterally.

## MODULE-SHAPE & TOOLING PITFALLS(learned after the hotkeys/global-shortcut pass)
- **Lazy-import display / optional backends so import stays Qt/X-free**: if a
  module needs a real display (X11 global key grabs via Xlib, etc.), NEVER
  `import Xlib` at module top — that pulls Xlib into `sys.modules` on import and
  fails the leash probe. Instead define the backend class but put
  `from Xlib import X, display` INSIDE `__init__`, and only CONSTRUCT it lazily
  through a `_make_x11_backend()` resolver called from `start(backend="x11")`.
  Tests use a `FakeBackend`; the X11 path is then only ever built on LO's real
  desktop. Worked skeleton in `references/lazy_display_backend.md`.
- **mypy: loop-variable reuse is a type error, and the cache lies**: reusing a
  loop variable name (e.g. `for bad in (...):` then later `bad = [...]`) makes
  mypy infer the name's type from the loop and reject the later reassignment
  ("Incompatible types in assignment"). Rename the loop var. Also: after editing
  a file, `mypy`'s incremental cache can report a STALE line/error that no
  longer exists — `rm -rf .mypy_cache` and re-run to get the truth.
- **Canonicalize user-facing strings SEMANTICALLY, not by identity**: when a
  module has both `parse` and `format`, `format(*parse(raw)) == raw` is FALSE if
  parsing normalizes aliases/order (e.g. "Super+Shift+A" reorders to
  "Shift+Super+A"; "Win+R" -> "Super+R"). Test the round-trip by RE-PARSING:
  `parse(format(*parse(raw))) == parse(raw)`, and assert `format` is idempotent.
  Comparing raw==formatted hides a real canonicalization you WANT.
- **importlint is a 4th gate**: the swarm task requires it. `python -m importlint
  check <file>` (fire CLI: `check`/`fix` subcommands) flags star-imports and
  reports import-ordering diffs; rc=0 + no output = clean. Run it on module +
  test (see cheat-sheet).
- **Classify pre-existing failures precisely**: when the full suite shows
  failures you didn't cause, PROVE they're unrelated: (a) `grep -c "<yourmod>"
  tests/test_<failing>.py` must be 0 (the failing test doesn't import your
  module); (b) you never edited that module. A `NotADirectoryError:
  '/dev/null/...'` is ENVIRONMENTAL (the box's /dev/null isn't a writable dir),
  NOT a logic defect — don't chase it. Report them under PRE-EXISTING in STATUS.

## TESTING A MODULE WITH EXTERNAL-COMMAND SIDE-EFFECTS (autostart pattern)
When auditing a module that WRITES real user files or SHELLS OUT on the live box
(e.g. `lumen/autostart.py`: writes `~/.config/autostart/lumen.desktop`, a systemd
user unit, and runs `systemctl --user enable lumen.service`), the leash extends to
the TEST run — a naive test would mutate LO's real login session. Neutralize ALL
side-effects in a fixture before calling the module:
- Redirect module write-target GLOBALS into `tmp_path`:
  `monkeypatch.setattr(mod, "AUTOSTART_DIR", tmp/…)` (the path helpers read the
  global at call time, so this reroutes every write).
- Kill the shell-out by controlling its trigger, not just mocking the call: the
  systemd branch fires only when `shutil.which("systemctl")` AND `XDG_RUNTIME_DIR`
  are both truthy — default the fixture to `which -> None` + `delenv XDG_RUNTIME_DIR`
  so it's skipped, then in the ONE positive test flip both and
  `monkeypatch.setattr(subprocess, "run", fake)` (the module does `import subprocess`
  inside the function, so patch the real `subprocess` module object — the in-function
  import returns the cached, patched module).
- `resolve_exec()`-style resolvers: patch `mod._appimage_candidates`/`shutil.which`
  to test the 3-tier order deterministically instead of depending on the real FS.
This closed the last non-core untested-module gap (autostart, 19 tests) with a PURE
test add and zero module edits — do NOT add a `--self-test` CLI to a shipped sibling
module unless you own it (that's a module edit, out of the ADD-ONLY lane).

## LEASH VERIFICATION (prove it, don't just assume it)
Running pytest under `QT_QPA_PLATFORM=offscreen` is necessary but NOT proof of
compliance on its own. Two cheap, decisive checks (full recipe + the rpc.py
case study in `references/leash_and_audit.md`):
- **No QApplication from YOUR tests**: `tests/conftest.py` monkey-patches
  `QApplication.__init__` and prints, in the session footer, a header
  `QApplication created by (in order)` followed by the name of every test that
  constructed one. That header prints on EVERY run. A violation is ONLY when
  test names are LISTED under it — if the list is empty you're clean. Inspect
  with `pytest ... -q 2>&1 | sed -n '/QApplication created by/,$p'`.
- **YOUR module pulls no Qt**: the conftest imports PyQt6 itself (harness
  plumbing), so a `grep` of `sys.modules` from inside the test process is
  unreliable. Prove the MODULE is clean with a subprocess:
  QT_QPA_PLATFORM=offscreen DISPLAY= .venv/bin/python -c "import sys, lumen.<mod>; bad=any(m.split('.')[0] in ('PyQt6','PySide6','Xlib') for m in sys.modules); print('QT/Xlib:' + str(bad))"
  # NOTE: also assert Xlib is ABSENT at import. A module with a lazy X11
 # backend MUST only import Xlib inside a function, never at module top —
 # otherwise this prints QT/Xlib:True and fails the leash. Recipe in
 # references/lazy_display_backend.md.
 and assert `QT:False`.
 - **Stronger variant — block Qt imports at the source**: temporarily replace
 `builtins.__import__` with a guard that raises `ImportError` for
 `PyQt6/PySide6/PySide2/PyQt5/Xlib`, then `import lumen.<mod>` and run
 `lumen.<mod>.self_test()` — it must STILL import and return `(True, ...)`.
 This proves leash-safety even against a hypothetical future lazy top-level
 import that the basic `QT:False` probe (which only checks what got imported)
 would not catch. `lumen/benchmark.py` passes this test.

 ## AUDITING AN UNTESTED ADD-ONLY MODULE(high-value alternative to build-from-scratch)
A shipped `lumen/<mod>.py` that has NO `tests/test_<mod>.py` and a RED
`--self-test` is a top gap and zero-collision (you only ADD a test file + a
minimal fix). Workflow:
1. Run `python -m lumen.<mod> --self-test`. If it exits 1, read the traceback —
   there is a real latent defect to fix.
2. Fix minimally; harden so the failure class can't recur (e.g. accept both a
   method and an attribute shape of a returned value).
3. Write `tests/test_<mod>.py` as a real pytest suite (real socket / injected
   fakes) locking every branch + error code + degradation path.
4. Run flake8 + mypy + importlint + the two leash checks above.
See `references/leash_and_audit.md` (rpc.py `status()`/attribute
collision case study) for the worked pattern. Worked case study:
`references/perfmon_adoption.md` — `lumen/perfmon.py` was the HIGHEST-VALUE
orphan because `auto_tune.govern()` and `stability_report.simulate()` both
CONSUME a `PerfSnapshot`, but nothing produced one from the live box and there
were zero tests. Adopting it = harden the orphan + write `tests/test_perfmon.py`
(30 tests) — a pure ADD (test file + minimal in-module fix), zero core edits.
The "missing link" gap (a type that is REFERENCED by siblings but never
CONSTRUCTED/TESTED) is the richest audit target; when resuming with your
assigned module already `[state: DONE]`, this scan beats random gap-grepping
and is the fastest route to the next highest-value ADD-ONLY task.

## VERIFICATION CHEAT-SHEET (repo has a `.venv` with pytest 9.x — use it)
```
cd ~/Desktop/apps/lumen
.venv/bin/python -c "import lumen.<mod>"            # import-smoke (no GUI)
.venv/bin/python -m lumen.<mod> --self-test         # liveness (exit 0)
.venv/bin/python -m pytest tests/test_<mod>.py -q   # unit suite
.venv/bin/python -m flake8 lumen/<mod>.py tests/test_<mod>.py
.venv/bin/python -m mypy lumen/<mod>.py --ignore-missing-imports   # add the flag if the module has LAZY optional imports (e.g. Xlib); otherwise plain
.venv/bin/python -m importlint check lumen/<mod>.py tests/test_<mod>.py   # 4th gate: star-imports + import ordering, rc=0 = clean
.venv/bin/python -m pytest -q                       # full-suite regression
python scripts/check_status.py STATUS_<YOURNAME>.md
```

## SUPPORT FILES
- `references/lumen_swarm_notes.md` — claimed-module snapshot (2026-07-11) + the
  two coding pitfalls with fix recipes.
- `references/lazy_display_backend.md` — the lazy-import display/X11 backend
  pattern (X11Backend + `_make_x11_backend()` resolver + FakeBackend + self_test
  CLI) so a module with real-display needs stays Qt/X-free at import.
- `references/headless_safety_and_mypy.md` — Qt-freeness proof (conftest
  QApplication pitfall), `mypy --follow-imports=silent` for sibling errors, the
  three-tier static/reactive/proactive stability architecture, the
  "target the missing layer of the #1 risk" gap strategy, and reusable
  decision/effect-simulation + hysteresis design patterns.
- `references/leash_and_audit.md` — COMPANION to the above: the subprocess
  `QT:False` import probe (proves YOUR module, not the conftest, is Qt-free),
  the audit-an-untested-add-only-module workflow + rpc.py `status()`/attribute
  collision case study, and live-swarm collision detection (re-scan for
  newly-appearing files + the full-suite failure-tally grep).
- `templates/status_lm_template.md` — copy for every STATUS_<NAME>.md.
- `references/dedup_content_hashing.md` — content-hash dedup recipe (skip the
  unique-id manifest + shared placeholder; enumerate all files) + deterministic
  tmp_path tests. Referenced by the dedup Pitfall.
- `scripts/check_status.py` — asserts a STATUS file has the required sections.
- `references/creator_module_pattern.md` — worked case study for a library-WRITING
 add-only module (native URL entry, `model.LIBRARY_DIR` patch target, the
 `.format()`-vs-braces trap, ID sanitization, collision policy, manifest fields).
- `references/importer_module_pattern.md` — worked case study for HARDENING a library-WRITING import/ingest module (the renderable guarantee + dead-entry cleanup, the module's OWN `LIBRARY_DIR` binding as the test patch target, `_plan_import` vs test-locked `detect_kind`, nested-media relative posix paths, and a leash subprocess that redirects `LIBRARY_DIR` to tmp so it never pollutes `~/.local/share/lumen`).
- `references/diagnostics_module_pattern.md` — read-only access recipes for
  safety/guard (`GUARD_FILE` direct parse, don't construct `BootGuard`;
  `safe_mode.self_test()` is safe to aggregate), profiles (`ProfileStore.load()`
  needs a path), the leash-safe lazy-Qt `ast.body` test, and the config-drift
  false-positive guard.
- `references/library_integrity_repair.md` — the library-integrity / repair
  ADD-ONLY module pattern (scan / build_repair_plan / repair(dry_run) /
  escape-confined writes / `.bak` backup / duck-typed `StatStore`
  integration) PLUS the three gotchas above (`lumen.wallpaper.model` Qt
  transitive import; wrong-root `is_renderable()`; mypy `a or b` union-attr)
  as a copy-ready recipe for the next library-hygiene module.
- `references/hardware_profiling.md` — the leash-safe GPU/WebGL capability
  profiler pattern: the `_detect_raw()` funnel, `/sys/class/drm` reads, the
  `lspci -nn` class-code-vs-vendor:device parsing GOTCHA (+ DISPLAY-strip
  recipe), the capability TABLE + fallback chain, and the additive-seam
  pattern (extend your OWN module with a lazy-import fallback function).
- `references/safe_archive_transfer.md` — the zip-slip-proof, integrity-checked
  `.tar.gz`/`.tar.xz` bundle EXPORTER/IMPORTER recipe (transport module, NOT a
  library writer): `tarfile` NEVER `extract(path=...)`, stream members into
  resolve()-validated paths, manifest `integrity_sha256`, corrupted-manifest
  clean `BundleError`, the mypy `tarfile.open` mode-Literal typing + `extractfile`
  None-narrowing gotchas, `zstandard` unavailable (gzip/xz only), default
  `dry_run` import with force-rollback, Workshop symlink deref, the stricter
  `PULLED_QT:[]` import-smoke denylist, and the symlink-target-outside-root
  test-fixture pitfall.
- `references/perfmon_adoption.md` — the "consume-but-never-produce" orphan
  adoption case study: `perfmon.py` was the missing live `PerfSnapshot` source
  for `auto_tune`/`stability_report`; how it shipped a silent dataclass
  field/method collision, how to harden + test it headlessly via a
  `SyntheticSource` test double (no core edit), and the regression/leash proof.
- `references/headless_fps_estimator.md` — the headless per-wallpaper FPS /
  drop-rate model: fragment load `w*h*dpr^2*fps`, box throughput T =
  capacity_surfaces × one 1920×1080@30 surface, the `draw_cost_ms <= 1000/fps`
  SMOOTH rule, `safe_fps = floor(T/(w*h*dpr^2))`, the SMOOTH/DEGRADED/UNUSABLE
  thresholds, and the **vsync-skip counter pitfall** (30fps-on-60Hz skips vsync
  by design → use delivered-rate, not raw skip count). Shipped as
  `lumen/benchmark.py`.
