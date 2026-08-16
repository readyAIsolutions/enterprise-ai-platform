# Fleet-monitor cron deliverable — when to report vs. stay silent

Companion to fleet-staleness-interpretation.md. Adds the decision rules for what the
monitor cron should OUTPUT once you've established the fleet is dormant.

## The [SILENT] decision rule
The fleet-monitor cron fires on a schedule and re-runs `monitor_fleet.py`, which
regenerates HEARTBEAT_LEDGER.md each pass. If the pass lands on the *standard dormant
baseline*, the correct cron deliverable is **[SILENT]** — do NOT emit a status report
every single pass just because the cron ran. A report is only warranted when there is
genuinely NEW, actionable signal.

The standard dormant baseline looks like (first confirmed 2026-08-11, re-confirmed 2026-08-14):
- Ledger counts ~40-49 DONE with an 8 IN-PROGRESS + 1 BLOCKED cluster.
- ALL of those IN-PROGRESS/BLOCKED STATUS files have OLD mtimes (~2.5 wks+ stale —
  they're stale markers, not live tasks; see fleet-staleness-interpretation.md).
- Exactly ONE builder file touched today, and its head reads "IDLE" + no control FIFO
  (`/tmp/eni_ctl_BUILDER_NN does not exist`) = the routine daily IDLE self-check, not a task.
  NOTE — that builder's number is NOT fixed across runs (08-11 vs some other builder, 08-14 it
    was BUILDER_37). Never key the check on a specific builder number. Do NOT demand mtime ==
    *today* strictly — the single IDLE self-check can legitimately carry YESTERDAY's mtime and still
    be the routine daily IDLE marker. Example: run on Fri Aug 15 found STATUS_BUILDER_37.md at
    Aug 14 15:57 (head "IDLE", no FIFO) while all 49 other builders were Jul 25 (~3 wks stale) — the
    big mtime GAP to the rest is the real tell, not the date match. Detect dormancy as "exactly ONE
    STATUS_BUILDER_* file in the last ~24-48h whose head == IDLE + no control FIFO, with ALL others
    weeks-stale". A ~3-week gap to the rest is the deciding signal.
- No HEARTBEAT_ALERTS.md present, or it lists nothing new.

## Two freshness traps (do not misread these as "fleet woke up")
1. **MASTER_STATUS.md and HEARTBEAT_LEDGER.md get their mtime bumped to the cron run
   time** (e.g. 20:15) every time the monitor executes. A fresh MASTER_STATUS mtime is
   the *monitor rewriting it*, NOT evidence of new fleet activity. Treat the STATUS_BUILDER_*
   mtimes as the source of truth, not MASTER_STATUS / LEDGER.
2. **HEARTBEAT_ALERTS.md is optional and often absent** from the workdir. When it doesn't
   exist, `monitor_fleet.py` computes `blocked_builders = set()` (empty), so NO builder is
   alert-force-blocked. A builder showing `[BLOCKED]` in the ledger is then reporting its
   OWN stale STATUS content — not an active alert. Don't treat it as a fresh failure.

## Report-only, always
Confirm dormancy and, if you do report, note that resurrecting the floor requires a
live-session directive — never dispatch/edit STATUS from this cron.
