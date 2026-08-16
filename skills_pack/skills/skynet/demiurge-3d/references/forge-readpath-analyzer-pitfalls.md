# forge read-path analyzer pitfalls (D3D10 — flow.py, 2026-07-11)

Condensed pitfalls for anyone building a read-path analyzer under `backend/forge/`
(that consumes `forge.gcodeparser` and must stay strictly read-only).

## 1. `mv.layer_index` is unreliable after Z-hops — track physical Z yourself

`gcodeparser` derives a layer index from `;LAYER:N` comments and from Z-plateau
falls. After a Z-hop (retract + `G1 Z` + unretract), the first move on the new
physical layer can be mis-indexed: the parser emits a **phantom** `layer_index`
(observed: a phantom index 1 right after a Z-hop) because the Z-plateau fallback
fires before the move is attributed to the new layer. `overhang.py` and
`printability.py` AVOID `mv.layer_index` for exactly this reason.

**Fix:** never key per-layer grouping on `mv.layer_index`. Track physical Z while
walking:
```python
_planar = 0
_cur_z = 0.0
_layer_z_index = {}   # rounded z -> int index (0-based by first appearance)
for mv in self._iter_moves(pr):
    if mv.z is not None:
        _cur_z = mv.z
    z_key = round(_cur_z, 4)
    if z_key not in _layer_z_index:
        _layer_z_index[z_key] = len(_layer_z_index)   # register UP FRONT
    ...
    if mv.is_extrude and mv.x is not None and mv.y is not None:
        _planar += 1
        # compute flow, check peak, and LABEL the worst move with
        # layer_z_index[z_key] (NOT mv.layer_index)
```
Use that own index for any per-layer report and for the "worst move" label.

## 2. Register the physical-Z layer BEFORE the peak-flow check (the `LNone` bug)

When I first built `flow.py` I computed `layer_z_index` lazily: the dict was
populated only when a *planar* move was processed, i.e. AFTER the peak-flow check
that labels the worst move. Result: the first over-limit move was labeled `LNone`
(the layer dict entry for its Z didn't exist yet).

**Fix:** register the `z_key -> index` entry as soon as you see the Z change,
unconditionally (step 1 above does this), so the worst-move label is always
resolved. Then re-`pytest` and assert the worst-move string is `L<idx> z=...`,
never `LNone`.

## 3. Read-only guarantee test for a `forge/*` module — source-scan, NOT a broad sys.modules check

A read-path analyzer imports ONLY `forge.gcodeparser` + stdlib (no printer /
moonraker / network). To PROVE read-only, mirror `tests/test_overhang.py` — do NOT
assert on `sys.modules`:

- **WRONG:** asserting `'socket' not in sys.modules` / `'httpx' not in sys.modules`
  after `import forge.<yourmod>`. FALSE-POSITIVES. `forge/__init__.py` imports heavy
  siblings (`pipeline`, `slicer`, `scad`, `slicer_bridge`, `printers`, `meshgen`)
  which TRANSITIVELY load `httpx` / `socket` / `urllib` / `requests` — so those
  modules are in `sys.modules` purely as a side effect of `forge/__init__`, NOT
  because your module imported them. (This is distinct from the already-documented
  "pytest preloads socket" false-positive — here it's `forge/__init__` transitively.)
- **RIGHT (proven, 3-part, lighter than the full subprocess check):**
  1. **Source scan** of YOUR file only for banned import roots:
     ```python
     _BANNED = ("moonraker", "httpx", "requests", "urllib",
                "socket", "telnetlib", "printer")
     src = Path(__file__).parent.parent / "forge" / "flow.py"
     text = src.read_text()
     # assert none of _BANNED appear as import roots;
     # assert it DOES `from .gcodeparser import ...`
     ```
  2. **Import delta** restricted to `printer`/`moonraker` ONLY (NOT socket/httpx/
     urllib — those are forge/__init__ noise):
     ```python
     def _loaded(prefixes):
         return {m for m in sys.modules if any(p in m for p in prefixes)}
     before = _loaded(("printer", "moonraker"))
     importlib.import_module("forge.flow")
     after = _loaded(("printer", "moonraker"))
     assert after - before == set()   # your module must not load printer/moonraker
     ```
  3. (Optional, strongest) the isolated `subprocess` import check from the
     skill's existing 3-part refinement — use it only if you need to be bullet-proof.

The skill's general "Read-only guarantee test must scan IMPORT LINES only" +
subprocess refinement still applies; this note just adds the `forge/__init__.py`
transitive-import caveat so a `forge/*` author doesn't waste a cycle chasing a
false-positive `socket`/`httpx` hit.

## 4. fixture recipe — exact-flow gcode so flow math is deterministic

The volumetric-flow of a planar move = `bead_cross_section_mm2 * feed_mm_per_min / 60`,
where `bead_cross_section = line_width_mm * layer_height_mm`. To assert exact mm³/s
in a test, hand-build gcode with a known modal feed:
```
G21 ; units mm
G90 ; absolute
M83 ; relative extrusion
G1 Z0.200 F3000
G1 X0 Y0 E0 F12000        ; fast planar extrude at Z0.2
```
`F12000` mm/min at `line_width=0.4 * layer_height=0.2 = 0.08 mm²` ->
`0.08 * 12000 / 60 = 16.0 mm³/s` (assert within a small tolerance, e.g. 15.5-16.5).
For exact worst-case values use the math; avoid assuming the parser's `mv.f` is
always set (moves without an `F` word fall back to `feed_fallback` — test that path
too: assert `n_unknown_feed == n_planar` and a "no F word" warning is emitted).

## 5. CLI integration is additive — new subparser only

`backend/forge/cli.py` wires analyzers as argparse subparsers. Adding one = add
`from . import flow as flow_mod`, a `sub = subparsers.add_parser("flow", ...)` with
its own args (`gcode`, `--nozzle`, `--line-width`, `--layer-height`, `--max-flow`,
`--filament`, `--feed-fallback`), a `cmd_flow(args)` that builds kwargs from the
parsed args and calls `flow_mod.analyze_file`, a `_render` branch, and an
`elif args.cmd == "flow": cmd_flow(args)` dispatch. Touch NO existing subparser or
behavior. After editing `[project.scripts]`-adjacent code, remember the
console-script-drift pitfall: the `python -m forge.cli` path works without a
re-install, but the `forge` console script in `.venv/bin` only regenerates on
`pip install -e .`.
