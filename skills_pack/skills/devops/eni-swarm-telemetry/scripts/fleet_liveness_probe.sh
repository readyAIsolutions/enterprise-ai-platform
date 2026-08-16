#!/usr/bin/env bash
# fleet_liveness_probe.sh — one-shot liveness triage for the ENI heapbeat.
# Run from the swarm dir (e.g. /home/hunter/Commander/eni_swarm) AFTER
# `monitor_fleet.py` has regenerated HEARTBEAT_LEDGER.md.
#
# Purpose: the ledger's [IN-PROGRESS]/[BLOCKED] rows are frequently STALE relics,
# not live work. This probe cross-checks disk state + processes so you can tell
# "actively building" from "dormant/parked" before reporting a fleet status.
# Exit 0 from monitor_fleet.py means ONLY that aggregation ran — NOT liveness.
set -u

SWARM_DIR="${1:-.}"
LEDGER="${SWARM_DIR}/HEARTBEAT_LEDGER.md"

# Guard: running from the wrong cwd (or omitting $1) silently yields all-zero
# "fleet dead" readings that look like a crash. THIS IS A FALSE ALARM — the real
# swarm dir is normally /home/hunter/Commander/eni_swarm. Detect and flag it.
_STATUS_COUNT=$(ls ${SWARM_DIR}/builds/STATUS_BUILDER_*.md 2>/dev/null | wc -l)
if [ "${_STATUS_COUNT}" -eq 0 ]; then
    echo "WARNING: 0 status files found under '${SWARM_DIR}/builds'."
    echo "  Likely wrong cwd or missing \$1. Correct usage:"
    echo "  bash $(basename "$0") /home/hunter/Commander/eni_swarm"
    echo "  (or cd /home/hunter/Commander/eni_swarm first)."
    echo "  A zero here is usually a bad path, NOT a dead fleet — re-check before reporting."
    echo
fi

echo "=== on-disk vs ledger ==="
echo "DISK_STATUS_FILES=$(ls ${SWARM_DIR}/builds/STATUS_BUILDER_*.md 2>/dev/null | wc -l)"
echo "LEDGER_LINES=$(wc -l < "${LEDGER}" 2>/dev/null || echo 0)"

echo "=== ledger state distribution ==="
grep -oP '^\[\K[A-Z-]+' "${LEDGER}" 2>/dev/null | sort | uniq -c

echo "=== IN-PROGRESS / BLOCKED rows (verify staleness below) ==="
grep -E '^\[(IN-PROGRESS|BLOCKED)\]' "${LEDGER}" 2>/dev/null

echo "=== freshness (the real signal) ==="
echo "total_status_files=$(ls ${SWARM_DIR}/builds/STATUS_BUILDER_*.md 2>/dev/null | wc -l)"
echo "fresh_today=$(find ${SWARM_DIR}/builds -name 'STATUS_BUILDER_*.md' -newermt 'today 00:00' 2>/dev/null | wc -l)"
# fresh_last24h is the more useful "marginal liveness" signal: 'today 00:00'
# EXCLUDES files touched yesterday evening on early-morning cron runs, which
# can make a genuinely live heartbeat look stale. Use -24h to catch it.
echo "fresh_last24h=$(find ${SWARM_DIR}/builds -name 'STATUS_BUILDER_*.md' -newermt '-24 hours' 2>/dev/null | wc -l)"
echo "newest 5 mtimes:"
ls -lt --time-style=+%Y-%m-%d_%H:%M ${SWARM_DIR}/builds/STATUS_BUILDER_*.md 2>/dev/null | head -5

echo "=== live builder processes ==="
ps aux | grep -iE "STATUS_BUILDER|eni_builder|eni_build" | grep -v grep || echo "NONE running"

echo "=== control FIFOs ==="
ls -la /tmp/eni_ctl_* 2>/dev/null | head -12 || echo "no /tmp/eni_ctl_* FIFOs"

echo "=== quick read of the freshest status file (often describes the parked state) ==="
newest=$(ls -t ${SWARM_DIR}/builds/STATUS_BUILDER_*.md 2>/dev/null | head -1)
[ -n "${newest}" ] && head -8 "${newest}" || echo "no status files"
