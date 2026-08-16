# monitor_fleet.py cron — ledger regeneration & health interpretation

The fleet monitor cron targets `/home/hunter/Commander/eni_swarm/monitor_fleet.py`.
It is a pure-Python script that **regenerates** `HEARTBEAT_LEDGER.md` from the
per-builder status files. Running it is NOT a live probe — it only re-serializes
what the STATUS files already say. Use it as the "aggregate the current ledger"
step, then interpret health with the recipe below.

## Run it
```bash
cd /home/hunter/Commander/eni_swarm && python3 monitor_fleet.py
# exit 0, prints nothing on success. Output goes to HEARTBEAT_LEDGER.md.
```

## What it does
- Fixes working dir = `builds/` subdir (falls back to cwd). Reads `STATUS_BUILDER_<N>.md`.
- Parses each file's state token. Handles varied formats:
  `[IN-PROGRESS] ...` | `# STATE: IN-PROGRESS` | `# ... IN-PROGRESS ...`,
  `[BLOCKED]...`, and falls back to first-line `[TOKEN]`.
- Maps to DONE | IN-PROGRESS | BLOCKED (anything not BLOCKED/IN-PROGRESS → DONE).
- If `HEARTBEAT_ALERTS.md` exists, builders listed there as `- BUILDER_N` are forced BLOCKED.
- Reads optional `verified=` / `blocker=` / `next=` lines.
- Writes one line per builder: `[STATE] BUILDER_N verified=... blocker=... next=...`.

## Interpret the ledger (the actual health report)
```bash
cd /home/hunter/Commander/eni_swarm
# 1) state distribution
grep -oP '^\[([A-Z-]+)\]' HEARTBEAT_LEDGER.md | sort | uniq -c
# 2) which builders are not done
grep -P '^\[(BLOCKED|IN-PROGRESS)\]' HEARTBEAT_LEDGER.md
# 3) STALENESS — the real signal. Fresh mtime != alive (see fresh-mtime trap ref).
ls --time-style=+%Y-%m-%d -l builds/STATUS_BUILDER_*.md | awk '{print $6}' | sort | uniq -c
# 4) LIVE PROCESS CROSS-CHECK — ledger says nothing about liveness.
ps aux | grep -iE 'builder' | grep -v grep | wc -l
```

Key judgment call: **the ledger is not liveness.** A state of IN-PROGRESS in a
status file that is weeks old means "stale/parked," not "building right now."
Always pair the ledger with (3) the mtime histogram and (4) the process count.
Typical health read:
- many files days/weeks old + 0 builder procs → **fleet parked**, awaiting directives.
- a few fresh IN-PROGRESS + matching procs → genuinely building.
- BLOCKED builder that says "no task assigned / awaiting PRODUCT_LEAD dispatch" →
  not an error; it is parked-by-design waiting on a control FIFO directive.

## Pitfall: ENI-COMPRESSED swallows large terminal output
`cat HEARTBEAT_LEDGER.md` (49+ lines) and multi-file `cat` loops come back
compressed as `<ENI-COMPRESSED ...>` with only head/tail shown. Avoid it by
reading narrowly:
- `grep -P '^\[(BLOCKED|IN-PROGRESS)\]'` to pull just the interesting lines,
- `grep -oP ... | sort | uniq -c` for counts (small output),
- `read_file` / one specific file at a time rather than `cat builds/STATUS_BUILDER_*.md`.
Counts and single greps stay small enough to return raw.