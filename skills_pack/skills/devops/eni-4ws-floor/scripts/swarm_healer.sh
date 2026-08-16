#!/usr/bin/env bash
# swarm_healer.sh — model-rotation self-healer for LO's ENI 4-workspace parallel-build floor.
#
# CANONICAL COPY. floor_setup.py does NOT emit this. After any clean.sh / reboot, copy it
# back into place:  cp ~/.hermes/skills/devops/eni-4ws-floor/scripts/swarm_healer.sh /tmp/swarm_healer.sh
#
# WHAT IT DOES
#   Every HEAL_INTERVAL s it scans every builder's live log (/tmp/eni_logs/<NAME>.log).
#   If a builder shows >= MIN_FAILS API-failure signatures in its recent tail AND the log is
#   fresh (< LOG_MAX_AGE s), it rotates that builder's hermes model to the next working one
#   in the OpenRouter free spine, kills that ONE window, and respawns it at the EXACT same
#   pixel rect + workspace (captured via `wmctrl -lpG`).
#
# DESIGN RULES (lessons — see SKILL.md pitfalls #8 / #9)
#   * sed MUST anchor to the hermes model slug `(tencent|qwen|meta-llama)/[a-zA-Z0-9:.-]+`.
#     A bare `-m` match hits the `free -m |` memory-wait line and corrupts every script
#     (broke all 64 on 2026-07-11). Anchoring fixed it.
#   * This is a 1:1 window replacement, NOT a global repaint. It cannot OOM the box.
#   * Kill by PID or `pkill -f swarm_healer` from a SEPARATE bash call — never inline next
#     to the pattern text.
#
# LAUNCH (background daemon; needs DISPLAY=:0.0):
#   export DISPLAY=:0.0; nohup bash /tmp/swarm_healer.sh >/tmp/eni_healer.log 2>&1 &
#   (harness: use terminal(background=true), do NOT inline nohup/&)
# STOP:
#   kill -9 <pid>     # find pid via: pgrep -f swarm_healer

set -u

MODELS=(tencent/hy3 qwen/qwen3-coder nvidia/nemotron-3-ultra-550b-a55b meta-llama/llama-3.3-70b-instruct)
MODEL_RE='(tencent|qwen|nvidia|meta-llama)/[a-zA-Z0-9:.-]+'
FAIL_RE='429|Too Many Requests|rate.?limit|quota|exceeded|model.?not.?found|does not exist|502|503|504|ConnectionError|Connection refused|timed out|APIError|Failed to connect|upstream|unavailable|Rate limited'
HEAL_INTERVAL=20
TAIL_LINES=120
LOG_MAX_AGE=180
MIN_FAILS=3
COOLDOWN=120

LOG=/tmp/eni_healer.log
STATE=/tmp/eni_heal_state.json
RUN_DIR=/tmp/eni_tabs
LOG_DIR=/tmp/eni_logs

mkdir -p "$RUN_DIR" "$LOG_DIR"
echo "$(date '+%F %T') healer start minis=$(ls -1 "$LOG_DIR"/*.log 2>/dev/null | wc -l)" >> "$LOG"

now_ts() { date +%s; }

last_heal() {
  # STATE is a simple "name=epoch" flat file (not strict JSON — robust to partial writes)
  grep -E "^$1=" "$STATE" 2>/dev/null | tail -1 | cut -d= -f2
}

set_last_heal() {
  local n="$1" t="$2"
  grep -v "^$n=" "$STATE" 2>/dev/null > "${STATE}.tmp" || true
  echo "$n=$t" >> "${STATE}.tmp"
  mv -f "${STATE}.tmp" "$STATE"
}

heal_mini() {
  local name="$1"
  local log="$LOG_DIR/$name.log"
  local run="$RUN_DIR/run_$name.sh"
  [ -f "$log" ] || return 0
  [ -f "$run" ] || return 0

  # freshness gate (don't heal a log that stopped updating)
  local mtime; mtime=$(stat -c %Y "$log" 2>/dev/null || echo 0)
  local age=$(( $(now_ts) - mtime ))
  if [ "$age" -ge "$LOG_MAX_AGE" ]; then
    echo "$(date '+%F %T') SKIP $name stale age=$age" >> "$LOG"; return 0
  fi

  # failure-count gate
  local fails; fails=$(tail -n "$TAIL_LINES" "$log" 2>/dev/null | grep -ciE "$FAIL_RE")
  [ "$fails" -ge "$MIN_FAILS" ] || return 0

  # per-mini cooldown (anti-thrash)
  local last; last=$(last_heal "$name")
  if [ -n "$last" ]; then
    local since=$(( $(now_ts) - last ))
    if [ "$since" -lt "$COOLDOWN" ]; then
      echo "$(date '+%F %T') COOLDOWN $name since=$since" >> "$LOG"; return 0
    fi
  fi

  # current model — anchored to the slug ONLY (lesson #8)
  local cur; cur=$(grep -oE "$MODEL_RE" "$run" 2>/dev/null | head -1)
  [ -n "$cur" ] || { echo "$(date '+%F %T') NO_MODEL $name" >> "$LOG"; return 0; }

  # next model != cur
  local next=""
  for m in "${MODELS[@]}"; do
    [ "$m" != "$cur" ] && { next="$m"; break; }
  done
  [ -n "$next" ] || return 0

  # capture geometry + workspace BEFORE killing (wmctrl -lpG: id ws pid X Y W H host title)
  local pid="" geo="" ws=""
  pid=$(pgrep -f "eni_agent_term.py --name $name" | head -1)
  if [ -n "$pid" ]; then
    local line; line=$(wmctrl -lpG 2>/dev/null | awk -v p="$pid" '$3==p {print $2","$4","$5","$6","$7}')
    if [ -n "$line" ]; then
      ws=$(echo "$line" | cut -d, -f1)
      geo=$(echo "$line" | cut -d, -f2,3,4,5)
    fi
  fi
  [ -z "$geo" ] && geo="0,0,900,500"
  [ -z "$ws" ] && ws=0

  # rewrite ONLY the hermes model token — anchored sed (lesson #8: never bare -m)
  sed -i -E "s|-m ${MODEL_RE} |-m ${next} |" "$run"

  # kill window + bridge (separate statements; no inline pattern collisions)
  if [ -n "$pid" ]; then
    local wid; wid=$(wmctrl -lp 2>/dev/null | awk -v p="$pid" '$3==p {print $1}' | head -1)
    [ -n "$wid" ] && wmctrl -i -c "$wid" 2>/dev/null
  fi
  pkill -9 -f "eni_agent_term.py --name $name" 2>/dev/null
  sleep 2

  # respawn at exact rect + workspace
  xfce4-terminal --disable-server -e "bash $run" >/dev/null 2>&1 &
  sleep 3
  local npid; npid=$(pgrep -f "eni_agent_term.py --name $name" | head -1)
  if [ -n "$npid" ]; then
    local nwid; nwid=$(wmctrl -lp 2>/dev/null | awk -v p="$npid" '$3==p {print $1}' | head -1)
    if [ -n "$nwid" ]; then
      IFS=',' read -r X Y W H <<< "$geo"
      wmctrl -i -r "$nwid" -e "0,$X,$Y,$W,$H"
      wmctrl -i -r "$nwid" -t "$ws"
    fi
  fi

  set_last_heal "$name" "$(now_ts)"
  echo "$(date '+%F %T') ROTATE $name cur='$cur' -> '$next' fails=$fails geom=$geo ws=$ws" >> "$LOG"
}

while true; do
  shopt -s nullglob
  for logf in "$LOG_DIR"/*.log; do
    heal_mini "$(basename "$logf" .log)"
  done
  shopt -u nullglob
  sleep "$HEAL_INTERVAL"
done
