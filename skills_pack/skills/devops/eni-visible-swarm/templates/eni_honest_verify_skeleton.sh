#!/usr/bin/env bash
# eni_honest_verify_skeleton.sh — REUSABLE, ADD-ONLY self-test skeleton for ANY
# ENI mini. Copy this into the mini's workdir and FILL the marked TODOs to encode
# the mini's REAL current-core contract. Do NOT edit the proven core — only add a
# new harness like this one.
#
# Design rules that prevented the ENI7 stale-GREEN / pipe-hang bugs:
#   * Runs checks DIRECTLY (stdout to the terminal) and `exit $BAD` at the end.
#     NEVER wrap this in `OUT="$(bash ...)"` capture — a background reader can
#     inherit the capture pipe and wedge the caller (180s timeout, no output).
#   * Creates its OWN test FIFOs via mkfifo, so it works whether or not the core
#     auto-creates them. Cleans up via `trap` so no strays linger.
#   * Scopes fleet/async tests to a 'V*' glob so it never broadcasts into the
#     LIVE swarm's FIFOs during a self-test.
#   * Documents the late-reader / durable-delivery limit as a NOTE, never a false PASS.
#
# Usage:  bash eni_honest_verify_skeleton.sh
set -uo pipefail

# TODO: point this at the mini's workdir (where the proven core lives).
cd /home/hunter/Commander/eni_swarm

PREFIX="LO via MASTER: "
BAD=0

# Test FIFOs this harness owns (scoped to V* so 'all' never hits live minis).
TMPF=(/tmp/eni_ctl_V1 /tmp/eni_ctl_V2 /tmp/eni_ctl_V3 /tmp/eni_ctl_VX /tmp/eni_ctl_VY)
cleanup() { rm -f "${TMPF[@]}" /tmp/vX.txt /tmp/vY.txt /tmp/v2.txt 2>/dev/null; }
trap cleanup EXIT
cleanup

echo "=== <MINI> self-test (aligned to CURRENT on-disk core) ==="

# TODO: replace these with the mini's ACTUAL current-core guarantees.
# Below is the ENI7 relay contract as a worked example — adapt to your mini.

# A. absent target => returns immediately, never wedges (encode the real rc).
rm -f /tmp/eni_ctl_V1
t0=$(date +%s); ./eni_relay.sh V1 "x" >/dev/null 2>&1; rc=$?; t1=$(date +%s); dt=$((t1-t0))
if [ "$rc" = "1" ] && [ "$dt" -lt 10 ]; then
  echo "PASS A: absent target -> rc=1, returned in ${dt}s (nonblock, never wedges)"
else
  echo "FAIL A (rc=$rc dt=${dt}s)"; BAD=1
fi

# B. live reader gets the prefixed body verbatim.
rm -f /tmp/eni_ctl_V2 /tmp/v2.txt; mkfifo /tmp/eni_ctl_V2
timeout 5 head -n1 /tmp/eni_ctl_V2 > /tmp/v2.txt &
RP=$!; sleep 0.3
./eni_relay.sh V2 "line with spaces and 'quotes'" >/dev/null 2>&1
wait "$RP" 2>/dev/null
got="$(cat /tmp/v2.txt)"; exp="${PREFIX}line with spaces and 'quotes'"
if [ "$got" = "$exp" ]; then echo "PASS B: prefixed body delivered verbatim to live reader"
else echo "FAIL B (got=[$got])"; BAD=1; fi

# C. FIFO present but NO live reader => nonblocking, fast (encode the real rc).
rm -f /tmp/eni_ctl_V3; mkfifo /tmp/eni_ctl_V3
t0=$(date +%s); ./eni_relay.sh V3 "orphan line" 2>/dev/null; rc=$?; t1=$(date +%s); dt=$((t1-t0))
if [ "$rc" = "2" ] && [ "$dt" -lt 10 ]; then
  echo "PASS C: no live reader -> rc=2 (ENXIO), returned in ${dt}s (nonblock)"
else
  echo "FAIL C (rc=$rc dt=${dt}s)"; BAD=1
fi
rm -f /tmp/eni_ctl_V3

# D. usage guard (no args) exits non-zero.
./eni_relay.sh >/dev/null 2>&1; rc=$?
if [ "$rc" != "0" ]; then echo "PASS D: usage guard exits non-zero (rc=$rc)"
else echo "FAIL D (rc=0)"; BAD=1; fi

# E. fleet/glob nonblocking dispatch, SCOPED to V* (never 'all' in a self-test).
rm -f /tmp/eni_ctl_VX /tmp/eni_ctl_VY /tmp/vX.txt /tmp/vY.txt
mkfifo /tmp/eni_ctl_VX; mkfifo /tmp/eni_ctl_VY
timeout 5 head -n1 /tmp/eni_ctl_VX > /tmp/vX.txt & RX=$!
timeout 5 head -n1 /tmp/eni_ctl_VY > /tmp/vY.txt & RY=$!
sleep 0.3
./eni_relay.sh 'V*' "fleet ping" >/dev/null 2>&1
sleep 0.2
if [ -p /tmp/eni_ctl_VX ] && [ -p /tmp/eni_ctl_VY ]; then
  echo "PASS E: fleet glob 'V*' nonblocking dispatch to both FIFOs"
else echo "FAIL E"; BAD=1; fi
wait "$RX" "$RY" 2>/dev/null
gx="$(cat /tmp/vX.txt)"; gy="$(cat /tmp/vY.txt)"
if [ "$gx" = "${PREFIX}fleet ping" ] && [ "$gy" = "${PREFIX}fleet ping" ]; then
  echo "PASS Eb: fleet content delivered verbatim to live readers"
else echo "FAIL Eb (vx=[$gx] vy=[$gy])"; BAD=1; fi

# F. status aggregation (if the mini has one).
# TODO: swap for the mini's own aggregator check.
./eni_status.sh > /tmp/status_out.txt 2>&1
if grep -q "STATUS_ENI7.md" /tmp/status_out.txt; then echo "PASS F: status aggregates STATUS_ENI*.md"
else echo "FAIL F"; BAD=1; fi

echo "NOTE: late-reader durability NOT guaranteed by current core (KNOWN LIMITATION — document in STATUS_<MINI>.md)"
echo "=== <MINI> self-test summary: $([ $BAD -eq 0 ] && echo GREEN || echo RED) (BAD=$BAD) ==="
exit $BAD
