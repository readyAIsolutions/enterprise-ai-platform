---
name: steam-proton-bepinex-modding
description: Install BepInEx-based mods (co-op, multiplayer, QoL) for Windows Unity/Mono games running under Steam + Proton on Linux, and force them onto a specific monitor. Use when the user wants a mod working for a Steam game on Linux, mentions BepInEx/KrokMP/Unity mods, or wants a Proton game to launch on a chosen monitor every time.
---

# Steam/Proton Unity Mod Setup (BepInEx)

## When to use
- User wants a mod (multiplayer/co-op/QoL) working for a Windows game they run via Steam on Linux.
- Game is a Unity build: has `UnityPlayer.dll`, a `MonoBleedingEdge/` or `*.exe` + `*_Data/` folder, or the mod docs mention BepInEx.
- User mentions BepInEx, KrokMP, "Casualties Together", or wants a Proton game to open on a specific monitor every launch.

## Core technique
Many Unity mods = a loader (BepInEx) + plugin DLLs dropped into `BepInEx/plugins/`. Under Proton you MUST tell Wine to load BepInEx's `winhttp.dll` via a launch option, or nothing happens — the mod is silently absent.

## Steps
1. **Locate the game.**
   - Snap Steam: `~/snap/steam/common/.local/share/Steam/steamapps/common/<Game>/`
   - Native Steam: `~/.local/share/Steam/steamapps/common/<Game>/`
   - Find appid: `find ~ -iname "appmanifest_<id>.acf"`; the `installdir` key gives the folder name. The Steam `.desktop` shortcut contains `rungameid/<id>`.
2. **Install BepInEx loader (if not present).** Download `BepInEx_win_x64_5.4.23.5.zip` from the BepInEx GitHub release, unzip into the game root. This adds `winhttp.dll`, `doorstop_config.ini` (enabled=true, target BepInEx/core/BepInEx.Preloader.dll), and `BepInEx/core`.
3. **Install the mod's plugins.** The mod usually ships a `mod/` folder containing `BepInEx/plugins/...` and often `steam_appid.txt`. Merge it into the game root:
   - `cp -r mod/BepInEx/. "<game>/BepInEx/"`  (merges plugins+patchers with the loader's core — do NOT overwrite core)
   - `cp mod/steam_appid.txt "<game>/"`  (must sit next to the exe so Steamworks/lobbies initialize)
4. **Set the Proton launch option (MANDATORY).** Steam: right-click game -> Properties -> Launch Options. Use:
   `WINEDLLOVERRIDES="winhttp=n,b" %command%`
   Without this, BepInEx never loads and the mod is invisible.
5. **Force a specific monitor / fullscreen (common request).** Use a WRAPPER SCRIPT, not `sh -c`. See the PITFALL below — Steam substitutes `%command%` in-place with no quoting, so if the Proton path contains a space (Snap Steam + "Proton - Experimental" does), an `sh -c '...%command%...'` launch option becomes `sh -c '... "Proton - Experimental"/proton ...'` — the inner single quotes collide with the script's outer single quotes and the game silently fails to boot (no error shown). Fix: a wrapper script that receives `%command%` as `"$@"`, sets the monitor primary, and `exec`s it.
   - Create `casualties_launch.sh` from `templates/casualties_launch.sh`, edit `MONITOR`/`WIDTH`/`HEIGHT`, `chmod +x` it.
   - Set Launch Options to: `/home/<you>/casualties_launch.sh %command% -screen-fullscreen 1 -screen-width <W> -screen-height <H>`
   - Get `<OUT>`/resolution from `xrandr --current` (e.g. `DisplayPort-0`, `2560x1080`).
   - Unity honors `-screen-fullscreen 1 -screen-width W -screen-height H` under Proton.
   - Only if your Proton path has NO spaces may you use the inline `sh -c` form instead.
5b. **Global "all games on monitor X" fix (no per-game option needed).** Steam/Proton/Unity fullscreen games open on the xrandr PRIMARY monitor. So instead of editing every game, make the target monitor persistently primary at login. On XFCE, drop a script `~/.config/set-middle-primary.sh` that runs `xrandr --output <OUT> --primary` (loop+sleep 5x since the display may not be ready at login), `chmod +x`, and an autostart entry `~/.config/autostart/set-<name>.desktop` (`Type=Application`, `Exec=<script>`, `X-XFCE-Autostart-enabled=true`). This handles ALL current and future games with zero Steam config; keep the per-game wrapper (step 5) only as a fallback for games that ignore primary. Note: a monitor can be the DE primary without the xrandr `primary` flag and reset on reboot/replug — the autostart re-asserts it every login.

6. **Launch from Steam** (not by double-clicking the exe) so Steam lobbies / Steamworks networking work. An MP button should appear on the main menu; a BepInEx console flashes on launch (normal).
7. **Verify / troubleshoot.** On failure inspect `<game>/BepInEx/LogOutput.log` (BepInEx 5 writes it directly under `BepInEx/`, NOT in a `logs/` subdir). Look for the mod's plugin "loaded!" line and "Steamworks initialized!". Most causes: launch option not saved, or game launched outside Steam.

## Pitfalls
- **`sh -c` quote-collision (silent no-boot):** A launch option like `sh -c 'xrandr ...; WINEDLLOVERRIDES=... %command% ...'` is dangerous. Steam injects `%command%` literally, and under Snap Steam it expands to a path with a space ("Proton - Experimental"), which Steam wraps in single quotes. Those single quotes collide with the outer `sh -c '...'` quotes, bash mis-parses, and the game never starts — no error, just nothing. ALWAYS use the wrapper-script pattern (`templates/casualties_launch.sh`) that takes `%command%` as `"$@"`. The inline `sh -c` form is only safe when the Proton path contains no spaces (native Steam + `Proton Experimental` without a space, etc.).
- **The one-shot launch-option mover LOSES THE RACE (use a persistent daemon instead):** a wrapper that moves the window once at launch fails because Unity/Proton opens a tiny init window on the right monitor, THEN switches to fullscreen at origin (0,0 = left monitor) a few seconds later — re-fullscreening AFTER the one-shot mover already ran and exited. Verified failure mode. The reliable fix is a **background daemon** (autostart) that loops every 1s: `wmctrl -lxG` -> for any window whose WM_CLASS starts with `steam_app_` and is real-sized (w>=800,h>=600), compute center X; if it's not within the target monitor's X span, `place()` it (remove,fullscreen -> xdotool windowmove/windowsize -> add,fullscreen). Because it re-checks forever, it corrects the game within 1s of any wrong-monitor fullscreen, needs ZERO per-game launch options, and works for every Steam game at once. Verified working: `/home/hunter/.local/bin/steam-middle-monitor-daemon.sh` + XFCE autostart `~/.config/autostart/steam-middle-monitor-daemon.desktop`. `wmctrl -lxG` columns = id desktop x y w h class host title. Manual move of the LIVE fullscreen window sticks (proven), so the daemon's continuous re-assert is all that's needed. Keep any BepInEx `WINEDLLOVERRIDES` launch option for the mod — monitor placement is now the daemon's job, orthogonal to the mod.
- **xrandr "primary" lie:** a monitor can be the DE's primary but NOT carry the xrandr `primary` flag (`xrandr` shows no `primary` tag after the name). Fullscreen then lands on the wrong screen. Always set `--primary` explicitly in the launch flow.
- **`--primary` is often NOT enough (game opens on the wrong monitor anyway):** many Proton/Unity fullscreen games ignore the xrandr primary flag and open on the monitor at coordinate ORIGIN (0,0) — usually the left monitor. When setting `--primary` (and `-screen-width/-screen-height`) still lands the game on the wrong screen, use a **window-mover wrapper**: snapshot existing window IDs, launch the game, and a background watcher detects the NEW large window (w>=1000,h>=600) and does `wmctrl -ir <id> -b remove,fullscreen; xdotool windowmove <id> <MX> <MY>; xdotool windowsize <id> <W> <H>; wmctrl -ir <id> -b add,fullscreen`. xfwm4 re-fullscreens the window on whichever monitor it currently sits on, so moving it to the target monitor first makes fullscreen land there. This does NOT touch the monitor layout, so desktop icons are undisturbed — preferred over repositioning displays. Re-assert in a loop (Unity recreates its window when switching to fullscreen). Verified working wrapper: `/home/hunter/steam_middle_monitor.sh` (generic) which `/home/hunter/casualties_launch.sh` delegates to. Requires `wmctrl` + `xdotool`.
- **wmctrl uses HEX window IDs, xdotool search returns DECIMAL:** don't cross them. `xdotool windowmove/windowsize` accept either, but `wmctrl -lG` lookups must use the hex id from `wmctrl -l`. Keep the whole wrapper wmctrl-hex-based to avoid the mismatch (a decimal id looked up in wmctrl silently returns nothing).
- **gamescope output-targeting (`-O/--prefer-output`) is unreliable when nested inside an existing X11/XFCE session** — it targets connectors on the DRM backend (when gamescope IS the session compositor), not as a nested window. Use the window-mover instead on a normal X11 desktop.
- **localconfig.vdf is Steam-owned.** Editing `.../userdata/<id>/config/localconfig.vdf` while Steam runs is pointless — Steam overwrites it on exit. If you must edit the file: fully shut down Steam (`killall steam`; confirm no process), back it up, edit, then relaunch. The GUI Properties > Launch Options field is the simpler path and avoids the messy VDF quoting entirely.
- **Wrong log path:** BepInEx 5 logs to `<game>/BepInEx/LogOutput.log`, not `<game>/BepInEx/logs/LogOutput.log`. The `logs/` subdir is a BepInEx 6 thing — don't grep the wrong place.
- **Nexus mod files are login-gated** — the agent cannot download them. Have the user download (free account) and drop the zip in `~/Downloads`; the agent extracts/installs it. Nexus auto-names the file oddly (e.g. `KrokMP 67 4.0.1 2026-...Z 5ZrIboegV.zip`) — match by age/size, not name.
- **Demo vs full game:** the installed build may be a "Demo" sharing the full game's appid; the mod usually still loads but content is limited.
- **Merge, don't clobber:** `cp -r mod/BepInEx/. game/BepInEx/` adds plugins/patchers without touching loader core/.
- **Steam must be running through Steam, not the exe**, or Steam-lobby-based multiplayer will fail to initialize.

## Interaction note
For this user, lead with the concrete deliverable (the exact launch-option string / exact command) and keep exposition short — they ask "what do I put in?" and want just the string.

## References
- `references/casualties-unknown.md` — the concrete instance this was built on (appid 4576510, KrokMP mod, exact verified launch string, file layout).
- `templates/casualties_launch.sh` — reusable launcher wrapper that forces a monitor + BepInEx and avoids the `sh -c` quote-collision bug.
