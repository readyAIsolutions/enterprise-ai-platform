# Fleet Monitor — Liveness Cross-Check: Is the Fleet Actually Running?

The ledger shows builder states, but stale STATUS files can persist for weeks after a
builder process dies. This reference covers how to determine **true fleet liveness**
by cross-referencing process lists, FIFOs, and file modification times.

## Two layers — do NOT conflate "control plane" with "builder floor"

- **Control plane (infra daemons):** `eni_controller ... serve --port 8940`,
  `eni_kb_daemon`, `eni_local_chat`, `swarm_turbocharger ... --port 8922`. These persist
  across floor dormancy and keep running even when ZERO builders are live.
- **Builder floor:** the `builds/STATUS_BUILDER_*.md` files + per-builder control FIFOs
  (`/tmp/eni_ctl_BUILDER_*`). A parked floor can have control-plane daemons UP and only
  a single surviving FIFO (observed: only `BUILDER_50` on a 50-builder floor).

**Parked floor ≠ dead swarm.** Always report both layers, e.g.
"Control plane UP (daemons + FIFO), builder floor DORMANT." A floor-parked verdict that
omits control-plane liveness misleads LO into unnecessary cold-restart work.

## The three-question liveness test

### 1. Are any builder processes running?

```bash
ps aux | grep -i "builder\|freed_swarm\|demiurge\|hermes\s*run" | grep -v grep
```

If this returns zero results, the fleet is **fully idle** regardless of what STATUS
files say. No builder is running code.

**PITFALL — pass-script self-PID false positive:** `fleet_monitor_pass.py` greps
`builder|eni_swarm` in `ps` and will always match its OWN transient bash wrapper + its own
python invocation. Discount those; a "BUILDER PIDS" line listing only the wrapper/python
you just ran means zero real workers (also applies to the manual grep above — filter out
your own command).

### 2. Are any control FIFOs alive?

FIFOs (named pipes at `/tmp/eni_ctl_BUILDER_*`) are the builder-control channels.
Each active builder should have one. Check:

```bash
ls -lt /tmp/eni_ctl_BUILDER_*
```

Signals:
- **Zero FIFOs** — no builder can receive signals. Even if STATUS files say
  IN-PROGRESS, no builder has a live channel.
- **Fewer FIFOs than STATUS files** — only that subset of builders has a live
  control channel. The rest are dormant/orphaned.
- **FIFO mtime >24h old** — builder may have died without cleaning up its FIFO.
  FIFOs persist in the filesystem even after the creating process exits.
- **Few/1 surviving FIFO + no recent mtimes** = parked floor, control mechanism intact,
  waiting on a live-session re-drive directive (not a cold restart).

### 3. When were the STATUS files last modified?

```bash
# Find the most recent modifications
find builds/ -name 'STATUS_BUILDER_*.md' -printf '%T@ %p\n' | sort -rn | head -10

# Count files by staleness bucket
find builds/ -name 'STATUS_BUILDER_*.md' -mtime +30 -printf '.' | wc -c  # >30 days
find builds/ -name 'STATUS_BUILDER_*.md' -mtime -7 -printf '.' | wc -c   # <7 days
```

If the most recent mtime is older than a few hours (or even days), and the swarm
is supposed to be active, something is wrong. Stale IN-PROGRESS with no
corresponding process = orphaned status.

**IDLE self-check vs. real churn:** a single newer file whose head reads `IDLE` and whose
FIFO is confirmed absent = daily IDLE self-check, NOT a live task. Do not count it as
activity. Real churn = multiple builders touched recently.

## Putting it together: interpretation matrix

| Processes? | FIFOs? | Recent mtime? | Verdict |
|------------|--------|----------------|---------|
| Yes | Yes | Yes | **Fleet active.** Ledger reflects current state. |
| No | Yes | Stale | **Mostly dead.** FIFOs are artifacts. Processes died; STATUS files not cleaned. |
| No | No | Stale | **Fully idle.** All builders exited. Ledger is a historical snapshot. |
| No | No | Mixed | **Partial collapse.** Some builders completed (recent DONE), others orphaned mid-task (stale IN-PROGRESS). |
| Yes | No | Yes | **Degraded.** Builders running but control plane missing — FIFO setup failed. Tasks may be stuck. |
| No | 1–few (stale) | Stale | **Parked floor, control-plane UP.** Infra daemons alive, no real churn. Awaiting directive. |

## Common fleet-states observed in production

| State | Pattern | Response |
|-------|---------|----------|
| **All DONE, no processes** | Ledger: 40+ DONE, no FIFOs, no builder procs | Fleet completed its work. Awaiting next directive. Prune stale STATUS files or leave as historical record. |
| **DONE + stale IN-PROGRESS, no procs** | Ledger: majority DONE, some IN-PROGRESS from 3+ weeks ago, no builder procs | Those builders died mid-task. STATUS files are orphaned. Flag as stalled — PRODUCT_LEAD needs to reassign. |
| **BLOCKED with no FIFO** | 1+ BLOCKED in ledger, no active FIFO for that builder | The blocker may have been resolved but status never updated. Check raw file for actual blocking condition. |
| **IDLE builders mapped to DONE** | Ledger says DONE but raw STATUS says IDLE, no FIFO | Script misclassification. Builder was a free worker that timed out. Its status should be pruned or reassigned. |

## Quick one-liner

For a complete liveness scan in one command:

```bash
echo "--- PROCESSES ---" && ps aux | grep -iE "builder|freed_swarm|demiurge" | grep -v grep | awk '{print $11, $NF}' && echo "--- FIFOs ---" && ls -lt /tmp/eni_ctl_BUILDER_* 2>/dev/null | head -5 && echo "--- RECENT STATUS ---" && find builds/ -name 'STATUS_BUILDER_*.md' -printf '%T+ %p\n' 2>/dev/null | sort -rn | head -5
```