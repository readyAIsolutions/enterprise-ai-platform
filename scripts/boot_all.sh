#!/usr/bin/env bash
# ===========================================================================
#  ENI ENTERPRISE — Boot All Servers (Linux / WSL)
# ===========================================================================
#  Boots every server the ENI Enterprise Platform needs:
#    1. Multiplayer coordination server  (WebSocket :8787 + HTTP :8788)
#    2. Local one-prompt->program brain  (HTTP :8913)
#    3. Free Model Router                (HTTP :8920) if present
#  Then optionally seeds the skills pack and starts a builder client.
#
#  usage: bash scripts/boot_all.sh [--headless] [--no-builder]
# ===========================================================================
set -euo pipefail
# scripts/boot_all.sh -> enterprise root (parent of this repo dir, where the
# `enterprise` package and platform_kernel.py live)
cd "$(dirname "$0")/../.."

PY="${PYTHON:-python3}"
HEADLESS=0
NO_BUILDER=0
for arg in "$@"; do
  case "$arg" in
    --headless) HEADLESS=1 ;;
    --no-builder) NO_BUILDER=1 ;;
  esac
done

ROOT=$(pwd)
export PYTHONPATH="$ROOT:$PYTHONPATH"

LOG="$ROOT/logs/boot"
mkdir -p "$LOG"

say() { printf '\n\033[1;34m==> %s\033[0m\n' "$1"; }

say "ENI ENTERPRISE — Server Boot"

# --- 1. Multiplayer coordination server :8787 ---------------------------------
say "[1/3] Multiplayer coordination server  ws://0.0.0.0:8787 (+http :8788)"
nohup "$PY" -m enterprise.multiplayer.server.server 8787 \
    >>"$LOG/multiplayer.log" 2>&1 &
echo "      pid=$!  log=$LOG/multiplayer.log"

# --- 2. Local one-prompt controller :8913 -------------------------------------
say "[2/3] Local one-prompt controller  http://127.0.0.1:8913"
nohup "$PY" -m enterprise.local_controller.controller --port 8913 \
    >>"$LOG/controller.log" 2>&1 &
echo "      pid=$!  log=$LOG/controller.log"

# --- 3. Free model router :8920 (optional) ------------------------------------
ROUTER="$HOME/.hermes/scripts/free_router.py"
if [ -f "$ROUTER" ]; then
  say "[3/3] Free Model Router  http://127.0.0.1:8920"
  nohup "$PY" "$ROUTER" --port 8920 --host 127.0.0.1 >>"$LOG/free_router.log" 2>&1 &
  echo "      pid=$!  log=$LOG/free_router.log"
else
  say "[3/3] Free Model Router not found - skipping."
fi

# --- builder client (skip in headless unless explicitly wanted) ----------------
if [ "$NO_BUILDER" = "0" ]; then
  if [ "$HEADLESS" = "1" ]; then
    say "Starting builder client (llm worker) in background..."
    nohup "$PY" -m enterprise.multiplayer.client.client --worker llm \
        --host 127.0.0.1 --port 8787 >>"$LOG/builder.log" 2>&1 &
    echo "      pid=$!"
  else
    read -r -p "Start a local builder client too (llm worker)? [y/N] " ans
    if [[ "$ans" =~ ^[Yy]$ ]]; then
      "$PY" -m enterprise.multiplayer.client.client --worker llm \
          --host 127.0.0.1 --port 8787
    fi
  fi
fi

say "All servers launched."
echo "  health http://127.0.0.1:8788/health   board http://127.0.0.1:8788/api/board"
echo "  brains http://127.0.0.1:8913/health"
echo "  verify: python3 scripts/eni_cli status"
echo "  logs:   $LOG/"
exit 0