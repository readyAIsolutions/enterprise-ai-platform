# Swarm ADD-ONLY sub-module build — technique bank (D3D09 cycle, 2026-07-11)

Condensed from building `backend/forge/preflight.py` (G-code pre-flight analyzer:
real-extrusion material/cost/printer-fit report) as unclaimed mini-builder D3D09.

## The shape that works
- Pick a **NEW consumer** of a stable existing read-path module. D3D09 used
  `forge.gcodeparser` (parses .gcode → moves/layers/bounds/stats, stops at
  `total_extrusion_mm`) and added the missing layer: turn real E-advance into
  filament volume/mass/cost + a printer-FIT check + a dashboard-ready JSON report.
- Do NOT re-implement the read-path and do NOT edit it. `preflight.py` imports
  only `from . import gcodeparser as _gp` — zero printer/network imports.
- Avoid name collisions: `estimator.py` and `hueforge/cost_estimator.py` already
  existed (they guess cost from model-volume×infill). `preflight` is distinct
  (uses the real bead cross-section from E). Always `search_files` a name before
  building it.

## How to confirm a module is unclaimed
1. `search_files(pattern="STATUS_*.md", output_mode="content", ...)` for
   `Owner:` / `builder:` / `Module:` → who claims what.
2. Read `STATUS_DEMIURGE3D_PRODUCTLEAD*` — it lists RED/unclaimed sub-tasks
   (B13 gcodeslice, B14 integrity, B16 parts_library …). Those are buildable IF
   the file isn't already on disk.
3. `search_files(pattern="<name>.py")` + `read_file` the candidate to be sure it
   doesn't already exist with different content (a sibling may have built it).

## G-code sample generators (for tests)
Two shapes — use the right one:

Exact-mass (no bounds needed):
```python
def _single_extrude(E, feed=600.0):
    return "\n".join([
        "G21","G90","M83","M104 S210","M140 S60","G28",
        f"G1 Z0.2 F{feed}",
        f"G1 E{E:.4f} F{feed}",   # M83 => this ADDS E mm of extrusion
        "M30",
    ])
```
Realistic bounds/fit (MUST trace a perimeter so the parser sees a real box):
```python
def _perimeter(x, y, z, per_edge=1.0, feed=600.0):
    return "\n".join([
        "G21","G90","M83","M104 S210","M140 S60","G28",
        f"G1 Z0.2 F{feed}",
        "G1 X0 Y0 F{feed}",
        f"G1 X{x} Y0 E{per_edge:.4f} F{feed}",
        f"G1 X{x} Y{y} E{per_edge:.4f} F{feed}",
        f"G1 X0 Y{y} E{per_edge:.4f} F{feed}",
        f"G1 X0 Y0 E{per_edge:.4f} F{feed}",
        f"G1 Z{z} F{feed}",
        "M30",
    ])
```
Note: with `M83` (relative E) each edge adds `per_edge` mm → `extrusion_mm =
4*per_edge`. With `M82` (absolute, default) E is CUMULATIVE — a repeated `E1`
advances only once, so don't use repeated absolute E to simulate length.

## Material math (verify it's wired, not faked)
```
area_mm2 = pi * (diameter_mm/2)^2
volume_mm3 = extrusion_mm * area_mm2
volume_cm3 = volume_mm3 / 1000
mass_g    = volume_cm3 * density_g_cm3          # PLA 1.24, PETG 1.27, TPU 1.21
cost_usd  = (mass_g/1000) * price_per_kg_usd    # PLA 22, PETG 25, TPU 35
```
In the test, recompute `exp_*` from these constants and assert
`abs(rep.mass_g - exp_mass) < 1e-9` — proves the pipeline is real, not hardcoded.

## Read-only guarantee test (safety-model critical)
```python
_BANNED = ("moonraker","httpx","requests","urllib","socket","telnetlib")
src = Path("forge/preflight.py").read_text()
for line in src.splitlines():
    s = line.strip()
    if not (s.startswith("import ") or s.startswith("from ")):
        continue
    assert not any(tok in s.lower() for tok in _BANNED), f"banned import: {s!r}"
# AND: a fresh import must not load printer/moonraker modules
import importlib, sys as _s
before = set(_s.modules)
importlib.import_module("forge.preflight")
loaded = set(_s.modules) - before
assert not any("printer" in m or "moonraker" in m for m in loaded)
```
Also assert the source .gcode file is byte-identical (sha256 + mtime) after
`analyze_file` — proves the module never writes to the part.

## Live READ-ONLY Moonraker route scan (boot-smoke, NO gcode)
Run `bash scripts/read_only_moonraker_probe.sh` (or the curl recipe inline).
GET only — never sends motion/heat. This cycle the two K2 Plus were reachable:
- `GET /printer/info` → `state` ("ready"/"paused"/"complete"), `hostname`.
- `GET /printer/objects/query?heater_bed&extruder&print_stats&toolhead` →
  bed/extruder `temperature` + `target`, `print_stats.state`, and crucially
  `toolhead.axis_maximum` = the REAL build envelope.
- `GET /server/info` → firmware/host confirm.

Real finding (2026-07-11): both K2 Plus report `axis_maximum ≈ [352.5, 352.0,
360.0]` and a 0.6 mm nozzle → build volume ≈ 352×352×360 mm. A static 350³
default is correctly conservative. One printer (`.65`) was mid-`paused` with a
245 °C hot nozzle — confirms read-only-only is mandatory; never send gcode.
(IPs/hostnames are volatile — re-probe live; do not hardcode in logic.)

## STATUS_D3D09.md deliverable (already covered in SKILL.md ENI section)
Line 1 `[state: DONE]`; PASS/FAIL board with REAL numbers (test counts, CLI
smoke output, the live route-scan table); `what adds R / what to drop`; an
`UNVALIDATED` section (live cost vs spool sensor, real slicer .gcode field
shape, the hot-nozzle printer left untouched). D3D09: 18/18 pytest passed,
AST clean, CLI rc=0/rc=2 both proven.

## Async test-harness pitfalls (Python 3.14, DEMIURGE3D backend) — D3D03 cycle
The backend is async (httpx, Moonraker clients, `asyncio.gather`). Offline
self-tests drive a fake async client; three non-obvious traps surfaced building
`demiurge/printer/route_scanner.py`:

### 1. `asyncio.gather(...)` as an arg to `asyncio.run()` → "no current event loop"
In 3.14, `asyncio.run(main())` creates the loop INSIDE run(). Writing
`asyncio.run(asyncio.gather(coro_a(), coro_b()))` evaluates `gather` in the
caller's thread BEFORE any loop exists →
`RuntimeError: There is no current event loop in thread 'MainThread'`.
FIX — wrap in an inner coroutine:
```python
async def _run():
    return await asyncio.gather(
        scan_printer("a", ..., client=fa),
        scan_printer("b", ..., client=fb),
    )
scans = asyncio.run(_run())
```

### 2. Fake async client must key routes by (path, params), not path alone
Two read-only routes can share a PATH with DIFFERENT query params (e.g.
`/printer/objects/query` once with `extruder&heater_bed&print_stats&toolhead`
and once with just `job_queue`). A fake keyed only by path returns the SAME
canned response for both → wrong classification. Key by the param set:
```python
def _key(path, params):
    return (path, frozenset((params or {}).items()))
# store/lookup responses under _key; default 404 if unmapped.
```
And in the fixture pass a DICT for params (not a frozenset) — the scanner
always passes a dict; a `frozenset({...}.items())` fixture value trips
`.items()` on a frozenset (`AttributeError`).

### 3. Enforce read-only at RUNTIME, not only in an import-line test
An import-line/substring scan proves the module doesn't import network libs
TODAY, but won't stop a future edit from adding a mutating POST. For any
printer/Moonraker scanner, make the route registry a FROZEN constant of
`RouteSpec(method="GET")` and add a runtime guard at the top of the scan fn:
```python
for r in routes:
    assert r.method == "GET", f"route {r.name!r} is not GET — scanner is read-only"
```
This fails fast (AssertionError) if anyone ever adds a POST route — the safety
property is now enforced in code, not just asserted in a test.

### 4. Opt-in live test (prove the live path without breaking headless CI)
The live read-only scan hits real printers (safe — GET only) but must not run in
headless CI. Gate it on an env var:
```python
@pytest.mark.skipif(os.environ.get("DEMIURGE_LIVE_SCAN") != "1",
                    reason="live scan opt-in (set DEMIURGE_LIVE_SCAN=1)")
def test_live_scan_real_k2plus_readonly():
    fleet = asyncio.run(scan_fleet(build_default_endpoints(), timeout=5.0))
    assert fleet.count == 2
    assert all(r.path != "/printer/gcode/script"
               for p in fleet.printers for r in p.routes)
```
Run with `DEMIURGE_LIVE_SCAN=1 pytest ...` to actually verify against the two
K2 Plus units. D3D03 verified both HEALTHY (klippy "ready", 14/14 routes 200).
