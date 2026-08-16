#!/bin/bash
# fleet_watchdog.sh — keeps the ENI swarm floor alive ALL DAY while LO is away.
# Every 10 min: if builder count < 48 or control windows missing, re-deploy the
# floor (5-min cooldown prevents thrash during a legit redeploy). Only ever calls
# fleet_deploy_ws.sh (which uses the safe PID kill), so it cannot take down the
# agent's own session. Run in background:
#   bash /home/hunter/.hermes/skills/devops/eni-build/scripts/fleet_watchdog.sh
export DISPLAY=:0.0
export PATH="/home/hunter/.local/bin:$PATH"
LOG=/tmp/fleet_watchdog.log
LAST=0
echo "$(date) watchdog started" >> "$LOG"
while true; do
  sleep 600
  total=$(wmctrl -l 2>/dev/null | grep -cE '_(B[0-9])')
  ctrl=$(wmctrl -l 2>/dev/null | grep -cE 'ENI:HEARTBEAT|ENI:PRODUCT_LEAD')
  now=$(date +%s)
  if [ "$total" -lt 48 ] || [ "$ctrl" -lt 2 ]; then
    if [ $((now - LAST)) -gt 300 ]; then
      echo "$(date) watchdog: total=$total ctrl=$ctrl -> REDEPLOY" >> "$LOG"
      ( cd ~/Commander/eni_swarm && BUILDERS_PER_SCREEN=4 bash fleet_deploy_ws.sh ) >> "$LOG" 2>&1
      LAST=$now
    else
      echo "$(date) watchdog: short (total=$total ctrl=$ctrl) cooldown active" >> "$LOG"
    fi
  fi
done
