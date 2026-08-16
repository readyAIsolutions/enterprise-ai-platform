# Demiurge 3D Forge — debugging & verification notes

Companion to the Demiurge 3D rebuild work (gated by `resume-codebase-rebuild`;
the `doom-builder` skill is the intended class but currently unresolvable by the
skill tools, so this lives here). Durable techniques discovered while rebuilding
the NL→OpenSCAD→STL→3MF→G-code forge.

## OpenSCAD solids: prefer `linear_extrude` of a 2D polygon over a hand-wound `polyhedron`
A `polyhedron(points=..., faces=...)` with any inverted face winding renders a
broken/degenerate mesh — often *still "succeeds"* (non-zero STL) but with flipped
normals, which slices badly or fails print validation. Build prisms from a 2D
cross-section instead:

    # right-triangular wedge: full height at x=0 → 0 at x=length, extruded across width Y
    f"translate([0,{y},0]) rotate([90,0,0]) linear_extrude(height={y}) polygon(points=[[0,0],[{x},0],[0,{z}]]);"

`linear_extrude` + `polygon` cannot have winding bugs. Use it for wedges,
chamfers-as-wedges, etc. The `wedge` shape in `forge/scad.py` was originally a
hand-wound `polyhedron` and produced an inverted/degenerate solid until switched
to this form.

## Verify a solid is actually manifold (binary STL)
Binary STL = 80-byte header + uint32 facet count + 50 bytes/facet, so
`filesize == 84 + 50 * n_facets`. A "too small" STL (e.g. 484 B) can STILL BE
VALID if the facet count is genuinely low — do not assume small == broken. To
truly judge health:
- parse each facet, compute **signed volume** = Σ tetra volumes (1/6 · det).
  Positive sign ⇒ outward normals (manifold, correct); negative ⇒ inverted normals.
- sanity anchor: `wedge(80, 20, 48)` must be exactly `0.5 * 80 * 48 * 20 = 38400 mm³`
  with a positive sign. This caught a wedge that looked fine by facet count but
  would have printed inverted.

## Python import gotcha: submodule shadowed by a re-exported function in `__init__.py`
`forge/__init__.py` defines `def understand(...)` AND `from . import understand as _understand`.
So `from forge import understand` (and `import forge.understand as understand`) resolves to
the *function*, not the module — `understand.from_text` then raises
`AttributeError: 'function' object has no attribute 'from_text'`. In tests, pull the real
module from `sys.modules`:

    import importlib
    understand = importlib.import_module("forge.understand")

## Forge CLI entry point (don't use the wrong module)
`cd backend && .venv/bin/python -m forge make "<request>" --out <dir>` writes
`scad/`, `stl/`, `README.md`, `BOM.md`, `MANIFEST.json` into the out dir. Default
project root is `~/Desktop/Demiurge 3D_Projects`.
`pipeline.orchestrate` has **no `__main__` guard** — `python -m pipeline.orchestrate`
just imports and exits 0 (silent no-op). Drive `forge make`, never `pipeline.orchestrate`.

## Frontend/backend contract drift
Frontend v2 (`Forge3D.tsx`) POSTs `{request: "..."}` to `/api/forge/understand`;
the backend Pydantic model expects `text`. Alias in the model
(`Field(alias="request")` + `model_config = {"populate_by_name": True}`) so both
keys work without touching the already-built UI. The backend is the contract source.
