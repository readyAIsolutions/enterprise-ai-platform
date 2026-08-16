#!/usr/bin/env bash
# eni_pick_model_auto.sh — live model picker with health demotion.
# Rotates the 3 known-live free slugs; demotes any slug that failed in the
# last 120s; never returns a known-dead model. Prints ONE slug to stdout.
LIVE=("tencent/hy3:free" "qwen/qwen3-coder:free" "meta-llama/llama-3.3-70b-instruct:free")
HEALTH=/tmp/eni_model_health
CTR=/tmp/eni_model_ctr
now=$(date +%s)
# purge demotions older than 120s
: > "$HEALTH.tmp"
while read -r line; do
  m="${line%%=*}"; ts="${line##*=}"
  [ -n "$ts" ] && [ $((now - ts)) -lt 120 ] && echo "$line" >> "$HEALTH.tmp"
done < <(cat "$HEALTH" 2>/dev/null)
mv -f "$HEALTH.tmp" "$HEALTH"
cands=("${LIVE[@]}")
for m in "${LIVE[@]}"; do
  grep -qxF "$m" "$HEALTH" 2>/dev/null && cands=("${cands[@]/$m}")
done
[ ${#cands[@]} -eq 0 ] && cands=("${LIVE[@]}")
n=$(cat "$CTR" 2>/dev/null); n=${n:-0}
printf '%s' "$(( (n+1) % 100000 ))" > "$CTR"
i=$(( n % ${#cands[@]} ))
echo "${cands[$i]}"
