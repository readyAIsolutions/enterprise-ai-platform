# Wallpaper Engine import + real-WE binary reference

## Steam (snap) workshop path
LO's Steam is installed as a **snap**, so the real workshop collection lives at:
```
/home/hunter/snap/steam/common/.local/share/Steam/steamapps/workshop/content/431960/
```
NOT `~/.steam` and NOT `~/.local/share/Steam` (classic paths). Always scan all
three plus `/home/hunter/.steam/steam/steamapps/workshop/content/431960/` as
fallbacks. Each subfolder is a wallpaper id (`<uint>`).

## Import strategy
- **Symlink, do not copy.** `ln -s <workshop>/<id> ~/.local/share/lumen/wallpapers/wp_<id>`
  so Lumen mirrors the live Steam subscription and never duplicates gigabytes.
- Scan with `Path(lib)/glob("wp_*")` + `glob("*")` (Lumen's own `lumen.json`
  samples). Every entry must resolve a preview/background or it's skipped.
- LO's collection (146 folders): ~39 web, ~85 scene, ~24 video, rest image/shader.

## Wallpaper Engine project.json (per folder)
```
{
  "title": "...",
  "description": "...",
  "type": "scene" | "web" | "video" | "image",
  "preview": "preview.gif",            # or preview.jpg/mp4
  "contentrating": "...",
  "tags": [ ... ],
  "file": "project.json"               # web/video/image entry
}
```
- **scene** = 3D Unity. Lumen has no Unity runtime → render the bundled
  `preview.gif`/`preview.mp4` (the live clip WE ships for every wallpaper).
  Map `KIND_SCENE` and set `original_type="scene"` so the card badges
  `SCENE · preview`. Assert all scene folders actually resolve a preview file.
- **web** → `QWebEngineView` (`project.json` + `index.html`/assets).
- **video** → libmpv, play `preview.mp4`/`video.mp4`; also accept `.gif`.
- **image** → `QLabel` + `QPixmap`.
- Lumen's own `lumen.json` (id, kind, title) is the alternate format for samples.

## Real `linux-wallpaperengine` binary (the WE Linux port)
Path (dev build): `/home/hunter/Dev/linux-wallpaperengine/build/output/linux-wallpaperengine`
CLI (confirmed via `--help`):
```
linux-wallpaperengine <wallpaper-folder> \
  --screen-root <monitor-name> \
  --bg <wallpaper-id> \
  --scaling <stretch|fill|fit|tile> \
  --assets-dir <dir>
```
- `--screen-root` throws a FULLSCREEN window that **buries desktop icons** — this
  is what "fucked LO's icons." If Lumen coexists, kill it first:
  `pkill -f linux-wallpaperengine` or scan `/proc/*/exe` (binary name >15 chars,
  so `pkill -x` by exact name FAILS).
- Use ONLY as an explicit, user-clicked "Render 3D via Wallpaper Engine" action
  for `scene` wallpapers — never auto-run, because it overlays icons and breaks
  LO's standing "icons must never vanish" rule.

## Icon-safety on XFCE + Nemo
- Desktop icons are owned by **`nemo-desktop`** (Nemo), NOT `xfdesktop`.
  Confirm: `xwininfo -root -children | grep -i nemo-desktop`.
- Setting `xfce4-desktop` backdrop transparent is harmless but ineffective.
  Instead: `gsettings set org.cinnamon.desktop.background picture-uri "file:///home/hunter/.local/share/lumen/transparent.png"`
  (1x1 RGBA PNG; make with PIL: `Image.new("RGBA",(1,1),(0,0,0,0)).save(p)`).
- Lumen's window is `_NET_WM_WINDOW_TYPE_DESKTOP` + `_NET_WM_STATE_BELOW` +
  `win.configure(stack_mode=X.Below)` (forced bottom of stack). With Nemo's
  backdrop transparent, the live wallpaper shows *behind* the icons.

## GUI placement verification (multi-monitor)
After `window.show()` call `_place_on_primary()`:
```python
g = QApplication.primaryScreen().geometry()   # LO: DisplayPort-0 @ +1920+0, 2560x1080
window.move(g.x() + (g.width()-window.width())//2,
            g.y() + (g.height()-window.height())//2)
window.raise_(); window.activateWindow()
```
Verify: `xwininfo -id <wid>` → absolute x must be inside primary range
(1920–4480 for DisplayPort-0). A GUI at `+2610+160` is correctly on primary.

## AppImage rebuild reminder
`pip install -e .` leaves an editable redirect — build from a throwaway clean
venv (`/tmp/buildvenv`, `pip install .` non-editable) so the package is copied
into `site-packages`. Then run `scripts/build_appimage.sh`. Recreated
`/tmp/buildvenv` each rebuild (it gets cleaned between turns).
