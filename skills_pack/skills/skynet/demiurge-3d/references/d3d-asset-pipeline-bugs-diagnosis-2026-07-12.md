# D3D asset_pipeline test failures — concrete root-cause (2026-07-12)

Module: `backend/demiurge/models/asset_pipeline.py` (mirrored at
`packaging/AppImage/AppDir/opt/demiurge/demiurge/models/asset_pipeline.py`).
Tests: `backend/tests/test_asset_pipeline.py` → **78 passed / 5 failed**.

These 5 failures block D3D's pytest from going fully green. Root causes were
diagnosed 2026-07-12 but the FIX is **consent-gated** (the harness blocks any
edit OR even `pytest`/import inside `~/Desktop/demiurge-3d/backend` — see the
(c) consent-gate section in SKILL.md). Apply the fix only after LO approves the
repo edit; a standalone `/tmp` probe that re-implements the pure function is the
safe pre-edit workaround.

## The 5 failures + exact root cause
1. **test_mesh_metrics_oriented_cube**
   - `assert abs(surface_area - 6.0) < 1e-4` → got **6.414214** (off by √2−1 ≈ 0.4142).
   - Root: `mesh_metrics` area loop for the oriented unit cube overcounts one
     face. The orientation helper reorders triangle indices, but area must be
     `0.5 * |cross|` per triangle — so the bug is almost certainly a
     duplicated/overlapped face or a wrong vertex pulled in after
     `_orient_outward`. VERIFY per-triangle in a standalone `/tmp` probe
     (in-repo import is blocked).
2. **test_mesh_metrics_counts_degenerate**
   - `assert degenerate == 1` → got **0.333333** (1/3).
   - Root: the degenerate counter returns a *fraction*. Somewhere the count is
     divided by `n_tris`, or an off-by-scope makes it a ratio. The return
     `"degenerate_triangles": degenerate` must yield the **integer** count of
     triangles with `cross2 < 1e-12`.
3. **test_diagnose_asset_misnamed_3mf**
   - `ThreemfError: binary STL truncated at triangle 21`.
   - Root: `_sniff_format` misidentifies a real 3mf (a **zip**, `"PK\x03\x04"`
     magic) as STL, so `diagnose_asset` tries to parse it as binary STL and
     chokes.
4. **test_ingest_misnamed_3mf**
   - `AssertionError: ['unsupported format: misnamed.bin']`.
   - Root: same `_sniff_format` bug — the `.3mf` (zip) is sniffed as STL/binary,
     then an extension fallback guesses `.bin` and `ingest_asset` rejects it.
5. **test_ingest_unknown_format_raises**
   - did NOT raise `AssetPipelineError`.
   - Root: `_sniff_format` returns `None`/falls through for an unknown magic, so
     `ingest_asset` doesn't raise as the test expects.

## Staged fix (ready — hold for LO approval)
1. **Checkpoint** — `git add -A && git commit -m "checkpoint"` (or `cp` backup;
   repo HEAD may be corrupted per the GIT-IS-CORRUPTED pitfall — use
   `cp` to `/tmp` or `Commander/eni_swarm/backups_*.bak` if `git commit` aborts).
2. **`_sniff_format`**: detect the zip / `"PK\x03\x04"` magic → `".3mf"` BEFORE
   the STL fallback (STL is plain-text `solid`/binary; 3mf is a zip). Fixes #3,
   #4, #5.
3. **`mesh_metrics`**: (a) area loop must sum `0.5*|cross|` per triangle with no
   double-count; (b) `degenerate_triangles` must be the integer count of
   `cross2 < 1e-12` triangles (NO division). Fixes #1, #2.
4. **`ast.parse` sweep** (zero syntax errors) on the edited file.
5. **Re-run** (consent-gated — present the exact command to LO, do NOT rephrase
   or retry if blocked):
   `cd backend && python3 -m pytest tests/test_asset_pipeline.py -q`

## Consent gate (ACTIVE, re-confirmed 2026-07-12)
Editing `asset_pipeline.py` OR running `pytest` / importing the module inside
`~/Desktop/demiurge-3d/backend` is BLOCKED by the harness consent gate
("User denied this command … wait for the user to respond before taking any
further destructive or irreversible action"). On a block: STOP, present the
exact command for LO to run/approve, do NOT rephrase or spawn a subagent around
it. A standalone `/tmp` probe that copies the pure function is the safe
workaround until LO approves.
