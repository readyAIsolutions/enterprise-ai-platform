#!/usr/bin/env bash
# verify_floor.sh — read-only health board for the ENI 4-WS build floor.
# Run: bash ~/.hermes/skills/devops/eni-4ws-floor/scripts/verify_floor.sh
# Proven working 2026-07-11 (produced the alive-state numbers after a repaint).
set -u
echo "=== time ==="; date '+%H:%M:%S'
echo "=== terminals (xfce4 class) per desktop ==="
for d in 0 1 2 3; do
  printf "  %4s %s\n" "$(wmctrl -l 2>/dev/null | awk -v d=$d '$2==d{c++} END{print c+0}')" "$d"
done
echo "=== builder proxies alive ==="
echo "eni_agent_term: $(pgrep -fc eni_agent_term.py 2>/dev/null)"
echo "=== hermes sessions ==="
echo "hermes chat: $(pgrep -fc 'hermes chat' 2>/dev/null)"
echo "=== sentinel ==="
pgrep -af mem_sentinel || echo "(none)"
echo "=== watchdog (must be absent) ==="
pgrep -af swarm_watchdog || echo "(none — good)"
echo "=== memory ==="
free -m | awk '/Mem:/{print "total="$2" used="$3" avail="$7}'
echo "=== STATUS written last 5 min ==="
find /home/hunter/Commander/demiurge_scaffold /home/hunter/Desktop/demiurge-3d /home/hunter/Desktop/apps/lumen \
  -name 'STATUS_*.md' -mmin -5 2>/dev/null | wc -l
echo "=== sample: is SB01 hermes producing output to its log? ==="
ls -l /tmp/eni_logs/SB01.log 2>/dev/null | awk '{print "SB01.log bytes: "$5}'
echo "=== lumen GUI must be absent (leash) ==="
pgrep -af 'python -m lumen[^-.]' | grep -v grep | wc -l
