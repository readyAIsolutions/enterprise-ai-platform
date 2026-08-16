# CFS empty-slot visibility (follow-up to cfs-ams-k2plus.md)

The main `references/cfs-ams-k2plus.md` covers skipping UNCONNECTED boxes
(state=None / all `-1`). ADDITIONAL rule confirmed this session:

Once a box is confirmed CONNECTED (`state="connect"`), its 4 positions are REAL
physical bays even when a spool is absent. LO wants ALL positions shown
(e.g. K1 = 8 slots, including empties). The original parser did
`if color AND material both "unknown": continue` — that DROPPED empty bays and
made K1 show 7 instead of 8.

Fix: inside a connected box, append every position. For an empty spool set
`empty: true`, `color_hex: "#888888"`, `filament_type: "EMPTY"`. Only `continue`
on the WHOLE box when it is unconnected — never `continue` on an individual
empty spool inside a connected box.

```python
for t in 1..4:
    tb = box[f"T{t}"]
    if not isinstance(tb, dict): continue
    if tb.get("state") in (None,"None") and all(str(c) in ("-1","None") for c in (tb.get("color_value") or [])):
        continue                       # whole box unconnected -> skip
    for i in 0..3:
        c, m = colors[i], mats[i]
        is_empty = c in (None,"unknown") and m in (None,"unknown")
        slots.append({
          slot: f"T{t}{chr(65+i)}",
          empty: is_empty,
          color_hex: "#888888" if is_empty else norm_hex(c or "888888"),
          filament_type: "EMPTY" if is_empty else mat_lut.get(str(m),"UNKNOWN"),
        })                              # NO continue on empty -> keeps all 8/K1
```

Also: the Forge UI "Send to Forge build" for a Swarm Design spec must call
`/api/forge/swarm-build` (which runs `pipeline.build(to_forge_spec(spec))`),
NOT `loadSpec` directly — otherwise swarm parts (mask_shell etc.) hit
`pipeline.build` untranslated and fail with "Could not turn that into a
buildable part". See `references/forge-geometry.md`.
