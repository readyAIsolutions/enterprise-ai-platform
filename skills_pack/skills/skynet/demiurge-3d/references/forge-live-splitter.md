# Forge live model splitter — technique + pitfalls

(Added 2026-07-16 by ENI. Feature lives in `forge/slicer.py` + `demiurge/webapp/forge_routes.py`.)

## What it does
Auto-chop an STL into printer-bed-fitting chunks when LO says "life sized" or
when the model overflows the bed. Wired into `/build` and `/arees/full` so it
fires inside the normal Forge flow, plus a standalone `/api/forge/auto-split`.

## Key algorithm (recursive multi-axis split)
- `plan_split()` decides IF + along which axis (worst overflow ratio vs usable
  bed = bed - 2*margin). `force_split` (the "life sized" path) overrides fit.
- `auto_split()` recurses: pick worst-overflow axis, slice into
  `ceil(size/usable)` slabs, recurse on each child until ALL axes fit.
- **Why recursive, not single-axis:** a single axis-aligned cut leaves the
  OTHER two axes still overflowing (e.g. a 700 cube cut on Z is still 700x700).
  Recursive split yields chunks <= bed on every axis. This was a real bug caught
  by the test (chunks came back 233x700x700).

## Triangle clipping (Sutherland-Hodgman, 1-D per axis)
- `_split_triangles(tris, A, lo, hi)`: for each triangle, clip its polygon to
  the slab on axis A. Vertices outside are cut at the boundary; the inside
  polygon is re-triangulated (tri -> tri, or tri -> quad -> 2 tris).
- Boundary-crossing edges become the CAP cross-section (returned as quads) so
  each chunk is a closed watertight manifold and printable.
- **Pitfall - child bounds:** do NOT recompute child bounds from the clipped
  vertex set. Thin hollow shells (test cube is a 12-tri shell) can clip to a
  degenerate empty piece, and reading bounds off `inside` verts can leave the
  full 700 size -> infinite recursion. Instead set child bounds DIRECTLY from
  the slab: `child_mn[A]=lo; child_mx[A]=hi; other axes inherited`. A clip
  never moves off-axis verts, so this is exact.

## 'life sized' / force semantics
- `force_split=True` must propagate into the recursion: a forced small model
  splits ONCE, then `child_force = force and any(child still overflows)` so it
  stops recursing forever. Without this the 100mm-cube force test returned 1
  chunk (recurse wrote it out before honoring force).

## ENI safe-edit workflow for this repo (from AGENTS.md)
1. `git add -A && git commit -m "checkpoint"` BEFORE edits (revertible).
2. After edits: `python3 -c "import ast,glob;[ast.parse(open(f,encoding='utf-8').read()) for f in glob.glob('**/*.py',recursive=True) if '__pycache__' not in f]"` - zero syntax errors.
3. `python3` is NOT on PATH here; use `python3` (3.14). pytest needs
   `TMPDIR=/home/hunter/.cache/d3d_tmp` (per-user /tmp quota EDQUOT).
4. Never write prose/markdown into a `.py`. Code only.

## Peg registration (current limitation)
Peg-hole CENTERS are emitted as coordinates in `plan["peg_centers_mm"]`, NOT
boolean-subtracted into the mesh. LO drills/aligns manually. Upgrading to real
subtracted dowel holes needs a mesh-CSG step (future work).

## Test recipe (reuse)
`tests/test_forge_live_splitter.py` (unit: plan/auto/force/no-split) +
`tests/test_forge_live_splitter_route.py` (FastAPI TestClient e2e on
`/api/forge/auto-split`). Run:
`TMPDIR=/home/hunter/.cache/d3d_tmp python3 -m pytest tests/test_forge_live_splitter*.py -q`
