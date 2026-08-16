# Fleet monitor cron — repeated-idle state (verified Aug 2026)

Session-verified procedure for the recurring `monitor_fleet.py` cron; confirms the
repeated-state suppression guidance and pins the correct probe path.

## Verified probe path (pitfall)
The skill ships `scripts/fleet_health_probe.sh`, but its **absolute path includes the
`devops/` category subdirectory** — invoking it WITHOUT `devops/` fails with
`No such file or directory`. Correct invocation from anywhere:

```bash
bash /home/hunter/.hermes/skills/devops/eni-swarm-floor-recovery/scripts/fleet_health_probe.sh
```

Do NOT `cd` into `eni_swarm/` first; the script locates its own workdir.

## The monitor run
1. `cd /home/hunter/Commander/eni_swarm && python3 monitor_fleet.py` regenerates
   `HEARTBEAT_LEDGER.md`. Symlinks/empty files pass the crash guard (0-byte status files
   are skipped).
2. Check STATUS file freshness (mtimes), not just ledger states — stale flags are the
   real signal.
3. Run the probe above for the four axes (builder floor / :8420 dashboard /
   :8922 turbocharger / controller).

## Repeated-state suppression (the decision that matters)
Aug 16 06:04→06:16 MDT, five consecutive firings produced an **identical** picture:
bridge floor parked since Jul 25, ledger 40 DONE / 8 stale IN-PROGRESS / 1 BLOCKED,
`gate=RED`, `windows=0`, `stalls=none` (dashboard :8420 down as before, turbocharger
:8922 + controller healthy). No new alerts, nothing advanced.

→ Per `monitor_cron_diagnostics.md` "Repeated-state suppression", the correct output is
`[SILENT]` — the idle state is a durable condition, not a per-firing failure, and
repeating the same report every cron tick desensitizes LO. Silence is correct when:
- gate=RED + windows=0 + stalls=none + no new alerts, AND
- prior-firing session confirms the identical state (use `session_search` to verify
  before suppressing).

## Interpreting common stale markers
- `BLOCKED BUILDER_46` with "no task assigned, awaiting PRODUCT_LEAD dispatch" — not a
  real blocker, just an unassigned builder; treat as idle, not failure.
- 8 stale IN-PROGRESS (B05/17/25/32/38/39/42/44) — leftover Jul 25 mid-task markers for
  Demiurge packaging / PRODUCT_LEAD resurrection; no runner alive on disk.
- `BUILDER_20` 0-byte status file — crashed/truncated write; crash guard skips it.
- `BUILDER_37` (newest, IDLE) — awaiting `/tmp/eni_ctl_BUILDER_37` FIFO directive.