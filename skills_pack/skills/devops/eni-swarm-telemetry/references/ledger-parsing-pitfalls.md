# Ledger-parsing & fleet-verdict pitfalls (from live fleet-monitor runs)

Two recurring gotchas when aggregating builder STATUS files into the HEARTBEAT_LEDGER
and turning that into a verdict. Both appeared in a real cron run; neither is a bug in
`monitor_fleet.py` — they're traps in *how you read its output*.

## 1. Zero-padded builder filenames: `STATUS_BUILDER_01.md` vs `..._1.md`
Builders 1–9 are written to disk as **zero-padded** two-digit names:
`builds/STATUS_BUILDER_01.md` … `STATUS_BUILDER_09.md`, while 10+ are unpadded
(`STATUS_BUILDER_10.md` … `_50.md`).

- Python's `glob("STATUS_BUILDER_*.md")` matches BOTH padded and unpadded → `monitor_fleet.py`
  correctly counts all 50.
- But a **shell** existence loop like `for i in $(seq 1 50); do [ -f "builds/STATUS_BUILDER_$i.md" ] || echo MISSING; done`
  prints a spurious **"MISSING BUILDER_1..9"** because it looks for the unpadded
  `_1.md` instead of `_01.md`.
- **Do not trust that "MISSING" list** to mean builders are absent. Cross-check with
  a glob count (`ls builds/STATUS_BUILDER_*.md | wc -l`) — 50 == healthy on a 50-builder floor.
- When reporting builder membership, normalize to the padded numeric ID.

## 2. Ledger lines < on-disk status files is EXPECTED, not a bug
`DISK_STATUS_FILES=50` but `HEARTBEAT_LEDGER.md` had only 48 lines. Cause: `monitor_fleet.py`
has an empty-file **crash guard** that skips any STATUS file with no non-blank lines.
A 0-byte file (e.g. `STATUS_BUILDER_20.md` got truncated to 0 bytes) is silently dropped.
- So ledger line-count vs disk file-count can differ by a couple. Verify by checking
  `stat -c %s` on the "missing" entries — 0 bytes explains it.
- Empty/blank STATUS files are also a stall signal on their own (a builder that wrote
  nothing), but in a dormant fleet they're just leftover from a truncated write.

## 3. DORMANT-fleet diagnosis quick-read (when verdict is "~dead")
The one freshest status file tellingly *isn't* live work — read its body. A `# ... IDLE`
header with "Control FIFO ... does not exist ... awaiting LO's directive" is a **parked
handoff**, the fleet's last real message. Combined with:
  - `fresh_today=0` / `fresh_last24h=1` (only the parked IDLE note),
  - `Live builder processes: NONE`,
  - leftover `/tmp/eni_ctl_*` FIFOs with no consumer,
  - no `HEARTBEAT_ALERTS.md` on disk (so any BLOCKED row is a stale relic, not a live alert),
→ verdict is **DORMANT/dead**, fleet needs a manual relaunch (worker pool + master driver +
per-builder FIFOs), not a kick. This is a normal, reportable state — never `[SILENT]` it.
