# Belt tension probe (K2 Plus / Creality Moonraker)

## The real data path (already in the codebase)
- `demiurge/printer/manager.py` -> `PrinterManager.read_belt_tension()`
  - Step 1: `query_object("belt_mdl")` — structured object (clean numbers).
  - Step 2: fallback fires `BELT_MDL_INFO MDL_NAME=mdlx` / `mdly` via
    `client.send_gcode(..., dry_run=False)` and parses console text with
    `_parse_belt_n()` (handles decimal / comma-decimal / hex / several label
    layouts the CA2714 firmware ships).
  - Returns `{x, y, calibrated, raw, source}` where `source` is one of
    `object | console | unparsed | none | no-client`.
- Live route: `GET /api/printer/{printer_id}/belt-tension` (server.py) ->
  returns `await m.read_belt_tension()`. THIS is the endpoint to curl.
- Separate (buggy/dead) route: `POST /api/printer/belt-tension` (server.py
  ~line 1742) calls `query_object("belt_tension")` — wrong object name,
  returns nothing useful. Don't use it; fix it to call `read_belt_tension()`.
- `save_belt_tension(dry_run=True)` persists via `BELT_MDL_SET` + `SAVE_CONFIG`.
  Defaults to DRY RUN. Refuses on uncalibrated sensors (CA2714 OTA-wipe
  sentinel 0xFFFFFFFF = uncalibrated; can trigger dangerous auto-tensioning).

## Critical client quirk
`query_object(name)` returns an EMPTY DICT `{}` for a non-existent Moonraker
object (NOT None). So a probe that does `obj if obj is not None else "NULL"`
will display `{}` and look like a hit when it's actually empty. Real belt
data only arrives via the `BELT_MDL_INFO` console fallback.

## Live probe recipe (run against the running backend on :8093)
```bash
# server must be up (launch with terminal(background=true), NOT nohup):
#   cd /home/hunter/Desktop/Demiurge3D/backend && source ../.venv/bin/activate \
#   && uvicorn server:app --host 0.0.0.0 --port 8093 >/home/hunter/.cache/d3d_tmp/demiurge_dbg_8093.log 2>&1 &
#   sleep 11   # let uvicorn boot
for pid in 5 6; do
  echo "=== /api/printer/$pid/belt-tension ==="
  curl -s -m 30 "http://localhost:8093/api/printer/$pid/belt-tension" | python3 -m json.tool
done
```
Read `x`, `y`, `calibrated`, and `raw` (the raw console text). If `x`/`y`
are null but `raw` has text, the console parser missed a layout -> extend
`_parse_belt_n` in manager.py. If `raw` is empty, the printer isn't answering
`BELT_MDL_INFO` (check connection / printer_id).

## Pitfall this recipe fixes
A hand-rolled `GET /api/_debug_objects/{id}` that iterated candidate object
names (`belt_mdl`, `belt_tension`, `belttension`, `mdl_info`, `calibration`,
`belt`, `printer_mdl`) returned `{}` for all of them — a wasted probe cycle.
The real impl already existed. GREP for the real method/route before adding a
TEMP debug endpoint.

## Tooling note
`search_files` returned empty for `query_object`/`send_gcode` on this tree
(sandbox indexer quirk). Use terminal `grep -rn` instead.
