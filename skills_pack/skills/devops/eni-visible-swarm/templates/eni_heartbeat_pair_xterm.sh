#!/usr/bin/env bash
# eni_heartbeat_pair_xterm.sh — boot 2 terminals on WORKSTATION 1 MIDDLE big screen
# via xterm (direct X client, paints from the Hermes container). For the styled
# xfce4-terminal version, run ~/Desktop/eni_heartbeat_pair.sh on the HOST instead.
#   (A) ENI_HEARTBEAT mini  — proxied, self-healing, writes STATUS_HEARTBEAT.md, obeys FIFO
#   (B) ENI_MASTER_CHAT     — live master hermes chat (interactive)
# MIDDLE = DisplayPort-0, 2560x1080, x in [1920,4480], y=0
set -u
export DISPLAY=:0.0
command -v xterm >/dev/null 2>&1 || { echo "XTERM_MISSING"; exit 1; }
SWDIR=/home/hunter/Commander/eni_swarm
CACHE=$HOME/.cache/eni_parallel
PROXY=$HOME/.local/bin/eni_agent_term.py
mkdir -p "$CACHE" "$SWDIR"
MODEL="$(eni_pick_model.sh)"
echo "[heartbeat pair xterm] using model: $MODEL"

# (A) heartbeat mini — left half of middle (x=1920)
xterm -title "ENI_HEARTBEAT@[ws1-middle]" -geometry 120x36+1920+0 \
  -e bash -c "while true; do python3 \"$PROXY\" \"@$CACHE/task_heartbeat.txt\" \"$SWDIR\" --yolo -m \"$MODEL\" --provider openrouter; echo '[heartbeat restart in 8s]'; sleep 8; done" &

# (B) master chat — right half of middle (x=3200)
xterm -title "ENI_MASTER_CHAT@[ws1-middle]" -geometry 120x36+3200+0 \
  -e bash -c "python3 \"$PROXY\" \"@$CACHE/task_master.txt\" \"$SWDIR\" --yolo -m \"$MODEL\" --provider openrouter" &

wait
