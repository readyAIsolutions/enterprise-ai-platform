# White-screen root cause + real-PC verification (Lumen)

## The bug (verified on LO's X11 box, DISPLAY=:0.0, XFWM4/nemo)
If Lumen boots with no traceback but the screen is fully WHITE, it is almost
never window stacking. Two causes, both in the web/shader surface:

1. **QWebEngineView white default page.** A `QWebEngineView` (and its
   `QWebEnginePage`) paints an opaque WHITE background until the page/HTML
   loads. On boot you see blinding white even though the GUI and engine are
   fine. Fix in `web.py` (and the shader surface):
   ```python
   from PyQt6.QtGui import QColor
   view.setStyleSheet("background:black;")
   view.setAutoFillBackground(True)
   view.page().setBackgroundColor(QColor(0, 0, 0))
   ```
   Also set the page HTML `<body>` background to `#000` (build_shader_html).
2. **Blank default wallpaper assignment.** If the default first-run wallpaper
   is a Steam Workshop web wallpaper that loads blank (e.g. "Adventure Cat"),
   you get white too. Default first-run to a bundled colourful sample
   ("Nebula Drift") instead.

## Window stacking (what it is NOT)
Under XFWM4/nemo, `X11BypassWindowManagerHint` (unmanaged) is CORRECT for
non-interactive wallpapers: it sits BELOW the managed GUI and BELOW
`nemo-desktop`, so the dark GUI stays visible AND desktop icons are preserved.
The "bypass renders above the GUI" claim was wrong for this compositor.

## Verify on LO's real PC (not xvfb)
When `DISPLAY` is set and the PyQt6 venv exists, test live and MEASURE:
```bash
cd ~/Desktop/apps/lumen
DISPLAY=:0.0 timeout 12 .venv/bin/python -m lumen
# grab the primary monitor (replace WxH and +xoff+yoff with primary geometry)
ffmpeg -y -f x11grab -r 1 -s 2560x1080 -i :0.0+1920+0 -frames:v 1 /tmp/lumen_shot.png
```
Then measure with PIL:
```python
from PIL import Image
import numpy as np
im = np.asarray(Image.open('/tmp/lumen_shot.png').convert('RGB'))
print("sidebar dark?", im[500:560, 1950:2000].mean(axis=(0, 1)))  # ~ (24,19,44)
print("wallpaper stddev", im.reshape(-1, 3).std(axis=0).mean())    # > 40 = colourful
near_white = (im.mean(axis=2) > 250).mean()                        # < 0.01 = good
```
Dark structured GUI + high-variance wallpaper + <1% near-white => fixed.
