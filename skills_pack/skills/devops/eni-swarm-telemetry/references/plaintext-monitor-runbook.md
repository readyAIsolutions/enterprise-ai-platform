# ENI Fleet Monitor — plaintext runbook (no compression required)

Workspace reality (verified 2026-08-15): the `eni-swarm-telemetry` SKILL.md, its
`templates/fleet-cron-report.md`, and every `references/*.md` file in this skill ship
**ENI-compressed** on disk — `skill_view`/`read_file` return an `ENI-COMPRESSED`
carrier blob (a PNG at `~/Desktop/eni_compression/carriers/`), not readable text.
The canonical report template is unrecoverable in plaintext through the normal path.
So keep THIS file plaintext; it reproduces the essentials needed to stdout a valid
fleet pulse without decompression.

## If you need the FULL template or deep reference content
Recover the carrier losslessly via the `eni-swarm-compression` skill:
`scripts/recover_carrier.py` (and `references/recovering-eni-carriers.md`). Fastest
bypass when you only need one file: `env -u PYTHONPATH` to kill the output hook,
or sed-chunk windows.

## Canonical cron entry point (do this first)
Run the on-disk regenerator rather than re-deriving status parsing:
```
cd /home/hunter/Commander/eni_swarm && python3 monitor_fleet.py
```
This scans `builds/STATUS_BUILDER_*.md`, maps state (IN-PROGRESS/BLOCKED/DONE with
robust marker parsing), crash-guards EMPTY files out of the ledger, folds any
blocked builders named in `HEARTBEAT_ALERTS.md` to BLOCKED, and writes
`HEARTBEAT_LEDGER.md`. Exit 0 = success. Then read `HEARTBEAT_LEDGER.md` for the
line-level state counts and pull the non-UNKNOWN `verified=`/`next=` fields.

## Fleet-status verdict logic (what "nothing changed" MEANS)
The fleet pulse is ALWAYS the deliverable — NEVER `[SILENT]` a monitor run, even
when dormant. A parked/dormant floor is itself a valid report.

- Fleets stop building and status cross the weeks-old threshold → verdict DORMANT /
  PARKED. Default framing: "parked and healthy, not a stall."
- **Stale IN-PROGRESS/BLOCKED builders are phantom relics, not live work.** If their
  STATUS file mtime is days/weeks old (e.g. all Jul 25-26 in a mid-Aug run), say so
  clearly in the report; do NOT let the board read as "floor is active."
- Distinguish `ps` liveness (no builder worker processes) from STATUS-file presence.

## Explicit "awaiting LO" check-ins to surface under "What would wake it"
Builders parked on `next=await LO directive via /tmp/eni_ctl_BUILDER_<N> FIFO` or
`awaiting LO directive via FIFO or direct chat` are the wake handles — list them.
The single-freshest STATUS file is the best re-dispatch candidate (e.g. BUILDER_37
in the Aug-15 run was the only file touched recently).

## Report shape (skim-able, LO watches live)
1. Header: run datetime, script, exit status, "ledger regenerated"
2. **Verdict** line (DORMANT / PARTIALLY LIVE / LIVE) + one-sentence why
3. Fleet snapshot table: DONE / IN-PROGRESS / BLOCKED / files-parsed counts
4. Liveness probe: freshness (newest mtime vs now), `ps` worker check, alerts file
5. Explicit "awaiting LO" check-ins
6. "What would wake it" + bottom-line; note monitor does NOT auto-dispatch