#!/usr/bin/env bash
# paint_4programs.sh -- 4-program parallel-build swarm, one program per X11 workspace.
# Each workspace: 12 builders (B01..B12) + heartbeat + PL/master.
# Proven mechanics: wmctrl -i -r placement, zero-padded titles, literal OANDA key,
# 1s stagger, no --fifo. See parallel-build-orchestration
# references/paint_4programs_swarm.md for the full rationale + pitfalls.
#
# Usage:  bash ~/Desktop/paint_4programs.sh          # idempotent (skips seated windows)
#         FORCE=1 bash ~/Desktop/paint_4programs.sh  # full relaunch (kills+respawns)
#
# BEFORE FIRST RUN: set OANDA_TOKEN below to the LITERAL key (write_file/heredoc mangles
# a $VAR ref to '***'; do NOT use $(grep ...) -- nested quotes break bash).
set -u
export DISPLAY="${DISPLAY:-:0.0}"
PROXY=~/.local/bin/eni_agent_term.py
TABDIR=/tmp/eni4p_tabs
CACHE=~/.cache/eni_parallel
LOCK=/tmp/paint_4programs.lock
mkdir -p "$TABDIR" "$CACHE"

# --- OANDA key: bake the LITERAL value (children inherit it through the process chain) ---
export OANDA_TOKEN="PASTE_LITERAL_OANDA_KEY_HERE"

# WS assignment: one program per workspace
PROGS=(STOCKBOT DEMIURGE3D DEMIURGE LUMEN)
WSS=(0 1 2 3)
MODELS=(tencent/hy3:free qwen/qwen3-coder:free meta-llama/llama-3.3-70b-instruct:free qwen/qwen2.5-72b-instruct:free)
PL_MODEL=qwen/qwen3-coder:free
MASTER_MODEL=tencent/hy3:free

mk_runscript() {  # $1=PROG $2=IDX(2-digit) $3=model
  local prog="$1" idx="$2" model="$3"
  local f="$TABDIR/run_${prog}_B${idx}.sh"
  cat > "$f" <<EOR
#!/usr/bin/env bash
while true; do
  python3 "$PROXY" --name ${prog}_B${idx} --task "$CACHE/task_${prog}_B${idx}.txt" \
    --repl "hermes chat --yolo -m ${model} --provider openrouter"
  sleep 1
done
EOR
  chmod +x "$f"
}

place() {  # $1=exact title $2=ws
  local t="$1" ws="$2" id
  id=$(wmctrl -l 2>/dev/null | grep -F "$t" | awk '{print $1}' | head -1)
  [ -n "$id" ] && wmctrl -i -r "$id" -t "$ws"
}

window_exists() { wmctrl -l 2>/dev/null | grep -Fq "$1"; }

(
flock -n 9 || { echo "another painter holds $LOCK -- exit"; exit 0; }

FORCE="${FORCE:-0}"
for i in "${!PROGS[@]}"; do
  prog="${PROGS[$i]}"; ws="${WSS[$i]}"

  # heartbeat (upper, single tab) on this workspace
  HB="$TABDIR/run_${prog}_HEARTBEAT.sh"
  cat > "$HB" <<EOR
#!/usr/bin/env bash
while true; do clear; echo "[$(date)] ${prog} heartbeat"; \
  ls -t /home/hunter/Commander/demiurge_scaffold/STATUS_${prog}*.md 2>/dev/null | head -3; sleep 15; done
EOR
  chmod +x "$HB"
  if [ "$FORCE" = 1 ] || ! window_exists "ENI:${prog} HEARTBEAT"; then
    xfce4-terminal --disable-server --title "ENI:${prog} HEARTBEAT" -e "bash $HB" \
      --geometry 200x6+1950+10 </dev/null >/dev/null 2>&1 &
  fi

  # builders B01..B12
  for n in $(seq -w 1 12); do
    m="${MODELS[$((10#$n % ${#MODELS[@]}))]}"
    mk_runscript "$prog" "$n" "$m"
    title="ENI:${prog}_B${n}"
    if [ "$FORCE" = 1 ] || ! window_exists "$title"; then
      xfce4-terminal --disable-server --title "$title" -e "bash $TABDIR/run_${prog}_B${n}.sh" \
        --geometry 90x23+1920+40 </dev/null >/dev/null 2>&1 &
      sleep 1   # 429-soften stagger
      place "$title" "$ws"
    fi
  done

  # PL/master
  PL="$TABDIR/run_${prog}_PL.sh"
  cat > "$PL" <<EOR
#!/usr/bin/env bash
while true; do python3 "$PROXY" --name PL_${prog} --task "$CACHE/task_PL_${prog}.txt" \
  --repl "hermes chat --yolo -m $PL_MODEL --provider openrouter"; sleep 2; done
EOR
  chmod +x "$PL"
  if [ "$FORCE" = 1 ] || ! window_exists "ENI:${prog} PL"; then
    xfce4-terminal --disable-server --title "ENI:${prog} PL" -e "bash $PL" \
      --geometry 200x23+1950+200 </dev/null >/dev/null 2>&1 &
    place "ENI:${prog} PL" "$ws"
  fi
done

# one MASTER chat (drives all) on WS0
if [ "$FORCE" = 1 ] || ! window_exists "ENI:MASTER"; then
  xfce4-terminal --disable-server --title "ENI:MASTER" \
    -e "hermes chat --yolo -m $MASTER_MODEL --provider openrouter" \
    --geometry 200x23+1950+450 </dev/null >/dev/null 2>&1 &
  place "ENI:MASTER" 0
fi

echo "PAINT DONE"
) 9>"$LOCK"
