# Fleet analytics chain — composition, seams, and test anchors (D3D07)

Condensed companion to the `## Fleet capacity estimator` section of SKILL.md.
Read this before building any ADD-ONLY module in the `fleet_snapshot → fleet_trends
→ fleet_health → fleet_capacity` chain.

## The 4-stage ADD-ONLY chain (all stdlib-only, read-only, never touch a printer)
1. `fleet_snapshot.py` (`demiurge/printer/`) — `SnapshotStore` (rolling on-disk
   history) + `diff_snapshots(prev, cur)`. Producer.
2. `fleet_trends.py` (`demiurge/printer/`) — `analyze_history(snapshots)` →
   per-printer latency-creep / connectivity-flap / temp-drift / print-state
   instability + a **0–100 health score** per printer + fleet-average +
   `ranked_alerts`. The **health map** source.
3. `fleet_health.py` (`demiurge/webapp/`) — `mount_fleet_health(app)` FastAPI panel
   (`/api/fleet/health`). Wires trends into the dashboard.
4. `fleet_capacity.py` (`forge/`) — `plan_capacity(...)` stateless what-if
   estimator. Consumer that turns the health map + a `queue_planner` batch into a
   completion estimate. It is the *planning input* a scheduler consumes, NOT a
   competitor to `demiurge/printing/queue_scheduler.py` (which is a stateful live
   dispatch engine — see the COLLISION AVOIDED note in SKILL.md).

## Data seams (the contracts to build against — read, never mutate)
- **QueuePlan** (`forge/queue_planner.py`):
  - `.dispatch` (ordered `PlannedJob` list), `.review`, `.blocked`, `.errors`.
  - `.totals['estimated_time_min']`, `.totals['mass_g']`, `.totals['cost']`.
  - `PlannedJob` carries name/minutes/optional mass/filament — read the attributes,
    do not mutate the plan.
- **Printer capacity snapshot** (fleet_state / fleet_snapshot tile):
  - `slots` (parallel lanes; K2 Plus = 1), `busy_min` (time left on current job),
    `available` (bool), `health_score` (0–100).
- **Health map**: `{printer_name: 0..100}`, e.g. from
  `fleet_trends.analyze_history().printers`. The D3D07 cohesion seam: a printer
  below `min_health` is dropped from eligible lanes.

## plan_capacity model (LPT greedy list-scheduling)
- Each printer = `slots` parallel lanes.
- Sort jobs DESC by minutes; assign each to the lane that frees earliest.
- `make_span = max(lane_load)`; `ideal_min = total_work_min / total_slots`.
- `utilization = total_work / (make_span * total_slots)`;
  `parallelism_efficiency = ideal / make_span`.
- `busy_min` shifts that printer's clock forward (head-start delay).
- `ETA = now + make_span * 60` (only when `now` is given).
- Classic list-scheduling heuristic, proven (4/3)-approx to optimal make-span.

## Known-OPTIMAL test anchors (prove the heuristic — don't just assert a number)
Use textbook instances whose optimal make-span is known, so a wrong scheduler
returns a worse number and the test fails:
- **3 lanes**, jobs `[9,7,6,5,3,2,1]` → LPT make-span **11**, util 27/27 = 100%.
  (This is the canonical LPT-optimal instance; returning >11 means the scheduler
  is wrong.)
- **2 lanes** `[5,5,4,4,3,3,3]` → make-span **15**, util 27/30.
- `slots=2`: three 10-min jobs → **20** (not 30) — proves lane parallelism.
- `health=0` printer → all work reroutes to the healthy one (make-span = sum of
  the batch).
- `busy_min=100` → make-span = `100 + clean_make_span`.
- All printers ineligible → `unassigned` non-empty, make-span 0.

## Gotchas
- **Falsy-zero `or` default** (see SKILL.md pitfall): `health_score=0.0` MUST stay 0,
  not become 100. Test it explicitly.
- **Read-only guarantee**: `fleet_capacity` imports ONLY `forge.queue_planner` +
  stdlib. Assert via an AST import scan that no `moonraker`/`httpx`/`requests`/
  `urllib`/`socket`/`telnetlib`/`subprocess`/`paramiko`/`asyncssh`/`websockets`
  module is imported, AND that a fresh `importlib.import_module` does not load any
  `printer`/`moonraker` module (`set(sys.modules)` diff before/after).
- `plan_capacity_from_plan` excludes BLOCKED/errored jobs (uses `.dispatch` +
  `.review` only).
- CLI end-to-end: `python -m forge.fleet_capacity --plan qp.json --printers p.json
  --health h.json --now T --policy lpt|spt|input --json` — run it as a subprocess
  in the test with `PYTHONPATH=<backend dir>` so `forge` is importable.
