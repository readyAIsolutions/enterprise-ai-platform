# Pipeline orchestration + 3MF packager — gotchas & API shapes

Captured 2026-07-10 when repairing `pipeline.orchestrate.run_pipeline`
(the README's headline NL→3D command, which raised `ModuleNotFoundError`).

## The broken import: `setup.Pipeline` never existed
- `backend/pipeline/orchestrate.py` does `from setup import Pipeline` (and
  `PipelineOrchestrator` depends on it). That class was **never written** →
  `ModuleNotFoundError: No module named 'setup'` (or `ImportError: cannot import
  name 'Pipeline'`).
- FIX (additive, verified working): `backend/setup.py` now defines
  `class Pipeline`, wrapping the already-tested Forge functions
  (`forge.understand` → `forge.scad.render_part` → `forge.slicer.estimate` →
  `forge.project.write_project` → `forge.threemf.package_project`).
- WHY `backend/setup.py` resolves as `setup`: when you run from the
  `backend/` cwd, sys.path includes cwd AND orchestrate inserts the repo-root.
  The legacy `setup/` dir at repo-root has **no `__init__.py`** (it's a stray
  namespace dir), so `import setup` binds to the regular module
  `backend/setup.py` (a real module beats a namespace dir). Do NOT delete
  `backend/setup.py` as "stray" — it IS the missing piece.

## How to drive it
- Programmatically (the only way that actually runs):
  ```python
  from pipeline.orchestrate import run_pipeline
  res = run_pipeline("phone stand 80mm wide with cable slot",
                     projects_root="/tmp/x", material="PLA", infill=0.20)
  # res: {ok, name, project_dir, parts, filament_mass_g,
  #       est_print_time_min, threemf_path, files:[...], errors:[...]}
  ```
- `python -m pipeline.orchestrate "..."` is STILL a silent no-op (no
  `__main__` guard) — only `forge make` and the programmatic `run_pipeline`
  actually execute.
- Offline-safe: no LLM, no printer, no slicer required. Slicing/G-code only
  happens if OrcaSlicer is installed AND `do_slice=True` (else `slice()`
  returns `[]` — correct, safe). `publish=True` is a deterministic stub.

## Tests added 2026-07-10
- `backend/tests/test_pipeline.py` (4) — drives `run_pipeline` on parseable
  requests + an unknown request (must return a clean `ok=False`, not crash).
- `backend/tests/test_threemf.py` (6) — validates `forge/threemf.py`, which
  was **implemented but had NO test file** (its own docstring pointed at a
  `tests/test_threemf.py` that didn't exist). Full suite = 97 passed.

## 3MF packager API shapes (`forge/threemf.py`)
Write tests against THESE exact keys — guessing them wastes a cycle.

- `read_stl(stl_path) -> dict`
  `{"vertices": [(x,y,z), ...],          # de-duplicated shared verts
    "triangles": [(i,j,k), ...],         # LIST of index tuples
    "size_mm": (x,y,z), "min": (x,y,z), "max": (x,y,z),
    "triangles_n": int}`                  # <-- the COUNT is triangles_n
  ⚠ `triangles` is a **list**; the count is `triangles_n`.

- `build_3mf(parts, out_path, *, metadata: dict = None, layout: str = "row") -> dict`
  `parts = [{"stl_path": str, "name": str}, ...]`
  returns `{"path": str, "objects": int, "triangles": int}`.

- `validate_3mf(path) -> (bool, [error_str, ...])`.

- `read_3mf(path) -> dict`
  `{"unit": "millimeter",
    "metadata": {name: value},
    "objects": [{"id": int, "name": str,
                 "n_vertices": int,              # <-- COUNT
                 "n_triangles": int,            # <-- COUNT
                 "vertices": [...], "triangles": [...]}],
    "build": [{"objectid": int, "transform": str|None}]}`
  ⚠ per-object counts are `n_vertices` / `n_triangles` (NOT `vertices`/
  `triangles`, which are the lists).

- `package_project(renders, out_path, *, project_name=None, layout="row") -> dict`
  `renders = [{"stl_path": str, "part": str, "count": int}, ...]`
  returns `{"path": str, "objects": int, "triangles": int}`.

- Float formatting: coordinates are emitted with `%.6f` (NO scientific
  notation) because slicers reject `1e+01`. Assert `"e+"`/`"e-"` absent in
  the `3D/3dmodel.model` payload when testing.
- Valid 3MF = ZIP with fixed layout: `[Content_Types].xml`, `_rels/.rels`,
  `3D/3dmodel.model` (namespace
  `http://schemas.microsoft.com/3dmanufacturing/core/2015/02`).
