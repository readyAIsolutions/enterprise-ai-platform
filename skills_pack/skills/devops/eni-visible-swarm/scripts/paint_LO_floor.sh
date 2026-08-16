#!/bin/bash
# ENI swarm floor painter — LO's layout (container-runnable, DETACHED so the
# terminal tool never hangs). Requires the skill's own launcher to have already
# created /tmp/eni_tabs/run_ENI*.sh, run_PRODUCT_LEAD.sh, run_master_chat.sh,
# and master_heartbeat.sh (the eni_visible_herself.sh / roster launcher does this).
#
# Layout (LO, 2026-07-09):
#   MIDDLE/DP-0 (workstation-1 big monitor) = 1 full-screen term, 2 tabs:
#     HEARTBEAT (live loop) + MASTER CHAT (guides all)
#   LEFT/RIGHT/BOTTOM = 4 terms each in a 2x2 grid; per term tab1 = MASTER:ENIx
#     (hermes chat) then ENI:ENIx builder tab. BOTTOM term1 also has PRODUCT_LEAD.
#
# KEY: every xfce4-terminal is launched DETACHED (</dev/null >/dev/null 2>&1 & disown)
# and interactive -e is wrapped in a script — otherwise `hermes chat` holds the
# parent pipe open and the painter TIMES OUT with nothing painted.
export DISPLAY=:0.0
TERM=xfce4-terminal
export PATH="/home/hunter/.local/bin:$PATH"

# --- kill old floor (specific patterns; SPARES host --maximize terminal + my session) ---
pkill -f '/tmp/eni_tabs/' 2>/dev/null
pkill -f '/home/hunter/.cache/eni_parallel/task_ENI' 2>/dev/null
pkill -f '/home/hunter/.cache/eni_parallel/task_PRODUCT_LEAD' 2>/dev/null
sleep 2

launch() { "$TERM" "$@" </dev/null >/dev/null 2>&1 & disown; }

paint_screen() {
  local OX=$1 OY=$2
  shift 2
  local ens=("$@")
  local i=0
  for e in "${ens[@]}"; do
    local col=$(( i % 2 ))
    local row=$(( i / 2 ))
    local gx=$(( OX + col*960 ))
    local gy=$(( OY + 24 + row*528 ))
    local geo="120x28+${gx}+${gy}"
    if [ "$e" = "ENI9" ]; then
      # BOTTOM term1 also carries PRODUCT_LEAD as an extra tab
      launch --disable-server --title "MASTER:$e" \
        -e "bash /tmp/eni_tabs/run_master_chat.sh" \
        --tab --title "ENI:$e" -e "bash /tmp/eni_tabs/run_${e}.sh" \
        --tab --title "ENI:PRODUCT_LEAD" -e "bash /tmp/eni_tabs/run_PRODUCT_LEAD.sh" \
        --geometry "$geo"
    else
      launch --disable-server --title "MASTER:$e" \
        -e "bash /tmp/eni_tabs/run_master_chat.sh" \
        --tab --title "ENI:$e" -e "bash /tmp/eni_tabs/run_${e}.sh" \
        --geometry "$geo"
    fi
    i=$((i+1))
  done
}

paint_screen 0 0     ENI1 ENI2 ENI3 ENI4
paint_screen 4480 0  ENI5 ENI6 ENI7 ENI8
paint_screen 2274 1080 ENI9 ENI10 ENI11 ENI12

# --- MIDDLE big monitor: 1 term, full screen, 2 tabs (heartbeat + master chat) ---
launch --disable-server --title "ENI HEARTBEAT (live)" \
  -e "bash /tmp/eni_tabs/master_heartbeat.sh" \
  --tab --title "MASTER CHAT (guides all)" -e "bash /tmp/eni_tabs/run_master_chat.sh" \
  --geometry 260x54+1920+24

echo "PAINT DONE"
