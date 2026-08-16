# Debian .deb packaging — condensed knowledge bank

Companion to the `linux-appimage-packaging` skill. Build a single-file `.deb`
for a Python (PyQt6/PySide) desktop app when `flatpak-builder` is unavailable
(no root / no Flathub remotes in the sandbox) but `dpkg-deb` + `fakeroot` +
network pip ARE present. `dpkg-deb` and `fakeroot` ship on Debian/Ubuntu and
run fine as a non-root user.

## Minimal build recipe
```bash
SRC=/path/to/app
STAGE=/tmp/app-deb
APP=$STAGE/opt/lumen            # vendored install prefix
VER=$(grep '^__version__' "$SRC/lumen/__init__.py" | head -1 | sed -E 's/.*"(.*)".*/\1/')
OUT=/path/to/app.deb
rm -rf "$STAGE"
mkdir -p "$APP" "$STAGE/DEBIAN" "$STAGE/usr/bin" "$STAGE/usr/share/applications"
pip install --target="$APP" "$SRC" PyQt6 PyQt6-WebEngine python-xlib python-mpv Pillow requests
# (see Pitfall 2) copy entry point to staging root
cp "$APP/lumen/__main__.py" "$APP/__main__.py"
# launcher + .desktop + DEBIAN/control (see Pitfall 1)
dpkg-deb --build "$STAGE" "$OUT"
```

## Verification (headless proof the artifact LAUNCHES)
```bash
dpkg-deb -I app.deb          # control: Package/Version/Depends must be sane
dpkg-deb -c app.deb          # contents: /opt/lumen/__main__.py, /usr/bin/<app>, .desktop
rm -rf /tmp/x && dpkg-deb -x app.deb /tmp/x
python3 /tmp/x/opt/lumen/__main__.py --version   # MUST print "App X.Y.Z" + exit 0
```
This mirrors the AppImage `--version` check: it proves the entry point + the
vendored deps resolve. The real GUI launch still needs the system Qt6 libs + X
(see Pitfall 3) and must be confirmed on the user's desktop.

## Pitfalls (learned the hard way)

### Pitfall 1 — Debian control files do NOT allow `#` comments
Symptom:
```
dpkg-deb: error: parsing file '.../DEBIAN/control' near line 5 package 'app':
 field name '#' must be followed by colon
```
A line starting with `#` is parsed as a *field name*, not a comment. **Never
put `#` comments inside the `DEBIAN/control` heredoc.** Put explanatory notes
as shell comments in the `build.sh` instead. The control body must be
`Field: value` lines only.

### Pitfall 2 — `pip install --target` entry point is one dir too deep
`pip install --target=/opt/lumen "$SRC"` installs the package entry at
`/opt/lumen/lumen/__main__.py`, NOT `/opt/lumen/__main__.py`. A naive launcher
`python3 /opt/lumen/__main__.py` then dies with `ModuleNotFoundError: No module
named 'lumen'` (the vendored deps are also NOT on the path). **Fix (cleanest):**
copy the entry to the staging ROOT so a directly-run script gets its own
directory on `sys.path[0]`:
```bash
cp "$APP/lumen/__main__.py" "$APP/__main__.py"   # sys.path[0] = /opt/lumen
# launcher:  exec python3 /opt/lumen/__main__.py "$@"
```
`sys.path[0]` of a directly-invoked script is the script's own directory, so
both `import lumen` and the vendored `PyQt6/` wheels resolve with no
`PYTHONPATH` hack. (Alternative: `export PYTHONPATH=/opt/lumen` and run
`python3 /opt/lumen/lumen/__main__.py`, but then sys.path[0] is the inner dir
and deps won't resolve — prefer the copy trick.)

### Pitfall 3 — PyQt6 wheels need SYSTEM Qt6 at runtime
PyQt6 / PyQt6-WebEngine wheels are vendored into `/opt/lumen` but they
`dlopen` the system Qt6 shared libraries. So `Depends` must list the **Qt6
runtime libs**, not the Python package:
```
Depends: python3 (>=3.8), libqt6core6, libqt6gui6, libqt6widgets6, \
         libqt6webenginecore6, libqt6webenginewidgets6, libgl1, \
         libxkbcommon0, libdbus-1-3
```
(Adjust lib names to the target distro.) Do NOT write `Depends: python3-pyqt6`
— that's the wrong dependency and would make the package uninstallable/unrunnable.
Note: a `--version` launch does NOT import PyQt6, so the headless verify in
the Verification section works even when Qt6 libs are absent.

### Pitfall 4 — non-root build warning (harmless)
```
dpkg-deb: warning: root directory ... has unusual owner or group 1000:1000
```
Building as a normal user triggers this; the package is still valid. For clean
`root:root` ownership on a real build host use `dpkg-deb --root-owner-group`
(requires root) or `fakeroot`. Ignore in the sandbox.

### Pip `--target` dependency-conflict warnings
`pip install --target=...` may print e.g.
`hermes-agent 0.15.2 requires requests==2.33.0, but you have requests 2.34.2`.
These are informational (the resolver checks the host's site-packages) and do
NOT fail the build or touch the system — the staging prefix is isolated. Ignore.

## When .deb beats Flatpak here
In this sandbox `flatpak-builder` is absent and there is no root / no Flathub
remote, so the Flatpak manifest can be authored + YAML-validated but NOT built.
`dpkg-deb` + `fakeroot` + network pip ARE available, so `.deb` is the feasible
3rd shippable target. Author the Flatpak manifest anyway (it's cheap and
validates) and build it on a Flathub-remote host later.
