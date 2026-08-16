# Demiurge 3D — forge + print features added 2026-07-16

Session where LO pushed: unblocked print flow, quality presets + "doom" 3MF,
Swarm Design button, spool tracking, AMS hardening. Capture the architecture so
the next session doesn't re-derive it.

## 1. Print flow — NO confirmation gate

LO: "I don't need a confirmation token blocking print. I need to choose files in
Demiurge or upload my own to print." So:
- Backend `/api/print/dispatch` (class `PrintJobIn`): REMOVED the required
  `confirm: str` field AND the `CALI_ALLOW_PRINT` gate. Printing is armed by
  default. The per-job gcode audit/repair (`quality_gate`) STILL runs — that
  safety stays; only the human-typed token was removed.
- Frontend `PrintDispatch.tsx`: removed the `confirm` state, the gate in
  `dispatch()`, and the confirm `<input>`. Jobs send `{ jobs, do_slice:false }`.
- Sources supported per job: `library` (file_id from `/api/files`), `upload`
  (POST `/api/files/upload` → filename), `gcode` (inline text).
- Dispatch currently does NOT wire a quality `tier` yet — see section 2.

## 2. Print-quality presets + "doom" 3MF

LO: "where are my presets like hueforge/draft/strength — it should use Orca to
slice properly for what I ask; the idea should live in a 3MF doom."

- `backend/forge/print_presets.py` (NEW): `PRINT_PRESETS` dict with tiers
  `draft / standard / strong / fine / mini / hueforge`. Each tier maps to
  concrete OrcaSlicer flags (layer_height, infill, wall_loops, speeds, support).
  `list_print_presets()` + `get_preset(tier)` + `preset_to_orca_args(tier)`
  (returns `[--flag, value, ...]` for the CLI).
- `backend/forge/threemf.py`: added `package_doom_project()` — zips model +
  sliced gcode + `preset.json` manifest (the "idea") into one 3MF-style archive.
  (Existing `package_project()` bundles STL renders only — keep separate.)
- Backend routes (server.py):
  - `GET /api/print-presets` → the tier catalog.
  - `POST /api/print/slice-doom` (class `SliceDoomIn`: model_path, tier,
    filament_type, output_name) → calls `slicer.slice_to_gcode()` (headless
    OrcaSlicer) then `threemf.package_doom_project()`. Graceful fallback: if
    Orca isn't installed (`orca_bin()` returns None) it uses `slicer.estimate()`
    and STILL produces the 3MF project (no dead end).
- OrcaSlicer detection: `slicer.orca_bin()` checks `shutil.which("orca-slicer")`
  and common install paths. If absent, install it OR rely on the estimate
  fallback. Bundling OrcaSlicer + OpenSCAD INTO the Demiurge distribution (so
  they ship with it, free/OSS) was requested but NOT yet done — open item.

## 3. Swarm Design button

LO: "add a swarm design button that allows me to ask things like 'rave mask
designed from the anime Berserk' ... Couldn't map this to a known part
automatically. Add dimensions or a photo, or let the swarm design it."

- `backend/forge/swarm_design.py` (NEW): `design_request(text, measurement,
  material)` decomposes ANY free-form creative request into printable parts.
  - `_detect_archetype()` recognizes: mask, helmet, figurine, cosplay_piece,
    phone_case, prop, container, mount, generic (from keywords).
  - Each archetype has `parts` (shape + dims + features), an `ask` field (the
    ONE dimension LO must give), `ask_q` (the question), `default_scale`.
  - Scales all dimensional parts by `measurement / default_scale`.
  - `ai_mesh` flag = True if `MESHY_API_KEY` or `OPENROUTER_API_KEY` is set
    (routes organic shapes through AI mesh); else parametric fallback.
- Route `POST /api/forge/swarm-design` (class `SwarmDesignIn`: text, measurement,
  material). Call once with just text → returns parts + `ask_q`; call again with
  `measurement` to lock scale.
- Frontend `Forge3D.tsx`: added a purple "🐝 Swarm Design" card at top of the
  Forge tab — textarea + "Design it" button + (when `ask_q` present) a mm input
  + "Lock scale" + a part-list preview + "→ Send to Forge build" (pushes the
  decomposed spec into `loadSpec`).
- The OLD `understand_text` fallback still says "Couldn't map..." — Swarm Design
  is the replacement path for vague creative prompts; route creative/vague text
  to `/api/forge/swarm-design`, not `/api/forge/understand`.

## 4. Spool tracking (1kg rolls)

See `references/cfs-ams-k2plus.md` "Spool / filament tracking" section. The
backend `spools` table supports `total_m`/`remaining_m`; decrement-on-print +
runout signal + reset-on-swap UI was requested but the frontend wiring was NOT
completed this session (backend primitives exist). Open item.

## 5. Belt tension display bug (UNRESOLVED)

After `BELT_TENSION_CALIBRATE`, the dial (`BeltTensionDial` in PrinterPanel)
shows nothing. Root cause traced to: the per-printer route
`/api/printer/{id}/belt-tension` calls `query_object("belt_tension")` on the hub
printer; if the K2 firmware doesn't populate a `belt_tension` object post-
calibration, it returns `{x:0,y:0}` and the dial renders empty. Fix = confirm
the live object name on the printer (probe `GET /printer/objects/query?belt_tension`)
and map it. NOT done — blocked on a printer-query approval.

## Quick file map (this session's touches)

- backend/forge/print_presets.py ........ NEW (tiers → Orca flags)
- backend/forge/swarm_design.py ......... NEW (creative decomposition)
- backend/forge/threemf.py ............. +package_doom_project()
- backend/server.py .................... +/api/print-presets, +/api/print/slice-doom,
                                          +/api/forge/swarm-design; dispatch confirm gate removed;
                                          _read_ams hardened (unconnected-box skip)
- frontend/src/components/forge/Forge3D.tsx ... +Swarm Design card
- frontend/src/components/print/PrintDispatch.tsx . confirm gate removed
- frontend/src/components/filaments/FilamentManager.tsx . live CFS panel
