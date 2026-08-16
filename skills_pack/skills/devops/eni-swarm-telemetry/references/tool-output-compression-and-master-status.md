# Reading telemetry when tool output is ENI-COMPRESSED + interpreting MASTER_STATUS.md

## Pitfall: tool outputs come back wrapped in `ENI-COMPRESSED` carrier PNGs

In this environment, the outputs of `terminal`, `execute_code`, and even `skill_view`
get losslessly compressed and returned as an `ENI-COMPRESSED ratio=Nx carrier=...png`
blob with `--- head ---` / `--- tail ---` excerpts. The full text is NOT in the reply —
it's persisted to the carrier PNG and only recoverable via decompress(carrier).

**Reliable workaround: use `read_file` / `search_files` tools to read telemetry files
raw.** They return plain text, not compressed wrappers. Do NOT `cat` or `execute_code`
to read STATUS/ledger files if you need the full content — you'll get a compressed
blob instead. Pattern that works:
  - `read_file(".../STATUS_BUILDER_46.md")` → raw text.
  - `search_files(target='content', pattern=...)` → raw matches.
  - If you must scan many files, do the aggregation inside a single `execute_code`
    and print only the distilled result (counts/summary), not full file bodies — the
    summary survives in the head/tail, and the carrier preserves the full print if
    you ever need it.

## Interpreting MASTER_STATUS.md alert counts — stale ≠ failure

`MASTER_STATUS.md` (regenerated every ~5 min by `status_hub.py` / worker w2) reports a
raw alert count that LOOKS alarming (e.g. "ALERTS: 391", "IN-PROGRESS: 388") but most
are NOT current failures:

- **Alert rule (stated in the doc):** ALERT is raised when STATE==BLOCKED OR
  (STATE != DONE AND age > 10 min). DONE minis are terminal — their age is
  informational only and does NOT raise a stall alert.
- **Stale-STALLED trap:** after a swarm is parked (e.g. all status files frozen in
  late July), every old IN-PROGRESS file becomes a STALLED alert. In a parked fleet
  the "391 alerts" collapse to a handful of real items.
- **Method for a status report:** ignore the raw ALERTS total; instead enumerate
  (a) the 3 BLOCKED rows, (b) the builder whose file says it's awaiting dispatch, and
  (c) whether the fleet is fresh or parked by checking the NEWEST builder-status file
  mtime vs now. 49/50 files older than ~7 days ⇒ the fleet is dormant, and all the
  IN-PROGRESS rows are stale state, not live work.
- **Deploy gate RED is by design** (no broker path until GREEN) — not a failure.
