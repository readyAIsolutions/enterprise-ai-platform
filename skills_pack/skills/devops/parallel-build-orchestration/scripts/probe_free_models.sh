#!/usr/bin/env bash
# probe_free_models.sh — discover which OpenRouter FREE models actually answer
# on this key RIGHT NOW.
#
# WHY: the OPENROUTER_FREE_POOL env var (and most "free model" lists) is
# frequently STALE. Entries return HTTP 429 (per-day free-tier cap) or
# HTTP 404 ("this model is unavailable for free"). Launching an agent swarm on
# those slugs produces silent 429s and dead-looking windows.
#
# Prints one working model slug per line (empty if all dead). Feed the output
# into your launcher's MODELS array. Uses the default profile (has the key).
set -u

PROBE_Q="${HERMES_PROBE_QUERY:-say OK}"
PROBE_TIMEOUT="${HERMES_PROBE_TIMEOUT:-45}"

# Candidate pool: the env var's models + a couple of known-good fallbacks.
CANDIDATES=""
if [ -n "${OPENROUTER_FREE_POOL:-}" ]; then
  CANDIDATES="${OPENROUTER_FREE_POOL//,/ }"
fi
CANDIDATES="$CANDIDATES tencent/hy3:free qwen/qwen2.5-72b-instruct:free"

for m in $CANDIDATES; do
  out=$(timeout "$PROBE_TIMEOUT" hermes chat -m "$m" --provider openrouter -Q -q "$PROBE_Q" 2>&1)
  if echo "$out" | grep -qiE 'HTTP 4[0-9][0-9]|HTTP 5[0-9][0-9]'; then
    : # dead — skip
  else
    echo "$m"
  fi
done
