# X11 Wallpaper Bottom-Stacking (icon-safe under XFWM4)

## The trap
Goal: wallpaper window BELOW `nemo-desktop` icons. Naive approach —
set `_NET_WM_WINDOW_TYPE_DESKTOP` + `_NET_WM_STATE_BELOW` (ClientMessage) +
`WA_X11NetWmWindowTypeDesktop`. This FAILS on XFCE/XFWM4 because:

- Qt appends `_NET_WM_WINDOW_TYPE_NORMAL` to whatever desktop hint you set.
  Probe of the resulting atom list:
  `[_NET_WM_WINDOW_TYPE_DESKTOP, _KDE_NET_WM_WINDOW_TYPE_OVERRIDE, _NET_WM_WINDOW_TYPE_NORMAL]`
- XFWM4 sees a multi-type list, ignores DESKTOP, treats window as NORMAL →
  stacks it ABOVE the `nemo-desktop` DESKTOP windows → covers icons.
- `Qt.Tool` is worse: forces `_NET_WM_WINDOW_TYPE_UTILITY` → also above icons.
- A remap trick (delete NORMAL atom after map) does not stick — Qt re-asserts.

## The fix (verified)
For NON-INTERACTIVE wallpapers (web/video/image/shader — no clicks needed):
use `Qt.WindowType.X11BypassWindowManagerHint`. This removes the window from
WM management entirely, so no EWMH type matters. Then `XLowerWindow` drops it
to the absolute bottom of the X root children list.

Probe proof (python-xlib):
```python
from PyQt6.QtWidgets import QWidget
from PyQt6.QtCore import Qt
from Xlib import display
w = QWidget()
w.setWindowFlags(Qt.WindowType.X11BypassWindowManagerHint)
w.setGeometry(1920, 0, 2560, 1080)   # over target monitor
w.show()
d = display.Display()
xw = d.create_resource_object("window", int(w.winId()))
xw.configure(x=1920, y=0, width=2560, height=1080)
d.sync()
xw.lower()           # XLowerWindow
root = d.screen().root
kids = root.query_tree().children
print(kids.index(xw) == 0)   # -> True: absolute bottom, below nemo frames
```
Live Lumen run: wallpaper windows landed at root-stack indices **3–14 of 232**
total — i.e. below `nemo-desktop` frames (icons safe, confirmed by process check).

For INTERACTIVE web wallpapers (need mouse): keep managed with
`WindowStaysOnBottomHint` (not bypass); accept it sits above icons only while
that wallpaper is the active interactive one.

## X11 helper (`lumen/utils/x11.py`)
- `set_wallpaper_window(win_id, monitor)` — managed-window path: write
  `_NET_WM_WINDOW_TYPE_DESKTOP`, `_NET_WM_STATE_BELOW`/`SKIP_PAGER`/
  `SKIP_TASKBAR`, `_NET_WM_DESKTOP=0xFFFFFFFF`, deliver as ClientMessage, then
  `win.configure(stack_mode=X.Below)` + `d.sync()`. Recurse into child windows
  (Chromium spawns child frames that also must be lowered).
- `ensure_desktop_bg_transparent()` — write a 1x1 transparent PNG to
  `~/.local/share/lumen/transparent.png` if missing, then
  `gsettings set org.nemo.desktop picture-uri "file://..."` (plus cinnamon/gnome
  variants) so the wallpaper shows through behind icons regardless of prior
  nemo state. Call at startup BEFORE seeding samples.

## Verification one-liner
```python
from Xlib import display
d = display.Display(); root = d.screen().root
kids = root.query_tree().children
print("total root children:", len(kids))
# locate your wallpaper windows by geometry, assert they sit at the LOW indices
```
Wallpaper windows must be at the LOW indices (bottom). If they're high (above
nemo), the bypass/lower did not take and icons will be buried.

## Note on screenshots
You cannot easily screenshot the bare desktop to prove icon safety when the
user has full-screen apps (trading terminal/browser) painted over the desktop
by the compositor — `xdotool windowminimize`/move attempts hit WM issues and
hide 0 windows. Trust the structural proof (root-child index) and ask LO to
glance at his screen.
