# DORMANT-fleet verdict runbook (cron mode)

Proven sequence for producing a clean fleet-status report when the floor is parked.
This is the path that yielded the correct verdict in the Aug 2026 cron runs.

## Canonical step order
1. `cd /home/hunter/Commander/eni_swarm && python3 monitor_fleet.py`
   - exit 0 only means the *ledger* regenerated — NOT that the fleet is live.
2. `bash ~/.hermes/skills/devops/eni-swarm-telemetry/scripts/fleet_liveness_probe.sh /home/hunter/Commander/eni_swarm`
   - This is the AUTHORITATIVE liveness cross-check. Do NOT trust the ledger alone.
3. Read the probe's `fresh_today` / `fresh_last24h` + `newest 5 mtimes` + `live builder processes`
   sections. Those three determine DORMANT vs PARTIALLY-LIVE vs LIVE, not the ledger counts.
4. Report per `templates/fleet-cron-report.md`.

## Reading the verdict from the probe
- `fresh_today=0` AND `fresh_last24h=0` AND `live builder processes: NONE` → **DORMANT / PARKED**.
- The 8-9 `IN-PROGRESS`/`BLOCKED` ledger rows are stale artifacts of the previous run (~weeks old
  mtimes), NOT live work. Do not mistake them for an actively stalling fleet.
- Value is confirmed by the freshest STATUS file — e.g. a header `# STATUS_BUILDER_37 — IDLE — <ts>`
  paired with `Control FIFO ... does not exist` + `blocker=none` + `next=await LO's directive` is the
  canonical **park marker**: healthy/parked-by-design, waiting on LO, not a crash and not a stall.

## ⚠️ ENI compression wrapper vs. skill files
Reading this skill's own files (SKILL.md, `templates/*`, `references/*`) via `read_file`/`cat` may
return `ENI-COMPRESSED` carrier output (a decompress wrapper is active in this profile), which hides
the middle of the file and makes the template hard to reconstruct. Workarounds in order of preference:
- **Just run `fleet_liveness_probe.sh` directly** — its output is plain text and NOT wrapped; it is
  the source of truth and gives you the report facts you need without reading the template at all.
- `sed -n 'A,Bp' <file> > /tmp/x.txt` then read that — may still be wrapped; do not rely on it.
- The probe's plain output + the state-distribution table are enough to write the report even if the
  template body stays compressed.

## Report semantics (do not suppress)
Per `eni-swarm-telemetry` protocol: a fleet monitor run must NEVER `[SILENT]`. A DORMANT fleet is STILL
a report to send — "nothing new" (floor parked/healthy) is itself the finding and the whole deliverable.
Only `[SILENT]` if the monitor itself did not run or the job isn't the fleet monitor.