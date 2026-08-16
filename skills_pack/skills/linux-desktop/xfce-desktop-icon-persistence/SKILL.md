---
name: xfce-desktop-icon-persistence
description: Stop XFCE desktop icons/folders from vanishing after a reboot or logout-login. On LO's box the icon provider is nemo-desktop, but XFCE's own xfdesktop is RUNNING and grabs the desktop, so nemo logs "Desktop already managed by another application" and draws nothing. Also nemo-desktop has no default autostart. Use whenever the user reports "my desktop icons/folders are gone after reboot" (a recurring, 5x-reported complaint) or you are wiring a wallpaper engine that depends on nemo-desktop's transparent background.
---

# Keep XFCE desktop icons alive across reboots

## Trigger
User says icons / folders on the desktop disappeared after a reboot or login.
Recurring on LO's box (reported 5+ times). NOT purely a Lumen bug — it's a desktop
config gap that ALSO silently breaks Lumen's transparent-background trick.

## Root cause (BOTH are true — fix BOTH)
1. **xfdesktop is running and STEALS the desktop.** XFCE's own `xfdesktop` is live
   (it was pid 9385 on this box) and grabs the desktop. nemo-desktop then refuses:
   `Desktop already managed by another application, skipping desktop setup.` So even
   if nemo autostarts, it bows out and you get NO icons. THIS is the real cause of
   the 5x complaint — not just a missing nemo autostart.
2. **nemo-desktop has no default autostart**, so even when allowed, nothing repaints
   the desktop after login.

The older hypothesis ("xfdesktop autostart is absent so nothing repaints") was
INCOMPLETE: xfdesktop was actually RUNNING and competing. You must make nemo ignore
xfdesktop AND disable xfdesktop, not just autostart nemo.

## Diagnose
```
echo "DISPLAY=$DISPLAY"
pgrep -a xfdesktop                                       # running? it's stealing the desktop
gsettings get org.nemo.desktop ignored-desktop-handlers  # xfdesktop MUST be listed
gsettings get org.nemo.desktop show-desktop-icons        # must be true
pgrep -a nemo-desktop                                    # running? if not, no icons
```
If `nemo-desktop` exits immediately with "Desktop already managed by another
application", xfdesktop is the culprit.

## The fix (all three parts)
### 1. Make nemo IGNORE xfdesktop
```
gsettings set org.nemo.desktop ignored-desktop-handlers "['conky','csd-background','xfdesktop']"
```
Tells nemo to ignore xfdesktop's claim and draw anyway. #1 missed step.

### 2. Disable xfdesktop for the desktop (kill now + stop at login)
```
xfconf-query -c xfce4-desktop -p /desktop-icons/style -s 0   # xfdesktop shows no icons
cat > ~/.config/autostart/xfdesktop.desktop <<'EOF'
[Desktop Entry]
Type=Application
Name=xfdesktop
Exec=xfdesktop
Hidden=true
NoDisplay=true
EOF
pkill -x xfdesktop                                       # kill the running one now
```

### 3. Autostart nemo-desktop (icons return after reboot)
```
cat > ~/.config/autostart/nemo-desktop.desktop <<'EOF'
[Desktop Entry]
Type=Application
Name=Nemo Desktop
Comment=Draw the desktop and its icons with Nemo (so they survive a reboot)
Exec=nemo-desktop
AutostartCondition=GSettings org.nemo.desktop show-desktop-icons
X-GNOME-Autostart-Phase=Desktop
X-GNOME-Autostart-Delay=2
X-GNOME-AutoRestart=true
NoDisplay=true
EOF
```
Deliberately NO `OnlyShowIn=XFCE;` — see Pitfall.

## PITFALL: .desktop launchers need `metadata::trusted=true` or xfce won't run them
A `.desktop` on the Desktop is NOT executed on double-click just because its file mode is
executable (`-rwxr-xr-x`). xfce (gvfs) requires the `metadata::trusted` extended attribute to be
`true`; without it, a click opens the file in a text editor or does nothing. This is a separate
axis from the icon-persistence bug above, but bites whenever you CREATE a shortcut on the Desktop
(games, apps, tools). After writing any Desktop `.desktop`, run:
  ```bash
  gio set "/home/hunter/Desktop/<Name>.desktop" "metadata::trusted" true
  ```
Verify: `gio info -a "metadata::trusted" <file>` → `metadata::trusted: true`. Force a re-read
with `pkill -HUP xfdesktop` (or logout/login) if the click still misbehaves. Also note: an inline
`env VAR=... command` Exec line does NOT reliably pass env vars when xfce launches it — prefer
pointing Exec at a wrapper script that sets the env itself. (Full game-launcher case study in
skill `linux-repack-wine-install`, Pitfall J.)

## PITFALL: NEVER `pkill -HUP xfdesktop` (or otherwise restart xfdesktop) to refresh launchers
On this box the ACTIVE desktop manager is **nemo-desktop**, NOT xfdesktop. xfdesktop may
show as a running process but it is NOT what paints the desktop or owns the panel/taskbar.
Running `pkill -HUP xfdesktop` (the "re-read .desktop" trick recommended on stock XFCE)
DESTROYS the panel here — `xfce4-panel` dies and minimized windows have nowhere to go,
so the user sees "apps don't disappear when I minimize them" / "desktop is glitched".
This happened in a live session and required a full desktop-stack restart to recover.
  - To refresh a new/changed Desktop `.desktop`, set `metadata::trusted` (above) and rely on
    nemo-desktop picking it up; if a hard refresh is truly needed, restart nemo-desktop
    (`kill -9 <nemo-desktop pid>` then relaunch via terminal(background=true)), NOT xfdesktop.
  - If the panel IS dead (minimize broken), the fix is: relaunch `nemo-desktop` + `xfce4-panel`
    (both via terminal(background=true)), then `xfwm4 --replace` if the WM is also affected.
    Verify with `wmctrl -l` + minimize a test window → `xwininfo -id <id>` should show
    `IsUnMapped` (proves minimize works again).
  - Symptom checklist that means "you broke the desktop with a bad pkill": panel gone,
    minimized windows don't vanish, `pgrep xfce4-panel` returns nothing, `nemo-desktop`
    still alive but confused.

## PITFALL: killing nemo-desktop / xfwm4 / xfce4-panel from a terminal CREATES DUPLICATE LAYERS (ghost tabs)
This is the #1 way to BREAK LO's desktop in a live session — it happened and made him
furious ("ghost tabs when I move a window"). Mechanics:
- `xfce4-session` (pid ~8501 on this box) autostarts `nemo-desktop` via
  `~/.config/autostart/nemo-desktop.desktop` AND manages `xfwm4` + `xfce4-panel`.
- If you `kill -9` the running nemo-desktop, the session does NOT always respawn it on
  death (autostart only fires at LOGIN here). Desktop goes BLANK (0 nemo, no background/icons).
- If you then manually `nemo-desktop` from terminal AND the session's copy is also still
  alive, you get TWO nemo-desktop processes. Two desktop layers STACKED = "ghost tabs" /
  rendering glitches when you drag a window. Same for xfwm4 (`xfwm4 --replace` can leave a
  stale original + a new one = 2 WMs fighting = glitches) and xfce4-panel (2 panels).
- REMEDY (surgical, NO session restart — LO forbade restart): get real PIDs, keep exactly
  ONE of each, kill only the DUPLICATE by explicit PID:
  ```bash
  # list real PIDs, EXCLUDING your own shell ($$), and note parents
  for p in $(pgrep -f nemo-desktop | grep -v "bash -c" | grep -v "^$$\$"); do
    echo "nemo $p ppid=$(ps -o ppid= -p $p | tr -d ' ')"; done
  # the session-managed one has ppid=1 or ppid=xfce4-session; the one YOU launched
  # has ppid = your bash wrapper. Kill the duplicate (your manual one OR the orphan),
  # NEVER both. Then verify count == 1.
  ```
- A "2" in pgrep counts is often a FALSE POSITIVE: your own `bash -lic '... nemo-desktop ...'`
  wrapper matches `pgrep -f nemo-desktop`. Always subtract your shell (the wrapper shows as
  a `bash -lic` cmdline, not a real `nemo-desktop` binary). Trust `ps -o ppid=` over raw pgrep.

## PITFALL: `pkill`/`kill` SELF-KILL trap — never put the target process name in your own cmdline
`pgrep -f xfwm4` / `pkill -f nemo-desktop` match the agent's OWN shell command line (which
contains that string), so the kill signal hits the shell → command dies with exit -9/-15 and
half the work is undone (e.g. the `mv`/`chmod` after a `pkill` never runs). Observed repeatedly.
  - Kill by EXPLICIT PID only: `kill -9 3958942` (number, not a process-name pattern).
  - The PID number must NOT appear inside a string that later matches the name (it won't —
    a bare PID is safe). Avoid `kill -9 $(pgrep -f xfwm4)` inside the same command that
    echoes "xfwm4" — split into two commands, or the shell matches itself.
  - Same trap bites `pkill -f "Launcher.exe"` when your command line also contains
    "Launcher.exe" (the test-launch string). Use `kill -9 <pid>` from a prior `pgrep` output.

## PITFALL: launching Proton/Steam games can KILL the compositor (black windows, no background)
After running Windows repack games under Steam's Proton (or any Steam/gamescope game) on
LO's box, the XFCE **compositor can die** and will NOT come back from xfwm4 restarts alone.
Symptoms the user reports: "tabs remain black", "no background", "workspaces switch but
content is black/blank". This is a separate axis from the duplicate-layer bug above.
Root cause observed in a live session:
- Steam/gamescope left `GAMESCOPE_*` properties on the X root window
  (`xprop -root` shows GAMESCOPE_COMPOSITE_FORCE, GAMESCOPE_DISPLAY_HDR_ENABLED, etc.).
- xfwm4's GL compositor then fails to (re)acquire the composite-manager slot:
  `xprop -root _NET_WM_CM_S0` returns "not found" even though `use_compositing=true`.
- Toggling `use_compositing` off/on, `xfwm4 --replace`, and killing/respawning xfwm4 ALL
  FAILED to restore `_NET_WM_CM_S0` in that session. The GL/compositor state at the X
  driver level was stuck from the game launch.
Diagnose:
```bash
DISPLAY=:0 xprop -root _NET_WM_CM_S0          # "not found" = compositor dead
DISPLAY=:0 xprop -root | grep -c GAMESCOPE    # >0 = stale Steam/gamescope props
xfconf-query -c xfwm4 -p /general/use_compositing   # likely "true" but CM unowned
```
Things that did NOT fix it (do not waste a session re-trying): toggling use_compositing,
`xfwm4 --replace`, killing+session-respawn of xfwm4, removing the GAMESCOPE root props
via `xprop -root -remove` (props gone but CM still unowned).
The ONLY reliable recovery seen: a clean **session restart** (`xfce4-session-logout --restart`)
which rebuilds the X display state. LO initially forbade restart ("no restart, fix what you
did") — if he holds that line, the best you can do is: kill the stray Steam client (pgrep
steam), remove GAMESCOPE props, restart xfwm4 once, and TELL HIM the compositor needs a
session restart to fully recover. Do NOT keep firing xfwm4 commands — each one risks
re-creating duplicate layers (see trap above) and makes it worse.
PREVENTION: prefer launching Proton games via a wrapper script that does NOT leave Steam's
display layer hooked (or just accept that a session restart may be needed after a gaming
session). Capture the GAMESCOPE-prop side effect in skill `wine-repack-install` too.

## PITFALL: do NOT add OnlyShowIn=XFCE;
`OnlyShowIn=XFCE;` makes the autostart SILENTLY SKIPPED if XDG_CURRENT_DESKTOP is
not exactly "XFCE". A skipped entry => icons still missing => exact bug returns.
Omit OnlyShowIn; the AutostartCondition already gates it (show-desktop-icons is
XFCE/nemo-specific, won't wrongly fire on other DEs).

## Launch now (no reboot needed)
The agent sandbox CAN reach the host X display (DISPLAY=:0 works; xrandr/gsettings
function) but shell-level background wrappers (nohup/disown/`setsid &`) are BLOCKED
by the platform. Launch nemo-desktop with `terminal(background=true)`:
```
nemo-desktop
sleep 3; pgrep -a nemo-desktop; xdotool search --class nemo | wc -l   # expect running + windows
```
nemo creates one desktop window per monitor (4 on this box).

## Verify after reboot
Log back in; icons must be present on all monitors and `pgrep xfdesktop` empty.
If you see DOUBLE icons (nemo + xfdesktop), xfdesktop respawned — re-check the
Hidden=true override and `desktop-icons/style=0`.

## Coupling with Lumen (wallpaper engine)
Lumen's `lumen/utils/x11.py ensure_desktop_bg_transparent()` sets
`org.nemo.desktop picture-uri` to a 1x1 transparent PNG so the Lumen wallpaper shows
BEHIND the nemo icons. That only works if nemo-desktop owns the desktop. Keep
nemo-desktop autostart ON and xfdesktop OFF; never disable nemo-desktop or
re-enable xfdesktop for the desktop. Lumen itself must NEVER autostart (see skill
`lumen-wallpaper-window-fix`).

## RECOVERY: desktop already broken (ghost tabs / blank / no minimize / BLACK windows) — surgical fix, NO restart
LO forbade `xfce4-session-logout --restart` ("no restart, fix what you did"). Steps that
actually recover without a login cycle:
1. Get real PIDs (exclude shell `$$`): `pgrep -f nemo-desktop | grep -v bash -c | grep -v "^\$\$"`
2. If nemo count > 1: keep the session-managed one (ppid 1 or xfce4-session), `kill -9` the
   duplicate(s) by explicit PID. If nemo count == 0: relaunch ONCE via `terminal(background=true)`
   `nemo-desktop` and do NOT also rely on autostart (it may not fire mid-session) — but watch
   for the session then ALSO spawning one (you'll see 2; kill the orphan).
3. xfwm4: keep ONE (ppid 1 = original). If 2, `kill -9` the stale `xfwm4 --replace` child.
4. xfce4-panel: if 0 (minimize broken) relaunch via `terminal(background=true)` `xfce4-panel`.
   If 2, kill the duplicate by PID.
5. BLACK WINDOWS / NO BACKGROUND (compositor dead): check `xprop -root _NET_WM_CM_S0`
   ("not found" = dead). This is NOT fixed by the layer steps above. If LO forbids restart,
   do the minimal: kill stray Steam (`pkill -x steam` / pgrep steam), `xprop -root -remove`
   each GAMESCOPE_* prop, `xfwm4 --replace` once, then TELL HIM a session restart is required
   to fully restore the compositor (see the compositor PITFALL above). Do NOT loop xfwm4
   restarts — they don't recover a dead GL compositor and risk duplicate layers.
6. Verify: `wmctrl -l | grep -iE "nemo-desktop|Desktop"` shows desktop windows; minimize a test
   Thunar → `xwininfo -id <id>` shows `IsUnMapped` (minimize works); `wmctrl -d | wc -l` == 4
   (workspaces intact); `xprop -root _NET_WM_CM_S0` shows a window id (compositor alive).
   Leave it alone once stable — do NOT relaunch again.

## Support files
- references/nemo-autostart.desktop — the exact nemo autostart file.
- references/xfce-nemo-fix-notes.md — verified session transcript (xfdesktop pid
  9385 stealing the desktop, ignored-desktop-handlers before/after, kill + nemo up).
