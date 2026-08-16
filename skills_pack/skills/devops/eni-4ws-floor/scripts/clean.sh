#!/usr/bin/env bash
# clean.sh — SAFE full-floor kill. ALWAYS run as its own `bash clean.sh`.
# (Inline pkill with the pattern text in the same shell kills your own call — exit -9.
#  See eni-4ws-floor PITFALLS #2.)
# Kills swarm xfce4-terminals, eni_agent_term, sentinel, watchdog, pl_stockbot_cycle.
# Use BEFORE redeploying the floor (then re-run floor_setup.py + launch sentinel).
set -u
echo "[clean.sh] killing swarm xfce4-terminals…"
for p in $(pgrep -x xfce4-terminal); do
  grep -qa -e run_ -e heart_ -e master_ /proc/$p/cmdline 2>/dev/null && kill -9 "$p"
done
pkill -9 -f 'eni_agent_term.py'
pkill -9 -f 'mem_sentinel'
pkill -9 -f 'swarm_watchdog'
pkill -9 -f 'pl_stockbot_cycle'
echo "[clean.sh] done. remaining hermes chat: $(pgrep -fc 'hermes chat' 2>/dev/null)"
echo "[clean.sh] remaining xfce4-terminal: $(pgrep -xc xfce4-terminal 2>/dev/null)"
