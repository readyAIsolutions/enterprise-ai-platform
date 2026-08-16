# Fleet snapshot run-recipe (cron / heartbeat)

Reusable command sequence to produce a complete fleet-status snapshot fast, verified working 2026-08.

## Commands (run from `/home/hunter/Commander/eni_swarm/`)
```bash
python3 monitor_fleet.py                     # regenerate HEARTBEAT_LEDGER.md from STATUS_BUILDER_*.md
cat HEARTBEAT_LEDGER.md                      # builder floor one-liners
grep -oP '^\[[A-Z-]+\]' HEARTBEAT_LEDGER.md | sort | uniq -c   # DONE/IN-PROGRESS/BLOCKED counts
cat MASTER_STATUS.md                         # status-hub master: minis DONE/IN/BLOCKED + ALERTS + mtimes
bash fleet_health_probe.sh                   # 4-axis probe -> the verdict line (health checks per axis)
```

The workspace ships its own `fleet_health_probe.sh` — PREFER it over hand-rolling
curls. It prints sections AXIS 1 (builder floor ledger) / AXIS 2 (dashboard :8420) /
AXIS 3 (turbocharger :8922) / AXIS 4 (controller / status hub) and appends an
interpretation line.

## CRITICAL: mapping the verdict (misreading this = false "fleet is down" alarm)
The probe's final pulse looks like:
```
[hh:mm:ss] ENI PULSE | windows=0 | stalls: none | gate=RED
Interpretation: gate=RED + windows=0 + stalls=none + empty queue == IDLE/dormant, NOT down.
```
- **gate=RED + windows=0 + stalls=none + empty queue  -> DORMANT/IDLE (parked), healthy.**
  This is the NORMAL resting state of a parked floor, NOT a failure. Report as
  DORMANT and say what would wake it (directive touch, PRODUCT_LEAD dispatch,
  creating a `/tmp/eni_ctl_BUILDER_N` FIFO).
- green gate / live windows / running procs -> LIVE.
- A `stalls: <n>` or a genuinely fresh STATUS file that is IN-PROGRESS/BLOCKED is
  the real problem signal — a hang, not a park.

## Reading MASTER_STATUS ALERTS
- `MASTER_STATUS.md` lists hundreds of ALERTS. On a parked fleet these are ALMOST ALL
  stale-age-driven: every ENI/DEMIURGE STATUS file's mtime is weeks old, so any
  IN-PROGRESS item trips the `>10min` stall rule. High ALERT count on a parked
  fleet is the *signature* of dormancy, not an active incident.
- The 3 "blocked" minis are likewise long-dormant (eni9_w3, gate.md, etc.), not
  live blockers.
- DONE minis are terminal; their age is informational and does NOT raise an alert.

## Pitfalls
- Blank/empty `STATUS_BUILDER_*.md` files are crash guards — skip them (the
  monitor's blank-file guard does). A row of `verified=unknown` placeholders across
  the ledger is NORMAL for a parked floor (47/50 in the observed run), not data loss.
- Freshness only upgrades/downgrades the verdict WORD (DORMANT -> PARTIALLY LIVE ->
  LIVE). It never makes a fleet-monitor run skippable.