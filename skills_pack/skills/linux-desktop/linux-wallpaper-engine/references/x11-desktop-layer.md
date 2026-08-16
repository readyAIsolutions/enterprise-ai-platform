# X11 Desktop-Layer Window (the core trick)

Goal: make a mapped Qt window behave like the desktop — bottom of the stack,
skipped by pagers/taskbars, present on every virtual desktop, with the file
manager's icons rendered on top of it.

## Working python-xlib implementation

```python
from Xlib import X
from Xlib.X import Xatom
from Xlib import protocol

_disp = None
def _display():
    global _d
    if _d is None:
        from Xlib.display import Display
        _d = Display()
    return _d

def set_wallpaper_window(win_id: int, interactive: bool = False) -> bool:
    d = _display()
    root = d.screen().root
    win = d.create_resource_object("window", int(win_id))
    a = lambda n: d.intern_atom(n)

    # Tag as a desktop window.
    win.change_property(a("_NET_WM_WINDOW_TYPE"), Xatom.ATOM, 32,
                        [a("_NET_WM_WINDOW_TYPE_DESKTOP")])
    # Present on every virtual desktop.
    win.change_property(a("_NET_WM_DESKTOP"), Xatom.CARDINAL, 32, [0xFFFFFFFF])

    states = [a("_NET_WM_STATE_SKIP_PAGER"), a("_NET_WM_STATE_SKIP_TASKBAR")]
    if not interactive:
        states.append(a("_NET_WM_STATE_BELOW"))
    win.change_property(a("_NET_WM_STATE"), Xatom.ATOM, 32, states)

    # EWMH requires state changes sent as a ClientMessage too.
    for st in states:
        ev = protocol.event.ClientMessage(
            window=win, client_type=a("_NET_WM_STATE"),
            data=(32, [1, st, 0, 1, 0]))   # 1 = add
        d.send_event(root, ev,
                     event_mask=X.SubstructureRedirectMask |
                                X.SubstructureNotifyMask)
    d.flush()
    return True
```

Call `set_wallpaper_window(int(widget.winId()))` **after** `widget.show()`.

## Pitfalls
- Property writes alone are often ignored; the `ClientMessage` is what makes
  the WM actually apply `_NET_WM_STATE`.
- `winId()` on X11 returns the real X window id — pass it directly (cast to int).
- Wrap the whole `Xlib` import in try/except and early-return False on Wayland
  (`XDG_SESSION_TYPE.startswith("wayland")`) so headless/dev builds survive.
- For interactive mode, send the same message with action `0` (remove) on
  `_NET_WM_STATE_BELOW` so the window can receive input.
- Keep `WA_TransparentForMouseEvents` set on non-interactive surfaces so the
  desktop beneath (icons, right-click menu) stays fully usable.
