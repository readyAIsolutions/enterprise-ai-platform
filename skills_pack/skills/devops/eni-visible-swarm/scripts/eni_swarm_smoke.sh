#!/usr/bin/env bash
# eni_swarm_smoke.sh -- ENI swarm spine self-test (ENI8).
# Proves the down-channel + self-heal WITHOUT touching the live fleet.
#   TEST A: relay -> /tmp/eni_ctl_<NAME> -> pty -> REPL EXECUTES the directive.
#   TEST B: non-blocking relay -> dead fifo returns rc!=0 in <2s (no hang).
#   TEST C: self-heal -> kill bridge -> NEW pid respawns; kill mini-run -> 0 orphans.
# Usage:  bash scripts/eni_swarm_smoke.sh [SMOKE_NAME]
set -u
NAME="${1:-ENI8SMOKE}"
ROOT=/home/hunter/Commander/eni_swarm
RUNPY=/home/hunter/.local/bin/eni_agent_term.py
SMOKE_REPL=/tmp/${NAME}_repl.sh
EXEC_LOG=/tmp/${NAME}_exec.log
CTL=/tmp/eni_ctl_$NAME
DEAD=/tmp/eni_ctl_${NAME}_DEAD

cleanup() {
  pkill -f "eni_agent_term.py --name $NAME" 2>/dev/null
  pkill -f "eni_mini_run.sh $NAME" 2>/dev/null
  pkill -f "$SMOKE_REPL" 2>/dev/null
  rm -f "$CTL" "$DEAD" "$EXEC_LOG" "$SMOKE_REPL" /tmp/${NAME}_bridge.log /tmp/${NAME}_mini.log
  rm -f "$ROOT/logs/${NAME}.log" "$ROOT/STATUS_${NAME}.md"
}
trap cleanup EXIT

cat > "$SMOKE_REPL" <<'EOF'
#!/usr/bin/env bash
while true; do
  printf "ENI> "
  read -r line
  [ -n "$line" ] && echo "EXEC:$line" >> /tmp/ENI8SMOKE_exec.log
done
EOF
# point the REPL log at our EXEC_LOG regardless of NAME
sed -i "s#/tmp/ENI8SMOKE_exec.log#$EXEC_LOG#" "$SMOKE_REPL"
chmod +x "$SMOKE_REPL"
: > "$EXEC_LOG"

echo "=== TEST A: relay -> FIFO -> pty -> REPL executes ==="
rm -f "$CTL"
python3 "$RUNPY" --name "$NAME" --task /dev/null --ctl "$CTL" --repl "bash $SMOKE_REPL" \
  >/tmp/${NAME}_bridge.log 2>&1 &
BRIDGE=$!
sleep 1.5
bash "$ROOT/eni_relay.sh" "$NAME" "smoke directive alpha"
sleep 1
if grep -q "EXEC:LO via MASTER: smoke directive alpha" "$EXEC_LOG"; then
  echo "TEST A RESULT: PASS  (directive traversed FIFO->pty->REPL and executed)"
else
  echo "TEST A RESULT: FAIL"; echo "--- exec log ---"; cat "$EXEC_LOG"; echo "--- bridge log ---"; cat /tmp/${NAME}_bridge.log
fi
pkill -f "eni_agent_term.py --name $NAME" 2>/dev/null
wait "$BRIDGE" 2>/dev/null
rm -f "$CTL"

echo "=== TEST B: non-blocking relay never hangs when mini is down ==="
rm -f "$DEAD"; mkfifo "$DEAD"
start=$(date +%s)
out=$(bash "$ROOT/eni_relay.sh" ${NAME}_DEAD "should not hang" 2>&1); rc=$?
end=$(date +%s); dur=$((end - start))
# expectation: relay exits NON-zero fast (ENXIO, no blocking open) and reports the dead mini
if [ $rc -ne 0 ] && [ "$dur" -lt 2 ]; then
  echo "TEST B RESULT: PASS  (rc=$rc in ${dur}s, no hang)"
else
  echo "TEST B RESULT: FAIL  (rc=$rc dur=${dur}s out=$out)"
fi
rm -f "$DEAD"

echo "=== TEST C: self-heal while-true restarts bridge after kill ==="
bash "$ROOT/eni_mini_run.sh" "$NAME" >/tmp/${NAME}_mini.log 2>&1 &
MINI=$!
sleep 2
B1=$(pgrep -f "eni_agent_term.py --name $NAME" | head -1)
echo "first bridge pid: ${B1:-NONE}"
kill -TERM "$B1" 2>/dev/null
sleep 4
B2=$(pgrep -f "eni_agent_term.py --name $NAME" | head -1)
echo "second bridge pid: ${B2:-NONE}"
if [ -n "$B1" ] && [ -n "$B2" ] && [ "$B1" != "$B2" ]; then
  echo "TEST C RESULT: PASS  (old bridge $B1 killed, new $B2 respawned by while-true)"
else
  echo "TEST C RESULT: FAIL  (B1=$B1 B2=$B2)"
fi
kill -TERM "$MINI" 2>/dev/null
sleep 2
if ! pgrep -f "eni_mini_run.sh $NAME" >/dev/null && ! pgrep -f "eni_agent_term.py --name $NAME" >/dev/null; then
  echo "TEST C cleanup: PASS  (no orphan processes)"
else
  echo "TEST C cleanup: FAIL  (orphans remain):"
  ps -eo pid,ppid,cmd | grep -E "eni_agent_term|eni_mini_run|while true; do printf" | grep -v grep
  pkill -f "eni_agent_term.py --name $NAME"; pkill -f "eni_mini_run.sh $NAME"; pkill -f "while true; do printf"
fi

echo "=== smoke complete ==="
