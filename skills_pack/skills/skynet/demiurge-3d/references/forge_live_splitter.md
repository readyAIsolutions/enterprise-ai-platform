# Forge Live Model Splitter (Demiurge3D)

Built 2026-07-16 by ENI. Auto-chops an oversize STL to fit the printer bed, triggered by the
"life sized" keyword OR auto-detected overflow on any axis.

## Where it lives
- `forge/slicer.py`: `plan_split()` (single-shot decision) + `auto_split()` (recursive cut) +
  `_split_triangles()` (1-D Sutherland-Hodgman per-axis clip) + `_write_binary_stl()`.
- `demiurge/webapp/forge_routes.py`: `/api/forge/auto-split` endpoint; wired into `/build` and
  `/arees/full` via `life_sized` / `printer_bed_mm` params (default bed K2 Plus 350,
  `_DEFAULT_BED_MM` in slicer.py).
- Tests: `tests/test_forge_live_splitter.py` (unit + FastAPI TestClient) and
  `tests/test_forge_live_splitter_route.py`.
- Proven by STATUS_DEMIURGE_FORGE_LIVE_SPLITTER.md (committed in-repo).

## What it does
- Real SPLITTER, not a downscaler: planar axis-aligned cuts + capped open faces + emitted peg-hole
  centers (dowel registration). Watertight per-chunk closed manifold.
- Recursive across all 3 axes: cut worst-overflow axis, then re-cut any child that still overflows
  on another axis until EVERY final chunk fits on ALL axes.
- Honor the slicer DRY-RUN contract — no printer contact.

## Pitfalls (hit + fixed this session)
1. SINGLE-AXIS split is wrong for a cube: 700 cut into 3 along Z -> 700x700x233 (X,Y still overflow).
   Must recurse until ALL axes fit. Test must assert all 3 axes <= bed, not just `max(size)`.
2. HOLLOW-SHELL corner slabs -> empty chunks: after 3-axis clip a cube's corner slab may have no
   surviving tris -> empty STL. Skip empty chunks; assert "non-empty chunks fit", not "==27 exact".
   Solid models won't hit this; the hollow test proxy does.
3. Recompute child bounds from the SLAB, not clipped verts: deriving child bbox from `inside`-verts
   of a thin shell is fragile (can fall back to full size -> infinite recursion). Child bounds = parent
   bounds with cut axis set to `[lo, hi]` -- exact, guaranteed to shrink.
4. `struct` import: slicer.py only imported `struct` locally inside `_stl_geometry`; new
   `auto_split`/`_write_binary_stl` call it at function scope -> NameError. Fix: `import struct` at top.

## Run / verify
- AST gate: `python3 -c "import ast,glob;[ast.parse(open(f,encoding='utf-8').read()) for f in glob.glob('**/*.py',recursive=True) if '__pycache__' not in f]"`
- Tests: `TMPDIR=/home/hunter/.cache/d3d_tmp python3 -m pytest tests/test_forge_live_splitter.py tests/test_forge_live_splitter_route.py -q`
- NOTE: use `python3` (binary `python` is absent on this box); route `TMPDIR` to a user dir to dodge
  the per-user `/tmp` QUOTA (EDQUOT).
