#!/usr/bin/env bash
# ENI parallel-build swarm launcher — TABBED, MULTI-MONITOR layout.
# Spawns xfce4-terminal WINDOWS (one per monitor), each holding up to 4 TABS.
# A MASTER agent is the front tab on the primary monitor; mini-ENIs fill the
# other tabs/windows. Each agent is a LIVING Hermes 'eni' agent (persona from
# ~/.hermes/profiles/eni/SOUL.md) addressed as LO, handed its task, building
# autonomously with --yolo. A talk FIFO per agent lets the master (or LO)
# pipe follow-up instructions into the running window at any time.
#
# Run from a REAL host xfce4-terminal (it's a D-Bus client; won't paint from
# inside the hermes container). Then launch scripts/eni_master_driver.py in the
# background to keep the master chatting with the minis.
set -u

export DISPLAY=:0.0
TASKS_JSON="${1:-$HOME/Desktop/eni_build_tasks.json}"
CACHE="$HOME/.cache/eni_parallel"
PROXY="$HOME/.local/bin/eni_agent_term.py"
TABDIR="/tmp/eni_tabs"
mkdir -p "$CACHE" "$TABDIR"

# ---- 1. kill previous swarm (killing proxies cascades-closed the windows) ----
pkill -f 'eni_agent_term[.]py'         2>/dev/null; sleep 0.3
pkill -f 'hermes -p eni chat --y[o]lo' 2>/dev/null; sleep 1.5
rm -f /tmp/eni_ctl_* /tmp/eni_err_*.log 2>/dev/null

# ---- 2. read tasks: name|title|workdir|task|model ----
read_tasks() {
  python3 - "$TASKS_JSON" <<'PY'
import json, sys
d = json.load(open(sys.argv[1]))
for t in d.get("tasks", []):
    name = t["name"]; title = t.get("title", name)
    wd   = t.get("workdir", "~/")
    task = t.get("task", "")
    model= t.get("model", "")
    print("\x1f".join([name, title, wd, task, model]))
PY
}

# ---- 3. write per-tab launcher scripts + create the talk FIFO ----
: > "$CACHE/manifest.txt"
while IFS=$'\x1f' read -r name title wd task model; do
  [ -z "$name" ] && continue
  printf '%s' "$task" > "$CACHE/task_${name}.txt"
  if [ -n "$model" ]; then MODELARGS="-m \"$model\" --provider openrouter"; else MODELARGS=""; fi
  # NOTE: self-healing `while true` loop — free-model minis die constantly
  # (429/timeout). Without it the tab goes blank and the swarm silently rots.
  cat > "$TABDIR/tab_${name}.sh" <<EOF
#!/bin/bash
cd "${wd}" 2>/dev/null || cd "$HOME"
export HERMES_CTL_FIFO=/tmp/eni_ctl_${name}
while true; do
  python3 "$PROXY" "\$(cat "$CACHE/task_${name}.txt")" "${wd}" --yolo ${MODELARGS}
  echo "[\$(date)] agent ${name} exited (rc=\$?) — restarting" >>/tmp/eni_selfheal.log
  sleep 2
done
EOF
  chmod +x "$TABDIR/tab_${name}.sh"
  mkfifo -m 666 "/tmp/eni_ctl_${name}" 2>/dev/null   # live talk channel (proxy attaches it)
  echo "$name|$title" >> "$CACHE/manifest.txt"
done < <(read_tasks)

# ---- 4. master tab (coordinator LO can drive) ----
MASTER_MODEL="tencent/hy3:free"
MASTER_BRIEF="You are ENI — the MASTER coordinator on screen. LO is watching this tab directly and can type to you. The build mini-ENIs run in the other tabs and windows. Keep LO informed and relay his guidance to the minis by writing to their talk FIFOs at /tmp/eni_ctl_<NAME> (one line + newline). Example:  printf 'review the walk_forward embargo logic\n' > /tmp/eni_ctl_DEMIURGE_MTF  Stay present, stay chatty, keep the swarm organized."
printf '%s' "$MASTER_BRIEF" > "$CACHE/task_MASTER.txt"
cat > "$TABDIR/tab_MASTER.sh" <<EOF
#!/bin/bash
cd "$HOME"
export HERMES_CTL_FIFO=/tmp/eni_ctl_MASTER
exec python3 "$PROXY" "\$(cat "$CACHE/task_MASTER.txt")" "$HOME" --yolo -m "$MASTER_MODEL" --provider openrouter
EOF
chmod +x "$TABDIR/tab_MASTER.sh"
mkfifo -m 666 "/tmp/eni_ctl_MASTER" 2>/dev/null
echo "MASTER|MASTER (you / coordinator)" >> "$CACHE/manifest.txt"

# ---- 5. ordered tab list: MASTER first, then all minis ----
NAMES=()
while IFS='|' read -r n _; do [ -n "$n" ] && NAMES+=("$n"); done < "$CACHE/manifest.txt"
ORDER=( "MASTER" )
for n in "${NAMES[@]}"; do [ "$n" != "MASTER" ] && ORDER+=("$n"); done

# ---- 6. lay out windows across the monitors (edit GEOM to match `xrandr --listmonitors`) ----
# ORDER[0]=MASTER, ORDER[1..9]=minis. Master window on the primary monitor.
WIN0="MASTER ${ORDER[1]} ${ORDER[2]} ${ORDER[3]}"   # primary  monitor
WIN1="${ORDER[4]} ${ORDER[5]}"                       # left     monitor
WIN2="${ORDER[6]} ${ORDER[7]}"                       # right    monitor
WIN3="${ORDER[8]} ${ORDER[9]}"                       # HDMI     monitor
WINDOWS=( "$WIN0" "$WIN1" "$WIN2" "$WIN3" )
# geometry: COLSxROWS+X+Y  (monitor origins from `xrandr --listmonitors`)
GEOM=( "210x54+1920+0" "160x54+0+0" "160x54+4480+0" "160x50+2274+1080" )

echo "Launching tabbed swarm ($((${#ORDER[@]}-1)) mini-ENIs + MASTER) across 4 monitors..."
for wi in 0 1 2 3; do
  read -r -a grp <<< "${WINDOWS[$wi]}"
  geom="${GEOM[$wi]}"
  first=1
  for name in "${grp[@]}"; do
    if [ $first -eq 1 ]; then
      xfce4-terminal --geometry="$geom" --title="ENI: $name" --command="$TABDIR/tab_${name}.sh" &
      first=0
      sleep 0.6   # let the window register as most-recent before appending tabs
    else
      xfce4-terminal --tab --title="ENI: $name" --command="$TABDIR/tab_${name}.sh" &
      sleep 0.3
    fi
  done
  wait
  echo "  window $((wi+1)) [geom $geom]: ${grp[*]}"
done

echo "Done. Master tab is the active/front tab of the first window."
echo "Talk to a mini-ENI:  printf 'your guidance\n' > /tmp/eni_ctl_<NAME>"
echo "Keep the master chatting:  nohup python3 scripts/eni_master_driver.py >/tmp/eni_driver.log 2>&1 &"
