#!/usr/bin/env bash
# eni_pick_model.sh — returns a HEALTHY OpenRouter free-model slug.
# Rotates across the known-live free pool and DEMOTES any slug that recently
# failed (429 / 400 / 404 / auth) so a dead API is never (re)selected.
# This is the "automatically fix failed apis -> working api" mechanism.
set -u
HEALTH=/tmp/eni_model_health
CTR=/tmp/eni_model_ctr
DEMOTE_SEC=120
NOW=$(date +%s)

# ONLY these 3 free slugs are known-live (2026-07-11 probe). Everything else
# is dead (400/404) and is NEVER a candidate.
LIVE=("tencent/hy3:free" "qwen/qwen3-coder:free" "meta-llama/llama-3.3-70b-instruct:free")

# Load last-fail timestamps (file lines: "model=epoch")
declare -A FAIL
if [ -f "$HEALTH" ]; then
  while IFS='=' read -r m t; do
    [ -n "${m:-}" ] && FAIL["$m"]="$t"
  done < "$HEALTH"
fi

# Build candidate list = live models NOT failed in the last DEMOTE_SEC.
cands=()
for m in "${LIVE[@]}"; do
  f="${FAIL[$m]:-0}"
  if [ $((NOW - ${f:-0})) -ge $DEMOTE_SEC ]; then
    cands+=("$m")
  fi
done
# If all are freshly demoted, fall back to the full live pool (pick least-recent fail).
if [ ${#cands[@]} -eq 0 ]; then
  cands=("${LIVE[@]}")
fi

# Round-robin across candidates for even distribution.
n=0
[ -f "$CTR" ] && n=$(cat "$CTR" 2>/dev/null || echo 0)
m="${cands[$((n % ${#cands[@]}))]}"
echo $((n + 1)) > "$CTR"
echo "$m"
