# Two Monitor Layers + Distinguishing "Monitoring Down" from "Fleet Dormant"

The ENI swarm is watched by TWO independent, separately-scheduled monitors.
When asked to report fleet health, know which one produced the data, and
fetch BOTH before concluding anything — a healthy monitor layer on top of a
stalled build floor is a common and misreadable state.

## Layer A — `monitor_fleet.py`  →  writes `HEARTBEAT_LEDGER.md`
- Reads `builds/STATUS_BUILDER_*.md` (a status file per builder), parses each
  file's state token, and writes a one-line-per-builder ledger:
  `[DONE|IN-PROGRESS|BLOCKED] BUILDER_N verified=... blocker=... next=...`.
- Also honours `HEARTBEAT_ALERTS.md`: builder numbers matched by the regex
  `- BUILDER_(\d+)` in that alerts file are FORCED to BLOCKED in the ledger.
- This is the parallel-build floor ledger specifically.

## Watch B — `status_hub.py`  →  writes `MASTER_STATUS.md`
- A separate aggregator (runs as worker w2), consolidates `STATUS_ENI*.md` in
  `eni_swarm/` PLUS recursive `STATUS_*` files under each live project
  (demiurge_scaffold etc.). Produces the consolidated ALERTS list.
- Its staleness rule is explicit in the file header: ALERT when STATE==BLOCKED,
  OR (STATE != DONE AND FILE-AGE > 10 min). DONE minis never alert on age.
- Output is also mirrored to `status_hub.cron.log` (lines like
  "MASTER_STATUS.md refreshed: 77 minis (57 done / 18 in-progress / 2 blocked)").

## Diagnosing "infra healthy but fleet DORMANT" (the common trap)
A cron run that completes cleanly and regenerates the ledger only proves the
MONITOR is alive. It says nothing about whether builders are working. To tell
"monitoring broke" from "the work stalled", check all of:

1. **Process truth (`pgrep`)**: is any builder/mini worker actually running?
   Grep `python.*hermes`, `builder`, `swarm`, `demiurge`. A gap of days with
   no worker process = no one driving the floor, regardless of what the ledger
   says. (Infra daemons like `swarm_turbocharger.py`, `eni_controller`,
   `eni_kb_daemon` running does NOT mean builders are active — they are infra,
   not workers.)
2. **STATUS-file mtimes**: 49/50 files older than 48h + a healthy monitor =
   the FLOOR stalled, not the monitor. Distinguish a few-stale (partial) from
   all-stale (dormant).
3. **`/tmp/eni_ctl_*` FIFO presence vs. liveness**: FIFOs exist means channels
   were created; a builder reporting "ctl FIFO does not exist (re-verified
   empirically via cron watchdog)" is IDLE, not blocked — a benign
   waiting-for-directive state.
4. **Stalled-task backlog**: consolidated alerts flagging dozens of IN-PROGRESS
   tasks quiet for 30-50 days all dates-grouped (Jul 10–13) = work abandoned
   mid-run, needs a human decision (resurrect vs mark terminal), not a fix.

## Report shape that worked
Give the ordering/number summary FIRST (38 DONE / 9 IN-PROGRESS / 1 BLOCKED /
1 missing = the eye-catcher), then separate "monitor infra status" from "work
progress status", then the concrete action for LO (re-run `status_hub.py` to
self-heal, decide on resurrecting mid-build stale builders, distinguish
waiting-for-directive IDLE from stalled).