# ENI Swarm Spine — hardening & self-test (ENI8, 2026-07-09)

Covers the three non-obvious correctness bugs in the swarm spine and the
reusable smoke harness that proves them. Applies to `eni_agent_term.py`,
`eni_relay.sh`, `eni_mini_run.sh` under `/home/hunter/Commander/eni_swarm/`.

The spine is REPL-agnostic: the live fleet runs `eni_agent_term.py ... --repl
hermes chat --yolo -m <slug> --provider openrouter`; the techniques below are
independent of which REPL the bridge forks.

## 1. Relay MUST be NON-BLOCKING (O_WRONLY | O_NONBLOCK)
The control FIFO `/tmp/eni_ctl_<NAME>` is held open `RDWR|nonblock` by the
bridge. A relay writer that opens it `O_WRONLY` *without* `O_NONBLOCK` will
**BLOCK FOREVER** if the bridge is momentarily down (its 2s self-heal gap, or
the mini is dead) — because an open-for-write on a fifo with no reader blocks
until a reader appears. On an `all` broadcast that stalls the whole relay call.

Correct pattern (`eni_relay.sh`):
```python
# eni_relay.sh opens the fifo like this (via python3 - <<'PY'):
import os, sys
ctl, line = sys.argv[1], sys.argv[2]
try:
    fd = os.open(ctl, os.O_WRONLY | os.O_NONBLOCK)
except OSError as e:           # ENXIO: no reader -> bridge down
    sys.stderr.write("relay: %s has no live bridge (%s)\n" % (ctl, e))
    sys.exit(2)
os.write(fd, (line + "\n").encode())
os.close(fd)
```
- Bridge alive (holds RDWR): open succeeds, line lands in the fifo buffer, bridge
  drains it on its next poll tick. Fire-and-forget.
- Bridge down: `O_NONBLOCK|O_WRONLY` returns `ENXIO` immediately -> `rc=2`, no hang.
- **Propagate the rc** (`return $rc` from the send function) so callers/scripts
  can detect a dead mini. The old code always exited 0 — callers couldn't tell.

LEGACY NOTE (do not reproduce): an earlier design tried a bounded `timeout 15s`
write that *spooled* to `/tmp/eni_spool_<NAME>` and returned 0. That had a real
bug — `exec 3>>FIFO` blocks with no reader, `timeout` SIGTERMs it, and the inner
shell surfaced the interrupted open as a code !=124, so a dead mini fell into a
false `exit 1`. The non-blocking open above is strictly simpler and correct.

## 2. Self-heal MUST use background-bridge + `wait` (clean TERM stop)
The naive form runs the bridge in the FOREGROUND inside `while true`:
```bash
while true; do
  python3 "$RUNPY" --name "$NAME" --task "$TASK" >>"$LOG" 2>&1   # foreground
  code=$?
  sleep 2
done
```
A `kill <mini_run_pid>` delivers TERM, but bash only runs its `trap TERM ...`
AFTER the foreground child exits — and the child won't exit until it's killed
itself. So TERM never propagates and the mini keeps running. LO's
"kill the tab to stop a mini" silently fails.

Fix: run the bridge in the BACKGROUND and `wait` on it. `wait` is interrupted by
the signal immediately, so the trap fires at once and kills the bridge:
```bash
BRIDGE_PID=""
cleanup() {
  [ -n "${BRIDGE_PID:-}" ] && kill -TERM "$BRIDGE_PID" 2>/dev/null
  wait "${BRIDGE_PID:-}" 2>/dev/null
  exit 0
}
trap cleanup TERM INT
while true; do
  python3 "$RUNPY" --name "$NAME" --task "$TASK" >>"$LOG" 2>&1 &
  BRIDGE_PID=$!
  wait "$BRIDGE_PID"          # interruptible: TERM fires cleanup() now
  code=$?
  sleep 2
done
```

## 3. Bridge MUST REAP its REPL child on exit
`eni_agent_term.py` forks the REPL via `pty.fork()`; on exit it MUST kill that
child or the REPL (a bash/agent loop) leaks as an orphan still holding the pty
slave. Add just before `sys.exit(0)`:
```python
try:
    os.kill(pid, signal.SIGKILL)
except OSError:
    pass
```

## 4. Smoke-test harness (`scripts/eni_swarm_smoke.sh`)
A throwaway mini (`ENI8SMOKE` by default, override with `$1`) + a dead-fifo
probe, fully self-cleaning so it never touches the live fleet. Three checks:
- **TEST A** (down-channel end-to-end): spawn bridge with a logging REPL, relay
  `smoke directive alpha`, assert the REPL *executed* it
  (`EXEC:LO via MASTER: smoke directive alpha` in its log). Proves
  `relay → /tmp/eni_ctl_<NAME> → pty → REPL`.
- **TEST B** (non-blocking relay): open a fifo with no reader and relay to it;
  assert the relay returns **non-zero in <2s** (ENXIO fast-fail), not a hang.
- **TEST C** (self-heal + clean stop): launch `eni_mini_run.sh ENI8SMOKE`, kill
  the bridge, assert a *new* bridge PID respawns inside `while true`; then `kill`
  the mini-run and assert **0 orphan processes** (bridge + REPL child both reaped).

Run `bash scripts/eni_swarm_smoke.sh` after ANY edit to the spine.
Last green run (this cycle, 2026-07-09): A=PASS, B=PASS, C=PASS.
