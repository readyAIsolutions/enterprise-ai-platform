#!/usr/bin/env bash
# verify_swarm_floor.sh — static (no-X) verification of the product-aware ENI floor.
# Run after editing swarm_products.cfg / the swarm scripts, BEFORE booting on X.
# Exit 0 = all checks pass; prints a PASS/FAIL board with real evidence.
set -u
SWARM=/home/hunter/Desktop/Commander/eni_swarm
cd "$SWARM" 2>/dev/null || { echo "CANNOT CD to $SWARM"; exit 1; }
export PATH="$HOME/.local/bin:$HOME/bin:$PATH"

pass=0; fail=0
ck(){ if [ "$1" = "0" ]; then echo "  [PASS] $2"; pass=$((pass+1)); else echo "  [FAIL] $2"; fail=$((fail+1)); fi; }

echo "=== 1) bash -n syntax on all swarm scripts + cfg ==="
bad=0
for f in swarm_products.cfg gen_run_scripts.sh swarm_lib.sh swarm_watchdog.sh swarm_start.sh; do
  bash -n "$f" 2>/dev/null && true || { echo "    SYNTAX FAIL: $f"; bad=1; }
done
ck "$bad" "all 5 scripts parse (bash -n)"

echo "=== 2) generator runs + writes product scripts ==="
out=$(bash gen_run_scripts.sh 2>&1)
nprod=$(echo "$out" | grep -oE 'products=([A-Z ]+)' | head -1)
echo "    $nprod"
ck "$(echo "$out" | grep -q 'builders=' && echo 0 || echo 1)" "gen_run_scripts.sh produced a builder count"

echo "=== 3) stale ENI/WS scripts removed from /tmp/eni_tabs ==="
stale=$(ls /tmp/eni_tabs 2>/dev/null | grep -E '^(run_ENI|heart_WS|master_WS|master_heartbeat|run_master_chat)' | wc -l)
ck "$(( stale == 0 ))" "no stale run_ENI*/heart_WS*/master_WS* (found $stale)"

echo "=== 4) product scripts present ==="
need="heart_SB.sh master_SB.sh launch_SB.sh run_SB1.sh status_SB1.sh heart_D3D.sh master_D3D.sh launch_D3D.sh run_D3D1.sh status_D3D1.sh heart_DEM.sh master_DEM.sh launch_DEM.sh run_DEM1.sh status_DEM1.sh heart_LUM.sh master_LUM.sh launch_LUM.sh run_LUM1.sh status_LUM1.sh"
missing=0
for s in $need; do [ -f "/tmp/eni_tabs/$s" ] || { echo "    MISSING /tmp/eni_tabs/$s"; missing=1; }; done
ck "$missing" "all 20 product scripts generated (4 products x 5)"

echo "=== 5) builder -> workspace mapping ==="
source swarm_products.cfg
mism=0
declare -A EXPECT=( [SB]=0 [D3D]=1 [DEM]=2 [LUM]=3 )
for pi in "${!PRODUCT_KEYS[@]}"; do
  key=${PRODUCT_KEYS[pi]}; nb=${PRODUCT_BUILDERS[pi]}; exp=${EXPECT[$key]}
  for ((i=1;i<=nb;i++)); do
    # recompute the same way builder_ws() would
    ws=0
    for q in "${!PRODUCT_KEYS[@]}"; do k2=${PRODUCT_KEYS[q]}; [[ "${key}${i}" == "${k2}"* ]] && { ws=${PRODUCT_WS[q]}; break; }; done
    [ "$ws" = "$exp" ] || { echo "    MISMATCH ${key}${i} -> ws$ws (expected ws$exp)"; mism=1; }
  done
done
ck "$mism" "every builder maps to its product's workspace"

echo "=== 6) viewer boot-log tab uses tail -F (not -f, which errors pre-existence) ==="
fc=$(grep -c 'tail -f /tmp/eni_logs' swarm_watchdog.sh)
ck "$(( fc == 0 ))" "no 'tail -f /tmp/eni_logs' in watchdog (found $fc; must be -F)"

echo "=== 7) non-prefixing key rule ==="
viol=0
for a in "${PRODUCT_KEYS[@]}"; do for b in "${PRODUCT_KEYS[@]}"; do
  [ "$a" = "$b" ] && continue
  [[ "$b" == "$a"* ]] && { echo "    KEY '$a' is a prefix of '$b'"; viol=1; }
done; done
ck "$viol" "no product key is a prefix of another (DEM vs D3D safe)"

echo
echo "RESULT: $pass passed, $fail failed"
[ "$fail" = "0" ] && echo "FLOOR CONFIG GREEN — safe to boot on X" || echo "FLOOR CONFIG RED — fix above before booting"
exit "$fail"
