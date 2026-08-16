# Fleet monitor pass — "fleet fully idle" interpretation (+ filename parsing pitfall)

Recorded from a cron pass Aug 2026 where the whole 50-builder fleet was parked
(world had moved on from active parallel builds). Useful as a **baseline/snapshot
interpretation** the next time everything reports c old or idle.

## What a fully-idle fleet looks like
- `monitor_fleet.py` exits 0, `HEARTBEAT_LEDGER.md` regenerates with all N builders parsed.
- **mtime scan**: 49/50 `STATUS_BUILDER_*.md` files are ~3 weeks old; only one builder
  self-touched recently. That one fresh file is `IDLE`, not IN-PROGRESS.
- The 8 `IN-PROGRESS` ledger entries come from STALE Jul-dated files, NOT live work.
  Always cross-check ledger state against file mtimes before calling anything active.
- Control-plane/worker separation: `ps` shows controller + router + daemon procs alive
  (hermes, eni_controller.controller, eni_local_chat.py, eni_kb_daemon, free_router,
  swarm_turbocharger) but **no builder worker** procs. Control plane up ≠ builders building.

## Distinguishing a REAL block from an alert override
- `monitor_fleet.py` reads `HEARTBEAT_ALERTS.md`; any `- BUILDER_(\d+)` line forces that
  builder to `[BLOCKED]`.
- **If `HEARTBEAT_ALERTS.md` does NOT exist**, the `[BLOCKED]` in the ledger is the genuine
  on-disk `[BLOCKED]` token from the STATUS file (e.g. "no task assigned, awaiting
  PRODUCT_LEAD dispatch"), not a script-applied override. Say so explicitly.

## Zero-padded STATUS filename pitfall
Status files are often zero-padded: `STATUS_BUILDER_04.md` → `<regex STATUS_BUILDER_(\d+)>`
groups to `4` → ledger shows `BUILDER_4`. So `ls STATUS_BUILDER_5.md` returns nothing while
the file is actually `STATUS_BUILDER_05.md`. Don't trust a `ls` of the non-padded name to
conclude the file is missing — check the padded variant / glob first.

## FIFO truth source for liveness
`ls /tmp/eni_ctl_BUILDER_*` shows which control FIFOs actually exist. A builder whose
STATUS file is fresh but whose named FIFO is absent is truly idle (no directive was ever
issued — e.g. BUILDER_37: verbose note re-verified "no /tmp/eni_ctl_BUILDER_37, only
BUILDER_50 + DEMIURGE* FIFOs present"). FIFO presence > STATUS heuristic for "is anyone
talking to this builder."

## Report style (LO's fleet-status cron)
Lead with: monitor exit code + ledger regenerated → overall verdict (idle/stale/active).
Then a live-builders section (fresh files only), an attention list (GENUINE blocks, absent
alerts file), then the process check. Close with an actionable bottom line (which builders
await dispatch / FIFO recreation). Keep it terse — this lands in the middle-monitor pulse.