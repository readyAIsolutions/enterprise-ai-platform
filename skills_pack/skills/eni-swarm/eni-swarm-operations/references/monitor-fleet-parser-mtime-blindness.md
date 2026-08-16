# monitor_fleet.py Parser — Mtime Blindness (False IN-PROGRESS)

## Symptom
`monitor_fleet.py` maps builder state **entirely from the bracket token** at the top of each STATUS file — e.g. `[IN-PROGRESS]`, `[BLOCKED]`, `[DONE]`, `[IDLE]`. It does **not** cross-reference file mtime or file body semantics.

**Result:** A 20-day-old STATUS file whose first line reads `[IN-PROGRESS] BUILDER_05 — 2026-07-25 16:13 MDT` but whose body says "awaiting task assignment" will show `[IN-PROGRESS]` in the ledger. The ledger is a lie.

## Why it matters
- The cron reads the ledger and reports "8 IN-PROGRESS builders" — but those 8 have not been touched in 20 days. The swarm floor is actually **dormant**, not partially active.
- A human or agent reading only the ledger (without an mtime cross-check) gets a misleading impression of swarm health.
- The parser's fallback chain:
  1. If `[IN-PROGRESS]` or `[IN_PROGRESS]` → `IN-PROGRESS`
  2. Else if `[BLOCKED]` → `BLOCKED`
  3. Else → `DONE` (catch-all, includes `[IDLE]`)
  There is **no DORMANT / STALE state** in the model.

## Detection
Always follow ledger read with an **mtime cross-check**:
```bash
stat -c '%y %n' builds/STATUS_BUILDER_*.md | sort
```
Compare the IN-PROGRESS builders' mtimes against the current time. If every IN-PROGRESS file is older than, say, 6 hours, the fleet is dormant — not actively building.

## Mitigation until script is fixed
- When reporting, **annotate** each IN-PROGRESS entry with `age=NNh` from the mtime scan.
- Flag any IN-PROGRESS entry older than 1 hour as **STALE** in the narrative, regardless of its bracket token.
- Do not edit builder STATUS files from this cron — the script is report-only.

## Long-term fix (not yet implemented)
The script's `parse_state()` function should accept an optional `max_age_seconds` parameter. If the file's mtime exceeds it and the mapped state is IN-PROGRESS, downgrade to STALE. The HEARTBEAT_LEDGER.md should use a `[STALE]` tag instead of `[IN-PROGRESS]` for these.

## Proven 3-pronged verification sequence (used by the fleet-monitor cron)
`monitor_fleet.py` alone is NEVER sufficient for a health report. Always run all three:

1. **mtime cross-scan** — flag every IN-PROGRESS/BLOCKED entry older than ~1h as STALE:
   ```bash
   stat -c '%y %n' builds/STATUS_BUILDER_*.md | sort
   ```
   In a typical dormant fleet ALL files carry the same old sweep timestamp (e.g. a single day), and only a handful are freshly touched — that is the dormancy signature. An isolated recent mtime means one builder was touched by a cron watchdog.

2. **live window count** — counts builder terminals that are alive RIGHT NOW:
   ```bash
   python3 fleet_pulse.py --once
   # => [HH:MM:SS] ENI PULSE | windows=0 | stalls: none | gate=RED
   ```
   `windows=0` + `gate=RED` = floor down, regardless of how many `[IN-PROGRESS]` tokens the ledger shows. This is the ground truth that overrides the parser.

3. **process scan** — catches stragglers that survive the floor teardown:
   ```bash
   pgrep -af "hermes-chat|BUILDER_|swarm"
   ```

**turbocharger health probe** (reverse-model proxy, port 8922):
```bash
curl -s -m 5 http://127.0.0.1:8922/health
# => {"status":"ok","proxy":"swarm_turbocharger","concurrency":50,"signal":-58}
```
Include this in a fleet report when the floor is down — a healthy turbocharger means the proxy layer is fine and the dormancy is a launch issue, not an infra one.

## Pitfall — lingering `cat` on a control FIFO blocks writers
After a floor teardown a stray `cat /tmp/eni_ctl_BUILDER_N` (and the surrounding `/usr/bin/bash -c source /tmp/hermes-snap-*.sh ... eval 'cat /tmp/eni_ctl_BUILDER_50 ...`) process can survive with the FIFO open for read. A process holding a FIFO for read **blocks any writer** (open-for-write hangs until a reader exists — but the reader is already there and never closes). Before reviving a builder, kill holders:
```bash
pgrep -af "cat /tmp/eni_ctl_BUILDER_"   # find them
pkill -f "cat /tmp/eni_ctl_BUILDER_"    # clear so writers can open
```