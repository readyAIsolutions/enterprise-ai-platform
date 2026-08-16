# Debugging a white / blank Lumen GUI

## Symptom
Lumen launches (boots without a traceback, log shows "Applied …" / "Slideshow
started") but the user sees an all-white or blank screen.

## Two possible causes
1. **The GUI itself is broken** — the QSS failed to load, a layout collapsed,
   or a widget renders white. Rare if the app constructs without error.
2. **An overlaying fullscreen surface is painting on top of the GUI** — almost
   always the *wallpaper* window. A fullscreen wallpaper surface that isn't
   correctly parked at the bottom of the stack covers the entire GUI, and if
   that wallpaper renders white/blank (a web page that failed to load, a white
   image, an uninitialized shader) the user sees a white screen.

Cause #2 is by far the more common "white screen" in Lumen. **Do not start
editing the GUI or QSS** — confirm which layer is white first.

## Triage (no access to the user's display needed)
Run the GUI under a virtual display with a **stub engine** so NO wallpaper
windows are created — this isolates the GUI:

```
xvfb-run -a python scripts/diag_gui.py        # saves /tmp/gui.png
```

Then measure brightness with PIL (see snippet below). Decision:
- **Grab is dark + structured** (mean RGB ~80, sidebar near-black, top bar
  dark, only ~15–20% near-white pixels from card previews) → the GUI and QSS
  are FINE. The white screen is an *overlaying wallpaper surface*. Fix window
  stacking, not the GUI.
- **Grab is white/light** → the GUI/QSS really is the problem (stylesheet
  dropped due to a syntax error, or a transparent/white widget). Inspect the
  QSS and the central-widget layout.

### Brightness check snippet
```python
from PIL import Image
im = Image.open("/tmp/gui.png").convert("RGB"); px = im.load()
w,h = im.size
def avg(b):
    rs=gs=bs=n=0
    for x in range(b[0],b[2],4):
        for y in range(b[1],b[3],4):
            r,g,b_=px[x,y]; rs+=r; gs+=g; bs+=b_; n+=1
    return (rs//n, gs//n, bs//n)
print("sidebar", avg((10,80,180,400)), "topbar", avg((220,10,1100,55)))
white = sum(1 for x in range(0,w,7) for y in range(0,h,7)
            if all(px[x,y][c] > 235 for c in range(3)))
print("near-white %%", 100*white//((w//7)*(h//7)))
```

## Fix when it's an overlaying wallpaper surface
The wallpaper window must sit **below** the GUI. See the Pitfalls note
"Wallpaper window must NOT use X11BypassWindowManagerHint" in SKILL.md: use a
**managed** `WindowStaysOnBottomHint` (not `X11BypassWindowManagerHint`, which
renders above managed windows like the GUI on several compositors) and
re-assert bottom with `QWidget.lower()` + `set_wallpaper_window()` AFTER the
GUI is shown (`engine.lower_all()`).
