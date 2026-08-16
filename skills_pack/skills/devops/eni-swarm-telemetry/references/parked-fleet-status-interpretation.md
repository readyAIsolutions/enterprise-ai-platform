# Parked-fleet status interpretation (how to read a quiet swarm)

The most common false alarm in fleet monitoring: reading the `[IN-PROGRESS]` / `[BLOCKED]`
tokens in status files as *active work* when the fleet is actually **parked/idle**.
This is the single most valuable interpretation to get right before reporting.

## Golden rule: FRESHNESS (mtime) is the real signal, NOT the state token

```
State tokens are only trustworthy if the status file was touched recently.
```

A `[IN-PROGRESS]` row in the ledger on a status file whose mtime is 2 weeks old is
**not busy** — it's a stale marker left from when the builder last ran. The builder is
idle/parked, not progressing. Before ever reporting "N builders stuck / in progress",
check the mtime AND read the header line.

## Parked-fleet signature (all four together = parked, NOT broken)

1. **Freshness very low:** only 0–1 status files updated in the last day; e.g. 49 of 50 stale.
   The one fresh file typically says `IDLE — awaiting LO's directive via /tmp/eni_ctl_BUILDER_N`.
2. **0 live builder processes** (`ps aux | grep -iE 'STATUS_BUILDER|claude|cmdk'` → none).
3. **Infra procs still alive** (gateway, airllm server, claude_cli_proxy, swarm_turbocharger,
   hermes chat) → the *monitor/controller* is healthy; the *fleet* is just parked.
   This is exactly how you tell a parked fleet from a dead monitor/controller.
4. **Stale non-DONE rows' headers say so:** the file's own header reads
   *"awaiting LO directive"`, `"no task assigned"`, `"awaiting PRODUCT_LEAD dispatch"` —
   i.e. it's an idle worker waiting for routing, not a stuck worker.

When all four hold, report: **fleet PARKED/IDLE, awaiting LO directive or FIFO routing.** Do not
report the stale IN-PROGRESS/BLOCKED ledger rows as breakdowns or zombie builders.

## Correct probe invocation (avoid the misleading zero)

`fleet_liveness_probe.sh` must run from the swarm dir OR receive the dir as `$1`:

```bash
cd /home/hunter/Commander/eni_swarm && bash .../fleet_liveness_probe.sh
# or: bash .../fleet_liveness_probe.sh /home/hunter/Commander/eni_swarm
```

Run from the wrong cwd it prints `0 status files found` + `NONE running` — which looks like a
dead fleet but is a bad path. Always re-check cwd before declaring the fleet dead.

## Ledger integrity check (quick)

```bash
cd /home/hunter/Commander/eni_swarm && python3 monitor_fleet.py  # ALWAYS python3 (bare python not on cron PATH)
LEDGER=HEARTBEAT_LEDGER.md
for f in builds/STATUS_BUILDER_*.md; do
  num=$(basename "$f" | sed -E 's/^STATUS_BUILDER_0*//; s/\.md$//')
  grep -qE "BUILDER_${num} " "$LEDGER" || echo "MISSING: $(basename "$f") ($(stat -c%s "$f") bytes, $(stat -c%y "$f" | cut -d. -f1))"
done
```

Expected: the ONLY missing file is the 0-byte crash-guard skip (e.g. `STATUS_BUILDER_20.md`,
0 bytes). Any OTHER non-zero file missing = a real gap.
Sanity: ledger rows should equal (# disk files − # zero-byte files). In the observed healthy
run: 50 on disk, 1 zero-byte → 48 ledger rows ≈ correct (builder numbering is 1-indexed, so
row echo is not exactly file count; reconcile by the grep above, not arithmetic).

## Minimal report for LO (heartbeat style)

- Monitor result: ledger regenerated, N rows, integrity OK/one gap.
- Fleet state: PARKED/IDLE (or ACTIVE/PROGRESSING) + the 4-point evidence.
- Non-DONE rows: list them but explicitly label stale ones as parked-idle, not busy.
- If so: "awaits LO directive / FIFO routing — the only living signal is BUILDER_N sitting
  IDLE waiting for /tmp/eni_ctl_BUILDER_N."