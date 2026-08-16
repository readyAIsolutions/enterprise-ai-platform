# monitor_fleet.py — ledger pipeline & the "healthy pipeline ≠ live fleet" trap

## What this is
`/home/hunter/Commander/eni_swarm/monitor_fleet.py` is the fleet HEARTBEAT ledger
generator. It scans `builds/STATUS_BUILDER_*.md`, parses each builder's state, and
writes `HEARTBEAT_LEDGER.md` (one line per builder in the cwd it's run from).

## Mechanics / quirks (learned 2026-08)
- STATUS files live in `builds/`; falls back to cwd. It picks the dir containing
  `STATUS_BUILDER_*.md` files.
- **Crash-guard:** empty/all-blank STATUS files are SKIPPED (not parsed). So a
  directory with N builder files can yield <N ledger lines — that's normal, not a bug.
  (Observed: 50 files → 48 ledger lines because 2 were empty.)
- **State parsing:** scans the whole file, not just line 1, for an IN-PROGRESS /
  BLOCKED marker (`[IN-PROGRESS]`, `# STATE:`, `# ... BLOCKED ...`). Falls back to a
  first-line `[TOKEN]`. Anything not IN-PROGRESS/BLOCKED maps to DONE.
- **Force-block:** reads `HEARTBEAT_ALERTS.md` for `- BUILDER_N` lines and forces
  those builders to BLOCKED regardless of file content.
- `verified=` / `blocker=` / `next=` lines are read for the ledger.
- Exit 0 + fresh ledger mtime = the monitor itself worked. That does NOT mean the
  fleet is working.

## ⚠️ The key interpretation trap (healthy-audit vs live-fleet)
A stall diagnosis must NOT be inferred from ledger/hub freshness. An all-healthy
*audit* pipeline — fresh `HEARTBEAT_LEDGER.md`, `MASTER_STATUS.md` regenerating every
few minutes, `swarm_turbocharger.py` / `status_hub` process running — can coexist with
a fully dead *fleet*. The monitor is just reading frozen STATUS files and re-printing
their old state.

**To judge actual fleet liveness, check per-builder STATUS file MTIMES**, not the
ledger freshness:
```
now=$(date +%s); for f in builds/STATUS_BUILDER_*.md; do \
  m=$(stat -c %Y "$f"); echo "$(( (now-m)/3600 ))h $f"; done | sort -n
```

## Fleet-wide stall signature
- All/most builder STATUS mtimes share a near-identical old timestamp (e.g. 42× at
  ~314h, i.e. ~13 days), except a single fresh outlier.
- `MASTER_STATUS.md` shows hundreds of IN-PROGRESS minis all way past the 10-min
  alert threshold → hundreds of ALERTS. That large ALERT count is the *expected*
  output of the rule, not a sudden fault — it means the workload went silent.
- A fresh single builder (e.g. BUILDER_37 writing "IDLE, waiting for FIFO") means
  the launch framework is alive but Workers are parked awaiting LO directives.
- Conclusion wording: "the monitoring pipeline is healthy; the fleet is stalled /
  effectively down since <date>." Recommend a formal relaunch/recovery (see
  eni-swarm-floor-recovery) OR formally idle the swarm — don't leave hundreds of
  stale alerts firing at an abandoned campaign.

## Fast-report recipe
For a cron heartbeat report, gather: (1) run monitor, (2) ledger state counts
(`grep -c '^\[DONE\]\|IN-PROGRESS\|BLOCKED'`), (3) per-builder mtime histogram,
(4) MASTER_STATUS summary line, (5) `ps` for swarm_turbocharger/status_hub. Report
"pipeline healthy, fleet <alive|stalled>" explicitly so the distinction is never
conflated.
