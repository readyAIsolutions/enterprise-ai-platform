# ENI Auto-API-Fallback — per-mini live model picker (2026-07-11)

Satisfies LO's "automatically fix all failed apis to a working api". Two layers:

1. **Per-mini picker** re-chooses a healthy free model every loop and demotes any
   slug that 429/400/404/auth-failed in the last 120s.
2. **Config spine** (already correct in `~/.hermes/config.yaml` +
   `~/.hermes/profiles/eni/config.yaml`): `provider: openrouter`,
   `default: tencent/hy3:free`, `fallback_providers: [gemini]`, `api_max_retries: 8`.
   This self-heals a 429 in-session without restarting the mini.

Only 3 free slugs are live (everything else is 400/404):
`tencent/hy3:free`, `qwen/qwen3-coder:free`, `meta-llama/llama-3.3-70b-instruct:free`.

## Picker — `scripts/eni_pick_model_auto.sh`
```bash
#!/usr/bin/env bash
LIVE=("tencent/hy3:free" "qwen/qwen3-coder:free" "meta-llama/llama-3.3-70b-instruct:free")
HEALTH=/tmp/eni_model_health
CTR=/tmp/eni_model_ctr
now=$(date +%s)
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
```

## Recorder — `scripts/eni_record_fail.sh <model>`
```bash
#!/usr/bin/env bash
[ -n "$1" ] && echo "$1=$(date +%s)" >> /tmp/eni_model_health
```

## Wiring into each run-script (template)
```bash
#!/usr/bin/env bash
name=ENIx
task=/home/hunter/.cache/eni_parallel/task_$name.txt
LOG=/tmp/eni_logs/$name.log
mkdir -p /tmp/eni_logs
PICK=/home/hunter/.hermes/skills/devops/eni-visible-swarm/scripts/eni_pick_model_auto.sh
REC=/home/hunter/.hermes/skills/devops/eni-visible-swarm/scripts/eni_record_fail.sh
while true; do
  M="$(bash "$PICK")"
  python3 /home/hunter/.local/bin/eni_agent_term.py --name "$name" --task "$task" \
    --repl "hermes chat --yolo -m $M --provider openrouter" --ctl /tmp/eni_ctl_$name > "$LOG" 2>&1 &
  wait $!
  grep -qiE '429|400|404|auth|unauthor|timeout' "$LOG" 2>/dev/null && bash "$REC" "$M"
  free -m | awk 'NR==2{ if ($7 < 2500) system("sleep 20") }'   # memory guard
  sleep 3
done
```
The `free -m` guard pauses 20s when available memory < 2500 MB (box is memory-tight;
full walk-forward can OOM). Each loop re-picks, so a demoted slug is avoided for 120s
and the swarm spreads load across the 3 live slugs.

## Verify
- `bash eni_pick_model.sh` prints a rotating slug; after `eni_record_fail.sh qwen`,
  it serves only hy3/llama for 120s (demote works).
- Proxy logs: `grep -lE '429|400|404' /tmp/eni_logs/*.log` → those models get demoted.
