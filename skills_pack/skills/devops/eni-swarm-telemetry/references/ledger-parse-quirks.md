# Ledger parse quirks — how `monitor_fleet.py` maps states (verified 2026-08-15 run)

When reading a fresh HEARTBEAT_LEDGER.md, do NOT take labeled states at face
value. The parser collapses several real builder conditions into DONE, which
makes a parked/healthy floor look busier than it is. These quirks matter for
the fleet-status report's "is this live or a stale relic" judgement.

## 1. IDLE → DONE (the big one)
A builder file whose state marker is `# STATUS_BUILDER_N — IDLE` (i.e. parked,
awaiting a directive, no work running) is NOT captured by the IN-PROGRESS or
BLOCKED matchers. The parser falls through to the "else → DONE" branch, so an
IDLE builder shows up as `[DONE]` in the ledger.

Consequence: DONE is NOT "finished". It means "not explosively
IN-PROGRESS/BLOCKED" — it includes genuinely-completed, anemic-but-alive, and
fully-parked/idle builders. The real "what is it doing" answer lives in the
status file's own `next=`/`blocker=` lines, NOT in the ledger's [DONE] tag.

Practical signal: if the freshest file mtime says `IDLE` in its first line but
the ledger tag is `[DONE]`, the builder is parked — read the `next=` line to
report "awaiting LO directive via FIFO".

## 2. Disk files vs ledger lines — the empty-file crash guard
`monitor_fleet.py` skips status files that are empty/blank (crash guard). So
`DISK_STATUS_FILES` (from the liveness probe, glob of STATUS_BUILDER_*.md) can
exceed `LEDGER_LINES`. A real observed run: 50 disk files vs 48 ledger lines
(expected — two builders left 0-byte status files). Do NOT flag this as an
anomaly; it is the normal gap.

## 3. State-distribution sum can disagree with ledger line count
Probe's `ledger state distribution` (DONE + IN-PROGRESS + BLOCKED) can sum to a
different number than the ledger line count for the same reason — empty files
are absent from both. Report the distribution table and the line count as the
probe prints them; don't force them to reconcile.

## How to tell live from relic in a report
State tags in the ledger NEVER establish liveness by themselves. Only the
liveness probe's freshness/mtime + process check does. A DORMANT verdict with a
fleet of [DONE]-tagged IDLE builders + one marginally-fresh parked builder is the
canonical "healthy-but-parked" outcome (see templates/fleet-cron-report.md line
about BUILDER_37).