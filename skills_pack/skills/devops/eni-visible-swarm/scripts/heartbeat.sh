#!/bin/bash
# ENI swarm PRODUCT-SWARM HEARTBEAT — one-line fleet pulse every 60s.
# Launch visibly: DISPLAY=:0 xfce4-terminal --disable-server --title ENI:HEARTBEAT_PULSE -e "bash heartbeat.sh"
# Reads PROJECT-ROOT STATUS (live), NOT eni_swarm/STATUS_*_B*.md (stale old deploy).
SB_ROOT=/home/hunter/Commander/demiurge_scaffold
DG_ROOT=/home/hunter/Commander/demiurge_scaffold
D3_ROOT=/home/hunter/Desktop/demiurge-3d
LM_ROOT=/home/hunter/Desktop/apps/lumen

newest_min() {  # minutes since newest mtime of root/glob; '-' if none
  local f
  f=$(ls -1t "$1"/$2 2>/dev/null | head -1)
  [ -z "$f" ] && { printf -- '-'; return; }
  printf -- $(( ( $(date +%s) - $(stat -c %Y "$f") ) / 60 ))
}

while true; do
  ts=$(date '+%H:%M:%S')
  win=$(wmctrl -l 2>/dev/null | grep -E 'ENI:' | grep -vc 'HEARTBEAT')
  live=$(pgrep -fc 'hermes chat -q' 2>/dev/null || echo 0)

  sb=$(newest_min "$SB_ROOT" 'STATUS_STOCKBOT*.md')
  dg=$(newest_min "$DG_ROOT" 'STATUS_DEMIURGE*.md')
  d3=$(newest_min "$D3_ROOT" 'STATUS_DEMIURGE-3D*.md')
  lm=$(newest_min "$LM_ROOT" 'STATUS_*LUMEN*.md')

  stalls=""
  for pair in "SB:$sb" "DG:$dg" "D3D:$d3" "LM:$lm"; do
    nm=${pair%%:*}; v=${pair##*:}
    [ "$v" != "-" ] && [ "$v" -gt 10 ] && stalls="${stalls}${nm} "
  done
  [ -z "$stalls" ] && stalls="none" || stalls="STALL ${stalls}"

  printf '%s | win:%d live:%d | SB:%sm DG:%sm D3D:%sm LM:%sm | %s\n' \
    "$ts" "$win" "$live" "$sb" "$dg" "$d3" "$lm" "$stalls"
  sleep 60
done
