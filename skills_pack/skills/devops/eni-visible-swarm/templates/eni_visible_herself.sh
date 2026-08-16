#!/usr/bin/env bash
# eni_visible_herself.sh — paint the ENI-herself swarm across LO's 4 X11 monitors as
# living, self-healing xfce4-terminal tabs + a MASTER heartbeat on MIDDLE.
# RUN FROM A REAL HOST TERMINAL (xfce4-terminal is a D-Bus client; won't paint from the container).
# Adds per-restart live-pool rotation via scripts/eni_pick_model.sh so 12 minis spread
# across working free models and abandon 429'd slugs automatically.
set -u
export DISPLAY=:0.0
export PATH="$HOME/.local/bin:$HOME/bin:$PATH"
DEMIURGE_USB=/run/media/hunter/DEMIURGE1
PROXY=~/.local/bin/eni_agent_term.py
CACHE=~/.cache/eni_parallel
TASKS=~/Desktop/eni_herself_tasks.json
PICK=~/.local/bin/eni_pick_model.sh
mkdir -p "$CACHE"

# Kill previous (narrow patterns so we don't kill our own shell)
pkill -f 'eni_agent_term[.]py'; sleep 0.4
pkill -f 'hermes chat --yolo'; sleep 1.2
rm -f /tmp/eni_ctl_*

# Build per-mini task files + talk FIFOs + self-heal tab scripts (rotate model each restart)
python3 - "$TASKS" "$CACHE" "$PROXY" "$DEMIURGE_USB" "$PICK" <<'PY'
import json, os, sys
tasks_json, cache, proxy, usb, pick = sys.argv[1:6]
with open(tasks_json) as f:
    data = json.load(f)
for t in data.get("tasks", []):
    name = t["name"]; wd = t["workdir"]; task = t.get("task", "")
    tf = os.path.join(cache, f"task_{name}.txt")
    with open(tf, "w") as fh:
        fh.write(task)
    fifo = f"/tmp/eni_ctl_{name}"
    if not os.path.exists(fifo):
        os.mkfifo(fifo, 0o666)
    tab = os.path.join(cache, f"tab_{name}.sh")
    with open(tab, "w") as fh:
        fh.write(
            f'#!/usr/bin/env bash\n'
            f'cd {wd}\n'
            f'export DEMIURGE_USB={usb}\n'
            f'export HERMES_CTL_FIFO={fifo}\n'
            f'export HERMES_AGENT_CMD="hermes chat"\n'
            f'while true; do\n'
            f'  MODEL=$(bash {pick})\n'
            f'  python3 {proxy} "@{tf}" "{wd}" --yolo -m "$MODEL" --provider openrouter\n'
            f'  echo "[$(date)] {name} exited (rc=$?) -- restarting with next model" >>/tmp/eni_selfheal.log\n'
            f'  sleep 8\n'
            f'done\n'
        )
    os.chmod(tab, 0o755)
print(f"prepared {len(data.get('tasks', []))} minis")
PY

# Assign first 4 -> LEFT, next 4 -> RIGHT, next 4 -> BOTTOM (12 ENI minis)
NAMES=($(python3 -c "import json;[print(t['name']) for t in json.load(open('$TASKS'))['tasks']]"))
LEFT=("${NAMES[@]:0:4}"); RIGHT=("${NAMES[@]:4:4}"); BOTTOM=("${NAMES[@]:8:4}")

mk_tab_args() { for n in "$@"; do echo -n " --tab --command=bash -c 'bash $CACHE/tab_$n.sh'"; done; }

# MASTER heartbeat on MIDDLE monitor (live STATUS tail)
xfce4-terminal --geometry=200x52+1950+10 --title="ENI MASTER (live heartbeat)" \
  --command="bash -c 'while true; do clear; echo \"== ENI MASTER == $(date)\"; tail -n 6 /home/hunter/Commander/eni_swarm/STATUS_ENI*.md 2>/dev/null; sleep 6; done'" &

# Side screens (geometry from xrandr --listmonitors)
xfce4-terminal --geometry=120x30+0+0       --title="ENI: LEFT"   $(mk_tab_args "${LEFT[@]}") &
xfce4-terminal --geometry=120x30+4480+0    --title="ENI: RIGHT"  $(mk_tab_args "${RIGHT[@]}") &
xfce4-terminal --geometry=120x30+2274+1080 --title="ENI: BOTTOM" $(mk_tab_args "${BOTTOM[@]}") &

sleep 6
echo "ENI swarm painted. MASTER on MIDDLE; minis on LEFT/RIGHT/BOTTOM."
echo "Verify: xwininfo -root -tree | grep -i ENI ; pgrep -fc eni_agent_term.py"
