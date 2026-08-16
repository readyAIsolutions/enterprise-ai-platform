# G-code repair policy + forge ADD-ONLY test conventions (D3D04)

Condensed from `forge/gcode_repair.py` (built 2026-07-11, D3D04). The repair
module is the 4th link of the D3D16 forge chain: it consumes `gcode_audit` and
emits a corrected, re-audited G-code. The *patterns* below generalize to any
"harden a flagged artifact" ADD-ONLY task in the forge.

## The 4-link chain
```
gcode_audit      safety-lint          (BLOCK / WARN / INFO  -> AuditReport)
print_readiness  single-file go/no-go (READY / REVIEW / BLOCKED)
queue_planner    batch queue plan     (dispatch / review / blocked buckets)
gcode_repair     offline hardener     (audit -> fix -> dispatch; re-audit proves it)
```
`gcode_repair` is a NEW CONSUMER of `gcode_audit` (and transitively of the
`gcodeparser` read-path). It never edits `gcodeparser.py`, `gcode_audit.py`, or
any printer/motion code.

## Repair policy table
| Rule | Class | Action | Why it is safe |
|---|---|---|---|
| H-TEMP-NOZZLE | FIXABLE | clamp M104/M109 `S` -> 320C | pulls an overtemp target down to the canonical hotend clamp |
| H-TEMP-BED | FIXABLE | clamp M140/M190 `S` -> 120C | pulls an overtemp bed target down to the max |
| H-COLD-INTERLOCK | FIXABLE | comment out `M302` | restores the cold-extrude lockout the interlock defeat removed |
| H-OOB-Z-LOW | FIXABLE | clamp any `Z` below bed -> `0.00` | prevents a nozzle crash into the bed |
| H-FEED-ABSURD | FIXABLE | clamp `F` -> 30000 mm/min | tames an absurd feedrate |
| H-PAUSE-BLOCK | FIXABLE | comment out `M0`/`M1` | removes an unattended halt |
| H-NO-HEATOFF | FIXABLE | append `M104 S0` / `M140 S0` | cooldown hygiene (file heated but never cooled) |
| H-NO-END | FIXABLE | append `M30` | well-formed end marker |
| H-OOB-XY | UNFIXABLE | leave BLOCK | needs a re-slice to fit the bed |
| H-NO-HOME | UNFIXABLE | leave BLOCK | source must home (`G28`) before extruding |
| H-COLD-EXTRUDE | UNFIXABLE | leave BLOCK | nozzle must reach temp before first extrude |
| H-OOB-Z-HIGH | ADVISORY | leave WARN | clamping would warp the part |
| H-EMPTY | ADVISORY | leave WARN | nothing to print |

Key invariant: every FIXABLE action strictly *reduces* hardware risk; no fix
changes the part geometry. UNFIXABLE hazards stay BLOCK with `fully_repaired=False`
so a caller never ships them.

## Per-line transform recipe (reuse for any text-hardening repairer)
1. `report = audit_gcode(text, envelope=env)` (or whichever validator owns the rules).
2. Build `line_edits: dict[int, str]` keyed by 0-based `finding.line - 1`.
3. For each finding apply a scoped regex transform on that line:
   - `_clamp_temp(line, val)`: `_S_RE.sub(lambda m: f"S{val:g}", line, count=1)`
     where `_S_RE = re.compile(r"S(\d+(?:\.\d+)?)", re.I)`.
   - `_clamp_feed(line, val)`: same shape with `F`.
   - `_clamp_z_low(line, tol)`: `_Z_RE.sub` that returns `"Z0.00"` iff `float(z) < -tol`.
   - `_comment_out(line)`: `line if line.lstrip().startswith(";") else f";REPAIRED: {line}"`.
   - For whole-file scans (e.g. H-OOB-Z-LOW, a file-level finding with `line=None`),
     iterate ALL lines and apply the Z clamp where it trips.
4. File-level hygiene (H-NO-HEATOFF / H-NO-END) = append lines at EOF (`M104 S0`,
   `M140 S0`, `M30`).
5. `new_lines = [line_edits.get(i, ln) for i, ln in enumerate(lines)]`, join.
6. **Re-audit:** `reaudit = audit_gcode(fixed_text, envelope=env)` and set
   `fully_repaired = (reaudit.grade != BLOCKED)`. Expose `reaudit` so callers get
   proof. Assert in tests that `rank(reaudit) <= rank(pre)`.

Do NOT regenerate G-code from parsed moves — you lose slicer comments/structure
and risk introducing errors. Edit the source text.

## Forge ADD-ONLY test conventions (copy for any new forge consumer module)
Run from `backend/`: `python3 -m pytest tests/test_<mod>.py -q`. (If the repo
root `.venv` is absent, system `python3` + `~/.local/bin/pytest` works — `conftest.py`
injects `backend/` onto `sys.path[0]`.) Mirror `tests/test_gcode_repair.py` (24 tests).

- **Import via `importlib.import_module`** (`ga = importlib.import_module("forge.gcode_audit")`)
  — avoids the `forge/__init__.py` re-export shadowing pitfall (see
  `references/forge-parsing-gotchas.md`).
- **Fixtures need a perimeter for bounds.** A single corner move gives a zero-width
  box (fit-check always "fits"). Trace `G1 X0 Y0` -> `X{x} Y0` -> `X{x} Y{y}` ->
  `X0 Y{y}` -> `X0 Y0` with `M83` (relative extrusion) so each edge's `E` adds
  cleanly. See `references/swarm-addonly-build.md`.
- **Read-only guarantee (printer-safety) — TWO tests:**
  - import-line scan: read the module source, keep only lines
    `strip().startswith(("import ","from "))`, assert none contain banned tokens
    (`moonraker`, `httpx`, `requests`, `urllib`, `socket`, `telnetlib`,
    `demiurge.printer`).
  - sys.modules diff: `before = set(sys.modules)`; `importlib.reload(importlib.import_module("forge.<mod>"))`;
    `after = set(sys.modules) - before`; assert no module with `printer`/`moonraker`.
- **`selfcheck()` returns real numbers** — a `selfcheck()` fn that builds a known
  fixture, runs the module, and returns a dict (counts, grade, booleans). Assert
  specific values in a test; it doubles as live evidence in the STATUS board.
- **CLI exit-code tests:** run `mod.main([...])` in-process. Conventions:
  0 = success/dispatchable, 1 = blocked/needs-review, 2 = missing file. Cover
  `--json` via `capsys` (parse `json.loads(capsys.readouterr().out)`) and file
  output (`-o out.gcode`, `--in-place`).
- **Re-audit / grade-not-worse assertion** (repairers specifically): after repair,
  assert `rank(result.reaudit_grade) <= rank(pre.grade)`.
- **Regression honesty:** run the sibling module set you depend on + your new
  file; report the total green and explicitly list pre-existing failures that do
  NOT touch your module (grep `FAILED` lines for your module name — if absent,
  they're unrelated). Full-suite runs on this box carry ~47 pre-existing failures
  (async `mode=strict`, float-ordering, key-error in unrelated modules) — they are
  environmental, not regressions from an ADD-ONLY two-file change.

## STATUS board shape (per D3D convention)
Line 1 exactly `[state: DONE|IN-PROGRESS|BLOCKED]`. Then a PASS/FAIL board with
REAL NUMBERS (test counts, `selfcheck()` dict), a `what adds R / what to drop`
list, and an `UNVALIDATED` section (live printer contact, visual sign-off,
full-suite timeouts). Forge quality work uses `STATUS_D3D<NN>.md` at the repo root.
