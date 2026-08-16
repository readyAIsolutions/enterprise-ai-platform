# Cron fleet-heartbeat run — step-by-step (verified end-to-end Aug 10 2026)

This is the canonical path a scheduled cron job follows to produce the fleet heartbeat
report. `monitor_fleet.py` itself is tiny and deterministic; the value is in the
liveness cross-check and the report framing.

## Steps that worked
1. `cd /home/hunter/Commander/eni_swarm && python3 monitor_fleet.py`
   - Regenerates `HEARTBEAT_LEDGER.md` from `builds/STATUS_BUILDER_*.md`.
   - **Exit 0 = aggregation ran, NOT liveness.** Never report from the ledger alone.
2. Read the freshest status files for all non-DONE builders:
   `for n in 5 17 25 ...; do cat builds/STATUS_BUILDER_$n.md; done`
   They almost always self-describe as parked/IDLE or a stale Jul-date IN-PROGRESS relic.
3. Run the liveness probe (authoritative freshness + procs + FIFOs):
   `bash <PROBE> /home/hunter/Commander/eni_swarm`
   Key outputs to cite: `DISK_STATUS_FILES`, `fresh_today` (vs total), `newest 5 mtimes`,
   `live builder processes`, `control FIFOs`, plus head of the freshest status file.

## Path pitfall — the probe script is NOT at the canonical skill path
`~/.hermes/skills/eni-swarm-telemetry/scripts/fleet_liveness_probe.sh` does NOT exist.
The real on-disk location is a subcategory deeper:
`/home/hunter/.hermes/skills/devops/eni-swarm-telemetry/scripts/fleet_liveness_probe.sh`.
Also, `skill_view` on this skill returns **ENI-COMPRESSED** content, so you cannot reliably
read the scripts through skill_view. When you need shell access to the scripts, locate
them first:
`find / -name "fleet_liveness_probe.sh" 2>/dev/null | head -3`
(or use the known `devops/` path above). Don't guess the canonical path and waste a call.

## Reporting framing that works
- State distribution: `grep -oP '^\[\K[A-Z-]+' HEARTBEAT_LEDGER.md | sort | uniq -c`
  but immediately qualify: `[DONE]` = "not BLOCKED, not IN-PROGRESS" per runbook, and the
  8 IN-PROGRESS / 1 BLOCKED rows are *stale relics* (16-day-old mtimes), not live work.
- The decisive signal is **freshness**: when only 1 of 50 status files is touched today
  and zero builder processes run, the verdict is "fleet dormant/parked" regardless of
  what the ledger's state column says. This is encore-dormancy, NOT a stall wave.
- A builder's status file that explicitly says `IDLE` + "do not invent work" and a missing
  control FIFO means: no directive issued, goal string is a scheduling template not an
  assignment. Do not invent work for it.
- Verdict line: "No action required — ledger regenerated, fleet parked awaiting LO
  directives." Resumption requires an explicit FIFO/directive dispatch to a builder.
