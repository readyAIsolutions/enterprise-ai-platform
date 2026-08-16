# D3D asset_pipeline.py — known test failures (diagnosed 2026-07-12)

Module: `backend/demiurge/models/asset_pipeline.py`
Tests:  `backend/tests/test_asset_pipeline.py` (5 failing; 78 passing before the fix)
Status:   ROOT CAUSES SUSPECTED but NOT yet confirmed — the in-repo diagnostic run that
          would have pinned them was consent-BLOCKED (see `demiurge-3d` SKILL.md
          "Command-denial guardrail" (c)). Empirical confirmation pending LO approval
          of an in-repo/pytest run. Fix under `backend/AGENTS.md` rules:
          `git add -A && git commit -m "checkpoint"` (or file-copy backup) BEFORE editing,
          `ast.parse` sweep after, code-only in the `.py`.

## Bug 1 — `mesh_metrics` surface area wrong for an oriented unit cube
- Symptom (test `test_mesh_metrics_oriented_cube`): oriented unit cube →
  `surface_area_mm2` = **6.414214** (expected **6.0**). Off by exactly √2−1 ≈ 0.414214.
- Suspect: a winding/vertex bug in the per-triangle area loop (`mesh_metrics`, ~line 561-573)
  OR the `_orient_outward` helper producing a degenerate/duplicated triangle whose area is
  √2−1 larger than the 0.5 it should be. Area = 0.5 * |cross(u,v)|; flipping winding does
  NOT change area, so the culprit is an actual wrong vertex index or a duplicate tri, not the
  orientation flip itself.
- Confirm by printing per-triangle area for the 12 cube tris and finding the one that reads
  ~0.914214 instead of 0.5.

## Bug 2 — `mesh_metrics` degenerate count returns 1/3, not 1
- Symptom (test `test_mesh_metrics_counts_degenerate`): cube + one collapsed triangle `(0,0,0)`
  → `degenerate_triangles` = **0.333333** (expected **1.0**).
- Suspect: the degenerate integer is being divided (likely `/ n_tris` somewhere, or a
  ratio is returned instead of the raw count). Or the collapsed tri is double-counted/
  skipped. The return value is the integer `degenerate` per the source — so something
  divides it before return. Grep for `degenerate` usages and any `/` involving it.

## Bug 3 — `_sniff_format` misidentifies a real 3mf (zip) as STL → cascades
- Symptom (3 tests):
  - `test_diagnose_asset_misnamed_3mf` → raises `ThreemfError: binary STL truncated at triangle 21`
  - `test_ingest_misnamed_3mf` → returns `['unsupported format: misnamed.bin']`
  - `test_ingest_unknown_format_raises` → DID NOT RAISE `AssetPipelineError` (should have)
- Root cause: `_sniff_format` detects the zip/"PK\x03\x04" magic of a real 3mf too late (or
  not at all) and falls through to the STL detector, which then tries to parse the zip bytes
  as a binary STL and chokes at facet 21. A `misnamed.bin` (actually a 3mf) is also sniffed
  wrong → "unsupported format". Because the format is mis-sniffed, the unknown-format test
  never reaches the `raise AssetPipelineError` branch.
- Fix direction: in `_sniff_format`, check the zip magic (`b'PK\x03\x04'`) BEFORE the STL
  binary/text detectors and return `".3mf"`; ensure a truly-unknown input still raises
  `AssetPipelineError` in `ingest_asset`/`diagnose_asset`.

## Quick re-verify after fix
From `backend/`: `python3 -m pytest tests/test_asset_pipeline.py -q` → target 83/83 pass.
Run the full suite too (`python3 -m pytest tests/ -q`) to confirm no sibling regression.
