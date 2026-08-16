# TRUST-TRAP: monitor_fleet.py ledger states ≠ builder liveness

The `[STATE]` token in `HEARTBEAT_LEDGER.md` is parsed from status-FILE TEXT, not
from any live process. A builder can be `[IN-PROGRESS]` in the ledger yet be
long-dead or never-started. **Do not report the ledger's IN-PROGRESS count as a
busy floor — cross-check staleness first.**

## Observed failure (real pass, Aug 08 2026)
- `monitor_fleet.py` produced: 8 IN-PROGRESS, 1 BLOCKED, 40 DONE/IDLE, 50 files.
- Reality: only **1** of the 50 STATUS files was fresh in the last 24h
  (STATUS_BUILDER_37, mtime today 15:50). All 8 "IN-PROGRESS" files were **~2
  weeks old** (last touched Jul 25). `pgrep` for builder/worker processes = **0**.
- Builder 37 was fresh but explicitly **IDLE** — "awaiting directive via
  /tmp/eni_ctl_BUILDER_37 FIFO" — i.e. alive dashboard writer, no active build.
- Verdict: control plane `/health` = all green (6/6), but the 50-builder build
  floor was effectively idle. This is a "healthy infra / stalled floor" split.

## Why it misleads
The script's state classifier treats any line bearing `IN-PROGRESS` + a marker
as `[IN-PROGRESS]`. `[IDLE]` is NOT a tracked first-class state — the fallback
maps unknown/non-BLOCKED to `DONE`, so an IDLE builder shows as `[DONE]` while a
stale IN-PROGRESS file shows as busy. Neither reflects reality.

## Minimum staleness gate before claiming "fleet is building"
For every STATUS_BUILDER_*.md in `/home/hunter/Commander/eni_swarm/builds`:
```python
age_min = (time.time() - os.path.getmtime(f)) / 60.0
```
- fresh (age < ~24h)  -> candidate "alive now"
- stale (age > ~7d)   -> corpse; ignore its `[IN-PROGRESS]` token
Then AND with a real process check:
```bash
pgrep -af 'hermes chat' ; pgrep -af 'eni_ctl_BUILDER'   # empty => floor is not live
```
Only report "N builders building" for builders that are BOTH mtime-fresh AND
have a live process / FIFO. If all files are stale + zero procs, the floor is
idle even when the ledger shows IN-PROGRESS.

## Healthy-infra / stalled-floor split (the useful summary shape)
When everything green but nothing fresh, distinguish clearly:
- INFRA healthy: controller :8940/health all ok (airllm, free_router, secrets,
  47/47 enterprise modules, hermes_runner, queue 0 pending).
- FLOOR idle/stale: N/50 status files >24h old, 0 worker procs, builders
  waiting on /tmp/eni_ctl_BUILDER_* FIFOs that don't exist.
Action, if LO expects active builds: create the FIFO + route a directive via
PRODUCT_LEAD; otherwise it is quiet steady-state and needs no intervention.