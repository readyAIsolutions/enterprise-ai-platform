# White-screen diagnostic — Lumen WebGL/Qt surfaces (code-only)

Scope: `lumen/wallpaper/webgl_engine.py` (WebGLSurface), `lumen/wallpaper/web.py`
(WebWallpaper / ShaderWallpaper), `lumen/wallpaper/window.py` (WallpaperWindow),
`lumen/app.py` (_WEBENGINE_FLAGS). Do NOT run Lumen — HARD LEASH.

## Hard rule: child setWindowFlags(FramelessWindowHint) is a NO-OP
- `self.view = QWebEngineView(self)` -> `view` is a CHILD of WallpaperWindow.
- `FramelessWindowHint` = 0x800. `WType_Mask` = 0xff. `windowType() = flags & WType_Mask`.
  0x800 & 0xff = 0x00 = `Widget`. So the child stays a child; it is NOT promoted to a
  top-level window and is NOT detached/hidden. Removing the call changes nothing
  visible. Do not report this as a fix.
- Legitimate top-level FramelessWindowHint uses: window.py WallpaperWindow
  (interactive + non-interactive branches) and drawer.py (a real overlay window).

## Why a QWebEngineView can be WHITE (the real candidates)
The view's default backing before content paints is Chromium's opaque WHITE page.
Mitigations in code: `page().setBackgroundColor(QColor(0,0,0))`, dark HTML body
(web.py shader template `#000`; webgl_engine template dark radial-gradient + `#fb`
dark fallback), and `_BLACK_HTML` fallback when no entry exists. So:
- If the page LOADS, it is dark, never white.
- Persistent WHITE => the page did NOT paint. Suspects, in order:
  1. Compositor off: `_WEBENGINE_FLAGS` includes `--disable-gpu-compositing`
     (AMD-safe, do not remove lightly). On some setups the dark page never
     composites -> stays white. Verify by understanding, not by deleting flags.
  2. Renderer/GPU init failure with `ErrorPageEnabled=False` -> silent blank white.
     Inspect `loadFinished` ok-flag + browser console; confirm `html_path.exists()`
     before `setUrl(QUrl.fromLocalFile(...))` in WebGLSurface.__init__.
  3. Wrong/empty entry: web.py paints `_BLACK_HTML` (black) when entry missing, so
     that path yields black, not white — rules it out as a white cause.

## Safe code-only verification recipe (no display, no Lumen import)
```
cd /home/hunter/Desktop/apps/lumen
# 1. enumerate flag uses
grep -rn "FramelessWindowHint" lumen/
# 2. syntax-only compile (parses AST, imports nothing)
python3 -m py_compile lumen/wallpaper/webgl_engine.py lumen/wallpaper/web.py
# 3. confirm the page body is dark (not the white source)
grep -n "background" lumen/wallpaper/webgl_engine.py lumen/wallpaper/shader.py
```
Never `python -m lumen`, never `import lumen`, never open a QApplication in this
diagnostic. Report findings + an UNVALIDATED section; only a real X11 run can
confirm a white->shader transition.

## Status convention
Write `STATUS_ENIx.md` (DONE|IN-PROGRESS|BLOCKED) with evidence + UNVALIDATED note.
