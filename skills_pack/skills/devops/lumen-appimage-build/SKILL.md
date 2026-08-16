---
name: lumen-appimage-build
description: Build and verify the Lumen wallpaper-engine AppImage on a quota-limited host, and clear the stale-.pyc swarm hazard that produces phantom pytest failures. Use whenever asked to build/pack Lumen, prove its deploy gate, or debug a "full suite fails but passes alone" mystery in the Lumen repo at /home/hunter/Desktop/apps/lumen.
---

# Lumen AppImage build + gate verification (quota-safe)

## When to use
- Building the shippable `lumen.AppImage` (the Lumen deploy gate is: "AppImage
  build must succeed and boot without rebooting the box").
- A pytest run shows failures that vanish when a single test file is run alone
  (classic stale-bytecode cascade from concurrent swarm edits).

## Hard constraints (LEASH)
- NEVER run `python -m lumen` GUI, never open PyQt/WebGL/X, never grab DISPLAY.
  Verify headlessly only: `QT_QPA_PLATFORM=offscreen DISPLAY=`.
- The build itself is headless; only the live GUI needs a display.

## 1. The /tmp per-user quota hazard (root cause of most build failures)
This box caps the `hunter` user's `/tmp` at ~257M (EDQUOT / Errno 122) even
though the filesystem has GB free. A full AppImage build (clean venv + PyQt6 +
PyQt6-WebEngine + AppDir copy) needs hundreds of MB, so it DIES in `/tmp`.

Fix: redirect ALL build temp to the home partition (405G free, no quota):
```
export LUMEN_BUILD_DIR=/home/hunter/.cache/lumen-appimage-build
export TMPDIR=/home/hunter/.cache/lumen_tmp
export PIP_CACHE_DIR=/home/hunter/.cache/lumen_pip
mkdir -p "$LUMEN_BUILD_DIR" "$TMPDIR" "$PIP_CACHE_DIR"
cd /home/hunter/Desktop/apps/lumen
QT_QPA_PLATFORM=offscreen DISPLAY= \
  LUMEN_BUILD_DIR="$LUMEN_BUILD_DIR" TMPDIR="$TMPDIR" PIP_CACHE_DIR="$PIP_CACHE_DIR" \
  bash build_appimage.sh
```
`build_appimage.sh` honours `$LUMEN_BUILD_DIR` (defaults to `/tmp` for
portability). `TMPDIR` is also used by `mktemp` (SMOKE_DIR/WS_TMP) and by pip's
ephemeral wheel cache, so set it too. `PIP_CACHE_DIR` keeps wheels cached so
rebuilds are fast.

## 2. What the build proves (the gate)
`build_appimage.sh` self-verifies and FAILS the build if any step breaks:
- asset presence (ui/styles.qss, ui/assets/logo.png, sample manifests+previews)
- white-screen deploy-gate: greps the bundled `web.py`/`webgl_engine.py` for
  `self.view.setWindowFlags` (the ENI9 child-detach bug) — must be ABSENT
- `--version` boots headlessly (exit 0, prints `Lumen x.y.z`)
- bundled-import smoke: extracts the AppImage and imports
  `lumen, lumen.app, lumen.ui.main_window, lumen.steam.steamworks,
  lumen.gallery_export` under offscreen Qt
If the script exits 0, the gate is met.

## 3. Verify the artifact manually (optional cross-check)
```
QT_QPA_PLATFORM=offscreen DISPLAY= ./lumen.AppImage --version     # -> Lumen 1.0.0
# confirm bundled samples / modules:
cd /home/hunter/.cache && rm -rf v && mkdir v && cd v
/home/hunter/Desktop/apps/lumen/lumen.AppImage --appimage-extract >/dev/null 2>&1
SP=$(find squashfs-root -type d -path '*site-packages/lumen/samples' | head -1)
ls "$SP" | grep -c '^shader_'      # count bundled samples
cd / && rm -rf /home/hunter/.cache/v
```
NOTE: when extracting manually, ALWAYS use the ABSOLUTE path to the AppImage.
Running `./lumen.AppImage` from a dir that doesn't contain it silently no-ops
and you'll see an empty `squashfs-root`.

## 4. The stale-.pyc swarm hazard (phantom pytest failures)
Concurrent sibling builders edit modules, leaving `.pyc` files NEWER/LARGER than
the current `.py`. Python then loads the old bytecode, causing failures that
disappear when the file is run in isolation (fresh import). Symptom: "full suite
fails, single file passes", or a module mysteriously lacks a method/class that
is present in its source.

Clear ALL bytecode before trusting a full-suite number:
```
cd /home/hunter/Desktop/apps/lumen
find . -name '__pycache__' -type d -not -path '*/build/*' -exec rm -rf {} +
find . -name '*.pyc' -not -path '*/build/*' -delete
QT_QPA_PLATFORM=offscreen DISPLAY= TMPDIR=/home/hunter/.cache/lumen_tmp \
  .venv/bin/python -m pytest -q -p no:cacheprovider
```
(Wheels in `build/` are precompiled by pip — don't strip those.)

## 5. Pitfalls
- A `python -c "import lumen.X; hasattr(lumen.X, 'foo')"` returning False is a
  RED HERRING if `foo` is a class METHOD, not a module function. Check the class.
- `tarfile.extractfile(name)` RAISES `KeyError` for a missing member — it does
  NOT return `None`. Guard with `try/except KeyError`, not `if x is None`.
- The AppImage's live GUI boot (`--minimized`) genuinely needs LO's X server;
  headless verification stops at `--version` + bundled-import smoke.

## 6. Verification checklist (leash-safe)
- [ ] `QT_QPA_PLATFORM=offscreen DISPLAY= ./lumen.AppImage --version` -> exit 0
- [ ] build log shows `IMPORTS OK` + `white-screen-safe`
- [ ] `tests/test_headless_integration.py` passes (render pipeline + doctor)
- [ ] full suite green AFTER clearing stale `.pyc`
