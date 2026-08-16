# Heartbeat Pair — Proven xterm + Proxy + per-window --fifo Invocation

Lights up WS1 MIDDLE with two terminals: a **heartbeat mini** (left) and the live
**MASTER chat** (right). Both self-heal (`while true`), both draw a distinct live
OpenRouter slug via `eni_pick_model.sh` on every restart, so a 429 just rotates +
respawns instead of killing the floor.

## Non-negotiable facts (derived the hard way)
- `xterm` paints from the Hermes container on `DISPLAY :0.0`. `xfce4-terminal` does
  NOT — it needs the HOST's real D-Bus session bus; from the container it spawns and
  dies silently (empty log, `pgrep` shows it gone in <1s). For the styled xfce4 look,
  hand LO a HOST-side command (`bash ~/Desktop/eni_heartbeat_pair.sh`).
  (CORRECTION 2026-07-09: `devops/eni-visible-swarm` later PROVED `xfce4-terminal`
  DOES paint from the container with `--disable-server` + explicit `--geometry`
  — the old "D-Bus blocker" belief was FALSE. This skeleton keeps `xterm` for
  determinism, but xfce4-terminal is now a viable container option too.)
- `hermes chat <file>.md` positional is invalid — the window dies instantly. Always
  load prompts through `eni_agent_term.py`.
- `eni_agent_term.py` defaults `--fifo` to `/tmp/eni_ctl_unnamed`. If you omit
  `--fifo`, two windows collide on the shared pipe and relay misses. Always pass
  `--fifo /tmp/eni_ctl_<NAME>` and `rm -f /tmp/eni_ctl_unnamed` first.
- **Proxy CLI is the NEW named-arg form (2026-07-09):** the old
  `eni_agent_term.py "@task.txt" <workdir> --yolo -m <m> --provider <p>` positional
  form is DEAD (errors with "the following arguments are required: --name"). The
  correct invocation is
  `eni_agent_term.py --name <NAME> --task <file> --fifo /tmp/eni_ctl_<NAME> --repl "hermes chat --yolo -m <model> --provider openrouter"`.
  Model/provider live INSIDE `--repl`, not as proxy flags.

## Proven launcher skeleton (container-runnable)
```bash
#!/usr/bin/env bash
set -u
export DISPLAY=:0.0
export PATH="$HOME/.local/bin:$HOME/bin:$PATH"
PROXY=~/.local/bin/eni_agent_term.py
CACHE=~/.cache/eni_parallel
mkdir -p "$CACHE"
rm -f /tmp/eni_ctl_unnamed                       # kill stale shared pipe
pick(){ bash ~/.local/bin/eni_pick_model.sh; }   # rotate live slug per restart

# HEARTBEAT mini (left half of middle monitor)
cp ~/.cache/eni_parallel/task_heartbeat.txt "$CACHE/task_heartbeat.txt" 2>/dev/null || true
xterm -geometry 120x36+1920+0 -title "ENI_HEARTBEAT@[ws1-middle]" -e bash -c "
  while true; do
    M=\$(pick)
    python3 \"$PROXY\" --name HEARTBEAT --task \"$CACHE/task_heartbeat.txt\" --fifo /tmp/eni_ctl_HEARTBEAT --repl \"hermes chat --yolo -m $M --provider openrouter\"
    sleep 8
  done" &

# MASTER live chat (right half of middle monitor)
cp ~/.cache/eni_parallel/task_master.txt "$CACHE/task_master.txt" 2>/dev/null || true
xterm -geometry 120x36+3200+0 -title "ENI_MASTER_CHAT@[ws1-middle]" -e bash -c "
  while true; do
    M=\$(pick)
    python3 \"$PROXY\" --name MASTER --task \"$CACHE/task_master.txt\" --fifo /tmp/eni_ctl_MASTER --repl \"hermes chat --yolo -m $M --provider openrouter\"
    sleep 8
  done" &
```

## Relay a directive into the heartbeat (proven end-to-end)
```bash
bash ~/Commander/eni_swarm/eni_relay.sh HEARTBEAT "<contextual instruction>"
# -> HEARTBEAT OK
```
The mini receives it on its next poll, re-reads the named minis' STATUS files, acts,
and appends a `MASTER BRIEFING` section to `STATUS_HEARTBEAT.md`.

## Verify (glass is real)
- `pgrep -af 'ENI_HEARTBEAT|ENI_MASTER_CHAT'` — both windows alive.
- `ls -l /tmp/eni_ctl_HEARTBEAT /tmp/eni_ctl_MASTER` — both pipes exist, `eni_ctl_unnamed` gone.
- Do NOT `cat` a FIFO to "verify" — the proxy holds it RDWR and `cat` blocks forever.
  Trust a successful `eni_relay.sh` return + a growing `STATUS_HEARTBEAT.md`.
- `cat ~/Commander/eni_swarm/STATUS_HEARTBEAT.md` should show a fresh `MASTER BRIEFING`
  section within ~60–90s (qwen2.5-72b is slow; give it room).
