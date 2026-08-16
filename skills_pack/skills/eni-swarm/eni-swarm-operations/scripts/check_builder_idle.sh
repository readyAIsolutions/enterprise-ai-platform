#!/usr/bin/env bash
# check_builder_idle.sh <BUILDER_NAME> — verify a builder is genuinely IDLE.
#
# Persisted from /tmp/check_builder_idle.sh (Aug 2026, BUILDER_37 pass) so the
# optional-but-canonical idle-reconciliation probe survives /tmp cleanups. Run it
# from the builder's cron / pass instead of re-deriving the mirror set by hand.
#
# Empirically confirmed (BUILDER_37, Aug 2026) there are FIVE STATUS mirror paths
# per builder, and four use markdown naming (STATUS_<NAME>.md) while the .cache
# mirror uses an ALTERNATE naming convention AND format:
#   BUILDER_37_STATUS.md  (under .cache, INI [STATUS] block: status=[IDLE])
#       vs
#   STATUS_BUILDER_37.md  (everywhere else, markdown H1: STATUS_<NAME> — IDLE)
# A builder pass must reconcile ALL five, not just the "obvious" ones.
#
# PITFALL FIXED Aug 2026: a grep token pattern that only matches the markdown H1
# (STATUS_... — IDLE) never catches the INI cache mirror, so on a genuine
# steady-state idle pass only 4/5 mirrors tokenize as IDLE and the script exits 1
# (false "not fully reconciled"), sending the pass into unnecessary rewrite work.
# This script tokenizes BOTH formats and counts the per-mirror IDLE state directly.
#
# Usage: bash check_builder_idle.sh BUILDER_37
# Exits 0 if: FIFO absent AND all found mirrors agree on the same [IDLE] state.
# Exits non-zero and prints what's out of sync otherwise.
set -u

B="${1:?usage: check_builder_idle.sh <BUILDER_NAME>, e.g. BUILDER_37}"
FIFO="/tmp/eni_ctl_${B}"

echo "=== FIFO check: ${FIFO} ==="
if [ -p "${FIFO}" ]; then
  echo "ASSIGNED: FIFO is a pipe (directive may be pending)"
  exit 3
elif [ -e "${FIFO}" ]; then
  echo "WARN: FIFO exists but is NOT a pipe (stale regular file)"
  exit 4
else
  echo "NO_ENTRY / NOT_A_PIPE -> no directive, IDLE candidate"
fi

echo
echo "=== STATUS mirror scan (all five paths) ==="
mirrors=(
  "${HOME}/Commander/eni_swarm/builds/STATUS_${B}.md"
  "${HOME}/.cache/eni_swarm/builder_logs/${B}_STATUS.md"
  "${HOME}/Desktop/Enterprise Builder/ENI_Swarm_NEW/tasks/status/STATUS_${B}.md"
  "${HOME}/Desktop/Enterprise Builder/ENI_Swarm_NEW/STATUS_${B}.md"
  "${HOME}/STATUS_${B}.md"
)

found=0
missing=0
idle=0
for m in "${mirrors[@]}"; do
  if [ -f "${m}" ]; then
    found=$((found+1))
    # tokenize BOTH markdown H1 (STATUS_... — IDLE) AND INI (status=[IDLE])
    tok=$(grep -Eo 'STATUS_[A-Za-z0-9_]+ — [A-Z-]+|status=\[[A-Z-]+\]' "${m}" | head -1)
    ts=$(stat -c '%y' "${m}" | cut -d'.' -f1)
    echo "  [present] ${m}"
    echo "            ${tok:-<no status line>}  (mtime ${ts})"
    # count per-mirror IDLE state (case of state token matters: INI is the sole
    # format writing status=[IDLE]; markdown uses the em-dash H1)
    if printf '%s' "${tok}" | grep -q 'IDLE'; then
      idle=$((idle+1))
    fi
  else
    missing=$((missing+1))
    echo "  [missing] ${m}"
  fi
done

echo
echo "Found=${found}/5  Missing=${missing}/5  Idle=${idle}/5"

if [ "${found}" -eq 0 ]; then
  echo "RESULT: no STATUS mirror exists yet — nothing to reconcile, genuinely idle."
  exit 0
fi

if [ "${idle}" -eq "${found}" ] && [ "${missing}" -eq 0 ]; then
  echo "RESULT: all 5 mirrors present and all agree on IDLE -> steady-state, nothing changed."
  exit 0
fi

echo "RESULT: mirrors NOT fully reconciled (missing, or not all IDLE). Reconcile all five, then re-run."
exit 1
