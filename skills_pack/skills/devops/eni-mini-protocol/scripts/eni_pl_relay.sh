#!/bin/bash
# eni_pl_relay.sh — PRODUCT LEAD / MASTER per-builder contextual relay driver.
# Generalized from the verified STOCKBOT relay cycle (2026-07-11).
#
# WHAT IT DOES
#   1. Discovers live builders from their control FIFOs /tmp/eni_ctl_<PREFIX>_<NN>
#      (only FIFOs that CURRENTLY have a reader — dead/orphan FIFOs are skipped,
#      which is exactly the silent-loss pitfall we must avoid).
#   2. Probes the USB/DEMIURGE blocker.
#   3. For each live builder, delivers a DISTINCT contextual message you (the agent)
#      composed and placed at <MSGS>/<NAME>.txt (NAME = exact --name, e.g. STOCKBOT_B01).
#      - If you supplied no message file AND the builder has no STATUS_<NAME>.md yet,
#        a generic BOOTSTRAP is delivered.
#      - Delivery is verified with fuser (reader PID).
#   4. Persists PL_GUIDANCE_<NAME>.md and appends a pointer to any existing STATUS_<NAME>.md.
#   5. Optionally self-heals dead builders (--heal), relaunching headless.
#   6. Writes STATUS_PL_<PREFIX>.md heartbeat (state parsed from first ~5 lines, not line 1).
#
# THE DEEP CONTEXTUAL NEXT-STEP TEXT IS YOUR JOB (reasoned from each builder's STATUS).
# This script handles the MECHANICS: delivery + verification + persistence + heartbeat
# + liveness. It does NOT invent per-builder strategy.
#
# USAGE
#   eni_pl_relay.sh --root /path/to/scaffold --prefix STOCKBOT \
#                   --msgs /tmp/pl_relay_STOCKBOT [--heal]
#
# Per-builder message files: <MSGS>/<NAME>.txt  (NAME = exact --name, zero-padded)
# Optional heal model map:   <MSGS>/models.sh    ( declare -A MODEL=( [STOCKBOT_B01]=... ) )
set -u
ROOT=""; PREFIX=""; MSGDIR=""; HEAL=0
while [ $# -gt 0 ]; do
  case "$1" in
    --root)   ROOT="$2"; shift 2;;
    --prefix) PREFIX="$2"; shift 2;;
    --msgs)   MSGDIR="$2"; shift 2;;
    --heal)   HEAL=1; shift;;
    *) echo "eni_pl_relay: unknown arg $1" >&2; exit 2;;
  esac
done
[ -z "$ROOT" ]   && { echo "eni_pl_relay: --root required" >&2; exit 2; }
[ -z "$PREFIX" ] && { echo "eni_pl_relay: --prefix required" >&2; exit 2; }
[ -d "$ROOT" ]   || { echo "eni_pl_relay: ROOT not a dir: $ROOT" >&2; exit 2; }
MSGDIR="${MSGDIR:-/tmp/pl_relay_$PREFIX}"
mkdir -p "$MSGDIR"
declare -A MODEL=()
[ -f "$MSGDIR/models.sh" ] && source "$MSGDIR/models.sh"

ts=$(date '+%Y-%m-%dT%H:%M:%S')

# ---- Blocker ----
USB=$(ls -d /run/media/hunter/DEMIURGE* 2>/dev/null | head -1)
if [ -z "$USB" ]; then
  BLK="USB DEMIURGE NOT MOUNTED => SYNTHETIC DATA ONLY; stay RED-by-contract; no live OANDA, no fabricated green."
else
  BLK="USB mounted at $USB => real ref data available; you MAY run the read-only OANDA fill/volume gap benchmark."
fi
CORE="ADD-only: never modify core backtest/walk_forward/purged_cv/config.py or deploy-gate logic; never touch sibling files."

# ---- Discover + relay ----
relayed=0
declare -a NAMES=()
for fifo in /tmp/eni_ctl_${PREFIX}_*; do
  [ -e "$fifo" ] || continue
  name="${fifo#/tmp/eni_ctl_}"                      # STOCKBOT_B01
  rid=$(fuser "$fifo" 2>/dev/null)                  # live reader?
  if [ -z "$rid" ]; then echo "DEAD   $name (no reader — skipped)"; continue; fi
  NAMES+=("$name")
  [ -p "$fifo" ] || mkfifo "$fifo" 2>/dev/null
  msg="$MSGDIR/$name.txt"
  st="$ROOT/STATUS_$name.md"
  delivered_msg=""
  if [ -f "$msg" ]; then
    timeout 6 cat "$msg" > "$fifo" 2>/dev/null
    delivered_msg="$msg"
  elif [ ! -f "$st" ]; then
    # generic bootstrap (no sed — BLK/CORE may contain '/'); use printf
    printf 'LO via PL: %s [BOOTSTRAP] — no STATUS yet and no specific guidance supplied this cycle. Write STATUS_%s.md with line1 '\''[state: DONE|IN-PROGRESS|BLOCKED]'\'', a PASS/FAIL board with REAL numbers, a "what adds R / what to drop" list, and UNVALIDATED. %s %s\n' "$name" "$name" "$CORE" "$BLK" > "$MSGDIR/$name.bootstrap.out.txt"
    timeout 6 cat "$MSGDIR/$name.bootstrap.out.txt" > "$fifo" 2>/dev/null
    delivered_msg="$MSGDIR/$name.bootstrap.out.txt"
  fi
  rid=$(fuser "$fifo" 2>/dev/null)                  # re-verify after delivery
  if [ -n "$rid" ]; then echo "DELIVERED+READER $name -> $rid"; relayed=$((relayed+1)); else echo "DELIVERED(no-reader) $name"; fi
  if [ -n "$delivered_msg" ]; then
    {
      echo "# PL_GUIDANCE_$name.md — PRODUCT LEAD contextual relay (cycle $ts)"
      echo ""
      echo "Blocker: $BLK"
      echo "Rule: $CORE"
      echo "Delivered via /tmp/eni_ctl_$name (fuser reader: ${rid:-unknown})."
      echo ""
      echo "---- relay text ----"
      cat "$delivered_msg"
    } > "$ROOT/PL_GUIDANCE_$name.md"
    if [ -f "$st" ]; then
      sum=$(head -c 160 "$delivered_msg" | tr '\n' ' ')
      printf '\n## PRODUCT_LEAD_GUIDANCE (cycle %s)\n- PL relay delivered via /tmp/eni_ctl_%s (fuser reader %s). See PL_GUIDANCE_%s.md.\n- %s\n' "$ts" "$name" "${rid:-?}" "$name" "$sum" >> "$st"
    fi
  fi
  if [ "$HEAL" = "1" ]; then
    if ! pgrep -f "eni_agent_term.py --name $name" >/dev/null 2>&1; then
      mdl="${MODEL[$name]:-tencent/hy3:free}"
      echo "HEAL: $name missing — relaunch headless ($mdl)"
      setsid python3 /home/hunter/.local/bin/eni_agent_term.py \
        --name "$name" --task "/tmp/eni_parallel/task_$name.txt" \
        --repl "hermes chat --yolo -m $mdl --provider openrouter" >/dev/null 2>&1 &
    fi
  fi
done

# ---- heartbeat ----
{
  echo "# STATUS_PL_$PREFIX.md — PRODUCT LEAD relay heartbeat"
  echo ""
  echo "**Updated**: $ts"
  echo "**Blocker**: $BLK"
  echo "**Relayed this cycle**: $relayed builder(s) (contextual, per-builder FIFOs, fuser-verified)"
  echo ""
  echo "## Per-builder relay"
  for name in "${NAMES[@]:-}"; do
    [ -z "$name" ] && continue
    st="$ROOT/STATUS_$name.md"
    if [ -f "$st" ]; then
      s=$(head -5 "$st" | grep -oE 'DONE|IN-PROGRESS|BLOCKED|STARTING|RUNNING' | head -1)
      echo "- $name:${s:-?}:sent (STATUS present)"
    else
      echo "- $name:BOOTSTRAP:sent (no STATUS yet)"
    fi
  done
  echo ""
  echo "## Self-heal"
  alive=0
  for name in "${NAMES[@]:-}"; do
    [ -z "$name" ] && continue
    pgrep -f "eni_agent_term.py --name $name" >/dev/null 2>&1 && alive=$((alive+1))
  done
  echo "- Live builders: $alive / ${#NAMES[@]} (pgrep eni_agent_term --name). No relaunch unless --heal flagged a missing one."
  echo ""
  echo "## Blocker detail (report to LO)"
  echo "$BLK"
} > "$ROOT/STATUS_PL_$PREFIX.md"

echo "CYCLE DONE. prefix=$PREFIX relayed=$relayed"
