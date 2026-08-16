# Fleet-liveness process + FIFO probe — grep gotchas (confirmed 2026-08-16)

When corroborating DORMANT vs live on the fleet-monitor cron (see
`fleet-staleness-interpretation.md`), process liveness and control-FIFO census
are the two truth sources besides STATUS-file mtimes. Both have grep noise
traps that can make a parked fleet LOOK busy — or flood the report.

## Trap 1: `ps ... | grep -i worker` matches kernel threads
`ps aux | grep -iE "swarm|orchestr|master_driver|worker"` returns dozens of
`root ... [kworker/0:0H-kblockd]`, `[kworker/1:1-mm_percpu_wq]`, etc. Kernel
worker threads match the substring `worker` and are pure noise. They are NOT
swarm processes.

Correct liveness probe — exclude kernel threads AND only match the real
swarm/controller proc names:
```bash
# pick the builder/worker-name grep, never bare "worker"
ps aux | grep -iE "master_driver|eni_swarm|orchestrat|worker_pool|BUILDER" \
  | grep -v grep | grep -v "kworker"
```
Empty output + no fresh STATUS mtimes (24h) => solid DORMANT, same as the
mtime-only verdict. In practice the only ENI-adjacent daemons you'll see on a
parked fleet are `eni_kb_daemon`, `eni-controller ... serve --port 8940`,
`swarm_turbocharger.py --port 8922`, and `eni_local_chat.py` — those alone are
NOT evidence of active building.

## Trap 2: FIFO census is a liveness signal worth capturing
A parked fleet has almost no control FIFOs. `/tmp/eni_ctl_BUILDER_*` count:
`ls /tmp/eni_ctl_BUILDER_* 2>/dev/null | wc -l`. On the confirmed 2026-08-16
dormant run there was exactly **1** (only BUILDER_50), and BUILDER_37's own
STATUS file explicitly re-verified its FIFO was absent (`[ -e ] NO_ENTRY`).
Near-0 FIFO count + no builder procs + stale mtimes triples the DORMANT
verdict. Report the FIFO count, don't just assert "no FIFOs".

## Optional harness for the cron (compute-don't-dump)
Re-runnable one-shot pass is `scripts/fleet_monitor_pass.py` (handles
zero-padded `STATUS_BUILDER_0N.md` and empty-file crash-guard). It can also
emit the FIFO count. Pair with `ls /tmp/eni_ctl_BUILDER_* | wc -l` and the
proc probe above to conclude "fleet parked, not actively processing" without
dumping the whole ledger.