# STATUS_HUB (MASTER_STATUS.md) — corroboration source for the fleet monitor

Companion to `monitor_fleet.py` / `monitor_cron_diagnostics`. When deciding idle-vs-down,
the ledger + `ps` + status-file mtimes + FIFOs are the primary sources. `MASTER_STATUS.md`
(adds a corroborating, independent view) and has two useful properties:

## What to read from it
- **Freshness head-check:** the `Generated: <ts>` line on line 2 (and the `# MASTER STATUS
  HUB` header) proves `status_hub.py` is currently running and self-healing. A fresh
  `Generated:` today = the orchestration/status brain is healthy **independently of the
  builder floor**. Do not conflate "status hub alive" with "builders running."
- **Aggregate summary block:** the `## Summary` section reports counts
  (e.g. `DONE: 207  IN-PROGRESS: 388  BLOCKED: 3  ALERTS: 391`). Use this as a sanity
  cross-check against the ledger buckets.

## The trap (observed 2026-08-11)
- The hub's aggregate counts are **grossly stale and NOT a live signal.** 388 IN-PROGRESS
  and 391 ALERTS were almost entirely July-dated artifacts (ENI minis 27,969m+ old,
  ws workers 45,493m+, BLOCKED minis 42,790m+). Exclude these from any report — do not
  say "the swarm has 391 alerts / 388 stuck minis." They are historical noise, same
  class of trap as stale `STATUS_BUILDER_*.md` files feeding the ledger.
- Verify the same way as the builder floor: check the underlying STATUS file's mtime, not
  the aggregate count. Age `> ~10 min` + IN-PROGRESS = stale (the hub's own methodology
  header documents this: alert fires on BLOCKED or non-DONE older than 10 min).
- Fresh today's-touch STILL means merely *parked*, not working: e.g. a builder status file
  rewritten today with `IDLE` / `blocker=none` / `awaiting LO directive via FIFO`, plus a
  missing control FIFO, means the builder is parked awaiting dispatch — not stuck.

## Cross-check source set (consolidated)
1. `HEARTBEAT_LEDGER.md` (parses `builds/STATUS_BUILDER_*.md`) — parse only, treat
   IN-PROGRESS/BLOCKED rows as signal ONLY if the underlying file's mtime is today.
2. `ps`/`pgrep` for builder worker processes (expected: zero when parked).
3. `ls -lt` status-file mtimes (17+ days old = parked/historical).
4. `/tmp/eni_ctl_*` FIFOs (presence/absence per-builder; rebuilt today = live-ish).
5. `MASTER_STATUS.md` `Generated:` line + agGREgate summary (**this file;** exclude stale
   counts from reports).