#!/usr/bin/env bash
# recover_headless_floor.sh — ENI swarm headless floor crash recovery.
# Kills stale flock holders by FD (never by name regex — that self-matches the
# running shell and SIGTERMs it), regenerates run scripts, relaunches, and
# clears stale logs so the NEXT error is the live one.
set -u
ROOT=/home/hunter/Desktop/Commander/eni_swarm
OD=/tmp/eni_opt
cd "$ROOT" || exit 1

# 1) Free any stale lock holder(s) by fd. Do NOT pkill by name — the
#    pattern would also match this script's own cmdline and kill the shell.
holders=$(fuser "$OD.lock" 2>/dev/null | tr ' ' '\n' | grep -v '^$')
if [ -n "$holders" ]; then
  echo "freeing stale lock holders: $holders"
  kill -9 $holders 2>/dev/null
  sleep 2
fi

# 2) Regenerate the 54 run scripts (applies any gen_floor_opt.sh fixes).
bash gen_floor_opt.sh >/dev/null 2>&1 && echo "GEN: $(ls "$OD"/run_*.sh | wc -l) run scripts"

# 3) Clear stale logs so the NEXT error is the live one (not last run's).
find "$OD"_logs -name '*.log' -exec truncate -s 0 {} \; 2>/dev/null

# 4) Idempotent relaunch (skips builders already alive, starts sentinel/healer).
bash swarm_start_opt.sh 2>&1 | tail -3

# 5) Sanity: the generated cmd must be literal, NOT empty.
echo "sample generated cmd (expect: nice -n 5 \"\${CMD[@]}\"):"
sed -n '14p' "$OD/run_D3D1.sh"
sleep 20
echo "alive proxies: $(pgrep -fc 'eni_agent_ter[m].py')"
echo "--- D3D1.log (expect hermes REPL banner, NOT 'No such file') ---"
tail -8 "$OD"_logs/D3D1.log 2>/dev/null
