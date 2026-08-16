# Heartbeat cron: reading the fleet correctly (parked vs stalled)

Written after an unattended cron run of `monitor_fleet.py` / `HEARTBEAT_LEDGER.md`
on the ENI swarm (`/home/hunter/Commander/eni_swarm/`). The rule below is the
single most important thing a heartbeat/scheduled-fleet-status pass must get right.

## The core rule
**Never treat a stale status file as a stall, and never treat a quiet fleet
as a failure.** A fleet that is *parked* (not dispatched) is a normal, healthy
state — the correct output is "no action required," not an alert.

Two traps, both seen together in one real run:

1. **Stale `[IN-PROGRESS]` ≠ actually working.** Status files whose text says
   `[IN-PROGRESS]` but whose mtime is ~20 days old (e.g. Jul 25 in an Aug run)
   are **parked remnants of an old cycle**, not live builders. The text state
   token is NOT the truth; **mtime freshness + live processes are the truth.**

2. **The fleet does not ask you to invent work.** A genuinely fresh status file
   (touched today) can still be an idle/waiting state. In one run,
   `STATUS_BUILDER_37` (fresh, 08:56) read literally:
   > "IDLE — do not invent work. Cron dispatch frame is a scheduling template,
   >   not an assignment. blocker=none. Await LO's directive via FIFO creation."

   When a status file explicitly says NOT to invent work, the correct heartbeat
   output is **report the parked state and stop**. Do not repurpose a cron
   template string into a fake task assignment.

## Truth signals ranked (use all of them)
- `fleet_liveness_probe.sh` (SKILL-BUNDLED under this skill) — the authoritative
  one-shot: disk count vs ledger count, ledger state distribution, mtimes,
  live processes, control FIFOs, and a read of the freshest status file.
- `fleet_mtime_staleness.py` — mtime-based staleness; call it from the *right*
  cwd so it finds the status files (it resolves a `builds/` subdir or cwd).
- `monitor_fleet.py` / `HEARTBEAT_LEDGER.md` — the parse/ledger layer only;
  it does NOT detect liveness. Treat it as the data source, never as the verdict.

## Freshness math that flags a real problem
- `fresh_today` → number of status files touched within the current day.
- `newest N mtimes` → the cliff: in a live swarm you see recent timestamps
  spread across builders; in a parked swarm the cliff is ~20 days with only a
  handful of today-touched files (often an IDLE "please wait" status).
- `live builder processes = NONE` + stale mtimes ⇒ parked, healthy.
- `live builder processes = NONE` + *recent* mtimes across many builders with
  no progress ⇒ this is the rare case worth flagging (a checker could be
  writing status without doing work).

## When an infra pass is flagged but no builder is working
The fleet sits ON TOP of infrastructure. On a parked fleet the surrounding
services being alive confirms "healthy-idle, not broken":
- hermes gateway + chat PTYs, `claude_cli_proxy` (:8912), `free_router` (:8920),
  `swarm_turbocharger` (:8922), `eni_local_chat`, Demiurge Odoo+Postgres,
  `tmux eni2p` — all up ⇒ the box is fine; only builders are idle.
- Control FIFOs exist but no builder owns them (`/tmp/eni_ctl_*`) ⇒ no directive
  issued ⇒ builders correctly idle.

## Output format for an unattended (cron) run — keep it decisive
- Lead with a one-line verdict, e.g. **"Fleet parked, not stalled — no action required."**
- Table: state × count from the ledger.
- List the stale IN-PROGRESS/BLOCKED rows and label them *parked*.
- Quote the freshest status file's actual text when it states IDLE/do-not-invent.
- Recommend the *resume path* (create/attach a control FIFO, e.g.
  `/tmp/eni_ctl_BUILDER_N`, or dispatch via master/PRODUCT_LEAD) and say no
  autonomous action was taken.