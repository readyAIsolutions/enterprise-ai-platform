#!/usr/bin/env bash
# eni_resume.sh — ENI mini generic RESUME wrapper (TEMPLATE; copy + adapt per mini).
# Bundles: (1) aligned self-test, (2) live real-data pulse, (3) USB blocker check,
# prints GREEN/RED verdict. Add-only: never modifies the proven core.
# Usage: bash eni_resume.sh <MINI> [selftest_script]
set -u
MINI="${1:?usage: eni_resume.sh <MINI> [selftest_script]}"
# derive default self-test name, e.g. ENI7 -> eni7_selftest_hook_v3.sh
NUM="${MINI#ENI}"
SELFTEST="${2:-eni${NUM}_selftest_hook_v3.sh}"
SWARM=/home/hunter/Commander/eni_swarm
cd "$SWARM" || { echo "ENI RESUME: cannot cd to $SWARM" >&2; exit 1; }

echo "═══════════════════════════════════════════════════════════════"
echo " ENI $MINI RESUME  $(date '+%Y-%m-%d %H:%M:%S %Z')"
echo "═══════════════════════════════════════════════════════════════"

echo "──[1/3] wire self-test ($SELFTEST)──"
if [ -f "$SELFTEST" ]; then
  bash "$SELFTEST"; WIRE_RC=$?
else
  echo "  (no self-test $SELFTEST found — author one ALIGNED to the CURRENT core)" >&2
  WIRE_RC=1
fi
echo "    wire self-test EXIT=$WIRE_RC"

echo "──[2/3] real-data pulse (eni_status.sh)──"
bash eni_status.sh > /tmp/eni_status_pulse_${MINI}.txt 2>&1
PULSE_RC=$?
echo "    eni_status.sh EXIT=$PULSE_RC  ($(wc -l < /tmp/eni_status_pulse_${MINI}.txt) lines)"

echo "──[3/3] blocker check (USB DEMIURGE)──"
if mountpoint -q /run/media/hunter/DEMIURGE1; then
  BLK="NONE — DEMIURGE1 MOUNTED"; BLK_RC=0
elif mountpoint -q /run/media/hunter/DEMIURGE; then
  BLK="NONE — DEMIURGE MOUNTED"; BLK_RC=0
else
  BLK="BLOCKED — no DEMIURGE USB mounted (real OANDA/ref data unavailable; synthetic only)"; BLK_RC=1
fi
echo "    blocker: $BLK"

if [ "$WIRE_RC" -eq 0 ] && [ "$PULSE_RC" -eq 0 ]; then
  echo "═══════════════════════════════════════════════════════════════"
  echo " ENI $MINI RESUME VERDICT: Green (wire + pulse OK) | blocker: $BLK"
  echo "═══════════════════════════════════════════════════════════════"
  exit 0
else
  echo "═══════════════════════════════════════════════════════════════"
  echo " ENI $MINI RESUME VERDICT: RED (wire rc=$WIRE_RC pulse rc=$PULSE_RC) -- self-heal required"
  echo "═══════════════════════════════════════════════════════════════"
  exit 1
fi
