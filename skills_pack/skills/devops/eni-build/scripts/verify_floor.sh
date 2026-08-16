#!/bin/bash
# verify_floor.sh — health check for the ENI swarm floor (no sudo).
# Exit 0 = healthy (48 builders, control present + sticky, drivers looping).
export DISPLAY=:0.0
PPS="${BUILDERS_PER_SCREEN:-4}"
PER_WS=$(( PPS * 3 ))
ok=1
echo "=== builders per X11 workspace (expected $PER_WS each) ==="
for d in 0 1 2 3; do
  n=$(wmctrl -l 2>/dev/null | awk -v D=$d '$2==D' | grep -cE '_(B[0-9])')
  printf "  ws%d: %s\n" $((d+1)) "$n"
  [ "$n" -lt "$PER_WS" ] && ok=0
done
ctrl=$(wmctrl -l 2>/dev/null | grep -cE 'ENI:HEARTBEAT|ENI:PRODUCT_LEAD')
echo "=== control windows: $ctrl (expected 2) ==="
if [ "$ctrl" -lt 2 ]; then ok=0
else
  for id in $(wmctrl -l 2>/dev/null | awk '/ENI:HEARTBEAT|ENI:PRODUCT_LEAD/{print $1}'); do
    if xprop -id "$id" _NET_WM_STATE 2>/dev/null | grep -q STICKY; then echo "  $id STICKY ok"
    else echo "  $id NOT sticky"; ok=0; fi
  done
fi
loop=$(pgrep -fc 'hermes chat -q')
echo "=== looping builder drivers (hermes chat -q): $loop (idle floor = ~0) ==="
[ "$loop" -lt 1 ] && ok=0
echo "=== STATUS writes in last 5 min ==="
find ~/Commander/demiurge_scaffold ~/Desktop/demiurge-3d ~/Desktop/apps/lumen \
  -name 'STATUS*.md' -mmin -5 2>/dev/null | head
if [ "$ok" -eq 1 ]; then echo "FLOOR HEALTHY"; else echo "FLOOR DEGRADED — redeploy or let watchdog self-heal"; fi
exit $((1-ok))
