# Demiurge 3D — K2 Plus CFS/AMS + Print Gate Notes

## K2 Plus CFS object structure (Moonraker, Creality fork)

The CFS is NOT `box.slot0.name`. Real shape (confirmed via
`GET /printer/objects/query?box` on a live K2 Plus at 192.168.1.65:7125):

- Top-level object `box` (real). Also `filament_rack`, `filament_switch_sensor filament_sensor`.
- `box` has 4 physical boxes: `box.T1`..`box.T4`, each 4 spools -> 16 slots `T1A`..`T4D`.
- Per box `T{n}`: `color_value` (list of 4 hex, e.g. `"09ea7ae"`), `material_type`
  (list of 4 codes, e.g. `"000003"`=PETG), `remain_len` (list of 4 meters),
  `temperature`, `dry_and_humidity`. Empty spools report `"unknown"`/`"None"`.
- `box.same_material`: list of `[code, hexcolor, [slots], type]` -> resolves code->type.
- Material codes: 000001=PLA 000002=ABS 000003=PETG 000004=TPU 000005=ASA 000006=PC
  000007=PA 000008=PVA 000009=HIPS 000010=PETG-CF 000011=PLA-CF 000012=ABS-CF.

### Parse pitfall (fixed bug)
Old code assumed `box.slot0.name/color/type` -> always `slots:[]` -> UI "no AMS slots"
despite loaded spools. Fix: iterate T1..T4, read parallel lists, skip spools where
color AND type are `unknown`/`None`.

### Hardening
Top-level try/except AND per-box `T{n}` try/except so one bad box never blanks the read.
Return partial slots. `_read_ams` is in `backend/server.py`. Printer DB ids are 5 and 6
(NOT 1/2) — `/api/printer/1/ams` returns `connected:false`.

## Print confirmation gate — REMOVED (LO standing preference, 2026-07-15)

LO: "i dont need a confirmation token in print i need to be able to choose the files in
demiurge or upload my own to print".
- Removed `confirm` field from `PrintDispatchIn` and the `CALI_ALLOW_PRINT` gate + 423
  from `/api/print/dispatch` (backend server.py).
- Removed confirm `<input>` + gating from `frontend/src/components/print/PrintDispatch.tsx`.
- KEEP offline gcode audit+repair (`forge.gcode_audit`/`forge.gcode_repair`) — real safety
  net, rejects BLOCK-grade files per-job. Not a UX gate.
- Flow: pick library file OR upload own (.gcode/.g/.3mf/.stl) -> choose printer(s) -> Dispatch.

## Multi-printer calibration

`/api/printer/calibrate` fans out correctly: `printer_ids:[5,6]` returns ok for BOTH in
dry-run. "Only 1 calibrates" was the dry-run default (nothing moves unless `armed:true`) —
NOT a fan-out bug. If arming still hits one, trace UI result surfacing, not the backend loop.

## AMS display location (LO decision)

LO: "ams details should go in filaments tab". Live CFS panel lives in `FilamentManager.tsx`
(Filaments tab): fetches `/api/printer/{id}/ams`, renders color chips + type + remaining,
"Sync to spools" button hits `/api/printer/{id}/ams/sync`.
