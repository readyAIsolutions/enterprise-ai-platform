# Lumen AMD boot-crash fix (deep dive)

## Symptom
Lumen reboots LO's box on launch (had to hard-reset twice). AMD RX 5700 XT,
amdgpu driver, 4 monitors, X11.

## Root cause
`lumen/wallpaper/engine.py` gave EVERY shader/web wallpaper its own
QWebEngineView => its own Chromium GPU process + its own WebGL context, one PER
MONITOR (4 live contexts). `app.py` launched Chromium with:
  --ignore-gpu-blocklist --enable-webgl --disable-gpu-sandbox
forcing HARDWARE accel. Four HW-WebGL surfaces hammering amdgpu at once hangs the
GPU and the kernel reboots.

## The fix (3 layers, all in ~/Desktop/apps/lumen)
1. **Boot guard** — `lumen/safety.py`
   - `BootGuard`: 2 consecutive boot crashes => SAFE MODE (tray only, no
     wallpapers) until `python -m lumen --reset-safe`.
   - State file: `~/.config/lumen/boot_guard.json`
     ({attempts, last_launch, last_clean_exit, consecutive_crashes, safe_mode}).
   - `app.py` registers `atexit` + a crash-window timer that calls
     `mark_clean_exit()` on a clean shutdown; a launch without a clean-exit
     record increments `consecutive_crashes`.
2. **SwiftShader software WebGL** — `app.py` launch flags changed to:
   --enable-unsafe-swiftshader --enable-webgl --disable-gpu-compositing
   --disable-features=Vulkan,UseChromeOSDirectVideoDecoder --disable-dev-shm-usage
   GPU sandbox stays ON. Software rendering cannot hang the amdgpu driver.
3. **GL-context cap + RSS watchdog** — `wallpaper/engine.py`
   - `max_webgl_surfaces` (default 1, set in `config.py`) caps live GL contexts.
   - `apply()` skips in safe_mode and enforces the cap.
   - `app.py` runs a 3s `QTimer` calling `process_tree_rss()`; if the tree RSS
     exceeds the cap it calls `drop_all_to_safe()` before any OOM/reboot.

## Verification
- Unit: the boot-guard logic was tested headless (2 crashes => safe_mode; reset
  clears; clean exit resets streak). RSS check returns a sane number vs the cap.
- Live GUI boot CANNOT be tested headless (no display). On the desktop run:
  `python -m lumen --minimized`  (or launch the rebuilt AppImage) and watch the
  log for wallpapers applying without a reboot. If it ever does reboot twice,
  safe_mode engages automatically; `python -m lumen --reset-safe` clears it.

## CRITICAL: the AppImage is a FROZEN bundle
`build_appimage.sh` copies the real `lumen` package from source at BUILD TIME.
Patching `lumen/*.py` does NOT change `~/Desktop/apps/lumen.AppImage`. After any
source fix, rerun `bash ~/Desktop/apps/lumen/build_appimage.sh` to ship it. The
build does a clean-venv `pip install` of PyQt6-WebEngine (pulls Chromium, ~+1-2 GB
RAM) — run it STANDALONE, never concurrent with a full floor redeploy (RAM
contention on 30G risks OOM).
