# Geometry-preserving diff / repair-verify (`forge.gcode_diff`)

Reusable pattern for "prove a transformed artifact is byte-faithful to the original."
Built by D3D04 to verify `gcode_repair` output is geometrically identical to the
source. Use the same shape for ANY "verify transform fidelity" task.

## The problem
`gcode_repair` re-audits (`reaudit.grade` improved) but never proves the *part*
geometry is unchanged. A hardened file is only trustworthy if (a) the part is
identical and (b) only *safe, non-geometric* transforms happened.

## The verdict (fail CLOSED)
`GcodeDiff` = two booleans ANDed:
- `geometry_preserved` — every G0/G1 motion command (X/Y/Z/E) is identical,
  allowing ONLY the safe sub-bed Z clamp.
- `only_safe_transforms` — every changed/added line matches a repair-policy
  safe shape.

`safe = geometry_preserved AND only_safe_transforms`. Any X/Y/E shift,
non-safe Z edit, or line REMOVAL => UNSAFE (never silently "safe").

## Algorithm shape
1. Line-diff original vs repaired (aligned by index; repair only edits in place
   or appends at EOF — never removes).
2. Classify each change:
   - `;REPAIRED:` prefix            -> comment_out  (safe: M302/M0/M1 blocker)
   - same temp code, S reduced      -> temp_clamp   (safe: M104/M109/M140/M190)
   - same `G1`, only Z changed from sub-bed (<0) to 0.00, rest equal -> z_clamp (safe)
   - appended `M104 S0`/`M140 S0`/`M30`/`M2`        -> footer       (safe)
   - anything else                  -> UNSAFE
3. `geometry_preserved` via motion signature: parse both with `gcodeparser`,
   extract `(code, x, y, z, e)` for every G0/G1 carrying geometry; compare
   sequences. Z rule: unchanged => preserved; sub-bed original raised to >=0 =>
   preserved (the clamp); any other Z edit => not preserved.

## Subtlety — identical files with sub-bed Z
For an UNCHANGED sub-bed Z (identical original/repaired both at Z-0.30), the
signature Z is equal => preserved. The clamp allowance fires ONLY when the
repaired Z was actually raised. Do NOT write the Z check as
"original<0 => allow" unconditionally — that wrongly rejects an unchanged
sub-bed Z in identical files. Correct check:

    if za == zb:                 preserved         # unchanged
    elif za < 0 and zb >= 0:     preserved         # safe sub-bed clamp
    else:                        not preserved     # any other Z edit

## Offline-proof
Imports ONLY `forge.gcodeparser` + stdlib. Verify with the 3-part check in
SKILL.md (AST import-line scan + fresh-importlib diff + isolated subprocess).
Do NOT assert session-wide `sys.modules` absence of `socket`/`httpx`/`requests`
— pytest preloads them, so that assertion FALSE-POSITIVES.

## Tests (`tests/test_gcode_diff.py`, 21)
AST offline scan; identical->clean; real repair->SAFE (8 safe transforms);
temp RAISE->UNSAFE; pause comment-out->safe; Z-low clamp->safe+geometry
preserved; XY edit->UNSAFE; footer append->safe; removal->UNSAFE; CLI exit
codes 0/1/2; selfcheck() real numbers (safe_repair_verdict=True,
evil_verdict=False, evil_detected_unsafe=True).
