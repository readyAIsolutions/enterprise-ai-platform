#!/bin/bash
# safe_kill_swarm.sh — tear down the ENI swarm floor WITHOUT killing your own
# session. Kills swarm xfce4-terminals by PID only (never by process group, and
# never a broad pkill whose pattern matches this shell's argv — that would SIGKILL
# the agent's own shell, exit -15/-9). Then reaps orphaned hermes-chat loops whose
# parent died (ppid==1) so they stop hammering the API.
export DISPLAY=:0.0
me=$$
mp=$PPID
echo "killing swarm terminals (xfce4-terminal.*eni_tabs) by PID ..."
for pid in $(pgrep -f 'xfce4-terminal.*eni_tabs' 2>/dev/null); do
  [ "$pid" = "$me" ] && continue
  kill -9 "$pid" 2>/dev/null
done
pkill -f '/tmp/eni_tabs/' 2>/dev/null
pkill -f 'eni_agent_term.py' 2>/dev/null
sleep 2
echo "reaping orphan hermes chat loops (ppid==1) ..."
for p in $(pgrep -f 'hermes chat --yolo' 2>/dev/null); do
  [ "$p" = "$me" ] && continue
  [ "$p" = "$mp" ] && continue
  pp=$(ps -o ppid= -p "$p" 2>/dev/null | tr -d ' ')
  if [ "$pp" = "1" ]; then kill -9 "$p" 2>/dev/null && echo "  killed orphan $p"; fi
done
echo "remaining builder windows: $(wmctrl -l 2>/dev/null | grep -cE '_(B[0-9])')"
