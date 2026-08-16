# DORMANT verdict — confirmation triad (worked example: Aug 15 2026)

When the fleet is parked, the report must land on **DORMANT** and back it with a
*verifiable* confirmation, not just "no work happening". The skill's pitfalls
scatter these signals across several files; assemble all three before writing
the verdict. A clean DORMANT run checks ALL of:

1. **Freshness window:** `fresh_last24h=0` (use the `-24h` window, NOT `today`).
   Compute the newest STATUS file's **exact age** and state it (e.g. "newest
   30.1h old") so you don't overclaim LIVENESS from a file that just crossed the
   window boundary. This is distinct from the early-morning `today 00:00` trap.
2. **No live processes:** the probe reports `NONE running` (pgrep for
   hermes-chat / ENI builders — remember it self-matches the cron wrapper shell,
   filter `ps … | grep -v 'bash -c'`).
3. **Freshest file body reads parked, not working:** read the newest STATUS
   file's BODY — if it says `IDLE` / "Control FIFO ... does not exist" / "No
   directive issued" / "next=await LO's directive via FIFO", that is a parked
   builder, not live work. One ticking file is not a live swarm.

Plus a **disk/ledger reconciliation**: `DISK_STATUS_FILES` may exceed
`LEDGER_LINES` by 1+ because the monitor skips 0-byte files (crash guard) — e.g.
50 files on disk, 48 ledger lines, `STATUS_BUILDER_20.md` is 0 bytes. State it
as *expected, not data loss*.

## Counter-check for a wrongly-live-looking floor
Past runs show the SAME 8 IN-PROGRESS + 1 BLOCKED rows persisting week over week
(all untouched ~3 weeks) while the floor is dormant. **Never report those as
live blockages.** Verify with mtime/proc first. Also ignore the `status_hub.py`
MASTER_STATUS aggregate (hundreds of minis/ALERTS, stale relics from other
mini-projects) — the fleet verdict comes from BUILDER_STATUS mtime/proc only.

## Worked report snapshot (Aug 15 2026 run)
- newest STATUS: BUILDER_37 @ 2026-08-14 15:57 → 30.1h old → `fresh_last24h=0`
- live builder procs: NONE
- BUILDER_37 body: `IDLE` / "Control FIFO /tmp/eni_ctl_BUILDER_37 does not exist
  ... No directive issued. next=await LO's directive via FIFO creation"
- HEARTBEAT_ALERTS.md absent → no forced BLOCKED; BUILDER_46 BLOCKED is leftover
  state, not an active alert (normal parked condition)
- control FIFOs present (25 `eni_ctl_*`: BUILDER_50 + DEMIURGE B01–B12 +
  DEMIURGE3D B01–B12) but **no builder running against them**
- ledger: 48 lines / 50 disk files (BUILDER_20 0-byte, crash-guard skipped)
- distribution: 40 DONE, 8 IN-PROGRESS, 1 BLOCKED
- **Verdict: DORMANT / healthy-but-parked. To wake: issue a directive via a
  control FIFO** (e.g. create/feed `/tmp/eni_ctl_BUILDER_<n>`); builders respawn
  on directive per the FIFO-launch pattern.