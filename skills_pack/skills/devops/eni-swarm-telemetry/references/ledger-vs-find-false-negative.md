# Ledger row "orphan" vs. find/ls false negative

## Symptom
During a fleet heartbeat you `find`/`ls` for a builder's STATUS file (e.g.
`STATUS_BUILDER_5.md`) and get nothing — yet the freshly-regenerated
`HEARTBEAT_LEDGER.md` clearly lists that builder (e.g. `[IN-PROGRESS] BUILDER_5`).

**Do NOT conclude "orphan ledger row" or "data anomaly" from this.**

`monitor_fleet.py` rebuilds the ledger from files it actually read, so a row in a
just-regenerated ledger almost always means the file exists at aggregation time.
An invisible-to-you file is far more likely a *query* problem than a *data* problem.

## Root cause seen in practice
The Hermes cron/terminal wrapper re-evals the command inside a
`source /tmp/hermes-snap-<id>.sh … eval '…'` shim. Nested **single-quoted glob
patterns passed to `find … -name 'STATUS_BUILDER_5\.*'`** (and to `ls DATUM.*`)
get their quoting mangled during the unescape, so the glob silently expands to
nothing → a bogus "no such file" exit 2. This produced a false finding that
BUILDER_5's file was missing while the ledger kept writing it.

## Correct diagnosis step
Before reporting ANY ledger-vs-disk mismatch, re-verify the exact path with a
quoting-safe probe:
- `ls -la /home/hunter/Commander/eni_swarm/builds/STATUS_BUILDER_5.md` (exact,
  no glob)
- or `search_files`/`read_file` (the Hermes tools, which don't route through the
  shell-shim quoting).

## Distinguish from the REAL ledger-mismatch case
The one genuine, documented mismatch is the reverse and is already expected:
`monitor_fleet.py` **skips 0-byte/blank STATUS files** as a crash guard, so on-disk
file count can exceed ledger rows (e.g. `STATUS_BUILDER_20.md` is 0 bytes → 50
files on disk but 49 ledger rows). That is not data loss and the probe reports
`DISK_STATUS_FILES` and `LEDGER_LINES` separately for exactly this reason.

Rule of thumb: files > ledger rows = expected (empty-file guard). Ledger rows with
no visible file = re-run the query with an exact path before believing it.