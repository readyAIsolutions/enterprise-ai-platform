# K2 Plus CFS / AMS — real Moonraker object structure

Captured live from a Creality K2 Plus (Moonraker @ :7125) during the Demiurge 3D
session. The original `_read_ams` parser assumed `box.slot0.name` and returned
empty slots ("no AMS slots" lie). This is the ACTUAL shape.

## Object discovery

`GET /printer/objects/list` shows (among 143 objects): `box`, `filament_rack`,
`print_stats`, plus `BOX_*` gcode macros and `filament_switch_sensor`.
The CFS state is in `box`.

## Real `box` structure

Four physical CFS units: `box.T1` .. `box.T4`. Each holds 4 spools addressed
`T1A`..`T4D` (16 slots total). Per-box state is in PARALLEL LISTS, NOT nested
spool dicts:

```
box.T1.color_value   = ["09ea7ae", "0ffffff", "06c84ff", "unknown"]   # 4 hex strings
box.T1.material_type = ["000003",  "000003",  "000003",  "unknown"]   # 4 Creality codes
box.T1.remain_len    = ["100",     "100",     "100",     "100"]       # 4 meters
box.T1.temperature        = "29"
box.T1.dry_and_humidity   = "27"
box.T1.filament_detected   = "None"
box.T1.state               = "connect"
```

`box.same_material` is `[[code, hexcolor, [slots], type], ...]`:
```
["000003", "09ea7ae", ["T1A"], "PETG"],
["000003", "0ffffff", ["T1B"], "PETG"],
...
```
Use this to build code->type lookup; fall back to the static map below.

`box.map` maps slot labels to themselves (`"T1A":"T1A"` ...) — not needed for parse.

## Creality material codes -> type

```
000001 PLA      000002 ABS     000003 PETG    000004 TPU
000005 ASA      000006 PC      000007 PA      000008 PVA
000009 HIPS     000010 PETG-CF 000011 PLA-CF  000012 ABS-CF
```

## Corrected parse algorithm (pseudo)

```
mat_lut = static_map
for row in box.same_material: mat_lut[row[0]] = row[3].upper()
slots = []
for t in 1..4:
    tb = box[f"T{t}"]
    colors, mats, remains = tb.color_value, tb.material_type, tb.remain_len
    for i in 0..3:
        c, m, r = colors[i], mats[i], remains[i]
        if c in (None,"unknown","None") and m in (None,"unknown","None"): continue
        slots.append({
          slot: f"T{t}{chr(65+i)}",          # T1A
          color_hex: norm_hex(c or "888888"),
          filament_type: mat_lut.get(str(m),"UNKNOWN") if m not in (None,"unknown") else "UNKNOWN",
          remaining_m: float(r) if numeric else 0.0,
          temp, humidity from tb
        })
```

`norm_hex` must accept Creality's 7-char `"09ea7ae"` (leading `0` + 6 hex) and
produce a proper `#RRGGBB`. Strip the leading `0` if length==7 and prefix `#`.

## Detecting which CFS units are ACTUALLY connected (K1=2, K2=1)

Not all 4 `box.T{n}` units are physically installed. LO's fleet: K1 (printer 5)
has 2 CFS boxes, K2 (printer 6) has 1. The "skip empty spool" rule alone is NOT
enough — an EMPTY/UNCONNECTED box returns a different signature than a connected
box with empty spools:

- Connected box with empty spools: `state="connect"`, `color_value=["09ea7ae",...,"unknown"]`
- UNCONNECTED / absent box:     `state=None`, `color_value=["-1","-1","-1","-1"]`
  (also `filament=None`, `material_type=["-1",...]`)

So you MUST skip whole boxes that are unconnected, BEFORE the per-spool loop:

```python
for t in 1..4:
    tb = box[f"T{t}"]
    if not isinstance(tb, dict): continue
    # skip unconnected bays — Creality reports state=None + all "-1"
    if tb.get("state") in (None,"None","none","") and str(tb.get("filament")) in (None,"None","none",""):
        continue
    colors = tb.get("color_value") or []
    if all(str(c) in ("-1","None","none","unknown","Unknown","") for c in colors):
        continue
    ...  # per-spool loop as above
```

Without this, K2 reports 4 phantom boxes (or the parser chokes on `-1` ints in
`remain_len`). After the fix: K1 → 8 slots across T1+T2, K2 → 4 slots across T1.

## Spool / filament tracking (1kg rolls)

LO: "all rolls are 1kg". Set `total_m = 1000` for every synced spool. The
`spools` table (`demiurge/webapp/db.py`) already has `remaining_m REAL` and
`total_m REAL` columns; `add_spool(...)` / `update_spool(...)` accept them.
Behavior LO wants:
- Seed `remaining_m` from printer `remain_len` when available, else 1000.
- Decrement `remaining_m` by filament used (from gcode/slice estimate) when a
  print completes; fire a runout warning at <= threshold (e.g. 0 or <2m).
- RESET counter on color/roll swap (re-sync from AMS, or manual swap).

## Hardening (added 2026-07-15)

Wrap the whole box-scan in a top-level try/except, and EACH `box.T{n}` read in
its own try/except. A single misbehaving box (e.g. `T3` returns a string
instead of a dict, or `color_value` is None) must NOT sink the other 15 slots
or return an empty `slots:[]` that reads as "no AMS". Log the box error and
`continue`. Same for the `filament` fallback query. This is what makes the
endpoint robust against Creality firmware quirks across box units.

## Live probe command (run on host, hits printer directly)

```bash
curl -s "http://<printer-ip>:7125/printer/objects/query?box" | python3 -m json.tool
```

## Pitfalls

- PRINTER IDS ARE DB IDS (5, 6 — NOT 1/2). `hub.get(1)` is None -> `connected:false`.
  Always pull real ids from `GET /api/printers` first.
- Multi-printer calibrate fan-out WORKS: dry-run `printer_ids:[5,6]` returned ok
  for both. "Only one calibrates" = dry-run default (wizard doesn't arm live
  G-code unless the arm toggle is on), not a loop bug.
- LO decided: AMS details belong in the FILAMENTS tab (live CFS panel with
  printer dropdown + color chips + Sync-to-spools), not the printer panel.
- Belt-tension result not showing after calibrate: the per-printer route
  `/api/printer/{id}/belt-tension` queries `query_object("belt_tension")` on the
  hub printer — confirm the K2 firmware actually populates a `belt_tension`
  object after `BELT_TENSION_CALIBRATE` (some Creality builds report it under a
  different key). If it returns `{x:0,y:0}`, the object isn't populated; the
  dial then renders empty by design.
