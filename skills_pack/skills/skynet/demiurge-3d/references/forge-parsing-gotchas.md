# Demiurge 3D — forge NL-parsing gotchas

## `forge.understand` submodule is shadowed
`forge/__init__.py` re-exports a function named `understand`, which **shadows** the
`forge.understand` submodule. `import forge.understand` resolves to the *function*, not the
module — so `forge.understand.from_text(...)` raises `AttributeError`. In tests/code that
needs the module, use:
```python
import importlib
understand = importlib.import_module("forge.understand")
understand.from_text(...)
```

## `_grid_size` drops `NxM` to 1×1
In `forge/understand.py`, `_grid_size` only matched `NxM` when followed by a grid-word
(`grid|bin|cell`). A request like `"gridfinity bin 2x3 60mm tall"` has no trailing
grid-word → falls back to `1x1` (wrong footprint). The fix also accepts `NxM` immediately
after `gridfinity`/`bin`. **When adding NL dimension patterns, ensure dims aren't silently
defaulted** — parse then assert the parsed value differs from the default.

## Forge real entry point
`python -m forge make "<request>" --out <dir>` (writes scad/stl/README/BOM/MANIFEST). NOT
`python -m forge.cli` and NOT `python -m pipeline.orchestrate` (no `__main__` → silent
no-op). Verify manifold STLs with the `stl_stats` volume check (see SKILL.md
"OpenSCAD manifold lesson").
