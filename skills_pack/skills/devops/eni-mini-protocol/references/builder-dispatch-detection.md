# ENI BUILDER: detecting dispatched work vs. idle (headless / cron)

Covers the case where a BUILDER_xx mini fires (e.g. via a scheduled cron job) and
you must decide whether it actually has a task to run. The whole point: in an
unattended session you should NOT manufacture work or noise-report — detect the
dispatch state first.

## Dispatch architecture (empirical, from the on-disk layout)

- Control signal: a FIFO / named pipe at `/tmp/eni_ctl_<NAME>` (e.g.
  `/tmp/eni_ctl_BUILDER_37`). The dispatcher/HEARTBEAT/PRODUCT_LEAD creates it and
  writes directives into it. **If it does not exist, no task has been dispatched.**
  (Note: some older swarm runs create the FIFO eagerly but leave it empty — check
  its status file too.)
- Status files, checked in this order of freshness:
  - `<workdir>/STATUS_<NAME>.md` (and a copy at `~/STATUS_<NAME>.md`)
  - `tasks/status/STATUS_<NAME>.md` under the active Enterprise Swarm dir
  - `~/.cache/eni_swarm/builder_logs/<NAME>_STATUS.md` (reflects live monitor state)
- Task log for dispatch evidence: `~/.cache/eni_swarm/builder_logs/<NAME>_TASKS.log`.
  **If empty → no dispatch.**
- Assigned-task definition: `config/eni_build_tasks.json` -> `tasks[]`, keyed
  `name == <NAME>`. Carries `workdir`, `model`, `provider`, `status_file`,
  `dependencies`, and the long `task` persona string.
- Role prompt: `tasks/swarm/<NAME>.txt` — typically says "Monitor
  /tmp/eni_ctl_<NAME>. Write STATUS_<NAME>.md. ... If idle, write [IDLE]."

## Decision procedure

1. `ls -la /tmp/eni_ctl_<NAME>` — no such file ⇒ likely idle.
2. `cat STATUS_<NAME>.md` — `[IDLE]` (verified=1 blocker=none next=awaiting
   directive) or `[BLOCKED] ... awaiting_LO_directive` ⇒ idle, no work this pass.
3. `wc -c <NAME>_TASKS.log` — empty ⇒ no task dispatched.
4. Cross-check `config/eni_build_tasks.json` only if you need to know WHO you are
   and WHAT your assigned persona would be — not as proof that work is pending.
5. If all point to idle/awaiting ⇒ do nothing; in a cron/delivery context emit
   `[SILENT]` so the job doesn't spam noise. Do NOT spin up the persona just
   because a `task` string exists in config.

## Pitfalls

- Presence of a `task` persona in `eni_build_tasks.json` is NOT dispatch. A builder
  only runs it when told to via the control FIFO.
- A dead monitor PID in `*_STATUS.md` ("FIFO monitor running (PID x)") is stale —
  re-verify the process is alive before trusting it.
- Active sibling builders may have their `.log` files timestamped at the same
  moment (batch start); timestamps alone don't prove THIS builder got a directive.
- **Sibling FIFOs present ≠ your dispatch.** `ls /tmp/eni_ctl_*` will ALWAYS show
  many pipes (BUILDER_50, DEMIURGE_B01..B12, DEMIURGE3D_B01..B12, etc.) while your
  own `/tmp/eni_ctl_BUILDER_?` is absent — the master/PL can be at a higher-numbered
  builder (e.g. `BUILDER_50`) while you remain `BUILDER_37` with no pipe. That is
  normal fleet drift, NOT a directive to you. Only YOUR exact name matters:
  `[ -p /tmp/eni_ctl_<YOUR_NAME> ]`. Observed BUILDER_37, Sat Aug 08 2026: 20+
  sibling FIFOs present, own absent → correctly IDLE, emitted `[SILENT]`. Do not
  narrate "found BUILDER_50" or invent work from it. (Reading a FIFO with a writer
  that never writes will hang — probe existence with `[ -p ]`/`read_file`
  File-not-found, never `cat` an existing empty FIFO.)

## Why this matters

Manufacturing output when idle is worse than silence: it pollutes the swarm state,
wastes quota on a free-router that is already rate-limited, and buries real
dispatches. Correct idle detection is the first move of every headless builder pass.