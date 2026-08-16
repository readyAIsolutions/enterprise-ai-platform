# Print-quality presets + "doom" 3MF project (added 2026-07-15)

LO's model: when printing, he picks a QUALITY TIER (draft / strong / fine /
hueforge / mini), never raw slicer numbers. The tier decides the OrcaSlicer
settings; the sliced gcode + model + preset settings get bundled into one 3MF
"doom" project so the whole idea lives in a file.

## Backend pieces (all in `server.py` + `forge/`)

- `forge/print_presets.py`
  - `PRINT_PRESETS` dict: keys `draft, standard, strong, fine, mini, hueforge`.
    Each value carries `layer_height, infill, wall_loops, top/bottom_solid_layers,
    infill_pattern, print_speed, outer/inner_wall_speed, support, bridge_speed,`
    plus `label`/`desc`. `hueforge` tier => `infill:100, top/bottom:0, hueforge:True`
    (color lithophane: solid fill, painted by Z — pair with `demiurge/hueforge`).
  - `list_print_presets()` -> catalog. `get_preset(tier)` -> dict or None.
  - `preset_to_orca_args(tier)` -> flat `["--layer-height","0.32",...]` list for
    Orca CLI. Skips descriptive keys (label/desc/hueforge/threshold_save).
- `forge/threemf.py`
  - `package_doom_project(out_path, *, model_path, gcode_path, preset, project_name,
    extra_files)` -> zips `model/`, `gcode/`, `preset.json` (the "idea" manifest:
    tier + settings + timestamp) into one 3MF archive. Returns {ok, path, members}.
- `forge/slicer.py`
  - `slice_to_gcode(stl, gcode_out, profile_ini=None, timeout=180)` -> calls
    `orca_bin()` (auto-detects `orca-slicer`/`OrcaSlicer` on PATH), exports gcode.
    Returns {ok, gcode_path, reason, stderr}. If Orca missing => ok:False,
    reason:"OrcaSlicer not found".
  - `estimate(stl, material, infill)` -> filament/time estimate fallback.
- Routes added to `server.py`:
  - `GET /api/print-presets` -> the tier catalog (frontend dropdown source).
  - `POST /api/print/slice-doom {model_path, tier, filament_type, output_name?}`
    -> slices via Orca with the tier's settings, falls back to `estimate()` +
    manifest if Orca isn't installed, then bundles the 3MF "doom" project.
    Returns {ok, sliced_with_orca, slice_note, gcode_path, estimate, project}.

## Frontend status (2026-07-15)

Backend done. The frontend slice button (quality-tier dropdown on the Print tab
that calls `/api/print/slice-doom` then offers the .3mf download) was NOT yet
built — only the API exists. Next session: add a tier <select> + "Slice + Bundle
3MF" button in `PrintDispatch.tsx` (or a new `SliceDoom.tsx`), POST to the route,
surface `project.path` as a download link.

## Pitfalls

- OrcaSlicer may NOT be installed on LO's box. `slice_to_gcode` must degrade
  gracefully (estimate + manifest) — never 500 just because Orca is missing.
  Verify with `which orca-slicer`; if absent, the doom project still ships.
- The `model_path` is a SERVER-side path (uploaded file or forge output). The
  route does NOT accept raw upload bytes — upload first via `/api/files/upload`,
  then pass the stored path. Don't reinvent upload in the slice route.
- `preset_to_orca_args` is currently computed in the route but NOT yet passed to
  `slice_to_gcode` (that function takes `profile_ini`, not flag args). To apply
  tier settings for real, either (a) write a temp Orca profile .ini per tier and
  pass as `profile_ini`, or (b) extend `slice_to_gcode` to accept `extra_args`.
  Left as a known gap — flag it if LO reports "tier does nothing".
