# Interpreting the on-disk fleet monitor: monitor_fleet.py → HEARTBEAT_LEDGER.md

Verified on the 2026-08-15 cron monitoring pass.

## The real monitor is on disk (distinct from the bundled probes)

`/home/hunter/Commander/eni_swarm/monitor_fleet.py` is the ACTUAL on-disk fleet
monitor. Run from the eni_swarm dir it reads the per-builder status files in the
`builds/` subdir (`STATUS_BUILDER_*.md`) and rewrites `HEARTBEAT_LEDGER.md`
one line per builder. There may be a duplicate/secondary `builds/HEARTBEAT_LEDGER.md`
as well — the authoritative one is the one the script wrote to cwd. If you need
live truth, prefer this script's ledger only as a summary, and cross-check mtimes.

## CRITICAL interpretation trap: "DONE" is the DEFAULT, not a verification

`monitor_fleet.py` maps each builder's state token:

    IN-PROGRESS → IN-PROGRESS
    BLOCKED     → BLOCKED
    everything else → DONE   ← the default catch-all

So `[DONE] BUILDER_x verified=unknown` does NOT mean "verified done". It means
"no IN-PROGRESS or BLOCKED marker found in the file". In a stale/dormant fleet
almost every builder shows `[DONE] verified=unknown`. Treat **`verified=` being
`unknown` as "unverified / possibly stale"**, not as a pass. The one trustworthy
signal is `verified=<something real>` (e.g. BUILDER_4:
`verified=power_change_applied_100pct_35concurrent_nice5`).

## State-distribution reading

- Count ledger states with regex `\[(DONE|IN-PROGRESS|BLOCKED|UNKNOWN)\]`.
- An **empty status file** (0 bytes) is crash-guarded/skipped by the script
  (e.g. `STATUS_BUILDER_20.md`) — it won't appear in the ledger at all, so
  ledger total can be STATUS-file-count minus empties.

## BLOCKED source ambiguity

`HEARTBEAT_ALERTS.md` may NOT exist. `[BLOCKED]` in the ledger can come from the
builder's OWN status file (a `[BLOCKED]` token / `BLOCKED` + status marker), not
from an alerts file. Don't assume alerts exist; check the source status file.

## Liveness vs staleness — the actual pass verdict

Ledger state alone tells you nothing about whether the fleet is working. On the
Aug-15 pass: 40 DONE / 8 IN-PROGRESS / 1 BLOCKED, but 48/49 status files were
mtime Jul 25 (stale ~3 weeks) and NO builder processes were running. The
IN-PROGRESS ones were hung relics. The real liveness signal is **status-file
mtime recency** + **live process check** (see `fleet_mtime_staleness.py` /
`fleet_liveness_probe.sh` and `fresh-mtime-vs-liveness-probe-location.md`), not
the ledger's state tokens. Verdict when it's all stale: swarm is IDLE/dormant
and needs a PRODUCT_LEAD routing / FIFO dispatch kick, not a "healthy" fleet.
