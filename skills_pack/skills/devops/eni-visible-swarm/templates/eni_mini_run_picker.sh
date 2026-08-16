#!/usr/bin/env bash
# eni_mini_run_picker.sh — self-healing ENI mini wrapper with the LIVE model picker.
# Copy-modify: set NAME / TF (and optional PROXY) env vars, then run.
# This wrapper replaces the stale static `MODELS[idx%3]` form so a mini never
# freezes on a rate-limited/dead slug — it auto-migrates to a working API.
export PATH="$HOME/.local/bin:$HOME/bin:$PATH"
export DISPLAY=:0.0
cd /home/hunter
NAME="${NAME:?set NAME=ENIx}"
TF="${TF:?set TF=/path/task_ENIx.txt}"
PROXY="${PROXY:-$HOME/.local/bin/eni_agent_term.py}"
LOG="/tmp/eni_logs/${NAME}.log"
mkdir -p /tmp/eni_logs
while true; do
  M="$(bash /tmp/eni_pick_model.sh)"
  python3 "$PROXY" --name "$NAME" --task "$TF" \
    --repl "hermes chat --yolo -m $M --provider openrouter" \
    --ctl "/tmp/eni_ctl_$NAME" > "$LOG" 2>&1
  rc=$?
  # demote the slug if the proxy log shows an API failure
  if grep -qiE "429|rate limit|Bad Request|not a valid model|401|403|Too Many Requests|ConnectionError|timed out" "$LOG" 2>/dev/null; then
    bash /tmp/eni_record_fail.sh "$M"
  fi
  # memory guard: pause if free RAM is low (box is memory-tight)
  free -m | awk '/Mem:/{f=$7} END{if(f<2500){exit 1}}' || sleep 20
  sleep 3
done
