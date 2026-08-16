# ENI Builder Task Diagnostics — "is there actually a task to process?"

Origin: cron/scheduled instruction fired asking to "process ENI builder task" for
`/tmp/eni_ctl_BUILDER_37`. Investigation showed NO such task existed. This is the
reusable workflow for deciding whether an ENI build task is real before acting on it.

## Trigger
Any queued/scheduled prompt that references a specific builder control FIFO or
says "process the builder task" / "run the ENI swarm job for <NAME>". Before doing
ANY work (spawning builders, writing task JSON, delegating), verify the floor state.

## The diagnostic sequence (in order, stop when it resolves)

1. **Ctl FIFO exists?** `ls -la /tmp/eni_ctl_*`
   - ENI builder control pipes are per-builder named FIFOs: `eni_ctl_BUILDER_<N>` or
     `eni_ctl_<PROJECT>_B<NN>` (e.g. DEMIURGE3D_B01..B11).
   - Builder indices are EPHEMERAL — they get rotated/cleaned up. If the referenced
     `<N>` is gone, the builder was rotated away or the task was never submitted.

2. **Is anything attached to the FIFO?** `timeout 5 lsof <fifo>`
   - No open reader/writer = no live builder behind it, even if the pipe file exists.

3. **Controller queue empty?** `curl -s localhost:8940/status` → `queue.pending`
   - The ENI Hermes Controller (served from `/home/hunter/.hermes/controller`, started
     via `python3 -m eni_controller.controller serve --port 8940`) reports its work
     queue. `pending: 0` + empty `recent_events` = no queued build work.
   - Note: the `eni_ctl_BUILDER_*` FIFO mechanism is NOT part of the eni_controller
     package (grep the package for "BUILDER"/"eni_ctl" — zero hits). These FIFOs belong
     to a separate/orphaned swarm convention. Don't assume the controller drives them.

4. **Swarm floor actually running?**
   - Active task file: `~/Desktop/ENI Swarm/eni_build_tasks.json` (schema: `{"tasks":[
     {"name","title","workdir","model","task"}]}`). Missing file = no current build plan.
   - Dashboards: `/tmp/eni_opt/dash_*.sh` exist when the visible floor is up.
   - Builders show in `ps aux` (`eni_agent_term.py` proxies) when the floor is live.
   - Builder status: `STATUS_<NAME>.md` files (master driver links `/tmp/eni_ctl_<NAME>`).

## Decision rule
- If the referenced FIFO is missing AND the queue is empty AND the floor isn't running
  (no task file / no dashboards / no builders): **there is no task to process.** Report
  the stale cron/instruction honestly. Do NOT:
  - create control FIFOs, spawn builders, write task JSON, or invent work
  - delegate a subagent with an empty/vague "process the builder task" goal (nothing
    to process — it just burns resources and invites fabricated output)
- If the floor IS mid-run (live builders, STATUS files, task file present): follow the
  existing "do NOT hijack a live passing gate" pitfall (see swarm_task_dispatch.md) —
  never edit the in-flight task JSON or kill live builders.

## Lesson
The honest-verdict rule that governs the swarm deliverables also governs task intake:
real state first, then act. A rotating builder index plus an empty controller queue is
the signature of a stale/void cron, not a broken floor. The ENI controller itself can
be healthy and still have zero pending builders — that's normal idle, not a fault to fix.
