# Fleet STATUS / ledger file parsing — gotchas

Learned while running `monitor_fleet.py` + ad-hoc state counting on 2026-08-16.

## PITFALL 1: hyphens break `\w+` state counting
State tokens in STATUS/ledger files are hyphenated: `[IN-PROGRESS]`, `[IN-PROGRESS]`,
`[DONE]`, `[BLOCKED]`, `[IDLE]`.

A naive `re.findall(r"\[(\w+)\]", ledger_text)` silently matches ONLY `IN` for
`[IN-PROGRESS]`, so you get a bogus state bucket and the real `IN-PROGRESS` rows
are dropped from the stats. This produced `{'DONE': 40, 'BLOCKED': 1, total: 41}`
when the file actually held `{'DONE': 40, 'IN-PROGRESS': 8, 'BLOCKED': 1, total: 49}`.

**Fix:** use a character class that includes the hyphen:
```python
import re
from collections import Counter
states = Counter(re.match(r"\[([A-Z-]+)\]", line).group(1)
                 for line in lines if line.strip())
```
Your manual analysis script must mirror `monitor_fleet.py`'s own
`[\\[|\\bSTATE\\b|STATUS]` scan logic — it already handles the hyphen correctly.

## Ledger vs STATUS mtimes
- The ledger (`HEARTBEAT_LEDGER.md`) is a single summary; the per-builder
  `builds/STATUS_BUILDER_NN.md` files carry the mtimes that matter for staleness.
- A ledger row can say `[IN-PROGRESS]` while the underlying STATUS file is weeks
  stale (Jul 25 mtimes seen) — stale markers do NOT mean live building. Always
  cross-check ledger state against STATUS file mtime before claiming "IN-PROGRESS".
- Check BOTH candidate ledger locations: the one written to cwd by
  `monitor_fleet.py` and `builds/HEARTBEAT_LEDGER.md`; they can be out of sync
  (fresh run writes to cwd, old artifact lingers under builds/).

## Discrepancy note
A missing builder in the ledger (e.g. BUILDER_20 on disk but absent from ledger)
is a minor, non-actionable discrepancy while the floor is parked — report it in
the notes but don't treat it as a failure.

## Alert/blocked states
`HEARTBEAT_ALERTS.md` may not exist (clean floor). `blocked_builders` is
extracted from `- BUILDER_NN` lines; absence of alerts file = nothing blocked
besides what the ledger's own `[BLOCKED]` says.