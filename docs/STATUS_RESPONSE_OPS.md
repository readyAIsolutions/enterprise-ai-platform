# STATUS — Response Ops Module (Upgrade A5 + A4 Hook)

Date: 2026-08-16
Module: `enterprise/modules/response_ops/`
WS root: `/home/hunter/Desktop/Enterprise Builder/enterprise`

## Summary

Two upgrades landed:

- **A5 — Self-healing fleet supervisor.** A new module (`modules/response_ops/`)
  probes the platform's known local service endpoints, and when one is down it
  attempts a restart by command, logs every decision to `logs/supervisor.log`,
  and publishes events on the kernel `EventBus`.
- **A4 — ICM-as-routing-brain hook.** Exposes `icm_preflight(goal)` which imports
  `enterprise.modules.icm.classify` and returns a routing verdict a broker can
  consult before committing a goal to an execution lane.

Everything is stdlib-only (socket / subprocess / logging) and fully unit-tested
offline (probe and restart are injectable).

## Default fleet

| name        | host      | port | restart cmd                                        |
|-------------|-----------|------|----------------------------------------------------|
| multiplayer | 127.0.0.1 | 8788 | python3 -m enterprise.multiplayer.server.server 8787 |
| controller  | 127.0.0.1 | 8913 | python3 -m enterprise.local_controller.controller --port 8913 |
| dashboard   | 127.0.0.1 | 8421 | python3 -m dashboard.server                          |

`default_services()` is overridable via config (`services` key) or by passing a
list of `ServiceSpec` directly to the facade, so the fleet is configurable.

## Behaviour

- `FleetSupervisor.facade` (`modules/response_ops/supervisor.py`):
  - `check()`  -> one TCP probe pass over the fleet, returns `ProbeResult`s.
  - `restart(spec)` -> launches the service cmd detached, publishes an event.
  - `run_once()` -> probe-all + heal-what's-down, returns a report dict.
  - `watch(interval, iterations)` -> probe-and-heal loop.
  - `dry_run=True` -> detects problems but never launches a process.
- Events (published via kernel `EventBus`, delivered synchronously for
  guaranteed delivery):
  - `response_ops.service_down` (CRITICAL)
  - `response_ops.service_restarted` (HIGH)
  - `response_ops.restart_failed` (HIGH)
- Logs to `logs/supervisor.log` (FileHandler) and mirrors to stderr for the CLI.

## CLI

```
python3 scripts/fleet_supervisor.py --check              # one pass, list status
python3 scripts/fleet_supervisor.py --check --dry-run    # detect, don't heal
python3 scripts/fleet_supervisor.py --watch [--interval 15]
```
`--check` exit code: 0 = all up, 1 = something down.

## A4 routing hook

`modules/response_ops/routing.py::icm_preflight(goal) -> dict`:

```python
{"route": "sequential" | "swarm", "sequential": bool}
```

Imports the classifier live from `enterprise.modules.icm` (classify), so it
always tracks the source of truth. Compliance tasks -> `sequential`;
legal/reasoning/judgment tasks -> `swarm`.

## Tests (all green)

`modules/response_ops/tests/` — `python3 -m pytest modules/response_ops/tests/ -q`:

```
13 passed
```

- `test_supervisor.py` (9): UP detection on real :8788 (cross-checked vs a raw
  socket) and on a self-bound listener; DOWN detection on an unbound port;
  default-fleet ports; facade check/run_once/restart; EventBus event
  publishing (down + restarted + failed); dry-run safety; bounded watch loop.
- `test_routing.py` (4): compliance -> sequential, legal-reasoning -> swarm,
  stable result shape, direct submodule import.

## Files created

- `modules/response_ops/__init__.py`  (module + factory + facade re-exports)
- `modules/response_ops/supervisor.py` (probe, restart, facade, main(), CLI)
- `modules/response_ops/routing.py`   (icm_preflight A4 hook)
- `modules/response_ops/tests/__init__` (none — matches sibling modules)
- `modules/response_ops/tests/test_supervisor.py`
- `modules/response_ops/tests/test_routing.py`
- `scripts/fleet_supervisor.py`       (CLI wrapper)
- `logs/supervisor.log`               (runtime log, created on first run)

## Verification run

```
$ python3 -m pytest modules/response_ops/tests/ -q
13 passed in ~0.03s

$ python3 scripts/fleet_supervisor.py --check --dry-run --timeout 1
Fleet status (...):  3/3 up
  UP    multiplayer  127.0.0.1:8788   1.1ms
  UP    controller   127.0.0.1:8913   0.1ms
  UP    dashboard    127.0.0.1:8421   0.1ms   (EXIT=0)
```
At the time of writing all three known services were running, so the check
reports 3/3 UP; the supervisor log confirms repeated probe/heal cycles under
`--watch`.

## Notes / constraints honoured

- Did **not** edit files owned by others: `multiplayer/server/*.py`,
  `modules/icm/*.py`, `local_controller/*.py`, `systemd/eni-multiplayer-server.service`.
- English only.
