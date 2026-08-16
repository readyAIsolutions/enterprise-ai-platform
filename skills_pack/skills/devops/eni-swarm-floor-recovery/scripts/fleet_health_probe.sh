#!/usr/bin/env bash
# Consolidated ENI fleet health probe — all four axes in ONE run.
# Drop-in for fleet-monitor cron runs. Reconstructs the full picture without
# hand-typing 4+ separate calls. Safe to run when floor is idle/dormant.
#
# Usage:  bash fleet_health_probe.sh   (run from eni_swarm/ or absolute)
# Exit:   0 always (it's a report, not a gate). Axes are reported independently.
#
# AXES (independent — one down does NOT imply system down):
#   1) Builder floor  -> STATUS_BUILDER_*.md mtimes + ledger state counts
#   2) :8420 dashboard -> up = /health HTTP 200 + bound port; 000 = down
#   3) :8922 turbocharger -> up = /health HTTP 200 + bound port
#   4) Controller brain -> fresh MASTER_STATUS.md mtime + status_hub.cron.log self-heal
# Plus: fleet_pulse --once (windows=N | gate=RED/GREEN) — run AFTER monitor_fleet.py.
#
# NOTE: env -u PYTHONPATH disables the ENI compression hook so large outputs
# return as plain text instead of <ENI-COMPRESSED> carrier wraps.

set -u
SWARM="${SWARM_DIR:-/home/hunter/Commander/eni_swarm}"
cd "$SWARM" || { echo "FATAL: cannot cd $SWARM"; exit 1; }

echo "############ FLEET HEALTH PROBE @ $(date '+%Y-%m-%d %H:%M') ############"

# --- 1) Builder floor -------------------------------------------------------
echo; echo "=== AXIS 1: builder floor ==="
# regenerate ledger FIRST so pulse/queue below reflect current disk state
env -u PYTHONPATH python3 monitor_fleet.py >/dev/null 2>&1
LEDGER="builds/HEARTBEAT_LEDGER.md"; [ -s "$LEDGER" ] || LEDGER="HEARTBEAT_LEDGER.md"
echo "ledger states: DONE=$(grep -c '^\[DONE\]' "$LEDGER") IN=$(grep -c '^\[IN-PROGRESS\]' "$LEDGER") BLOCKED=$(grep -c '^\[BLOCKED\]' "$LEDGER")"
echo "rows with no real detail: $(grep -c 'verified=unknown blocker=unknown next=unknown' "$LEDGER")"
echo "-- newest STATUS files --"
find . -name 'STATUS_BUILDER_*.md' -printf '%TY-%Tm-%Td %TH:%TM %f\n' 2>/dev/null | sort | tail -3
echo "-- oldest STATUS files --"
find . -name 'STATUS_BUILDER_*.md' -printf '%TY-%Tm-%Td %TH:%TM %f\n' 2>/dev/null | sort | head -3

# --- 2) dashboard :8420 -----------------------------------------------------
echo "[2] AXIS 2: dashboard :8420"
curl -s -o /dev/null -w '  health=%{http_code}\n' --max-time 5 http://127.0.0.1:8420/health
ss -ltn 2>/dev/null | grep -q ':8420' && echo "  :8420 bound" || echo "  :8420 NOT bound"

# --- 3) turbocharger :8922 --------------------------------------------------
echo "[3] AXIS 3: turbocharger :8922"
curl -s -o /dev/null -w '  health=%{http_code}\n' --max-time 5 http://127.0.0.1:8922/health
ss -ltn 2>/dev/null | grep -q ':8922' && echo "  :8922 bound" || echo "  :8922 NOT bound"

# --- 4) controller ----------------------------------------------------------
echo "[4] AXIS 4: controller"
if [ -s MASTER_STATUS.md ]; then
  echo "  MASTER_STATUS.md mtime: $(stat -c '%y' MASTER_STATUS.md)"
else
  echo "  MASTER_STATUS.md MISSING"
fi
LOG=$(find . -maxdepth 2 -name 'status_hub.cron.log' 2>/dev/null | head -1)
[ -n "$LOG" ] && echo "  status_hub.cron.log tail:" && tail -2 "$LOG"

# --- pulse (single tick only — bare fleet_pulse.py LOOPS forever) -----------
echo "[~] pulse: $(env -u PYTHONPATH timeout 10 python3 fleet_pulse.py --once 2>&1 | grep -iE 'windows|gate|stall' | head -1)"

echo "=============================================================="
echo "Interpretation: gate=RED + windows=0 + stalls=none + empty queue == IDLE/dormant, NOT down. Only relaunch against real queued work."