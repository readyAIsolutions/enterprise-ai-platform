#!/usr/bin/env bash
# ============================================================================
#  eni_swarm_floor.sh  —  LO's 4-monitor ENI parallel-build swarm (HOST-SIDE)
#  RUN THIS FROM A REAL HOST TERMINAL ON LO'S XFCE SESSION.
#  xfce4-terminal needs the host's real D-Bus bus; it will NOT paint from the
#  Hermes container. This script paints the floor LO asked for:
#    MIDDLE (DisplayPort-0, 2560x1080, +1920+0): 2 windows
#        - ENI MASTER  (big, workspace 1)  = live heartbeat chat LO talks to
#        - ENI: PRODUCT_LEAD               = owns all product builds
#    LEFT   (DisplayPort-2, 1920x1080, +0+0):      ENI1 ENI2 ENI3 ENI4
#    RIGHT  (DisplayPort-1, 1920x1080, +4480+0):   ENI5 ENI6 ENI7 ENI8
#    BOTTOM (HDMI-A-0,      1920x1080, +2274+1080):ENI9 ENI10 ENI11 ENI12
#  + 12 PRODUCT WORKER windows (Lumen, DEMIURGE-3D x3, 8 forex, CAVEMAN_STACK)
#    tiled on the MIDDLE screen as the product-lead's "tabs".
#  Every window is a self-healing `eni chat` mini. THIS chat (ENI) is the
#  persistent master tab that keeps the floor alive + relays if the visible
#  master ever goes quiet.
#
#  GEO NOTE: the per-monitor origins below MUST match `xrandr --listmonitors`
#  on LO's box. They were corrected from a stale 4-in-a-row assumption that
#  spawned workers off-screen. If monitors are rearranged, update both this
#  file's GEO_* arrays AND eni_spawn_worker.sh's GEO map.
# ============================================================================
export DISPLAY=:0.0
export PYTHONPATH=/home/hunter/.local/lib/python3.14/site-packages
export PATH="$HOME/.local/bin:$HOME/bin:$PATH"

PROXY="$HOME/.local/bin/eni_agent_term.py"
SWARM="$HOME/Commander/eni_swarm"
CACHE="$HOME/.cache/eni_parallel"
FLOOR="$CACHE/floor_tasks"
mkdir -p "$FLOOR"

command -v xfce4-terminal >/dev/null 2>&1 || {
  echo "ERROR: xfce4-terminal not found on this host. Install it (apt install xfce4-terminal) and re-run."
  exit 1
}

# ---- kill any stale swarm so we relight clean ----
pkill -f 'eni_agent_term[.]py' 2>/dev/null; sleep 0.5
pkill -f 'eni_mini_run[.]sh'  2>/dev/null; sleep 1
rm -f /tmp/eni_ctl_* /tmp/eni_spool_* 2>/dev/null

# ---- live model pool (round-robin so we dodge per-account free caps) ----
MODELS=( tencent/hy3:free qwen/qwen3-coder:free meta-llama/llama-3.3-70b-instruct:free qwen/qwen2.5-72b-instruct:free )
mi=0
nm(){ echo "${MODELS[mi % ${#MODELS[@]}]}"; mi=$((mi+1)); }

# ---- geometry per monitor (from `xrandr --listmonitors`) ----
GEO_MASTER="210x52+1940+8"          # big master, middle
GEO_MID2="95x32+1940+565"           # product-lead, middle
GEO_L=( "72x32+8+8" "72x32+948+8" "72x32+8+548" "72x32+948+548" )            # LEFT
GEO_R=( "72x32+4488+8" "72x32+5448+8" "72x32+4488+548" "72x32+5448+548" )   # RIGHT
GEO_B=( "72x32+2282+1088" "72x32+3242+1088" "72x32+2282+1648" "72x32+3242+1648" ) # BOTTOM
# 12 product workers tiled 6x2 across the MIDDLE ultrawide
GEO_PW=( "48x28+1924+8" "48x28+2372+8" "48x28+2820+8" "48x28+3268+8" "48x28+3716+8" "48x28+4164+8" \
         "48x28+1924+548" "48x28+2372+548" "48x28+2820+548" "48x28+3268+548" "48x28+3716+548" "48x28+4164+548" )

# ---- spawn ONE self-healing window (writes a runner script to dodge quoting hell) ----
spawn() {
  local NAME="$1" GEO="$2" TASKFILE="$3" WD="$4" MODEL="$5" FIFO="$6" TITLE="$7"
  mkfifo -m 666 "$FIFO" 2>/dev/null || true
  local RUN="$FLOOR/run_${NAME}.sh"
  cat > "$RUN" <<EOF
#!/usr/bin/env bash
export PYTHONPATH=$PYTHONPATH
while true; do
  python3 "$PROXY" "@$TASKFILE" "$WD" -m "$MODEL" --provider openrouter --fifo "$FIFO"
  echo "[\$(date +%T)] $NAME exited rc=\$? restarting"
  sleep 3
done
exec bash
EOF
  chmod +x "$RUN"
  xfce4-terminal --title "$TITLE" --geometry "$GEO" -e "bash $RUN" &
}

# ---- generate every task file from the two JSON rosters + add swarm-mode notes ----
python3 - <<'PY'
import json, os
HOME=os.path.expanduser("~")
SWARM=os.path.join(HOME,"Commander","eni_swarm")
FLOOR=os.path.join(HOME,".cache","eni_parallel","floor_tasks")
os.makedirs(FLOOR,exist_ok=True)

WS=("If your goal has clear independent sub-parts, fan them out as worker tabs: "
    "bash %s/eni_spawn_worker.sh <YOURNAME> <N> '<concrete subprompt>'. Claim sub-parts so siblings don't duplicate. "
    "Write STATUS_<YOURNAME>.md into %s every cycle. Self-heal is automatic." % (SWARM,SWARM))

him=json.load(open(os.path.join(HOME,"Desktop","eni_herself_tasks.json")))
for t in him["tasks"]:
    n=t["name"]; task=t["task"]
    open(os.path.join(FLOOR,n+".txt"),"w").write(task+"\n\n## SWARM MODE (worker tabs)\n"+WS.replace("<YOURNAME>",n))

prod=json.load(open(os.path.join(HOME,"Desktop","eni_build_tasks.json")))
plead=("You are PRODUCT_LEAD, the ENI mini that OWNS all product builds (Lumen, DEMIURGE-3D x3, 8 DEMIURGE forex modules, CAVEMAN_STACK). "
       "The 12 product builders are launched as worker windows by this floor launcher; you oversee them. "
       "Each cycle read STATUS files under ~/Desktop/apps/lumen, ~/Desktop/demiurge-3d, ~/Commander/demiurge_scaffold (STATUS_*.md) "
       "and the swarm STATUS_ENI*.md. Write ~/Commander/eni_swarm/STATUS_PRODUCT_LEAD.md with per-product state + blockers. "
       "If a product mini is BLOCKED or stale, relay a specific fix via 'bash ~/Commander/eni_swarm/eni_relay.sh <NAME> \"<directive>\"'. "
       "Keep momentum, self-heal on death.")
open(os.path.join(FLOOR,"PRODUCT_LEAD.txt"),"w").write(plead)

for i,t in enumerate(prod["tasks"],1):
    n=t["name"]; task=t["task"]
    extra=("\n\n## SWARM MODE\nYou are product builder '%s'. cd into your workdir and BUILD (do not just report). "
           "Write STATUS_%s.md into your workdir each cycle. If blocked (USB not mounted, missing dep), report the exact blocker "
           "+ the command that would unblock. Self-heal is automatic." % (n,n))
    open(os.path.join(FLOOR,"PROD_%d_%s.txt"%(i,n)),"w").write(task+extra)

with open(os.path.join(FLOOR,"product_manifest.txt"),"w") as f:
    for i,t in enumerate(prod["tasks"],1):
        f.write("%s\t%s\t%s\tPROD_%d_%s.txt\n"%(t["name"],t["workdir"],t["model"],i,t["name"]))
print("task files written:", len(os.listdir(FLOOR)))
PY

# ---- master coordinator brief (live heartbeat + relay; this is the term LO chats to) ----
MASTER_BRIEF="You are the MASTER coordinator tab for LO's ENI parallel build swarm (live heartbeat). You are the term LO chats to on the middle screen, workspace 1. Your job is NOT to build — it is to keep LO informed and relay his steering into the minis' tabs. Duties: 1) Inventory: confirm all /tmp/eni_ctl_<NAME> FIFOs exist and every mini is alive (pgrep -af eni_agent_term.py). 2) Read STATUS: each mini drops STATUS_<NAME>.md into its WORKDIR; check real mtimes (stat -c '%y'). 3) Brief LO: dashboard of DONE-on-disk vs cooking vs blockers, separating pre-launch vs live artifacts. 4) Relay: when LO steers, write the FULL untruncated directive to the right FIFO via 'bash ~/Commander/eni_swarm/eni_relay.sh <NAME> \"<directive>\"' — one NAME, or 'all'/'DEMIURGE_*' for fleet-wide. Read each mini's own STATUS and reply to THAT mini only; never send the same canned text to all. 5) Show a heartbeat every loop (proxy counts, fresh STATUS). You read progress from STATUS files + the process table only. Keep momentum, self-heal on death."
echo "$MASTER_BRIEF" > "$FLOOR/MASTER.txt"

# ---- launch MASTER (middle, big, workspace 1) ----
spawn MASTER "$GEO_MASTER" "$FLOOR/MASTER.txt" "$SWARM" "$(nm)" "/tmp/eni_ctl_MASTER" "ENI MASTER (live heartbeat)"
sleep 1
wmctrl -r "ENI MASTER (live heartbeat)" -t 0 2>/dev/null || true

# ---- launch PRODUCT_LEAD (middle small) ----
spawn PRODUCT_LEAD "$GEO_MID2" "$FLOOR/PRODUCT_LEAD.txt" "$SWARM" "$(nm)" "/tmp/eni_ctl_PRODUCT_LEAD" "ENI: PRODUCT_LEAD"

# ---- launch ENI1-4 (LEFT) ----
for i in 0 1 2 3; do
  n="ENI$((i+1))"
  spawn "$n" "${GEO_L[$i]}" "$FLOOR/$n.txt" "$SWARM" "$(nm)" "/tmp/eni_ctl_$n" "ENI: $n"
done
# ---- launch ENI5-8 (RIGHT) ----
for i in 0 1 2 3; do
  n="ENI$((i+5))"
  spawn "$n" "${GEO_R[$i]}" "$FLOOR/$n.txt" "$SWARM" "$(nm)" "/tmp/eni_ctl_$n" "ENI: $n"
done
# ---- launch ENI9-12 (BOTTOM) ----
for i in 0 1 2 3; do
  n="ENI$((i+9))"
  spawn "$n" "${GEO_B[$i]}" "$FLOOR/$n.txt" "$SWARM" "$(nm)" "/tmp/eni_ctl_$n" "ENI: $n"
done
# ---- launch 12 PRODUCT WORKERS (middle grid, under the product-lead) ----
i=0
while IFS=$'\t' read -r NAME WD MODEL TASKFILE; do
  spawn "PROD_$NAME" "${GEO_PW[$i]}" "$FLOOR/$TASKFILE" "$WD" "$MODEL" "/tmp/eni_ctl_PROD_$NAME" "PROD: $NAME"
  i=$((i+1))
done < "$FLOOR/product_manifest.txt"

echo "ENI swarm floor launched."
echo "  - Master heartbeat on MIDDLE screen, workspace 1 (the term LO chats to)."
echo "  - 14 top-level windows (master + product-lead + ENI1..ENI12)."
echo "  - 12 product worker windows tiled on the MIDDLE screen under the product-lead."
echo "  - This chat (ENI) stays open as the persistent master tab and keeps the floor alive."
echo "Verify with:  xwininfo -root -tree | grep -i ENI"
echo "Proxy count:  pgrep -af eni_agent_term.py | wc -l   (expect ~26)"
