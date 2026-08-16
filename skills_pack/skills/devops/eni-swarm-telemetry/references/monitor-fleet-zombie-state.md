# monitor_fleet.py — zombie-state pitfall (ledger overstates activity)

Location: `/home/hunter/Commander/eni_swarm/monitor_fleet.py` (cron run).

What it does: reads `builds/STATUS_BUILDER_*.md`, parses a state token
(`[IN-PROGRESS]` / `# STATE: ...` / `BLOCKED` / `[DONE]` / `[IDLE]`), applies
`HEARTBEAT_ALERTS.md` blocked-builder overrides, and writes
`HEARTBEAT_LEDGER.md` (one line per builder).

## THE PITFALL
`monitor_fleet.py` performs **NO liveness / freshness check**. It re-labels a
STATUS file as `IN-PROGRESS` / `BLOCKED` purely from the stale file's embedded
state token. Real observed failure (2026-08-12):
- Ledger reported **8 builders IN-PROGRESS** (5,17,25,32,38,39,42,44) + **1 BLOCKED** (46).
- All of those STATUS files were **~17.8 days stale** (mtime 2026-07-25/26).
- **Zero** builder/hermes-chat processes were actually running — the fleet was dormant.
- Only builder 37 had a fresh STATUS file (updated that morning) and it was `IDLE`.

So the heartbeat OVERSTATED activity and would have looked healthy when the
builder floor was actually stalled.

## GROUND-TRUTH CHECKS (do these before trusting the ledger)
1. **Process liveness:** `ps aux | grep -iE "hermes-chat|STATUS_BUILDER|eni_swarm"`
   — expect actual builder workers, not just infra. Infra-only leftovers
   (e.g. `eni_controller serve :8940`, `swarm_turbocharger.py :8922`,
   `eni_local_chat.py`) are the control plane, NOT builders — their presence
   does not mean the floor is producing.
2. **STATUS mtime staleness:** for each builder, `stat -c %Y` vs `date +%s`.
   Anything older than ~30 min is not actively working.
   `scripts/fleet_mtime_staleness.py` exists for this.
3. **Control FIFOs:** `/tmp/eni_ctl_*` present but idle (no `prw` consumer reading)
   = scaffolding, not work.
4. **windows:** no swarm/builder windows on `:0` corroborates a down floor.

## Recommended fix (if a future session touches monitor_fleet.py)
Treat builders whose STATUS mtime exceeds a stale threshold (e.g. >30 min) as
`STALLED` (or drop them from IN-PROGRESS) instead of trusting the embedded
state token. That way HEARTBEAT_LEDGER.md reflects real liveness, matching the
liveness-probe philosophy this skill already preaches.