---
name: lumen-wallpaper-window-fix
description: Fixes the Lumen live-wallpaper bug where the wallpaper ("took over my whole PC", covered the desktop, forced reboots) instead of sitting behind the desktop icons/apps on X11. Use whenever Lumen paints a fullscreen wallpaper that hijacks the screen, or when touching lumen/wallpaper/window.py / x11.py stacking.
---

# Lumen wallpaper must never cover the desktop / apps

## Symptom
Lumen launches (manual or autostart) and paints a fullscreen, opaque wallpaper
that sits ON TOP of everything. Mouse may pass through (WA_TransparentForMouseEvents)
but you can't SEE or use any app -> user reboots. On LO's box this has happened
at login (autostart) and on manual launch.

## Root cause
`lumen/wallpaper/window.py` WallpaperWindow.__init__ non-interactive branch used
`X11BypassWindowManagerHint` (override-redirect / UNMANAGED window). An unmanaged
window cannot be restacked by the WM, so the whole "sit at the bottom" behaviour
depended entirely on `x11.set_wallpaper_window()` succeeding (python-xlib lowering
the window). If that ever failed (X not ready at login, xlib import hiccup, timing
race), the override-redirect fullscreen window was left with NO bottom hint and
painted on top of the desktop + every app. The interactive branch was already a
safe managed window -- only the DEFAULT (`interactive: False`) path was dangerous.

## The fix (canonical desktop-wallpaper pattern)
In window.py, replace `X11BypassWindowManagerHint` in the non-interactive branch
with `WindowStaysOnBottomHint` (keep FramelessWindowHint + WindowDoesNotAcceptFocus).
A normally-MANAGED bottom window physically CANNOT cover the user's apps: worst
case it sits behind the desktop icons, but all normal windows always stay above it.
Keep `x11.set_wallpaper_window()` (sets _NET_WM_WINDOW_TYPE_DESKTOP + _NET_WM_STATE_BELOW
via ClientMessage) as best-effort reinforcement -- now harmless if it fails.

```python
# non-interactive branch in WallpaperWindow.__init__
self.setWindowFlags(
    Qt.WindowType.FramelessWindowHint
    | Qt.WindowType.WindowDoesNotAcceptFocus
    | Qt.WindowType.WindowStaysOnBottomHint
)
```

## Verify
- `grep -n X11BypassWindowManagerHint lumen/wallpaper/window.py` -> only in comments.
- `.venv/bin/python -m py_compile lumen/wallpaper/window.py` -> OK.
- All wallpaper types inherit WallpaperWindow (WebWallpaper, ShaderWallpaper->WebWallpaper,
  VideoWallpaper, ImageWallpaper); the fix covers all. The Chromium `view` is a CHILD
  (`QWebEngineView(self)`) so its own setWindowFlags is a no-op -- top-level flags come
  from WallpaperWindow.
- Only remaining `showFullScreen()` is engine.py `_apply_wayland` (Wayland-only; also
  uses WindowStaysOnBottomHint). Not used on X11.

## Autostart (separate, must also be OFF)
Lumen must NOT auto-start on LO's box. Use `lumen.autostart.set_autostart(False)`
(config key `start_on_boot` defaults False; GUI toggle writes ~/.config/autostart/lumen.desktop
+ optionally a systemd --user lumen.service). Hard-disable both via the API and confirm
`is_autostart_enabled() == False`. LO boots Lumen HIMSELF (Desktop "Lumen" icon ->
`python -m lumen`, the app window, which also paints the safe background wallpaper).

## HARD RULE (do not violate)
Never auto-enable Lumen startup and never let its wallpaper take over the screen.
Both have repeatedly "fucked" LO's session (forced reboots, unusable PC). The
wallpaper must ALWAYS sit behind desktop icons/apps. If a change risks either,
stop and confirm with LO first.

## XFCE desktop architecture on LO's box (CRITICAL — read before touching desktop/icons/workspaces)
Lumen lives ON this desktop, so its layer model depends on how XFCE lays the
desktop out. Two managers are involved and BOTH must stay alive:
- **nemo-desktop** owns the DESKTOP ICONS.
- **xfdesktop** (XFCE's own) owns the WORKSPACES + the session desktop layer.

`xfdesktop` `desktop-icons/style = 3` = "file manager handles the desktop":
xfdesktop does NOT draw icons and delegates them to nemo. This is the CORRECT
value. (0=none, 1=minimized, 2=FM [older], 3=FM-mode on this build.)

**PITFALL (cost LO a broken session this run):** do NOT kill xfdesktop, do NOT
set `style=0`, and do NOT drop a `Hidden=true` xfdesktop autostart override.
xfdesktop owns workspaces — removing it makes the workspace/desktop layer
misbehave (terms appear to jump workspaces, desktop feels "broken"). Keep
xfdesktop running and autostarted (its default autostart is fine).

**PITFALL:** do NOT put `OnlyShowIn=XFCE;` in the nemo-desktop autostart.
If the session string differs even slightly it is SILENTLY skipped and icons
vanish again after reboot.

### Verified fix: icons visible AND persistent after reboot
1. `gsettings set org.nemo.desktop ignored-desktop-handlers "['conky','csd-background','xfdesktop']"`
   — nemo draws even though xfdesktop is present.
2. `xfconf-query -c xfce4-desktop -p /desktop-icons/style -s 3` — FM mode (nemo owns
   icons; xfdesktop stays alive for workspaces).
3. Create `~/.config/autostart/nemo-desktop.desktop` (Exec=nemo-desktop, NO
   OnlyShowIn, `AutostartCondition=GSettings org.nemo.desktop show-desktop-icons`).
   → nemo starts at login → icons survive reboot.
4. Ensure xfdesktop is NOT disabled (no Hidden=true override).
5. `gsettings set org.nemo.desktop show-desktop-icons true`.

### "Ugly" desktop — nemo 6.4.5 CANNOT wallpaper
nemo 6.4.5's schema has NO wallpaper key (no `picture-uri` / `background-color`;
only `background-fade`). It paints the GTK theme's desktop background — by default
the light **Greybird** theme → washed-out/ugly. Workaround that keeps Lumen's
nemo-layer design intact (no desktop-manager switch, no Lumen rework):
- `gsettings set org.gnome.desktop.interface gtk-theme 'Greybird-dark'`
- `xfconf-query -c xfwm4 -p /general/theme --create -s 'Greybird-dark'` (dark borders)
- (xsettings `/Gtk/ThemeName` may need `--create` if missing; gsettings is the
  authoritative GTK source nemo reads.)
- restart nemo: `pkill -x nemo-desktop; nemo-desktop &`
- Reversible; terminal profiles are separate (stay black/white). User dislikes
  purple GTK themes — avoid Yaru-purple*; Greybird-dark / Adwaita-dark are safe.
- For a REAL image wallpaper instead: either (a) flip desktop to xfdesktop-managed
  (then Lumen's `ensure_desktop_bg_transparent()` must be RE-POINTED to the
  xfce4-desktop backdrop) or (b) install `feh` and set root bg (needs nemo
  transparent — not guaranteed). Flat dark is the safe default.

### KNOWN GAP (UNVALIDATED — do not assume Lumen shows behind icons)
Lumen's `utils/x11.py ensure_desktop_bg_transparent()` sets
`org.nemo.desktop picture-uri` to a 1x1 transparent PNG. On nemo 6.4.5 that key
DOES NOT EXIST (confirmed via `gsettings list-keys` + `dconf dump`), so the call
is a silent NO-OP. If nemo's desktop window paints an opaque GTK bg, Lumen's
bottom window would be HIDDEN behind it. Before claiming "Lumen wallpaper works
behind icons" on this box, VERIFY (launch Lumen, confirm wallpaper visible behind
icons); if hidden, re-point `ensure_desktop_bg_transparent()` to set the
xfce4-desktop backdrop transparent, or make nemo's desktop transparent another way.

See references/xfce-desktop-architecture.md for the full command transcript +
diagnosis recipe.

## Kill switch if anything misbehaves
`pkill -f 'lumen'` (kills the app + its wallpaper child surfaces). Boot guard
(~/.config/lumen/boot_guard.json, safe_mode) auto-disables wallpapers after 2 crash
loops; reset by writing defaults or deleting the file so wallpapers paint again.

## White screen (different symptom — blank opaque WHITE/light full-screen, NOT a takeover)
This is NOT the "took over my PC" bug above. Symptom: the wallpaper surface is a
plain WHITE/light window where the shader/WebGL content should be.

CODE-ONLY diagnostic protocol (HARD LEASH — never run/import/activate Lumen; no
QApplication, no display, no venv launch):
- Enumerate every flag use: `search_files pattern="FramelessWindowHint"`. Separate
  CHILD-view `setWindowFlags` calls (web.py / webgl_engine.py `_configure`, where
  `self.view = QWebEngineView(self)`) from real top-level-window calls (window.py
  WallpaperWindow branches + drawer.py — those are legitimate and must stay).
- Reason from Qt semantics, do NOT guess-and-edit-and-claim. A CHILD QWidget's
  `setWindowFlags(FramelessWindowHint)` is a NO-OP for visibility: FramelessWindowHint
  (0x800) is a hint bit, NOT in WType_Mask (0xff), so `windowType()` stays `Widget`
  and the widget remains a child of its parent. It does NOT detach into a separately
  shown top-level window. => removing that line is cosmetic; it is NOT a white-screen
  cure. (The earlier note "child setWindowFlags is a no-op" in this skill is correct;
  do NOT "fix" white screens by deleting that line and declaring victory.)
- Validate syntax ONLY with `python -m py_compile lumen/wallpaper/<file>.py` — it
  parses the AST, imports nothing, touches no display. Never `import lumen` to test.
- Prime suspects for a PERSISTENT white QWebEngineView (when the dark HTML body /
  `page().setBackgroundColor(black)` should otherwise show):
  1. `--disable-gpu-compositing` in app.py `_WEBENGINE_FLAGS` (set for AMD safety).
     Disabling the compositor can leave the page uncomposited/white on some GPUs;
     the dark page only appears once compositing paints it. Investigate BEFORE
     touching these flags — they exist specifically to stop driver reboots.
  2. The page never paints (GPU/renderer init fails) while ErrorPageEnabled=False
     hides the failure -> blank white view. The WebGL template uses a dark
     radial-gradient body + a `#fb` dark fallback, so a *loaded* page is never white;
     white means the page did not paint. Check the surface's `loadFinished`/console
     and whether `html_path` actually exists before `setUrl`.
- Always write STATUS_ENIx.md with DONE/IN-PROGRESS/BLOCKED, the evidence (grep +
  py_compile), and an explicit UNVALIDATED section: never claim "white screen fixed"
  without a display-run, because the real cause may be GPU/compositor, not the code.

See references/white_screen_diagnostic.md for the candidate matrix + recipe.
