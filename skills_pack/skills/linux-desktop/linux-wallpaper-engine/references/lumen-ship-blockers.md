# Lumen ship-state & ENI-mini re-verify (condensed knowledge bank)

Durable facts about the Lumen -> Steam ship state and the exact command set an
ENI swarm mini uses to re-verify GREEN every resume. NOT a one-off task log —
reuse on any future Lumen ship / ENI10-style resume.

## Where the placeholder App ID 480 lives (all must be mirrored to a REAL id)
- /home/hunter/Desktop/apps/lumen/steam_appid.txt  -> 480
- /home/hunter/Desktop/apps/lumen/lumen/steam/steamworks.py line ~18 APP_ID = 480
- /home/hunter/Commander/eni_swarm/lumen_shipkit/app_build.vdf  AppID 480
- /home/hunter/Commander/eni_swarm/lumen_shipkit/depot.vdf  DepotID "1" (placeholder; no AppID field by design)
480 is Valve's sample App ID — NOT shippable. LO must supply a real App ID +
a publisher STEAM_USER login. The agent cannot auto-supply these.

## Depot blocker guard (NEXT_BUILD.sh)
Run bash /home/hunter/Commander/eni_swarm/lumen_shipkit/NEXT_BUILD.sh
- With NO STEAM_USER env -> exits 10 with
  "!! BLOCKER(10): app_build.vdf AppID is still the placeholder 480".
- The 10-exit is the intended guard; it is NOT a failure of the build.
- Real upload form: STEAM_USER=<publisher_account> bash .../NEXT_BUILD.sh
  (still blocked until the 480->real id mirror is done first).
- Prep/stage alone (no creds) is safe to run; it stages
  content/lumen.AppImage (~246 MB).

## ENI-mini re-verify command set (run fresh each resume; core untouched)
  # 1. source compiles
  python3 -m compileall -q /home/hunter/Desktop/apps/lumen          # expect exit 0
  # 2. bundled AppImage version
  /home/hunter/Desktop/apps/lumen.AppImage --version                # expect "Lumen 1.0.0" exit 0
  # 3. offscreen smoke (PNGs go to <OUTDIR>/ directory, exit 139 benign)
  QT_QPA_PLATFORM=offscreen timeout 150 \
    /home/hunter/Desktop/apps/lumen.AppImage --screenshot /tmp/smoke
  ls -l /tmp/smoke/        # 01_library / 02_store / 03_settings REAL; 04_wallpaper blank offscreen
  # 4. blocker live?
  cat /home/hunter/Desktop/apps/lumen/steam_appid.txt               # expect 480 (blocker)
  bash /home/hunter/Commander/eni_swarm/lumen_shipkit/NEXT_BUILD.sh 2>&1 | tail -3   # expect exit 10
  # 5. live display
  xrandr --query | grep -c connected                                 # expect 4
  # 6. staged artifact
  ls -l /home/hunter/Commander/eni_swarm/lumen_shipkit/content/lumen.AppImage   # ~246629568 bytes

All of the above = GREEN. Only the App ID + STEAM_USER + live-X store-asset
capture remain blocked. Fleet worker STATUS files STATUS_ENI10_w1..w10
(10) should all be present (DONE).

## Known-but-benign (do NOT call these regressions)
- AppImage offscreen --screenshot exits 139 (SIGSEGV) on WebEngine teardown —
  PNGs already written; benign.
- 04_wallpaper.png is ~1961B blank offscreen (no display) — fills on real X11.
- "Failed to create Vulkan instance" / "QVulkanInstance: Failed to initialize
  Vulkan" on launch — benign (SwiftShader).
- AppRun plugin-path typo PyQt6/Qt/plugins (should be Qt6/plugins):
  works on LO's rig via silent fallback to system Qt plugins; fix before wide
  release to machines lacking system Qt. Grep: grep -n 'Qt/plugins' AppRun build_appimage.sh.

## Disruptive steps that wait for LO's live session
- capture_headless.sh (Library/Workshop/Settings/wallpaper PNGs) and
  trailer_capture.sh (ffmpeg x11grab ~30s) pop the GUI and record the screen.
- check_assets.py flags 01/02/03 at 1180x760 offscreen (below Steam's
  1280x720/16:9) — EXPECTED; on live X, GUI shots need the window resized to
  >=1280x720 16:9 first, and 04 fills. Not a core regression.

## ENI-mini discipline (operating procedure)
- Re-read own STATUS_<NAME>.md; re-verify the smoke/self-tests above GREEN.
- PREP the EXACT next real-data/build command; REPORT the blocker
  (e.g. USB not mounted, or here: App ID + STEAM_USER missing).
- ADD NEW files only; NEVER rewrite the proven core (no Lumen source edits during
  a bridge/resume — bridge/report only).
- Keep STATUS_<NAME>.md current with [DONE|IN-PROGRESS|BLOCKED].
- Self-heal on death: on resume, re-run the targeted real checks directly
  (no rebuild, no core edits); lumen_bridge.sh is the full re-audit script.
- USB DEMIURGE mount is IRRELEVANT to Lumen ship (DEMIURGE bot data only) and
  does NOT clear the Steam blocker.
