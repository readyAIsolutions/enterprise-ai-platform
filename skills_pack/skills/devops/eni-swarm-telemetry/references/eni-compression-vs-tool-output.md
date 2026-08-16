# ENI-COMPRESSION wrapper vs. tool stdout — reading fleet data reliably

When the environment's ENI compression layer is active (LO's running setup), large tool
results get losslessly compressed and the raw JSON / stdout can be mangled or truncated in
what you actually see. This bites specifically when running the fleet monitor as a cron
job and trying to read `HEARTBEAT_LEDGER.md` / `STATUS_BUILDER_*.md`. Observed 2026-08-14
during a `monitor_fleet.py` run.

## Symptoms
- `execute_code` calling `from hermes_tools import terminal` → `JSONDecodeError: Expecting
  value: line 1 column 1` (the wrapper choked on compressed output, not on your code).
- Native `terminal` results come back wrapped as `<ENI-COMPRESSED ratio=… carrier=…>` with
  only a head/tail excerpt of the true output — so `cat` of a 50-line ledger is unreliable.

## The workaround that works
- **Prefer the native `terminal` tool over `execute_code`'s `terminal()` helper.** The
  native tool tolerates/handles the compression; the sandbox helper does not.
- **Don't `cat` whole files.** Use aggregate/streaming commands that return tiny outputs:
  `grep -oP '^\[[^]]+\]' … | sort | uniq -c`, `awk '{print $1}' | sort | uniq -c`, `wc -l`,
  `ls | wc -l`. These produce short lines that survive compression intact.
- For per-builder mtime/staleness or state classification, do it in `execute_code` with
  pure Python (`os.path.getmtime`, `datetime`, `glob`, `re`) and `print` only a compact
  summary — file reads inside Python are NOT compressed; only the printed result is, and a
  short summary survives. (This is exactly what `scripts/fleet_mtime_staleness.py` does.)

## Why it matters for the heartbeat
The heartbeat/ledger read path is a cron job with no human to re-run on failure. If the
first read attempt throws or comes back compressed-garbled, you must fall back to the
grep/awk-native-terminal path rather than giving up or trusting a mangled `cat`.

## Cross-check worth keeping
Running the monitor writes the ledger to the launch cwd, NOT always `builds/`. Verify which
`HEARTBEAT_LEDGER.md` is authoritative by mtime (see
`references/status-file-format-parsing.md` for the silent-drop and dual-ledger pitfalls).
