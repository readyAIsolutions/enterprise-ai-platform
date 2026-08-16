# Forge 3MF packager — validation technique (condensed)

Captured 2026-07-10 while validating `forge/threemf.py` (the "missing link"
STL→3MF path that `pipeline.build(do_3mf=True)` calls). The module shipped
with **zero tests** even though its own docstring pointed at
`backend/tests/test_threemf.py`. Heuristic: a module docstring referencing a
test file that does not exist == unvalidated module. Write it.

## 3MF essentials (for debugging the packager)
- A 3MF is a **ZIP** with a fixed relationship layout:
  - `[Content_Types].xml` (declares content types)
  - `_rels/.rels` (MUST point at `/3D/3dmodel.model`)
  - `3D/3dmodel.model` (the mesh data)
- `3dmodel.model` namespace: `http://schemas.microsoft.com/3dmanufacturing/core/2015/02`.
- Coordinates are `THREE_MF_FLOAT`: plain decimals, **NEVER scientific notation**.
  Format with `f"{v:.6f}".rstrip("0").rstrip(".")` and guard the
  `0.0 → "0"` / `"-0"` edge cases. A stray exponent makes the file
  unparseable by slicers.
- Triangle `v1/v2/v3` are **0-based** indices into the object's vertex list.
- Geometry must be EMBEDDED: real `<vertices>` + `<triangles>` inside
  `<mesh>`, not a raw STL dumped in the zip (which is what the legacy
  `demiurge/webapp/threemf.py` did). Slicers open the embedded mesh.

## Offline STL fixtures (no OpenSCAD needed for unit tests)
Hand-write a minimal valid STL so tests don't depend on a render:
- **Binary**: 80-byte header + `<I` triangle count + per triangle
  (3 floats normal + 3×3 floats vertices) + `<H` attrib (0).
- **ASCII**: `solid name` … `facet normal … outer loop vertex … endloop
  endfacet` … `endsolid name`.
- Cube fixture recipe (the template): 8 unique vertices, 12 triangles;
  the packager's `read_stl` deduplicates shared vertices onto a 1e-4 mm
  grid and DROPS degenerate (zero-area) triangles — assert
  `triangles_n` after dedup, and that a forced degenerate tri is removed.

## Validation gate
`validate_3mf(path)` returns `(ok, [errors])`. It checks: zip layout,
`_rels/.rels` → `/3D/3dmodel.model`, model namespace, ≥1 object with
vertices+triangles, build-item object ids resolve, and every triangle index
is in range. Round-trip via `read_3mf(path)` to assert vertex coords and
triangle counts survive into the `<mesh>`.

## Real-render e2e (OpenSCAD present on this host)
`/usr/bin/openscad` (2021.01) IS installed, so forge e2e tests can render
**real** STLs. Guard them so headless/CI boxes without OpenSCAD still pass:
```python
import shutil
@pytest.mark.skipif(not shutil.which("openscad"), reason="openscad not on PATH")
def test_e2e_render_then_3mf(tmp_path):
    import forge.parts_library as pl, forge.scad as scad, forge.threemf as tm
    part = pl.GENERATORS["mounting_plate"](length=40, width=30, thickness=4)["part"]
    meta = scad.render_part(part, tmp_path)
    assert meta["dimension_ok"] is True
    res = tm.package_project([meta], tmp_path / "p.3mf", project_name="Plate")
    ok, errs = tm.validate_3mf(tmp_path / "p.3mf")
    assert ok, errs
```
Also exercise the full chain `pipeline.build(spec, root=tmp_path, do_3mf=True)`
from an NL request and assert `summary["threemf_path"]` validates.

## Shippable samples generator
`backend/samples/make_samples.py` (reproducible) builds 5 real demo
projects through the pipeline and writes them under `backend/samples/projects/`:
mounting_plate, standoffs×4, gridfinity 2×3, drone_frame, phone_stand.
Each gets stl/ + scad/ + BOM.md + README.md + MANIFEST.json + a **validated**
`.3mf`. Regenerate with `python3 backend/samples/make_samples.py`. These
are the product's "samples" deliverable.
