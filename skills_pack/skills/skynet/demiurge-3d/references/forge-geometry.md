# Demiurge Forge — geometry / mesh techniques

Reusable fixes from the forge build pipeline (OpenSCAD + trimesh).

## trimesh boolean ops: NEVER pass engine="manifold"

`trimesh.boolean.intersection/difference(...)` with `engine="manifold"` fails on
LO's box — `manifold3d` is NOT installed. The default engine (None → blender/
scipy fallback) and the explicit `"blender"` engine both work.

```python
# WRONG (raises "No module named 'manifold3d'"):
trimesh.boolean.intersection([a, b], engine="manifold")
# RIGHT:
trimesh.boolean.intersection([a, b])          # default engine
trimesh.boolean.difference([slab, hole])       # default engine
```

Verify available engines once:
```python
import trimesh
m = trimesh.creation.box(extents=[10,10,10])
b = trimesh.creation.box(extents=[10,20,20])
for e in ["manifold","blender",None]:
    try: r = trimesh.boolean.intersection([m,b], engine=e); print(e, len(r.vertices))
    except Exception as ex: print(e, "ERR", str(ex)[:60])
```

## Difference only if the mesh is still a watertight volume

After several chained boolean differences a mesh can become non-manifold and the
next `difference` raises "Not all meshes are volumes!". Guard every subtraction:

```python
if slab.is_volume:
    try: slab = trimesh.boolean.difference([slab, hole])
    except Exception: pass   # chunk still prints, just without that dowel
```

## Large-model splitter (native Luban "split big thing")

`forge/large_model_split.py` — given a mesh + ONE real-world dimension, upscale
to IRL size, segment along longest axis into bed-fit chunks (K2 bed = 350mm,
use `usable = bed[0] - 2*margin`), and bore alignment dowel holes on cut faces.

Key steps:
1. `mesh.apply_scale(reference_mm / current_axis_len)` — scale whole model so the
   chosen axis matches the real size LO gave.
2. Center, then rotate so the longest extent sits on X (`_orient_longest_axis`).
3. Slab = `trimesh.boolean.intersection([mesh, clip_box])` where clip_box is a
   box of X-width = chunk_len centered at the slab midpoint. Y/Z of clip_box =
   `mesh.extents*2 + 50` (oversize so it never clips the cross-section).
4. Dowels: `trimesh.creation.cylinder(radius, height, sections=20)` rotated
   `rotation_matrix(pi/2, [0,1,0])` to lie along X, translated to the cut face.
   Bore 4 per interior face (2x2 grid offset from centerline).
5. Export each slab as its own STL + a `manifest.json` + a separate `alignment_dowels.stl`.

Validated: 2250mm box -> 7 chunks @ 321mm + dowel strip (8 STL files).

## OpenSCAD custom shapes the forge pipeline understands

`forge/scad.py::_base_solid` renders these `Part.shape` values to OpenSCAD:
`box, cylinder, cone, tube, sphere, wedge, mask_shell, shell_hemi, box_hollow,
figurine_body, phone_case`. To add a swarm archetype shape, add a branch here
AND a `thickness`/`height` field on `forge/geometry.py::Part` (the swarm
`to_forge_spec()` translator maps swarm parts -> these shapes + `Feature`s).

`mask_shell` = hollow scaled sphere flattened at back (face shell); `shell_hemi`
= hollow hemisphere; `box_hollow` = box minus inner cavity; `figurine_body` =
tapered pillar on a round base.

## Swarm Design -> buildable STL

`forge/swarm_design.py::design_request(text)` decomposes a vague creative prompt
("Berserk rave mask") into a spec with `parts` (shape + dims + feature hint).
`to_forge_spec(spec)` translates that into forge-compatible `Part` dicts
(mapping `feature: "eye_slots"` -> two `slot` Features, `"hole_grid"` -> corner
holes, etc.). The Forge UI's "-> Send to Forge build" calls
`/api/forge/swarm-build` which runs `pipeline.build(to_forge_spec(spec))`.
Without this translation the swarm parts hit `pipeline.build` directly and fail
with "Could not turn that into a buildable part".
