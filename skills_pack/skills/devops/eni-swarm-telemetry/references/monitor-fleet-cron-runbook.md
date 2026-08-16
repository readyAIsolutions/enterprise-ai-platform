# Verified cron runbook: monitor_fleet.py + parked-fleet interpretation

Purpose: run the `monitor_fleet.py` gardener as a scheduled job and report fleet
health *correctly* (i.e. not fooled by parsing artifacts of frozen STATUS files).
The other compressed references in this skill can be unrecoverable (`decode_carrier.py`
sometimes fails on the run-recipe carrier with `zstd decompress error: Dictionary
mismatch`). This file is the plaintext fallback that re-derives the procedure.

## Where everything lives

- Script: `/home/hunter/Commander/eni_swarm/monitor_fleet.py`
- Inputs: `builds/STATUS_BUILDER_*.md` (glob) — must run from the repo cwd so
  `HEARTBEAT_LEDGER.md` / `HEARTBEAT_ALERTS.md` resolve there.
- Output: `HEARTBEAT_LEDGER.md` (one `[STATE] BUILDER_N verified=... blocker=... next=...`
  row per builder).
- Bidirectional cwd: the script picks `builds/` if present else cwd. Running from
  `/home/hunter/Commander/eni_swarm` with the `builds/` subdir present is correct.

## Exact run + verification sequence (verified working)

1. Run the monitor:
   ```bash
   cd /home/hunter/Commander/eni_swarm && python3 monitor_fleet.py && cat HEARTBEAT_LEDGER.md
   ```
2. **Ledger rows are STALE snapshots, not live activity.** Do NOT report
   IN-PROGRESS/BLOCKED counts as "builders working" — see the mtime cross-check.
3. Authoritative freshness — mtime histogram:
   ```bash
   cd /home/hunter/Commander/eni_swarm/builds
   ls STATUS_BUILDER_*.md | wc -l                                  # expect ~50
   stat -c '%y' STATUS_BUILDER_*.md | awk '{print $1}' | sort | uniq -c   # date counts
   ls -t STATUS_BUILDER_*.md | head -5                             # freshest files
   find . -maxdepth 1 -name 'STATUS_BUILDER_*.md' -size 0 -printf '%f\n'  # 0-byte drops
   ```
4. Read the fresh file's STATE TOKEN, not its mtime alone:
   ```bash
   cat STATUS_BUILDER_<NN>.md   # [IDLE]/[IN-PROGRESS]/[BLOCKED]/[DONE]
   ```

## The parked-fleet signature (how to READ the histogram)

`N-1` files share one old "parking date" + exactly **one** fresh `[IDLE]` file =
**DORMANT/PARKED fleet with a single warm-idle waiter** (observed: 49 files dated
2026-07-25, only STATUS_BUILDER_37 fresh on a later date, token `[IDLE]`, its FIFO
`/tmp/eni_ctl_BUILDER_37` absent → no directive issued, do-not-invent-work).

- IN-PROGRESS/BLOCKED ledger rows on an otherwise-parked fleet are **parsing
  artifacts of frozen Jul-25 files**, and BLOCKED rows mostly say "no task assigned /
  awaiting dispatch" — not real stalls.
- `ledger rows < file count` is expected: 0-byte STATUS files (e.g.
  `STATUS_BUILDER_20.md`) are silently dropped by the crash guard, not lost workers
  (observed: 48 ledger rows for 50 files).

## Live-truth cross-check (corroborates dormancy)

```bash
wmctrl -l 2>/dev/null | wc -l               # window count (e.g. 17)
wmctrl -l 2>/dev/null | grep -iE "eni|hermes"
pgrep -af hermes | grep -v grep | wc -l      # hermes-chat proc count
echo $DISPLAY                               # :0 expected
```
Observed baseline: 1 `demiurge-linux ENI | HERMES + LOCAL` window + ~11 hermes procs
→ ENI infrastructure is alive, the 50-builder build floor is idle. That is the normal
steady state, not an incident.

## Reporting rule (cron delivery)

When the output matches the parked-fleet baseline with no NEW stalls/crashes/directives
pending to non-waiting builders → report the dormant status normally OR emit
`[SILENT]` if the job's framing is "alert only on change". Do not fabricate activity.