# Filament presets (Orca-style auto-tune)

Built this session. Gives the Filaments tab an OrcaSlicer-like experience: a preset dropdown
plus a one-click "Tune from preset" that fills a spool's print settings from a known-good
profile, instead of blank fields.

## Backend
- `backend/forge/filament_profiles.py`
  - `FILAMENT_PROFILES: dict[str, dict]` — keyed by filament type. Each value carries:
    - `nozzle_temp`, `bed_temp`, `first_layer_temp` (°C)
    - `print_speed`, `first_layer_speed` (mm/s)
    - `infill` (%), `cooling` (fan %), `retraction` (mm)
    - `notes` (string tip shown under the form)
  - `Custom` key MUST stay `{}` (empty) — the frontend treats it as "no preset" and disables Tune.
  - `list_filament_profiles()` returns a deep copy for the API.
- Route: `GET /api/filament-presets` added to `server.py` near the spool routes
  (`from forge.filament_profiles import list_filament_profiles`). Returns the dict as JSON.

## Frontend — `frontend/src/components/filaments/FilamentManager.tsx`
- On mount: `fetch('/api/filament-presets')` → builds the type `<select>` from the keys
  (Custom last) and stores the map in `presets`.
- Type dropdown lists ALL preset types, not a hardcoded 5.
- **⚡ Tune from preset** button copies the selected type's profile into the form's `print`
  settings (all 8 fields). Disabled when the type has no preset (e.g. Custom).
- Saved spool `print_settings_json` now carries all 8 fields; the spool card renders a badge
  for each non-null value (temps, speed, infill, cooling, retraction).

## Extending
- Add a filament type: append a key + dict to `FILAMENT_PROFILES`. No DB/schema change needed —
  print settings live in the spool's `print_settings_json` TEXT column, which `update_spool`
  writes because `print_settings_json` is in `_ALLOWED_SPOOL_COLS`. If you ever add a NEW spool
  column, also add it to `_ALLOWED_SPOOL_COLS` in `demiurge/webapp/db.py` or `update_spool` will
  silently drop it.
