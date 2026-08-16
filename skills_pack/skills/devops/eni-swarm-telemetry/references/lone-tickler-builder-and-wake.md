# Lone "tickler" builder trap + waking a parked builder

Observed in a cron fleet-monitor run (Aug 10 2026): the ledger showed several
[IN-PROGRESS], one [BLOCKED], and most [DONE], plus ONE builder with a
TODAY-dated STATUS mtime — which could be mistaken for "the fleet is alive."

Cross-checking every OTHER signal resolved it as **full dormancy**:
- builder procs (`ps aux | grep -iE 'eni_builder|BUILDER_|hermes.*builder'`) = **0**
- control FIFOs in `/tmp` (`ls /tmp/eni_ctl_BUILDER*`) = **1** (only BUILDER_50)
- STATUS mtime spread by day =
  `ls --time-style='+%Y-%m-%d' -l STATUS_BUILDER_*.md | awk '{print $6}' | sort | uniq -c`
  → 49 × stale-date, 1 × today

## The trap
A single builder (here BUILDER_37) rewrites its STATUS file every-so-often as an
**IDLE** heartbeat (`# STATUS_BUILDER_37 — IDLE — <now>`). Its recent mtime makes
it look active, but it is a *tickler* — just confirming it exists, not doing work.
A lone fresh mtime ≠ fleet alive. Always stack ALL signals (procs + FIFOs +
mtime-spread) before reporting "builders are working." One healthy-looker among a
50-wide stale spread is the rule, not activity.

## Recovery: wake a parked IDLE builder
An IDLE builder's STATUS typically reads:
`blocker=none` / `next=await LO's directive via /tmp/eni_ctl_BUILDER_N` — and the
control FIFO does NOT exist (`ls /tmp/eni_ctl_BUILDER_N` → no entry) even though
other builders' FIFOs (e.g. BUILDER_50) are present. The builder is parked waiting
for dispatch. To wake it:
```
mkfifo /tmp/eni_ctl_BUILDER_N
# then write a directive to that FIFO
```
That is the standard un-park step; no rebuild/restart needed if the builder proc
survives (verify the proc is alive first — if procs=0, re-spawn instead).

## 0-byte STATUS guard
A STATUS_BUILDER_N.md of size 0 is a crash artifact — `monitor_fleet.py` skips it
(via the crash guard), so it legitimately won't appear in the ledger. Expect a gap
in builder numbering when one exists; don't read it as a "missing" builder.
