#!/usr/bin/env bash
# READ-ONLY Moonraker fleet boot-smoke for the 2x K2 Plus (DEMIURGE-3D).
# GET only — NEVER sends gcode / heat / motion. Use for swarm-builder
# "boot-smoke + route scan" verification. Re-probe live; do not hardcode IPs.
set -u
HOSTS=("${@:-192.168.1.65 192.168.1.66}")
for ip in "${HOSTS[@]}"; do
  echo "================ $ip:7125 (READ-ONLY) ================"
  echo "-- /printer/info --"
  curl -sS -m 6 "http://$ip:7125/printer/info" \
    | python3 -c "import sys,json;d=json.load(sys.stdin).get('result',{});print('state:',d.get('state'),'| host:',d.get('hostname'))" \
    || echo "  UNREACHABLE"
  echo "-- /printer/objects/query (temps, print state, build envelope) --"
  curl -sS -m 6 "http://$ip:7125/printer/objects/query?heater_bed&extruder&print_stats&toolhead" \
    | python3 -c "
import sys,json
try:
    s=json.load(sys.stdin)['result']['status']
    print('bed:',s['heater_bed']['temperature'],'C (tgt',s['heater_bed']['target'],')')
    print('extruder:',s['extruder']['temperature'],'C (tgt',s['extruder']['target'],') nozzle',s['extruder']['nozzle_diameter'],'mm')
    print('print_state:',s['print_stats']['state'],'| filename:',s['print_stats']['filename'])
    print('axis_maximum (build vol):',s['toolhead']['axis_maximum'])
except Exception as e:
    print('  parse/unreachable:',e)
" || echo "  UNREACHABLE"
  echo "-- /server/info --"
  curl -sS -m 6 -o /dev/null -w "  HTTP %{http_code}\n" "http://$ip:7125/server/info" || echo "  UNREACHABLE"
done
echo "DONE — read-only scan complete (no gcode sent)."
