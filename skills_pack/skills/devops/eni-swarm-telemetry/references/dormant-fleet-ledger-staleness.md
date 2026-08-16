# Dormant-Fleet Ledger Staleness Trap

## Symptom
After the ENI fleet has parked (no builders running, no directives issued), every
`monitor_fleet.py` run regenerates `HEARTBEAT_LEDGER.md` with the SAME stale rows:

```
[IN-PROGRESS] BUILDER_5  verified=unknown ...
[BLOCKED]     BUILDER_46 verified=unknown ...
```

This is NOT live work. The ledger reflects the last state written to each
`builds/STATUS_BUILDER_*.md` file — which is frozen at the moment the builder
last ran (often weeks earlier). The non-DONE rows therefore read as active
IN-PROGRESS/BLOCKED work forever, even with zero processes running and zero
fresh files.

## Root cause
`monitor_fleet.py` maps state from the status files' contents/markers and has no
timestamp awareness. It aggregates DONE|IN-PROGRESS|BLOCKED faithfully, but
"faithful to a stale file" is not "live". Exit 0 from monitor_fleet.py means
ONLY that aggregation ran — not that the fleet is alive.

## Proven triage (already encoded in fleet_liveness_probe.sh)
Never report fleet status from the ledger alone. Always run, after regenerating
the ledger:

```
cd /home/hunter/Commander/eni_swarm
bash ~/.hermes/skills/devops/eni-swarm-telemetry/scripts/fleet_liveness_probe.sh /home/hunter/Commander/eni_swarm
```

The decisive signals, in order:
1. `fresh_last24h=N` — if 0, nothing has written this cycle. Fleet is not building.
2. `live builder processes` = NONE — strongest liveness signal.
3. `newest 5 mtimes` — shows how long non-DONE rows have been parked.

## Reporting rule
When `fresh_last24h=0` AND no builder processes are running:
- Label every non-DONE ledger row as **"parked/IDLE since <mtime>"**, NOT live work.
- State the fleet verdict plainly: **dormant / awaiting LO directive**.
- Do not invent a stall. A parked fleet is the expected resting state between
  directives.

## Optional hardening (offered, not yet implemented)
Annotate the ledger with each non-DONE row's actual last-touch date, e.g.
`[IN-PROGRESS (parked 2026-07-25)] BUILDER_5`. This makes the heartbeat read
"parked ×days ago" instead of resembling live work. Implement by having
`monitor_fleet.py` emit `mtime=<ts>` per row (already available from the
glob-stat it does).