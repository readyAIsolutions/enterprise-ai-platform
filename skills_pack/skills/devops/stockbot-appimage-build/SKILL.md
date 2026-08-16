---
name: stockbot-appimage-build
description: Build the DEMIURGE STOCK BOT unified AppImage on this box. Covers the appimagetool silent-fail pitfall and the manual runtime+squashfs fallback that actually works. Use when shipping stockbot AppImages or debugging a failed build.
---

# STOCK BOT AppImage build (this box)

## The pitfall (verified, 2026-07-12)
`build_unified_stockbot_appimage.sh` step [3/4] calls:
`appimagetool --runtime-file <runtime> <AppDir> <OUT>`
On this AMD Ubuntu box the continuous appimagetool prints
`... should be packaged as <OUT>` then **exits 1 with NO error message and
produces NO file**. `mksquashfs` itself works perfectly standalone (tested:
1796 files -> 21MB, exit 0). The failure is purely in appimagetool's
runtime-embedding step. The `| tail` in the original script masked the real
exit code (pipeline reported 0).

## Fix (already patched into build_unified_stockbot_appimage.sh)
After appimagetool fails, fall back to the standard AppImage type-2 layout
= ELF runtime prepended + squashfs appended:

```bash
SQ=$(mktemp -p "${TMPDIR:-/tmp}" unified.XXXXXX.squashfs)
mksquashfs "$APPDIR" "$SQ" -noappend -comp gzip -quiet
cat "$RUNTIME" "$SQ" > "$OUT"      # runtime.x86_64 is already an ELF (7f45 4c46)
rm -f "$SQ"
chmod +x "$OUT"
```

`RUNTIME=/home/hunter/.cache/runtime.x86_64` (193KB type-2 runtime, already
cached). `appimagetool=/home/hunter/.local/bin/appimagetool` is present but
unreliable for the embed step.

## Verify the image is valid (no FUSE needed)
```bash
./dist/DEMIURGE-stockbot-UNIFIED-x86_64.AppImage --appimage-extract   # writes squashfs-root/
ls squashfs-root/usr/share/stockbot/<your_module>.py                   # confirm module bundled
rm -rf squashfs-root
file dist/DEMIURGE-stockbot-UNIFIED-x86_64.AppImage   # expect "ELF 64-bit LSB executable"
```

## How a new feature module gets bundled
`packaging_dedup_bundle.py --out build/StockBotUnifiedAppDir` globs
`stock*.py` from the REPO ROOT (NOT builder-suffixed `*_gate_wire*` files)
and copies them into `usr/share/stockbot/`, then renames colliding NEW_COLS
in alphabetically-later modules (`col__loser`). So simply placing
`stock_<name>_feature.py` in the repo root is enough to be auto-bundled.
Pre-flight `stockbot_package_preflight.py` must report `exact=0` (the script
hard-aborts the build on exact collisions). Your columns must be unique.

## Per-builder AppImage builds (SB1/SB2/SB3/... — NOT the unified one)
Each builder ships its own image via a dedicated script, e.g.
`build_stockbot_appimage_sb3.sh`. These target `build/StockBotAppDir`
(which DOES carry a bundled `.venv` with PyQt6/pandas/scipy/sklearn + a
universal AppRun), unlike the unified AppDir noted above. KEY DIFFERENCE from
the unified build: `appimagetool` **succeeded directly** here (no silent-fail
fallback needed) — the script calls `appimagetool <AppDir> <OUT>` and it
produces the file + prints "Success". So if you are rebuilding a per-builder
image, just run the script; do not assume the runtime+squashfs fallback is
required (only the UNIFIED build hits the embed bug).

What the per-builder script does (ADD-ONLY, refresh-only):
- `rm` old `*.py` from `usr/share/stockbot/`, then `cp` all repo `*.py` in.
- Copy the builder's runtime artifacts (JSON verdicts/metrics) if present.
- `cp -r` `swarm/`, `samples/`, `assets/` (rm then cp, to avoid nested dirs).
- Write `VERSION`, set AppRun + `.desktop` + icon, then `appimagetool`.
- Step [5/5] runs `timeout 40 "$OUT" --offscreen --selftest` and tolerates
  non-zero (image still ships) but prints "SELFTEST OK" on success.

Verify a per-builder image the same way:
```bash
cp -f dist/DEMIURGE-stockbot-SB3-x86_64.AppImage DEMIURGE-stockbot-SB3-x86_64.AppImage
./DEMIURGE-stockbot-SB3-x86_64.AppImage --offscreen --selftest   # exit 0 = SELFTEST OK
```
A non-zero exit from the headless selftest still ships the artifact, but a 0
exit proves the bundled GUI boots offscreen. If the build script is missing for
your builder, copy an existing `build_stockbot_appimage_sbN.sh` and rename the
`OUT`/branding — the AppDir skeleton is shared.

## Notes
- The bundled AppDir has NO `.venv`/PyQt6. AppRun falls back to system
  python3; the GUI boot test (`--appimage-extract-and-run --offscreen
  --selftest`) needs host PyQt6 to fully pass but the image is still a valid
  shippable artifact.
- `packaging_dedup_bundle.py` IMPORTS each module via importlib to read
  NEW_COLS; if a module raises at import it is still COPIED (copy is separate
  from the import-based dedup scan), so a heavy import won't drop it from the
  bundle — but keep top-level import cheap so the preflight is fast.
- Set `TMPDIR=/home/hunter/.cache/d3d_tmp` (this box has a /tmp quota that
  EDQUOTs). `DEMIURGE_DIR` can be the unmounted path; the bundle build does
  not need the USB.
