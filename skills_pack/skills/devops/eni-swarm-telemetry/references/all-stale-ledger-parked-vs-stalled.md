# Interpreting an ALL-STALE ledger: "parked fleet" vs "stalled mid-task"

## The trap
`monitor_fleet.py` (and the heartbeat heartbeat) parse on-disk `STATUS_BUILDER_*.md`
into `HEARTBEAT_LEDGER.md`. Those files are written by the builders themselves — they
are **NOT live**. If the last build run ended and nobody texted the builders back, every
STATUS file keeps its old timestamp AND its old IN-PROGRESS/DONE/BLOCKED tag.

Observed (2026-08-15): 50 STATUS files, 39 DONE / 10 IN-PROGRESS / 1 BLOCKED —
but **every file was dated Jul 25 (~21 days old)** and **no builder process was running**
and **no build log was newer than Aug 7**. The "10 IN-PROGRESS" tags were stale snapshots,
not active work. Reporting "10 builders in progress / 1 blocked" as live status is wrong.

## The rule
Never trust the ledger's state tags alone. They only mean "what the file said last time
it was written." Before claiming builders are working or stalled, verify liveness:

## Live-signal cross-check (do these, in this order)
```bash
# 1. Builder / swarm processes actually running?
ps -eo pid,etimes,cmd | grep -iE 'hermes|builder|swarm' | grep -v grep
#    (NOTE: use -eo etimes, not -o with output clash — 'ps -o pid,etime,cmd' can
#     throw "conflicting format options" on some systems. -eo is safe.)

# 2. Control FIFOs present? Only live builders keep one.
ls -la /tmp/eni_ctl_BUILDER_* 2>/dev/null   # a fresh mtime here = active attention

# 3. Build/log mtimes — recently written logs mean real activity.
ls -lat /tmp/*eni*.log /tmp/demiurge_freed_swarm_logs/*.log 2>/dev/null | head
find /tmp -name '*.log' -newermt '<2 days ago>' 2>/dev/null

# 4. Wall-clock sanity.
date --iso-8601=seconds
```

## Classification
- **All STATUS files old AND no builder procs AND no fresh FIFOs/logs → fleet is PARKED.**
  Ledger tags are stale. No recovery needed; no "stall" alarm. Just report the fleet is
  idle/awaiting dispatch.
- **Some builders actively running (procs alive) OR fresh log/FIFO writes → fleet is LIVE;**
  a stale-STATUS-file builder that is actually running = the fresh-mtime trap (see
  `fresh-mtime-vs-liveness-probe-location.md`).
- **Builder procs running but a specific builder's STATUS is stale and it has no proc /
  no fresh FIFO → that one may be genuinely STALLED.** Investigate individually.

## Reporting
When the ledger is all-stale and the fleet is parked, say so explicitly and give the
evidence (file dates + zero procs + stale logs). Call out the one real actionable item
(e.g. a BLOCKED builder awaiting dispatch) rather than re-listing stale IN-PROGRESS tags
as if they were live work.