# status_hub.cron.log spin-loop diagnostic — telling "dormant" from "live"

Verified 2026-08-14 fleet-monitoring cron pass.

## The signal

During a fleet-health pass, tail `status_hub.cron.log` (in `eni_swarm/`). If
every recent line is **byte-for-byte identical** with a FIXED stale aggregate
(e.g. `598 minis (207 done / 388 in-progress / 3 blocked), 391 ALERTS`) and the
file just grows with repeats, that is a **spin loop, NOT a live fleet**:

```
MASTER_STATUS.md refreshed: 598 minis (207 done / 388 in-progress / 3 blocked), 391 ALERTS -> ...
MASTER_STATUS.md refreshed: 598 minis (207 done / 388 in-progress / 3 blocked), 391 ALERTS -> ...
```

It means the status_hub cron keeps regenerating `MASTER_STATUS.md` from a frozen
template / upstream count that never changes. The fleet behind it is dormant —
nobody is producing new STATE transitions. Do NOT read the constant aggregate as
"598 minis actively running". Corroborate with liveness facts:

- Linear `tail` growth of the log with zero content variation.
- All `STATUS_BUILDER_*.md` mtimes ~weeks old (see `fresh-mtime-vs-liveness-probe-location.md`).
- `ps aux | grep -iE 'swarm|builder|master'` shows no builder/master/driver proc
  (only unrelated leftovers, e.g. an odoo daemon using the DB user, a turbocharger).
- Control FIFOs mostly gone: `ls /tmp/eni_ctl_BUILDER_* | wc -l` far below the
  expected builder count. A lone leftover FIFO (e.g. only BUILDER_50, created days
  earlier) is a relic, not proof of a live rig.
- `MASTER_STATUS.md` / `STATUS_MASTER.md` may still say State: RUNNING with an OLD
  `Updated:` timestamp — a stale status marker, not a live process.

## Interpretation & response

- Dormant ≠ crashed necessarily; may be a deliberate rest. Report the dormancy
  plainly rather than presenting ledger DONE counts as completed/fresh work.
- If LO expects live builds, flag it for a relaunch (`eni_launch.sh` / master
  driver) — the monitor cron itself must NOT re-dispatch (it's read-only).
- The spin-loop check is cheap and definitive: `tail -n 5 <log> | sort -u` yields
  one distinct line when stuck. Use it as a first gate before deeper triage.
