# Fleet Monitor — State Classification Gap: ACTIVE/BUILDING → DONE

The `monitor_fleet.py` script maps builder states to three ledger values: `DONE`, `IN-PROGRESS`, and `BLOCKED`. Its detection logic has a gap for builders that use `ACTIVE` or `BUILDING` as their state token instead of `IN-PROGRESS`.

## How the script classifies states

1. **First pass** — scan all lines of the builder's STATUS file for:
   - `[IN-PROGRESS]` or `# STATE: IN-PROGRESS` (bracket/STATE keyword + "IN[-_ ]?PROGRESS") → mapped to `IN-PROGRESS`
   - `BLOCKED` keyword with a `[` or `STATE` or `STATUS` or `BLOCKED` nearby → mapped to `BLOCKED`

2. **Fallback** — first non-empty line, extract `[STATE_TOKEN]` via regex `\[([^\]]+)\]`. If found, use that token; if not, `state = "UNKNOWN"`.

3. **Map** — `BLOCKED` → `BLOCKED`, `IN-PROGRESS`/`IN_PROGRESS` → `IN-PROGRESS`, everything else (including `UNKNOWN`, `ACTIVE`, `BUILDING`, `READY`, `IDLE`) → `DONE`.

## The gap

A builder file with a header like:
```
# STATUS_BUILDER_13 — ACTIVE — Sat Jul 25 16:17 MDT 2026
**State:** BUILDING
```
or
```
# STATUS BUILDER 22
## STATE: ACTIVE
```
or
```
# STATUS_BUILDER_37 — IDLE — Fri Aug 14 15:57 2026
```

will be classified as `DONE` in the ledger, even though the builder is actively working (ACTIVE/BUILDING) or is idle-yet-live (IDLE). The words `ACTIVE`, `BUILDING`, and `IDLE` are not in the IN-PROGRESS or BLOCKED matchers, so they hit the `else → DONE` branch.

**IDLE is not DONE.** An IDLE builder has a live watchdog/status process but no current task — fundamentally different from a builder whose project is complete. IDLE builders should be treated as available workers, not completed tasks. When the ledger shows `[DONE]` and the raw STATUS file says `IDLE`, reclassify as IN-PROGRESS (available).

## Impact

- When reading the LEDGER, a builder showing `[DONE]` with `verified=unknown` and `blocker=unknown` may actually be in the middle of work.
- When cross-checking `HEARTBEAT_LEDGER.md` against builder STATUS files, **always inspect the STATUS file directly** for builders where the state seems uncertain. A `[DONE]` entry with no verified/blocker/next metadata is suspicious.
- The script's summary is useful but not authoritative — always spot-check a few ACTIVE-looking builders.

## Affected builders (known examples)

| Builder | STATUS file header | Script classifies as | Actual state |
|---|---|---|---|
| BUILDER_13 | `ACTIVE` + `**State:** BUILDING` | DONE | IN-PROGRESS (LUMEN AppImage/polish) |
| BUILDER_22 | `ACTIVE` via `## STATE: ACTIVE` | DONE | IN-PROGRESS |
| BUILDER_37 | `IDLE` via `# STATUS_BUILDER_37 — IDLE —` | DONE | IDLE (live watchdog, no task) |
| BUILDER_04 | `[READY]` | DONE | DONE (ready/idle is correctly DONE) |

## Workaround when reading the ledger

If the ledger shows a builder as `[DONE]` with `verified=unknown` (no task-specific metadata), check the raw STATUS file's first 3 lines. If it says `ACTIVE`, `BUILDING`, or `IDLE`, manually reclassify as `IN-PROGRESS` (actively working or available).

## Longer-term fix

Patch `monitor_fleet.py` to add `ACTIVE`, `BUILDING`, and `IDLE` to the IN-PROGRESS matcher:
```python
# In the first-pass detection loop, change:
if re.search(r"IN[-_ ]?PROGRESS|ACTIVE|BUILDING|IDLE", ul)
```
Alternatively, add an explicit `IDLE` → `AVAILABLE` ledger state so it's distinguishable from DONE at a glance.