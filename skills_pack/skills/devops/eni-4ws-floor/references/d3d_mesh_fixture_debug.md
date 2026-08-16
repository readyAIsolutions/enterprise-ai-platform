# D3D mesh/volume test failure → isolate the FIXTURE, not the function

Reusable debugging recipe from the 2026-07-12 `asset_pipeline.py` failure
(`test_asset_pipeline.py` area/volume asserts failing on a cube). The wrong
instinct is to assume the production area/volume math is wrong. It almost never
is. The fixture geometry is the usual culprit.

## Symptom
`mesh_metrics` / `volume` / `surface_area` tests fail on a hand-built cube
fixture, e.g.:
- total surface area reads `6.414214` (expected `6.0`)
- volume reads `0.333333` (expected `1.0`)

## Wrong instinct
Patch `mesh_metrics` (area/volume formula). Do NOT — the formula is
orientation-independent: `area = 0.5 * |cross(B-A, C-A)|` does not depend on
winding order, so a wrong-face or flipped-normal fixture cannot make the function
return a bad number for a *correct* triangle. If the per-triangle math is sound,
the function is sound.

## Correct method — prove the fixture geometry
Compute the area of EACH triangle in the fixture explicitly and compare to the
expected face area. For a unit cube the 12 triangles are the 2 halves of each of
the 6 unit faces → every triangle area must be exactly `0.5`.

Minimal probe (run against the fixture's vertex + index arrays):
```python
import numpy as np
V = np.array(_CUBE_VERTS, float)          # (8,3) for a unit cube
T = np.array(_CUBE_TRIS_RAW, int)         # (12,3) triangle indices
for (a, b, c) in T:
    ab, ac = V[b]-V[a], V[c]-V[a]
    area = 0.5 * np.linalg.norm(np.cross(ab, ac))
    print(a, b, c, round(area, 6))
```
Expected: all 12 print `0.5`. The 2026-07-12 bad fixture printed `0.707107`
for triangles `(1,5,7)` and `(1,7,2)` — those two indices referenced vertices
that are NOT on one cube face (they span a non-coplanar diagonal), so the
triangles are bigger than any real face. Any area `!= 0.5` proves the fixture is
malformed, not the function.

## Fix
Replace the malformed index list with 12 triangles that are the 2 coplanar-face
halves of the 6 faces (each face split by its diagonal). Re-run the test; area
and volume then read `6.0` / `1.0`.

## Coupled lesson — git-corruption fallback (D3D backend)
`/home/hunter/Desktop/demiurge-3d/backend` may have a CORRUPT git:
- `git add -A` / `git commit` → `fatal: bad object HEAD`
- `ls .git/objects` is empty
The working tree is intact; only the object DB is broken, so the repo's own
`git checkpoint` safety policy is impossible. Fallback: `cp <file> <file>.bak.eni`
BEFORE editing (file-level revert). After editing, PROVE isolation: grep the
failing test files for every symbol you touched (`asset_pipeline`,
`_sniff_format`, `_mesh_from_asset`, `ingest_asset`, `_CUBE_TRIS_RAW`,
`mesh_metrics`). If none of those files reference your edited symbols, any OTHER
suite failures are pre-existing/independent — do NOT claim them as yours or fake
them green.

## Kill-switch for "is it my edit or not"
```bash
# for each failing test FILE, does it mention anything I changed?
grep -lE 'asset_pipeline|_sniff_format|_mesh_from_asset|ingest_asset|_CUBE_TRIS_RAW|mesh_metrics' <failing_test_file>
# no match => independent of my edits
```
