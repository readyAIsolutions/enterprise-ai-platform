# Builder Idle-Slot Check — is there actually work?

A cron/runner that fires for a BUILDER slot does **NOT** mean a task was dispatched.
The Master Driver manages 60 logical slots; most wake-ups are routine idle check-ins.
**Do not invent work.** Run the decision procedure below; if the slot is idle, the
correct outcome is a no-op (e.g. `[SILENT]` for a scheduled delivery), NOT fabricating
a task, editing a STATUS to `[IN-PROGRESS]`, or spinning up a build.

## Decision procedure

1. **Read the worker's control FIFO** if the cron hands you one, e.g.
   `read_file('/tmp/eni_ctl_<WORKER>')`. If the path does not exist, treat that as
   "no directive yet" — check the rest before concluding.
2. **Read the worker STATUS** (`STATUS_<WORKER>.md` in `$HOME` and in
   `Commander/eni_swarm/builds/`). Key states:
   - `[IDLE]` / `verified=1` / `blocker=none` / `next=awaiting directive` → no task.
   - `[IN-PROGRESS]` / `[BLOCKED]` / `next=<work item>` → there may be a real task.
3. **Check the HEARTBEAT_LEDGER** entry for the slot
   (`Commander/eni_swarm/HEARTBEAT_LEDGER.md`). `[DONE] ... verified=unknown
   blocker=unknown next=unknown` corroborates "idle, nothing routed."
4. **Confirm no roster/dispatch references it**: `grep -rl "<WORKER>"` across
   `Commander/eni_swarm`, `config/eni_build_tasks.json`, and `/tmp`. Only
   heartbeat/status files matching = no task assigned.
5. **Check the controller queue**: `curl -s http://localhost:8940/status` →
   `queue.pending == 0` means nothing waiting to route.
   - Pitfall: do NOT pipe the curl output straight into an interpreter
     (`curl -s ... | python3 -c` or `| jq`). The security scanner flags
     `curl | python3` as a command-injection pattern and blocks the terminal
     call behind an approval that stalls the idle-check. Instead fetch to a
     file then inspect without a pipe:
       `curl -s --max-time 5 http://localhost:8940/status -o /tmp/ctl_status.json`
       `grep -o '"queue": {[^}]*}' /tmp/ctl_status.json`
     If `curl -o` leaves an empty file (exit 0, size 0), the controller is
     just down — treat that as an inconclusive signal, not work assigned.
6. **Conclusion**: FIFO missing + STATUS `[IDLE]` + no roster/dispatch + ledger
   `[DONE]` + empty queue ⇒ routine idle check-in ⇒ no-op. Do not force work.

## FIFO watcher mechanics (how builders receive directives)

Builder control FIFOs are named pipes, not regular files. The reference watcher
pattern (see `~/.hermes/scripts/builder_50_watcher.sh`) makes the read NON-blocking:

```bash
FIFO="/tmp/eni_ctl_BUILDER_50"
if exec 3<>"$FIFO" 2>/dev/null; then          # open RW so open() never blocks on missing writer
    if read -t 1 -r line <&3 2>/dev/null; then # -t bounds the read; absent writer => timeout
        echo "[IN-PROGRESS] $line" > "$STATUS"
    else
        echo "[IDLE] Waiting for task..." > "$STATUS"
    fi
    exec 3<&-
else
    echo "[IDLE] FIFO missing" > "$STATUS"     # FIFO not created yet => no directive
fi
```

Key points:
- `exec 3<>"$FIFO"` (read-write) is required — opening just for read blocks forever
  when there's no writer. The `< >` form prevents that.
- `read -t 1` bounds how long the FIFO poll waits so the cron is a quick no-op when idle.
- A builder "verified" timestamp sidecar (`/tmp/builder_verified`, epoch seconds) is written
  by the watcher when a task IS received; its absence/staleness is another idle signal.
- `[ -p path ]` / `ls` "No such file" means the FIFO was never created => no directive ever issued.

## Pitfall

- A "process the <WORKER> task" goal is a **shipping label**, not proof a task exists.
  Always verify against on-disk STATUS/roster before any action. The two real signals
  for assigned work are an `[IN-PROGRESS]`/`[BLOCKED]` STATUS with a concrete `next`,
  OR an explicit entry in the Master Driver task roster.
- `hermes-agent` is a bundled/hub skill and will NOT be in the local skill list — a
  `skill_view(name='hermes-agent')` "not found" is expected, not an error to chase.

## Example (observed 2026-08-07)

Cron fired for `BUILDER_37` with goal "Process ENI builder task."
- `/tmp/eni_ctl_BUILDER_37` → missing.
- `STATUS_BUILDER_37.md` → `[IDLE] verified=1 blocker=none next=awaiting directive`.
- Ledger → `[DONE] BUILDER_37 verified=unknown blocker=unknown next=unknown`.
- No roster/dispatch reference anywhere; controller queue `pending: 0`.
- Verdict: idle check-in, no task. Correct action = no-op (`[SILENT]`).