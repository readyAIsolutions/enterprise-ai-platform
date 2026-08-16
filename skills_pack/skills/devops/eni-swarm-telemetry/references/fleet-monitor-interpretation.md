# Interpreting `monitor_fleet.py` output (and its blind spots)

`monitor_fleet.py` runs as a cron pulse: it scans `STATUS_BUILDER_*.md`
files under `builds/`, parses each file's state token, and regenerates
`HEARTBEAT_LEDGER.md`. It is a **token reader, NOT a liveness probe**.

## What it does
- Picks the dir containing STATUS files (prefers `builds/`, else cwd).
- Reads `blocked_builders` from `HEARTBEAT_ALERTS.md` lines matching
  `- BUILDER_(\d+)`. If that file is empty/absent, any `[BLOCKED]` in the
  ledger came from the status file's own token, not from an alert.
- Parses state from the file: `[IN-PROGRESS]`/`# STATE:`/`[BLOCKED]`/`[DONE]`/`[IDLE]`.
- Writes one ledger line per builder: `[STATE] BUILDER_N verified=.. blocker=.. next=..`

## Blind spots / traps
1. **Stale tokens = zombies, not active builds.** The monitor only reads the
   state *string*; it does not check whether the builder is actually running.
   A status file dated weeks ago still says `[IN-PROGRESS]` and the ledger
   will faithfully report it as IN-PROGRESS. ALWAYS cross-check each builder's
   STATUS file age before reporting "active":
   `stat -c "%n age=%Y" builds/STATUS_BUILDER_*.md` and compare to `date +%s`.
   If IN-PROGRESS/BLOCKED files are ~3 weeks old, the floor is idle and those
   are stalled/zombie markers — flag them, don't report them as live work.

2. **Empty files are silently dropped.** The crash guard skips 0-byte/blank
   STATUS files. So a builder MISSING from the ledger is itself a signal:
   check for an empty STATUS file (a blank/half-written build footprint) — it
   may be a race/crash rather than a completed-and-removed builder.

3. **`DONE` may be a default, not a success.** The parser maps anything it
   can't classify (unknown/unmatched tokens) to `DONE`. A file with no
   recognizable state marker collapses to `[DONE]` with `verified=unknown`.
   Treat `verified=unknown` + `next=unknown` DONE entries as indeterminate.

## Signal that a builder IS live
- A **fresh-mtime** STATUS file (touched recently) is the only reliable "alive"
  indicator. `[IDLE]` on a fresh file = alive but waiting (e.g. the FIFO-awaiting
  builder: `Control FIFO /tmp/eni_ctl_BUILDER_N does not exist ... awaiting LO
  directive`). `[IN-PROGRESS]` on a fresh file = genuinely working.

## Environment quirk
- On this box `python` is not on PATH; use `python3`.