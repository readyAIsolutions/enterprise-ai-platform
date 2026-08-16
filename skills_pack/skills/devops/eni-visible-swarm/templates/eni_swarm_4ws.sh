#!/usr/bin/env bash
# eni_swarm_4ws.sh — TRUE 4-WORKSTATION fan-out (4 physical PCs on the LAN), NOT 4 monitors.
# Spreads ENI1..12 across 4 IPs so per-account free-model caps don't kill a single-box swarm.
# Combines BOTH axes: model (eni_pick_model.sh) + IP (this script).
# PREREQ (one-time, host-side, needs LO's password):
#   ssh-copy-id hunter@192.168.1.65 ; ssh-copy-id hunter@192.168.1.66
# USAGE:
#   eni_swarm_4ws.sh --bootstrap   # rsync Hermes + eni profile + swarm + launcher to each WS
#   eni_swarm_4ws.sh               # slice tasks 4-per-host, print per-host launch cmd
set -u
HOSTS=("192.168.1.65" "192.168.1.66" "192.168.247.128")
USER=hunter
TASKS=~/Desktop/eni_herself_tasks.json
OUT=~/Desktop
BOOTSTRAP="${1:-}"

probe() { ssh -o BatchMode=yes -o ConnectTimeout=5 "$USER@$1" true >/dev/null 2>&1 && echo UP || echo DOWN; }

if [ "$BOOTSTRAP" = "--bootstrap" ]; then
  for h in "${HOSTS[@]}"; do
    echo "== $h: $(probe $h)"
    [ "$(probe $h)" = "UP" ] || { echo "  skip (down / no key)"; continue; }
    rsync -az --delete ~/.hermes "$USER@$h:~/" 2>/dev/null
    rsync -az ~/Commander/eni_swarm "$USER@$h:~/Commander/" 2>/dev/null
    rsync -az ~/Desktop/eni_visible_herself.sh ~/Desktop/eni_herself_tasks.json "$USER@$h:~/Desktop/" 2>/dev/null
    echo "  bootstrapped"
  done
  echo "Bootstrap done. Now run: eni_swarm_4ws.sh"
  exit 0
fi

mapfile -t NAMES < <(python3 -c "import json;[print(t['name']) for t in json.load(open('$TASKS'))['tasks']]")
i=0
for h in "${HOSTS[@]}"; do
  slice=("${NAMES[@]:i:4}"); i=$((i+4))
  [ ${#slice[@]} -eq 0 ] && continue
  python3 - "$TASKS" "$OUT/eni_herself_tasks_ws_$h.json" "${slice[@]}" <<'PY'
import json, sys
src, dst = sys.argv[1], sys.argv[2]
keep = set(sys.argv[3:])
data = json.load(open(src))
data["tasks"] = [t for t in data["tasks"] if t["name"] in keep]
json.dump(data, open(dst, "w"), indent=2)
PY
  echo "HOST $h ($(probe $h)) -> $OUT/eni_herself_tasks_ws_$h.json : ${slice[*]}"
  echo "   on $h run:  bash ~/Desktop/eni_visible_herself.sh ~/Desktop/eni_herself_tasks_ws_$h.json"
done
