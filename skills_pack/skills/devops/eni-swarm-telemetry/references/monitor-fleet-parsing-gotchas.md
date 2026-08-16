# monitor_fleet.py — parsing & freshness gotchas

Field notes for running / auditing `/home/hunter/Commander/eni_swarm/monitor_fleet.py`
and interpreting its output. These bit during a real cron run.

## 1. STATUS_BUILDER files are ZERO-PADDED
Files are named `STATUS_BUILDER_01.md` … `STATUS_BUILDER_50.md` — **not** `STATUS_BUILDER_1.md`.
- The script's regex `STATUS_BUILDER_(\d+)\.md` captures `"01"` → int 1, so the **ledger numbers are correct**. Rebuilds are unaffected.
- BUT manual inspection traps you: `ls STATUS_BUILDER_5.md` FAILS (file is `STATUS_BUILDER_05.md`). Always glob with the zero-pad pattern:
  ```bash
  ls builds/STATUS_BUILDER_0*.md        # 01..09
  ls builds/STATUS_BUILDER_[1-5]*0.md   # 10..50
  ```
  Or list the raw dir and parse the number yourself.

## 2. `wc -l` on HEARTBEAT_LEDGER.md UNDERCOUNTS entries
The script writes `"\n".join(lines_out)` with **no trailing newline**, so the last builder line isn't counted by `wc -l`.
- Example: 49 builder entries → `wc -l` reports **48**.
- Don't use line count to detect missing builders. Count the state tokens instead:
  ```bash
  grep -oE "\[[A-Z-]+\]" HEARTBEAT_LEDGER.md | sort | uniq -c
  ```

## 3. 0-byte builder files are silently skipped (crash guard)
`monitor_fleet.py` skips any `STATUS_BUILDER_*.md` that is empty, so **disk file count ≠ ledger entry count**.
- A 0-byte file (e.g. BUILDER_20) disappears from the ledger entirely — it is not listed as DONE/IN-PROGRESS/BLOCKED, it's just absent.
- When reconciling "50 files but 49 ledger rows", check for an empty file before assuming a parse bug.

## 4. State tokens can be STALE — trust mtime + live procs, not the token
A status file left as `[IN-PROGRESS]` from a prior (dead) run shows as IN-PROGRESS in the ledger, but the fleet is NOT live.
- Freshness gate is the file mtime plus live processes, not the `[STATE]` token.
- Pattern that works: `ls -la --time-style=+%Y-%m-%d_%H:%M builds/STATUS_BUILDER_*.md` + `ps aux | grep -E "hermes-chat|eni_swarm"`.
- If all IN-PROGRESS files are weeks old and 0 procs are up → fleet is DORMANT/parked, and those entries are stale flags, not real work.
- When reporting, explicitly call out that IN-PROGRESS count ≠ live builders.

## 5. Verdict vocabulary
Fleet report verdicts by freshness: DORMANT (all stale + no procs) → PARTIALLY LIVE → LIVE.
A dormant/unchanged fleet is still a report to send — the pulse IS the deliverable. Never `[SILENT]` a fleet-monitor run.