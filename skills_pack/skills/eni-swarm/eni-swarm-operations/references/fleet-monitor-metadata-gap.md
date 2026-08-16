# Fleet Monitor — Metadata-Gap IN-PROGRESS Builders

A common pattern in `HEARTBEAT_LEDGER.md` output: builders listed as `[IN-PROGRESS]` but with `verified=unknown`, `blocker=unknown`, `next=unknown`. This is a **ghost-state diagnostic signal** — the builder is marked active but has not reported any actual work progress.

## How to detect

Scan the ledger for lines matching:
```
\[IN-PROGRESS\] BUILDER_\d+ verified=unknown blocker=unknown next=unknown
```

In `execute_code`:
```python
import re
ledger = open("/home/hunter/Commander/eni_swarm/HEARTBEAT_LEDGER.md").read()
ghosts = re.findall(r"\[IN-PROGRESS\] (BUILDER_\d+) verified=unknown blocker=unknown next=unknown", ledger)
```

## What it means — three possibilities

| Pattern | Likely cause | Action |
|---------|-------------|--------|
| Recent mtime (minutes old) | Freshly spawned, hasn't had a cycle yet | Normal — check next pass |
| Stale mtime (hours/days) + header says "fresh spawn" or "no prior task" | Builder spawned but never received work | Report as idle; needs FIFO or master dispatch |
| Stale mtime + generic header (e.g. `# STATUS_BUILDER_32`) | Ghost/abandoned state; builder process may not be alive | Cross-check with `ps aux | grep BUILDER_{n}`; flag as possibly dead |

## Sub-swarm health indicator in builder headers

Some builder status files embed **higher-level swarm health** in their first line. Example from BUILDER_39:
```
[IN-PROGRESS] BUILDER_39 — fresh spawn, no prior task assigned. builds/ empty. Swarm: 207 DONE / 380 IN-PROGRESS / 3 BLOCKED
```

This is the `status_hub.py` (5-min cron) output being echoed into a builder state file by a higher-level orchestrator. Detection:
```python
swarm_health = re.search(r"Swarm:\s*(\d+)\s*DONE\s*/\s*(\d+)\s*IN-PROGRESS\s*/\s*(\d+)\s*BLOCKED", first_line)
```
This gives you a 1-line window into the wider 598-mini fleet state without running `status_hub.py`.

## Work redistribution signal

If a builder's header references another builder by number, it indicates **work redistribution**. Example from BUILDER_25:
```
# STATUS_BUILDER_25.md — DEMIURGE FREED SWARM B25 (catch-up from B46)
```
This means B46's work was reassigned to B25. The blocked builder (B46) becomes a "dead-end" node while the catch-up builder carries the actual work. When interpreting the fleet:
- The **blocked builder** may be a structural bottleneck, not a failing task
- The **catch-up builder** tracks the actual task that was being attempted

## BLOCKED — non-environmental reasons

Some BLOCKED builders are not blocked on tooling, missing packages, or environment issues — they are blocked on **human dispatch**. Example from BUILDER_46:
```
[BLOCKED] STATUS_BUILDER_46
Blocked on: no task assigned. Awaiting PRODUCT_LEAD dispatch via FIFO or master routing.
```

These are **idle waiting** builders, not failing builders. They should be reported as "awaiting directive" rather than "blocked on error." The distinction matters because:
- Environmental blocks → may need a fix or retry
- Dispatch blocks → the fleet is waiting for a human to assign work