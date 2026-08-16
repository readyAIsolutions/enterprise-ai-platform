# `monitor_fleet.py` state-parsing algorithm

This is the **canonical algorithm** that `monitor_fleet.py` uses to classify each STATUS_BUILDER_N.md file into one of three states: DONE, IN-PROGRESS, or BLOCKED. The algorithm lives in `/home/hunter/Commander/eni_swarm/monitor_fleet.py`.

## Inputs

1. **50 STATUS files** under `builds/` (or cwd as fallback): `STATUS_BUILDER_01.md` … `STATUS_BUILDER_50.md`
2. **Optional `HEARTBEAT_ALERTS.md`** — lines matching `- BUILDER_(\d+)` force those builder numbers to BLOCKED
3. **Workdir resolution**: prefers `<script_dir>/builds/` if it contains any STATUS files; falls back to cwd

## State-parsing pipeline (per STATUS file)

### Step 0: Crash guard
Skip the file entirely if it's empty (0 bytes) or contains only whitespace lines. The builder is silently **excluded from the ledger** — no line at all, no UNKNOWN placeholder.

### Step 1: Two-pass state resolution

**Pass 1 — scan every line for combined markers:**
```python
for l in lines:
    ul = l.upper()
    # Match if line has [STATE], "STATE", or "STATUS" keyword AND "IN-PROGRESS"
    if re.search(r"\[|\bSTATE\b|STATUS", ul) and re.search(r"IN[-_ ]?PROGRESS", ul):
        state = "IN-PROGRESS"; break
    # Match if line has "BLOCKED" keyword AND one of [STATE/STATUS/BLOCKED marker]
    if ("BLOCKED" in ul) and re.search(r"\[|\bSTATE\b|STATUS|BLOCKED", ul):
        state = "BLOCKED"; break
```

The pattern `IN[-_ ]?PROGRESS` accepts: `IN-PROGRESS`, `IN_PROGRESS`, `IN PROGRESS`.
The `[STATE]` match requires at least one of `[`, `STATE`, or `STATUS` to be present — a bare mention of "BLOCKED" in a description won't trigger it.

**Pass 2 — fallback to first-line `[STATE]` token:**
If Pass 1 left `state == "UNKNOWN"`, read the first non-empty line and look for a `[STATE]` token:
```python
state_line = next((l.strip() for l in lines if l.strip()), "")
m2 = re.match(r"\[([^\]]+)\]", state_line)
state = m2.group(1).strip().upper() if m2 else "UNKNOWN"
```
This catches files formatted as `[IDLE] BUILDER_01 …` where "IDLE" is not in the Pass 1 keywords.

**⚠️ `#`-prefix pitfall**: If the first non-empty line starts with `#` (e.g. `# STATUS_BUILDER_37 — IDLE — …`), `re.match` fails because it anchors at position 0 — the `#` blocks the `[` pattern. State stays `UNKNOWN` and Step 2 maps it to `DONE`, silently misclassifying an IDLE builder as DONE. The `[` bracket pair must be on position 0 of the first non-empty line for this fallback to work.

### Step 2: State mapping
```python
if state == "BLOCKED":            mapped = "BLOCKED"
elif state in ("IN-PROGRESS", "IN_PROGRESS"): mapped = "IN-PROGRESS"
else:                             mapped = "DONE"
```
**Everything that is neither BLOCKED nor IN-PROGRESS becomes DONE** — IDLE, UNKNOWN, UNKNOWN, WAITING, etc.

### Step 3: Alert-file override
If the builder number appears in the `blocked_builders` set (parsed from `HEARTBEAT_ALERTS.md` lines matching `- BUILDER_(\d+)`), its state is forced to `BLOCKED` regardless of what the STATUS file says.

### Step 4: Key-value extraction
After state mapping, the script extracts three optional fields from any line:
```
verified=...   → e.g. "power_change_applied_100pct_35concurrent_nice5"
blocker=...    → e.g. "none" or "no task assigned"
next=...       → e.g. "awaiting LO directive via FIFO or direct chat"
```
These are emitted verbatim in the ledger line but are **informational only** — they don't influence the state classification.

## Ledger output format

Each line in `HEARTBEAT_LEDGER.md`:
```
[STATE] BUILDER_N verified=... blocker=... next=...
```
Builders are emitted in numeric order (sorted keys). The file is **overwritten** fully each run — no append, no diff.

## Known behaviors

- **Builders from ALERTS that have no STATUS file**: not emitted (the loop only processes files on disk). The alert override only applies to builders that *do* have a STATUS file.
- **Empty files → silent omission**: a builder with a 0-byte STATUS file disappears from the ledger entirely. This is NOT a DONE classification — it's absence. Always cross-check `ls builds/STATUS_BUILDER_*.md | wc -l` against ledger line count.
- **`#`-prefix header → silent IDLE→DONE misclassification**: If the first non-empty line starts with `#` (e.g. `# STATUS_BUILDER_37 — IDLE — Fri Aug 14 …`) and the IDLE token is NOT wrapped in `[brackets]`, the Pass 2 fallback `re.match(r"\[([^\]]+)\]", state_line)` returns `None` because `re.match` anchors at position 0. State stays `UNKNOWN`, and the Step 2 mapping converts `UNKNOWN` → `DONE`. The builder appears `[DONE]` in the ledger despite being clearly IDLE in its status file. This inflates the DONE count — cross-check by grepping the raw STATUS files for `IDLE` lines with no `[IDLE]` bracket pair.
- **Self-reported `[BLOCKED]` may really be IDLE**: A builder can write `[BLOCKED]` in its own STATUS header for any reason. If the blocker reason (from the `blocker=` field) is "no task assigned", "awaiting assignment", or similar idle-language, it is IDLE masquerading as BLOCKED — not a genuine blockage. Cross-check the `blocker=` value before treating a `[BLOCKED]` ledger entry as actionable.
- **`[BLOCKED]` in ledger with no ALERTS file**: means the STATUS file itself contains a `[BLOCKED]` or `# BLOCKED` token — not an active alert. Check `HEARTBEAT_ALERTS.md` existence before treating it as a force-block.
- **State is NOT the same as freshness**: a `[DONE]` BUILDER may have been touched today (IDLE self-check). A `[IN-PROGRESS]` BUILDER may be stale from last week. Always cross-check mtime.

## Invocation
```bash
cd /home/hunter/Commander/eni_swarm && python3 monitor_fleet.py
```
Exit code 0 means the script ran (possibly processing 0 files if workdir is wrong) — NOT that the fleet is healthy. Verify ledger was actually written and has expected line count.