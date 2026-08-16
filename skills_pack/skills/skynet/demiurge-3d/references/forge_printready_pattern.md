# Forge print-ready pattern (knowledge bank)

Condensed from the 2026-07-17 session where ENI built the Forge generator brain
from scratch: a parametric OpenSCAD mechanism/tolerance library + a zero-dep
STL watertight validator + an ENI-swarm fan-out that only emits validated
geometry. 13/13 parts rendered watertight.

## The problem
The on-disk `forge` (`demiurgenas_stash/demiurge/builder/forge/`) is ONLY a thin
OpenSCAD<->OrcaSlicer CLI wrapper (`render.py` + `slice.py`). It has NO
NL->geometry brain. To "make Forge able to generate anything print-ready" you
must BUILD that brain.

## Proven stack
1. `forge_core.py` - parametric OpenSCAD primitive builders that bake in FDM
   clearance so every design inherits correct fit:
   - `press_fit_hole(shaft_d, depth)` -> hole diameter = shaft_d - 2*0.15 (friction)
   - `free_hole(shaft_d, depth)` -> hole = shaft_d + 2*0.30 (slides/rotates)
   - `snap_hook(depth, width, undercut=0.60, wall=1.20)` -> cantilever catch
   - `living_hinge(len, width, gauge=1.00)` -> thin bridge + rigid lands
   - `printed_thread_peak(d_major, pitch, turns, length, play=0.25)` -> sampled helix
   - `spur_gear(module, teeth, thickness, bore)` -> star-polygon teeth + press bore
   - `shell_box(w,h,d,wall,r)` -> hollow open-top box
   - `rounded_box`, `hole_cylinder`
   Canonical TOL dict: xy_clearance 0.30, press_fit 0.15, snap_undercut 0.60,
   hinge_gauge 1.00, thread_play 0.25, wall_min 1.20, fn 96.
2. `stl_validator.py` (see scripts/) - zero-dep watertight check. Reads ASCII +
   binary STL. Edge-manifold test: every triangle edge shared by EXACTLY 2 tris
   => closed/watertight. Rejects degenerate (zero-area) tris. Optional trimesh
   second opinion if importable.
3. `build.py` - emit `.scad` per part (`module part(){...} part();`), call
   OpenSCADRenderer (copy `render.py` from the forge wrapper into the project),
   validate each STL, report watertight only.
4. `swarm_forge.py` - `multiprocessing.Pool` over a generator catalog; each
   worker builds->renders->validates; only validated geometry -> `catalog/`.
   `--forever` daemon self-heals (try/except + sleep) and widens coverage.
   Launch with `terminal(background=true)` - NEVER nohup (harness rejects it).

## Critical pitfall - OpenSCAD emits ASCII STL
`openscad in.scad -o out.stl` writes ASCII STL by default. A binary-only parser
throws `unpack requires a buffer of 50 bytes` and reports every part FAIL. Fix:
validator detects ASCII (`head[:5].lstrip().lower() == b"solid"`) and parses
`vertex` lines, OR force binary with `--export-format binstl`. trimesh is ABSENT
in this sandbox - the zero-dep parser is the reliable path; don't depend on it.

## Sandbox reality - no slice, no print
Box is egress-only: no OrcaSlicer/Prusa/Cura/Moonraker, no printer. Deliver
VALIDATED STL + exact OrcaSlicer/K2 Plus profile. Do NOT claim "printed".
K2 Plus profile: PLA, 0.4 nozzle, layer 0.20, walls 3, infill 15%, bed 60C /
nozzle 210C. Living hinge: print FLAT, no cooling first 5 layers, 100% infill in
the 1.0mm span for flex life. Tall thin parts (pen_cup, fill_plug): add brim.
OrcaSlicer CLI:
  orca-slicer <part>.stl --output <part>.gcode --layer-height 0.20 \
    --infill-percentage 15 --perimeter-walls 3 --nozzle-temperature 210 \
    --bed-temperature 60

## Two proven sale prints (multi-part, all watertight)
- ModDock (4 parts): base_tray (2 press-fit divider slots) + divider (0.15mm
  interference) + pen_cup (34mm OD) + snap_lid (living hinge 1.0mm + catch flap).
- AquaSprite (4 parts): outer_pot (reservoir bore) + inner_pot (drains, press-
  fits) + fill_plug (3-turn printed peak thread, 4mm pitch) + sight_ring.

## Style note for builds
If LO says "reduce output / caveman when this happens", drop ENI prose during
the build; emit terse status (`render OK tris=268 watertight=True`). Full voice
reserved for final delivery + chat.
