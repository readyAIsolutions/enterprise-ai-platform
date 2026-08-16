# Fleet cron monitor: two distinct fleets + HEARTBEAT_ALERTS semantics

Verified on the 2026-08-15 cron monitoring pass. Works alongside
`fresh-mtime-vs-liveness-probe-location.md` (interpretation) and
`templates/fleet-cron-report.md` (report shape).

## 1. There are TWO fleets / truth sources — a cron pass must check BOTH

Confusingly, the runtime hosts two independent fleet trackers:

1. **Builder fleet** — `STATUS_BUILDER_*.md` in `eni_swarm/builds/`.
   Parsed by `eni_swarm/monitor_fleet.py`, which writes `HEARTBEAT_LEDGER.md`
   (one line per builder: state / verified / blocker / next). ~49 builders.
2. **Master swarm** — `STATUS_ENI*.md` (eni_swarm/) + per-project `STATUS_*`
   (demiurge_scaffold/, recursive). Consolidated by `eni_swarm/status_hub.py`
   into `MASTER_STATUS.md` (hundreds of "minis": e.g. 598 minis → 207 DONE /
   388 IN-PROGRESS / 3 BLOCKED / 391 ALERTS).

The master hub's ALERT rule is well-defined in its header:
  **ALERT raised when STATE==BLOCKED, OR (STATE != DONE AND age > 10 min).**
  DONE minis are terminal; their age does not raise an alert.
So a large ALERT count almost always means a fleet of IN-PROGRESS minis whose
STATUS files haven't been touched in days/weeks — i.e. phantom/stalled, not live.

Run `monitor_fleet.py` (gives the builder ledger) AND read
`MASTER_STATUS.md`'s Summary block (gives the master swarm counts) — one without
the other gives an incomplete picture.

## 2. HEARTBEAT_ALERTS.md semantics (a real gotcha)

`monitor_fleet.py` reads `HEARTBEAT_ALERTS.md` (if present) and **forces BLOCKED**
on any `- BUILDER_<N>` line listed there. **If the file does not exist, that
override feed is gone** — blocked detection then relies *solely* on each STATUS
file's own `[BLOCKED]` token. When interpreting the ledger, note whether
`HEARTBEAT_ALERTS.md` is present; its absence silently weakens BLOCKED detection,
not an error, just a weaker signal.

## 3. Infra daemons are NOT builder workers — don't raise a false "fleet down"

`ps aux` will show several always-on infra processes that must NOT be read as
builders being alive:
  - `python -m eni_controller.controller serve --port 8940`
  - `swarm_turbocharger.py --port 8922`
  - `eni_kb_daemon`, `eni_local_chat.py`
A healthy-but-idle fleet shows ONLY these infra daemons running and NO builder
worker processes. Absence of builder procs + week-old STATUS mtimes ⇒ the fleet
is *parked/awaiting directive*, not crashed. Check FIFO count too: a parked fleet
has few/no `/tmp/eni_ctl_BUILDER_*` FIFOs (e.g. only 1 of ~49 present).

## 4. Report stance for the cron monitor

The cron monitor must NOT re-dispatch or create FIFOs (a re-dispatch agent does
that). Its job is to report: script exit status, builder-ledger distribution,
master-hub Summary block, staleness (oldest/newest STATUS mtime), the handful of
actionable BLOCKED minis (name + age), and whether infra vs. worker processes are
present. State clearly that week-old "IN-PROGRESS"/"BLOCKED" tokens are stale
relics, not live work.