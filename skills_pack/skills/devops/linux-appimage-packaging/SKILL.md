---
name: linux-appimage-packaging
description: Build, verify, and ship a self-contained Linux AppImage for a Python (PyQt6/PySide/Tk/CLI) desktop app WITHOUT linuxdeploy. Covers offline venv bundling, appimagetool .desktop validation pitfalls, pure-stdlib icon generation, Flatpak manifest, and a headless launch test harness.
---

# linux-appimage-packaging

## When to use
- You must distribute a Python GUI/CLI app as a single `.AppImage` that runs on a clean Linux box with no Python installed.
- The app uses a venv with pandas/numpy/sklearn/PyQt6 etc.
- You specifically must NOT use `linuxdeploy` (it cannot locate a venv-bundled PyQt6).

## Support files (on-disk inventory)
Ready-to-copy templates/scripts (EXIST on disk):
- `templates/app.desktop` — .desktop file template for AppDir
- `templates/test_packaging_data.py` — pytest that validates pyproject package-data globs
- `templates/AppRun_selfheal` — crash-resilient launcher with restart budget
- `references/deb_packaging.md` — Debian .deb build recipe + 4 traps
- `references/pyqt6_webengine_appimage.md` — LD_LIBRARY_PATH + plugin-path fix
- `references/build_script_setu_unbound_var.md` — set -u trap fix
- `references/bundled_python_pyvenv_cfg.md` — pyvenv.cfg host-fallback fix
- `references/setuptools_package_data_subpackages.md` — subpackage collision + TOML quoted-key fix
- `references/appimage_deploy_gate.md` — data-asset deploy-gate recipe
- `references/self_healing_apprun.md` — crash-resilient launcher detail
- `references/pyqt6_headless_pytest.md` — modal-dialog freeze fix

Described inline in this SKILL.md (recipes are complete, copy from here or generate from the body):
- `templates/build_appimage.sh` — the full offline venv-bundling build script (see Core recipe below)
- `templates/AppRun` — the launch script with PVER + LD_LIBRARY_PATH + QT plugin wiring (see AppRun section below)
- `templates/org.example.App.yaml` — Flatpak manifest skeleton (see Flatpak section below)
- `templates/test_packaging.py` — verification contract test suite (see Verification contract below)
- `scripts/make_icon_stdlib.py` — pure-stdlib RGBA PNG generator without PIL
- `references/appimage_pitfalls.md` — compiled from the Pitfalls section below

## Core recipe (offline-safe)
Bundle the project's EXISTING venv (no network) instead of re-pip-installing:

1. `mkdir -p AppDir/usr/{bin,lib} AppDir/usr/share/<app>`.
2. Copy the venv interpreter:
   `cp "$(readlink -f $VENV/bin/python3)" AppDir/usr/bin/python3; chmod +x AppDir/usr/bin/python3`.
   **Also write `AppDir/usr/bin/pyvenv.cfg`** (see Pitfalls — missing it makes the bundled interpreter fall back to the HOST site-packages, importing an editable `<app>` from SOURCE and a possibly-incomplete host PyQt6). The marker pins `sys.prefix` to the bundle and sets `include-system-site-packages = false`.
3. Copy site-packages **dereferencing symlinks** (venv has symlinks into base Python):
   `cp -rL "$VENV/lib/python$PVER" AppDir/usr/lib/python$PVER`.
4. Compute `$PVER` at RUNTIME inside `AppRun` from the bundled interpreter:
   `"$HERE/usr/bin/python3" -c 'import sys;print("%d.%d"%sys.version_info[:2])'`.
5. Strip `__pycache__`, `*.pyc`, and `pip/setuptools/wheel` from site-packages.
6. Copy source trees (root `*.py`, `swarm/`, `samples/`, …) into `AppDir/usr/share/<app>`.
7. Add `AppRun`, `<app>.desktop`, and an icon.
8. `appimagetool AppDir <out>.AppImage`.

Full working template: `templates/build_appimage.sh`.

## AppRun (launcher)
Sets env so the bundled interpreter finds its own stdlib/site-packages AND PyQt6 Qt plugins.
Template: `templates/AppRun`. Key lines:
```
PVER=$("$HERE/usr/bin/python3" -c 'import sys;print("%d.%d"%sys.version_info[:2])')
export DEMIURGE_HOME="$HERE/usr/share/<app>"        # app resolves its data dir
export LD_LIBRARY_PATH="$HERE/usr/lib/python$PVER/site-packages/PyQt6/Qt6/lib:$HERE/usr/lib:${LD_LIBRARY_PATH:-}"
export PYTHONPATH="$HERE/usr/lib/python$PVER/site-packages:$HERE/usr/share/<app>:$HERE/usr/share/<app>/swarm/L1_dashboard:${PYTHONPATH:-}"
export QT_QPA_PLATFORM_PLUGIN_PATH="$HERE/usr/lib/python$PVER/site-packages/PyQt6/Qt6/plugins"
exec "$HERE/usr/bin/python3" "$HERE/usr/share/<app>/main.py" "$@"
```

## Self-healing AppRun (crash-resilient launcher)
For a GUI/desktop app that must NEVER silently die, make `AppRun` a restart
loop instead of a one-shot `exec`. Two layers:
1. **In-process:** a Python `supervise()` that relaunches the UI on any
   uncaught exception / non-zero exit (bounded budget, e.g. 5).
2. **Process-level:** the `AppRun` bash `while` loop relaunches the child even
   on a hard segfault outside Python (the Python supervisor can't catch those).

AppRun runs the app with a flag like `--no-supervise` so the SHELL loop is the
single process-level restart authority (don't let the Python supervisor also
relaunch at the process level — pick one owner per layer). Copy
`templates/AppRun_selfheal` and set `APP_MODULE` + `RESTART_BUDGET`.

PITFALL — **`set -e` KILLS a self-heal loop.** A wrapper whose whole job is to
relaunch a failing child must NOT have `set -e`: the first non-zero child exit
aborts the script instead of looping. Use `set -u` only. Verified: with
`set -e` it died after 1 restart; with `set -u` it ran the full budget (5) then
exited 1 with a clear "exceeded restart budget" message.

FALLBACK for system-wide Qt/PyQt6: if PyQt6 is installed at
`/usr/lib/python3/dist-packages` (NOT in your venv) and you do NOT bundle Qt,
append it to `PYTHONPATH` so the AppImage runs on the box without bundling the
Qt libs:
```
export PYTHONPATH="$PYTHONPATH:/usr/lib/python3/dist-packages"
```
(The bundled interpreter still needs its own stdlib/site-packages first; this
fallback is additive.) `PyQt6.QtWebEngineWidgets` is frequently absent even
when `PyQt6` is present — don't embed a browser; open dashboards in the system
browser instead.

Full recipe, the validated `set -u` loop, and a no-GUI verification trick:
`references/self_healing_apprun.md`.

## Pitfalls (learned the hard way)
Full detail in `references/appimage_pitfalls.md`. Highlights:
- **appimagetool validates the `.desktop` file and FAILS the whole build on invalid `Categories`.** "Trading" is NOT a registered category. "Finance" is only *supplementary* and REQUIRES a MAIN category (e.g. `Office`, `Utility`). Use `Categories=Office;Finance;`. Non-standard categories must be prefixed `X-`. Without a valid main category the build dies with `Desktop file contains errors`.
- **appimagetool is often NOT on PATH.** Check `/home/hunter/.local/bin/appimagetool`, then `/tmp/appimagetool`, else download the continuous release. (Technique, not a hard rule.) Prefer an on-PATH `appimagetool` (copy it to `/tmp/appimagetool`) over re-downloading. **FUSE fallback:** `appimagetool` is itself an AppImage and needs FUSE to run directly; on a FUSE-less host the direct run fails. Guard it: `if ! "$APPIMAGETOOL" "$APPDIR" "$OUT"; then TMPAT="$(mktemp -d)"; ( cd "$TMPAT" && "$APPIMAGETOOL" --appimage-extract >/dev/null 2>&1 ); "$TMPAT/squashfs-root/AppRun" "$APPDIR" "$OUT"; rm -rf "$TMPAT"; fi`. The happy path is unchanged; the fallback only triggers on failure.
- **Don't re-pip if you can copy the venv** — offline and deterministic.
- **Icon without PIL:** generate a valid RGBA PNG with stdlib `zlib`+`struct` so the bundled interpreter (which may lack Pillow) can regenerate it. Script: `scripts/make_icon_stdlib.py`.
- **Repo-root resolution in nested tests:** a test at `<root>/swarm/B4_package/test_x.py` needs **2** `dirname`s to reach `<root>`, not 3. Off-by-one makes every path resolve to the parent of the real root and ALL file checks fail.
- **Packaging-staging tests must resolve APPDIR location-robustly (root vs in-snapshot).** A test that asserts `build/AppDir/usr/share/<app>/<mod>.py` exists passes from the repo root but FAILS when the test file is copied INTO the AppDir snapshot (the relative path resolves to the snapshot copy, or to a non-existent original). Derive APPDIR with a candidate/root fallback: `_CANDIDATE = os.path.join(ROOT, "build", "AppDir", "usr", "share", "<app>"); APPDIR = _CANDIDATE if os.path.isdir(_CANDIDATE) else ROOT`. Assert the staged files relative to `APPDIR`. This makes the SAME test green both at repo root and inside the extracted snapshot (proven on the SB1 mean-reversion packaging test — was RED inside the snapshot, fixed with the fallback).
- **setuptools subpackage `package-data` collision (Lumen 2026-07-12):** when a subpackage (e.g. `lumen.ui`) carries data files (qss/png/samples/web templates), the parent package's `ui/*.qss` glob **silently fails to bundle them** — the build's `assert_asset` deploy-gate catches it (`'ui/styles.qss' missing from bundled lumen`). Fix: add a per-subpackage key `"lumen.ui" = ["*.qss","assets/*"]`. CRITICAL TOML trap: you cannot write `lumen = [...]` (list) AND `lumen.ui = [...]` (collides → `Cannot mutate immutable namespace`); the subpackage key MUST be QUOTED: `"lumen.ui" = [...]`. Full recipe + verify: `references/setuptools_package_data_subpackages.md`.
- **PyQt6/PyQt6-WebEngine AppImage needs `PyQt6/Qt6/lib` on `LD_LIBRARY_PATH` (Lumen 2026-07-12, the #2 LUMEN build failure).** Modern PyQt6 wheels install Qt into `site-packages/PyQt6/Qt6/` (NOT the legacy `PyQt6/Qt/`). If `AppRun` only sets `LD_LIBRARY_PATH="$HERE/usr/lib"` and `QT_QPA_PLATFORM_PLUGIN_PATH=.../PyQt6/Qt/plugins`, the Python modules import but the NATIVE libs can't resolve → `ImportError: libQt6WebChannel.so.6: cannot open shared object file` at `from PyQt6.QtWebEngineWidgets import QWebEngineView`. FIX: set `LD_LIBRARY_PATH` to include `.../site-packages/PyQt6/Qt6/lib` AND `QT_QPA_PLATFORM_PLUGIN_PATH` to `.../PyQt6/Qt6/plugins`. This applies when you SPLIT site-packages into `usr/lib/python$PVER/site-packages` (not the whole-`.venv` B4 approach, where Qt resolves automatically under `.venv`). Also apply the SAME `LD_LIBRARY_PATH`/`QT_QPA_PLATFORM_PLUGIN_PATH` exports to any OFFSCREEN import-smoke you run against the extracted artifact — the smoke runs the artifact python DIRECTLY (not via AppRun), so AppRun's env does not apply and the lib path must be set inline. Full recipe: `references/pyqt6_webengine_appimage.md`.
- **`set -euo pipefail` build script + offscreen import-smoke `LD_LIBRARY_PATH` unbound-var (Lumen 2026-07-12, #3 LUMEN build failure).** The build script runs under `set -euo pipefail`. Its OFFSCREEN import-smoke runs the artifact's python DIRECTLY (not via AppRun) as a command-prefix assignment: `LD_LIBRARY_PATH="$EXROOT/.../Qt6/lib:${LD_LIBRARY_PATH}" ... python3 -c "import ..."`. That `${LD_LIBRARY_PATH}` is evaluated by the BUILD script's own shell under `set -u` — NOT written literally. On a clean shell (no `LD_LIBRARY_PATH` exported, e.g. a fresh agent/CI context) the whole build aborts with `build_appimage.sh: line NNN: LD_LIBRARY_PATH: unbound variable`, AFTER `--version` and `white-screen` checks already passed (looks like a flaky last-step failure). The artifact mtime does NOT update, so you can't tell from the file. FIX: `${LD_LIBRARY_PATH:-}` in the smoke command-prefix. Also harden the `AppRun` generation line the same way (defensive — if a future edit un-escapes the heredoc var, the build would hit the same trap). Concrete corrected lines + the diagnostic that reveals the real error (run the artifact import with `2>&1` visible, NOT `2>/dev/null`): `references/build_script_setu_unbound_var.md`.
- **Bundled interpreter without `pyvenv.cfg` falls back to HOST site-packages (Lumen 2026-07-12, #4 / final LUMEN build failure).** The split-layout recipe copies only the python BINARY; if you do NOT write a `pyvenv.cfg` beside it, the interpreter has no venv marker and resolves `sys.prefix` to the HOST. It then imports from the HOST site-packages: an editable `<app>` install resolves to its SOURCE tree (traceback shows `/home/.../apps/<app>/<app>/...` instead of the bundled copy) and the host PyQt6 may be incomplete (e.g. `No module named 'PyQt6.QtWebChannel'`). The bundled PyQt6 is actually COMPLETE — it is just never consulted. The offscreen import-smoke (which runs the artifact python DIRECTLY, not via AppRun) fails even though `--version` and a source grep pass. FIX: write `AppDir/usr/bin/pyvenv.cfg` with `home = /usr/bin`, `include-system-site-packages = false`, `version = $PVER`. The SOURCE-tree path in the traceback is the host-fallback tell. Full recipe + diagnostic: `references/bundled_python_pyvenv_cfg.md`.

- **Long AppImage builds can outlive a context compaction.** A multi-minute build (fresh venv + PyQt6-WebEngine pip + mksquashfs) launched as a background process may not survive a context-compaction boundary — the background-process registry can come back EMPTY, so the build silently never ran (artifact stays at its old mtime). Always re-verify after compaction: `pgrep -af build_appimage` + `head` the build log; if the registry is empty and the log/artifact are stale, RELAUNCH and confirm the log head shows the venv/pip phase before walking away.
- **`--appimage-extract` ALWAYS writes `./squashfs-root` relative to the CWD — never to a temp dir you made.** If you `EX=$(mktemp -d)` and run `"$OUT" --appimage-extract` WITHOUT `cd "$EX"`, the squashfs lands in YOUR CWD (the repo, not `$EX`), so `ls "$EX/squashfs-root"` reports "No such file" and you FALSELY conclude the artifact is broken/missing modules. Fix: `cd "$EX" && "$OUT" --appimage-extract` (extract into the temp dir) OR inspect `$(pwd)/squashfs-root` after. This burned several false-negative debugging cycles on Lumen 2026-07-12 (a real `No module named 'PyQt6.QtWebChannel'` was real; the "MISSING in artifact" checks were bogus because the extraction had gone to CWD).

- **Headless launch test:** pass `--offscreen` (sets `QT_QPA_PLATFORM=offscreen`) plus a `--selftest` flag that boots the UI ~1.5s then quits; assert exit 0. This is the clean-box proof.
- **PyQt6 `pytest` HANGS FOREVER on modal dialogs (product code blocks headless).** A `QMessageBox.question` / `QDialog.exec` / `QFileDialog.get*` call in the app path (e.g. a settings "reset all" confirm) opens a NATIVE modal that never resolves without a user → the test sits at 0% CPU forever (Lumen froze exactly this way at `SettingsPage._reset_all`). Fix in the HARNESS, never the product: add a conftest autouse fixture that, when `QT_QPA_PLATFORM == 'offscreen'`, monkeypatches `QMessageBox.question/.warning/.critical/.information` to return a canned button, stubs `QDialog.exec`→returns 0, and `QFileDialog.get*`→returns a temp path. Product code stays intact (the dialog still works for a real user). Also: PyQt6 renamed `exec_`→`exec` (test helpers calling `dialog.exec_()` raise `AttributeError`). Full fixture + slow-box wide-suite run pattern (`-rfE --tb=line`, background, long timeout) + the "fix real bugs, don't relax tests" quality bar: `references/pyqt6_headless_pytest.md`.
- **PyQt6 `QPen`/`QBrush` REQUIRE `QColor` instances (TypeError pitfall):** passing a hex *string* (`QPen("#2ec27e")`) compiles but raises `TypeError: arguments did not match any overloaded call` at *paint* time (not at import). Always wrap: `QPen(QColor("#2ec27e"))` / `QBrush(QColor(...))`. This bites pure-Qt dashboards that draw with computed colors — the error only surfaces when the widget actually paints.
- **Pure-Qt dashboard = cleanest bundle:** draw with `QPainter` primitives (lines/rects/ellipses/text) instead of embedding `matplotlib` or `PyQt6.QtWebEngineWidgets`. No browser, no heavy native deps → the AppImage runs headless (`QT_QPA_PLATFORM=offscreen`) and a `--selftest` boot proves it on a clean box. The DEMIURGE STOCKBOT dashboard (`stockbot_dashboard.py`) is a working example: 4 panels (GATE/MODULES/PAIRS/EQUITY), all hand-drawn, no matplotlib.
- **Whole-`.venv` (B4) bundle is the simplest offline path:** instead of splitting the venv into `usr/bin/python3` + `usr/lib/python$PVER`, copy the ENTIRE project `.venv` to `AppDir/usr/share/<app>/.venv` and point `AppRun` at `$HERE/usr/share/<app>/.venv/bin/python`. This is exactly what the shipped `DEMIURGE-*.AppImage` uses (the `B4_PY` branch in its `AppRun`). Pros: no PVER math, PyQt6 Qt plugins resolve automatically under `.venv`, one copy step. Cons: larger artifact (a real venv is ~0.7GB) — fine for a one-shot ship. In `AppRun`, set `QT_QPA_PLATFORM=offscreen` when `DISPLAY` is empty so the bundle still boots headless.
- **Incremental AppImage rebuild — reuse an EXISTING AppDir with a bundled venv (STOCK BOT SB10):** when you only changed source + a metrics JSON (e.g. after a gate re-run), DON'T re-copy the venv or re-pip. Start from the committed `build/StockBotAppDir/` (which already carries `AppRun` + `.venv` + `<app>.desktop`), copy just the changed `*.py` + `*.json` + `samples/` into it, then run the LOCAL offline `appimagetool` (`/home/hunter/.local/bin/appimagetool` — no network). This turned a 0.7GB venv re-bundle into a seconds-long source refresh and produced a 227MB image that boots headless (`--selftest` exit 0). Keep the AppDir skeleton in-repo as the packaging baseline; rebuilds = `refresh sources + appimagetool`. See `references/scaffold_stockbot_gate.md`.
- **`cp *.py` into the AppDir sweeps DEBUG scripts too (STOCK BOT SB3, 2026-07).** The
  `build_stockbot_appimage.sh` pattern does `find "$SHARE" -name '*.py' -delete` then
  `cp "$SCAFFOLD"/*.py "$SHARE/"` — every `*.py` in the repo ROOT lands in the image,
  INCLUDING temporary debug helpers (e.g. `_dbg_revbreadth.py`). Ship them and you
  pollute the bundle + the shipped binary. FIX: keep debug/temp scripts out of the repo
  root (use `/tmp`), or `rm -f _dbg_*.py` before building, then rebuild. VERIFY
  inclusions WITHOUT a heavy full extract: `./<app>.AppImage --appimage-extract` then
  `ls squashfs-root/usr/share/<app>/<mod>.py` (and confirm the debug file is ABSENT),
  then `rm -rf squashfs-root`. The SB3 run built once WITH the debug script, deleted it,
  and rebuilt to ship a clean 237MB image (SELFTEST OK).
- **`tar` staging recursion trap:** when copying the whole repo into `usr/share/<app>` with `tar cf - . | (cd dest && tar xf -)`, EXCLUDE the directory that *contains* the AppDir (e.g. `--exclude='./build'`) or you copy the AppDir into itself recursively. Also exclude `.venv` (copied separately) and `*.AppImage`. Recipe:
  `( cd "$REPO" && tar cf - --exclude='.venv' --exclude='__pycache__' --exclude='*.AppImage' --exclude='.git' --exclude='./build' . ) | ( cd "$APPDIR/usr/share/<app>" && tar xf - )`
- **Non-Python assets silently drop from the squashfs (the #1 AppImage failure):** a QSS theme / sample / icon / config / web template missing from package-data globs is absent from the build, but the app boots fine via fallback — so a `--selftest` pass HIDES it. Test-lock the globs (parse `pyproject.toml` `[tool.setuptools.package-data]`, assert every shippable asset is covered) and verify the extracted artifact (`--appimage-extract` then `find` for the assets). Full recipe + reusable test: `references/appimage_deploy_gate.md`, `templates/test_packaging_data.py`. Do NOT trust `*.egg-info/SOURCES.txt` (regenerated from the last build — can be stale).

## Headless-only / leashed build hosts (no display, heavy build gated)
Some agent/sandbox runtimes forbid opening a display AND treat a full AppImage
build (fresh venv + PyQt6-WebEngine pip + mksquashfs) as out-of-bounds or a
swarm-risk. In that case DO NOT run the build automatically. Instead:
- **Derive every path from `BASH_SOURCE`** (never hardcode `/home/...`):
  `SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"` and drop the artifact
  at `"$SRC/<app>.AppImage"`. Portable AND matches autostart/desktop
  integrations that look for `<repo>/<app>.AppImage`.
- **Gate the REAL build behind an env var** so it only runs on a build host:
  `@pytest.mark.skipif(os.environ.get("LUMEN_RUN_APPIMAGE_BUILD") != "1", ...)`
  wrapping a test that runs `bash build_appimage.sh` and asserts the artifact
  exists + `--version` prints the expected string. Default = skip = safe.
- **Make the script self-verify headlessly:** after `appimagetool`, run
  `"$OUT" --version`. `argparse action="version"` prints and exits BEFORE any
  `QApplication`/`QWebEngineView` is constructed, so it is display-free and
  proves the shipped binary imports + reports the right version. Strongest
  leash-safe check you can bake in.
- **Static headless gate (always run, no network/RAM):** a pytest module that
  does `bash -n` (syntax), asserts no `linuxdeploy` invocation, asserts the
  generated `AppRun` keeps the GPU sandbox ON (no `QTWEBENGINE_DISABLE_SANDBOX`),
  asserts the AppRun wires `LD_LIBRARY_PATH`/`PYTHONPATH`/`QT_QPA_PLATFORM_PLUGIN_PATH`
  and `exec ... -m <pkg>`, and asserts `pyproject` package-data ships the
  theme+samples the AppImage relies on. Locks the recipe without building.

## Verification contract (make the build testable)
A packaging test suite (`templates/test_packaging.py`) should assert:
1. `bash -n build_appimage.sh` exits 0 (syntax).
2. `bash build_appimage.sh --dry-run` prints a plan + `DRY-RUN OK` (parseable no-op contract).
3. `python main.py --offscreen --selftest` exits 0 and prints the app banner.
4. `AppRun`, `<app>.desktop` (Exec=AppRun, Icon set), and the icon exist and are non-empty.
5. Flatpak manifest YAML parses with correct `id` / `finish-args` / `modules`.
6. Sample bundle (parquet/csv + config) loads with valid config thresholds.
THEN actually BUILD the image and launch it headless as the final proof (don't ship on authoring alone).

## Deploy-gate: verify the artifact ships your DATA (not just boots)
A green `--selftest` boot can still ship a BROKEN app: non-Python assets (QSS
theme, samples, icons, web templates, config) are silently absent from the
squashfs when nothing declared them as package data, and the app falls back to a
blank theme / empty gallery on a clean box. Lock this down at two levels:

0. **A glob-coverage gate MUST be mutation-proven or it proves nothing.** A
   dynamic "every asset matches a declared glob" test passes trivially when the
   globs happen to be broad (e.g. `samples/*/*`), so a green run is NOT evidence
   the gate has teeth. Verify by mutation: temporarily drop one glob and confirm
   the uncovered count jumps (verified on Lumen: full globs → 0 uncovered/pass;
   drop `samples/*/*` → 54 uncovered/fail). Prefer this dynamic
   `fnmatch(rel, glob)`-vs-`rglob` assert over a weak `"samples/*/*" in text`
   string search — the string search can't detect a NEW asset dir added since.
   `tomllib` (stdlib, py3.11+) parses the package-data cleanly.
1. **Test-lock the globs (source of truth, no build):** parse `pyproject.toml`
   `[tool.setuptools.package-data]`, expand every glob, walk the package dir, and
   assert each shippable non-`.py` asset is matched by a declared glob. Do NOT
   prove shipping via `pip wheel` (a dev venv may lack `setuptools.build_meta`)
   and do NOT trust `*.egg-info/SOURCES.txt` (regenerated from the LAST build —
   it lies about assets added since). Reusable: `templates/test_packaging_data.py`.
2. **Verify the built artifact headlessly:** `./<app>.AppImage --appimage-extract`,
   then `python -m <pkg> --version` (proves interpreter+entry intact),
   `python -c "import <pkg>, <pkg>.app, ..."` (proves deps present), and
   `find squashfs-root -name styles.qss -o -name preview.png` (proves the
   specific assets are in the squashfs). Full recipe: `references/appimage_deploy_gate.md`.

## Flatpak (optional)
Manifest skeleton: `templates/org.example.App.yaml`. Uses `org.freedesktop.Sdk.Extension.python3.11`, installs deps via pip into `/app`, copies source, installs `AppRun` as the command. Build: `flatpak-builder builddir org.example.App.yaml --force-clean`.

## Debian .deb (the feasible 3rd target when Flatpak is blocked)
When `flatpak-builder` is unavailable (no root / no Flathub remotes in the
sandbox) but `dpkg-deb` + `fakeroot` + network pip ARE present, build a `.deb`
instead. Full recipe, exact error transcripts, and the headless verify are in
`references/deb_packaging.md`. The four traps that bite:
- **Control files reject `#` comments** — `dpkg-deb` parses a `#` line as a
  field name and aborts (`field name '#' must be followed by colon`). No `#`
  inside the `DEBIAN/control` heredoc; put notes in the `build.sh` as shell comments.
- **`pip install --target=/opt/lumen` puts the entry at `/opt/lumen/lumen/__main__.py`,
  not `/opt/lumen/__main__.py`** — a launcher `python3 /opt/lumen/__main__.py`
  dies with `ModuleNotFoundError`. Fix: `cp "$APP/lumen/__main__.py" "$APP/__main__.py"`
  so a directly-run script gets its own dir on `sys.path[0]` (vendored deps +
  `import lumen` both resolve, no `PYTHONPATH` needed).
- **PyQt6 wheels need SYSTEM Qt6 at runtime** — `Depends` must list
  `libqt6core6 libqt6gui6 libqt6widgets6 libqt6webenginecore6
  libqt6webenginewidgets6 libgl1 libxkbcommon0 libdbus-1-3`, NOT `python3-pyqt6`.
- **Headless launch test:** `dpkg-deb -x pkg.deb /tmp/x && python3
  /tmp/x/opt/lumen/__main__.py --version` must print `App X.Y.Z` + exit 0. This
  proves the launcher + vendored deps resolve (mirrors the AppImage `--version`
  check); the real GUI still needs Qt6 + X on the user's desktop.

## Guardrails
- Never edit core engine files to make packaging work; add a launcher/entrypoint module instead.
- The AppImage must NOT itself open any broker/network path — the app's own gate logic stays enforced.

## References / templates / scripts
- `references/appimage_pitfalls.md` — desktop validation rules, appimagetool location fallback, offline bundle details, SCAFFOLD off-by-one, headless verify.
- `templates/build_appimage.sh`, `templates/AppRun`, `templates/app.desktop`, `templates/org.example.App.yaml`, `templates/test_packaging.py`
- `scripts/make_icon_stdlib.py` — pure-stdlib RGBA PNG generator (no PIL).
- `references/appimage_deploy_gate.md` — the data-asset deploy-gate recipe: test-lock package-data globs (no wheel needed) + verify the extracted artifact ships your theme/samples/icons.
- `references/setuptools_package_data_subpackages.md` — the subpackage `package-data` collision + TOML quoted-key fix (when a subpackage like `lumen.ui` carries qss/png and the parent glob silently drops them — the build's `assert_asset` gate catches it).
- `references/pyqt6_webengine_appimage.md` — PyQt6/Engine AppImage native-lib path fix: `libQt6WebChannel.so.6` ImportError, the `PyQt6/Qt6/lib` + `Qt6/plugins` LD_LIBRARY_PATH/plugin-path recipe, and the offscreen import-smoke that proves the bundle imports (split-layout builds).
- `references/build_script_setu_unbound_var.md` — `set -euo pipefail` build script + offscreen import-smoke `LD_LIBRARY_PATH` unbound-variable trap (Lumen #3 build failure): the corrected `:-` AppRun + smoke snippets, and the `2>&1`-visible diagnostic that surfaces the real `libQt6WebChannel.so.6` ImportError.
- `references/bundled_python_pyvenv_cfg.md` — bundled interpreter falls back to HOST site-packages when `pyvenv.cfg` is missing (Lumen #4 / final build failure): SOURCE-path traceback tell, `ModuleNotFoundError: PyQt6.QtWebChannel`, the `pyvenv.cfg` fix, and the `2>&1`-visible offscreen smoke diagnostic.
- `references/deb_packaging.md` — Debian `.deb` build recipe + the 4 traps (no `#` in control, pip `--target` entry-point depth + `sys.path[0]` fix, PyQt6 system-Qt6 `Depends`, headless `dpkg-deb -x` + `--version` verify). Use when Flatpak is blocked in the sandbox.
- `templates/test_packaging_data.py` — reusable pytest that parses pyproject globs and asserts every shippable non-Python asset is covered (set `PKG_NAME`).
- `references/self_healing_apprun.md` — crash-resilient launcher: two-layer self-heal (Python `supervise()` + AppRun `while` loop), the `set -e` kills-the-loop pitfall, the system-wide PyQt6 fallback, and a no-GUI verification recipe.
- `templates/AppRun_selfheal` — copyable self-healing AppRun (`set -u`, restart budget, additive system dist-packages fallback). Run the app with `--no-supervise`.
