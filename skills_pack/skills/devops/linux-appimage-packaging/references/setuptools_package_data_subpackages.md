# setuptools package-data: subpackage data files + the TOML collision trap

When a Python app has a *subpackage* that ships non-Python data (qss/style
sheets, png icons, sample bundles, web templates), the **parent** package's
`[tool.setuptools.package-data]` globs do NOT capture files inside the
subpackage directory. The wheel builds, the AppImage's `--version`/import smoke
passes, but the data is silently absent from the squashfs — the classic
"assets drop from squashfs" failure. The build's own `assert_asset` deploy-gate
usually catches it: `assert_asset('ui/styles.qss')` fails before the image ships.

## Symptom (real — Lumen AppImage, 2026-07-12)
```
!! packaging-data regression: 'ui/styles.qss' missing from bundled lumen
!! add a glob in [tool.setuptools.package-data] covering it
```
`pyproject.toml` had:
```toml
[tool.setuptools.package-data]
lumen = [ "ui/*.qss", "ui/assets/*", "samples/*/*", "samples/*/*/*" ]
```
But `lumen/ui` is a **declared subpackage** (`lumen.ui` in `packages = [...]`),
so setuptools treats `ui/` as the subpackage boundary and the parent `lumen`
glob `ui/*.qss` never matches `lumen/ui/styles.qss`. The file is dropped.

## FIX 1 — add a per-subpackage key (REQUIRED)
```toml
[tool.setuptools.package-data]
lumen = [ "samples/*/*", "samples/*/*/*", "**/*.qss", "**/*.png", "**/*.json" ]
"lumen.ui" = [ "*.qss", "assets/*" ]
```
`"lumen.ui"` keyed by the dotted subpackage name: `*.qss` matches
`lumen/ui/styles.qss`; `assets/*` matches `lumen/ui/assets/logo.png`. This is
the robust fix — recursive `**/*.qss` globs under the *parent* key are NOT
reliably honored by setuptools package_data, so the explicit subpackage key is
what actually bundles the files.

## FIX 2 — the TOML collision that always follows
You CANNOT write both of these:
```toml
lumen    = [ ... ]     # makes `lumen` a LIST
lumen.ui = [ ... ]     # ERROR: can't put a sub-key under a list
```
setuptools/tomllib raises:
```
TOMLDecodeError: Cannot mutate immutable namespace
('tool', 'setuptools', 'package-data', 'lumen')
```
because `lumen` is already a list, so `lumen.ui` would be a sub-key of it.
**Use a QUOTED key** so it is a distinct string key that setuptools still maps
to the `lumen.ui` package:
```toml
"lumen.ui" = [ "*.qss", "assets/*" ]   # correct
```

## Verify before rebuilding
```bash
python3 -c "import tomllib; d=tomllib.load(open('pyproject.toml','rb')); \
print(d['tool']['setuptools']['package-data'])"
```
Must show BOTH `lumen` (list) and `lumen.ui` (list) as separate keys.

## Bonus — bundle everything (optional, harmless)
Add recursive globs under the parent key so any runtime-asset dir you forgot
also ships: `"**/*.qss","**/*.png","**/*.jpg","**/*.json","**/*.html",
"**/*.css","**/*.js","**/*.mp4","**/*.webm","**/*.svg","**/*.glsl"`. Even if
`**` is ignored by an older setuptools, the explicit subpackage key + the
explicit sample globs already cover the deploy-gate asserts.

## Reuse
Generic Python-packaging form — applies to ANY AppImage (or wheel) whose
package tree has subpackages carrying non-Python data. Pairs with the
`assert_asset` deploy-gate pattern in `references/appimage_deploy_gate.md`.
