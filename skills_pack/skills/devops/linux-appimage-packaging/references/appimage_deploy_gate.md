# AppImage deploy gate — verify the artifact ships your DATA

The single most common AppImage failure is SILENT: the build succeeds, the app
boots, but a non-Python asset (QSS theme, sample, icon, config, web template,
translation `.qm`) is MISSING from the squashfs because nothing declared it as
package data. The app then falls back to a blank theme / empty gallery / default
icon on a clean box — and you only discover it after shipping, because a
`--selftest` boot passes (the fallback is graceful).

## Recipe 1: test-lock your package-data globs (source of truth, no build needed)
Do NOT prove your data ships by running `pip wheel` and inspecting it. A dev venv
may lack the setuptools build backend (`BackendUnavailable: Cannot import
'setuptools.build_meta'`), and the wheel is a heavy, slow, network-dependent
artifact. Instead assert the contract at source-of-truth level:

1. Parse `pyproject.toml` `[tool.setuptools.package-data]` globs directly
   (`tomllib.load(open("pyproject.toml","rb"))` -> `tool.setuptools.package-data`).
2. For each package, expand its globs (`ui/*.qss`, `samples/*/*`, `samples/*/*/*`,
   etc.) with `glob.glob(..., recursive=True)` against the on-disk tree.
3. Walk the package dir for every non-`.py` shippable asset and assert it is
   matched by at least one declared glob. This catches a newly added
   `ui/styles.qss` or `samples/shader_x/preview.png` that the globs forgot.
4. (Optional) an actual `pip wheel --no-build-isolation --no-deps .` test, gated
   to SKIP when the build backend isn't importable — it runs on the real build
   host, not the dev venv.

Reusable pytest module: `templates/test_packaging_data.py` (adjust `PKG_NAME`).

## Caveat: do NOT trust `egg-info/SOURCES.txt`
`*.egg-info/SOURCES.txt` is REGENERATED from the LAST build. It will NOT reflect a
sample/theme you added since the previous build, so it lies about current
shippability. Source of truth = `pyproject.toml` globs + on-disk reality.

## Recipe 2: verify the built artifact headlessly (the real deploy gate)
After `appimagetool` exits 0:
1. `./<app>.AppImage --appimage-extract` into a temp dir (or `unsquashfs` if
   `squashfs-tools` is present).
2. Run the squashed copy's entry: `cd squashfs-root && python -m <pkg> --version`
   (or `./AppRun --version`) — must print the version, proving the interpreter +
   stdlib + entry module are intact in the bundle.
3. Import the key modules from the extracted tree to catch missing deps:
   `python -c "import <pkg>, <pkg>.app, <pkg>.ui.main_window, ..."` -> `IMPORTS OK`.
4. `find squashfs-root -name 'styles.qss' -o -name 'preview.png' ...` — assert the
   specific non-Python assets you care about are ACTUALLY PRESENT in the squashfs.
   This is the proof the data-glob lock above was correct.
5. (If the app supports it) launch headless with `--minimized` / `--offscreen` on a
   real desktop and watch the log for the expected "applied" line.

This whole check is fast, offline, and catches the drop-list failure a green
`--selftest` boot alone will miss.
