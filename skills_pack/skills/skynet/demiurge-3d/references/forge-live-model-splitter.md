# Forge live model splitter - recursive bed-fit partitioning

## Trigger
LO asks for a model to be auto-chopped to fit a printer bed when it's "life
sized" or bigger than the build volume. Output must be WATER-TIGHT bed-fitting
CHUNKS with registration keyways - NOT a downscaled single STL.

## Where it lives (Demiurge3D backend)
- `forge/slicer.py` -> `plan_split()` (single-shot decision) + `auto_split()`
  (recursive multi-axis partition) + `_split_triangles()` (Sutherland-Hodgman
  clip per axis).
- `demiurge/webapp/forge_routes.py` -> `/api/forge/auto-split` + splitter
  auto-wired into `/build` and `/arees/full` (fires on `life_sized` /
  `force_split` OR when bbox overflows `printer_bed_mm`, default K2 Plus 350^3).
- Tests: `tests/test_forge_live_splitter.py`, `tests/test_forge_live_splitter_route.py`.

## THE KEY BUG (do not repeat)
A single-axis planar split of an over-size model leaves the OTHER two axes
still overflowing the bed. A 700^3 cube cut into 3 along Z yields 700x700x233
chunks - X and Y still fail. Fix = RECURSIVE partition: after slicing on the
worst-overflow axis, recompute each child's bounds from the SLAB it occupies
(child_mn[A]=lo, child_mx[A]=hi; other axes inherited - clipping can never move
a vertex outside the slab, so this is exact and can't go infinite), then recurse
on any child that still overflows. A hollow test-shell cube loses some corner
slabs to degeneracy -> skip writing EMPTY chunks (triangles==0), don't let empty
prune the recursion.

## Clip correctness note
`_split_triangles` must actually SLICE each triangle at the slab boundaries
(Sutherland-Hodgman on the 1-D axis), keeping the inside portion and building
the cap from clipped edges. Computing cap intersection points but then dropping
the crossing triangle (all-or-nothing keep) produces chunks whose bbox still
equals the full model -> infinite recursion. Cap quads are 4-vert lists ->
triangulate (a,b,c)+(a,c,d).

## Verify
`python3 -m pytest tests/test_forge_live_splitter.py tests/test_forge_live_splitter_route.py -q`
asserts: overflow detection, every non-empty chunk <= bed on ALL axes, force on
a fitting model still splits once, no-split-when-fits, and a real TestClient hit
on `/api/forge/auto-split` lands chunk files on disk. Use `python3` (3.14),
NOT `python` (binary missing on this box). Set `TMPDIR=/home/hunter/.cache/d3d_tmp`
(per-user /tmp quota -> EDQUOT).

## Open extension (not yet built)
Peg holes are emitted as COORDINATES, not boolean-subtracted into the mesh.
Drilling actual dowel holes needs a mesh-CSG step. No GUI chip button yet
(keyword/API driven). Offer these when LO asks for "keyed" or "printable-ready"
chunks.
