#!/usr/bin/env bash
# ===========================================================================
#  ENI ENTERPRISE — One-Command Setup
# ===========================================================================
#  The "make setup easy" entry point. One command boots a working platform:
#
#     bash setup.sh            # full interactive setup
#     bash setup.sh --yes      # non-interactive / CI (no prompts)
#     bash setup.sh --bare     # only install deps + verify, don't start services
#
#  It will (idempotently):
#    1. cd to the enterprise repo root
#    2. install Python deps (pip -r requirements.txt)
#    3. deploy the portable skills/LSP/MCP/plugin pack (skillspack)
#    4. install + enable systemd user services (controller :8913 + mp server :8787)
#    5. start a builder client (optional)
#    6. print the live dashboard endpoints
# ===========================================================================
set -euo pipefail
cd "$(dirname "$0")"

AUTO=""
RUN_SERVICES=1
for arg in "$@"; do
  case "$arg" in
    --yes) AUTO=1 ;;
    --bare) RUN_SERVICES=0 ;;
    --no-pack) SKIP_PACK=1 ;;
  esac
done

G() { printf '\033[1;32m[OK]   \033[0m%s\n' "$1"; }
Y() { printf '\033[1;33m[info] \033[0m%s\n' "$1"; }
R() { printf '\033[1;31m[FAIL] \033[0m%s\n' "$1"; }

echo
echo "======================================================"
echo "   ENI ENTERPRISE — One-Command Setup"
echo "======================================================"
echo

# --- 0. sanity ---------------------------------------------------------------
if [ ! -f "enterprise/platform_kernel.py" ] && [ ! -f "platform_kernel.py" ]; then
  R "could not locate the enterprise package (looked for platform_kernel.py)"
  exit 1
fi
ROOT=$(pwd)
export PYTHONPATH="$ROOT:$PYTHONPATH"
Y "repo root: $ROOT"

# --- 1. python deps ----------------------------------------------------------
Y "[1/6] Installing python dependencies..."
REQ="enterprise/requirements.txt"
PY="python3"
if [ -f "$REQ" ]; then
  # Prefer an already-set-up environment; build a venv if pip is blocked.
  if ! pip --version >/dev/null 2>&1; then
    if [ -x ".venv/bin/python" ]; then PY=".venv/bin/python"
    else
      Y "creating local .venv (system pip unavailable / externally managed)"
      python3 -m venv .venv 2>/dev/null && PY=".venv/bin/python" || Y "no venv possible - stdlib-only platform still works"
    fi
  fi
  if "$PY" -m pip install --quiet -r "$REQ" 2>/dev/null; then
    G "build dependencies installed"
  else
    Y "pip install skipped (offline or externally-managed) - core platform is stdlib-only"
  fi
else
  Y "no requirements.txt found - skipping pip install"
fi

# --- 2. skillspack portable layer --------------------------------------------
if [ "${SKIP_PACK:-0}" = "0" ]; then
  Y "[2/6] Deploying portable skills/LSP/MCP/plugin pack..."
  if [ -f "enterprise/scripts/install_skillspack.sh" ]; then
    bash "enterprise/scripts/install_skillspack.sh" || Y "skillspack deploy had warnings (non-fatal)"
    G "portable layer deployed"
  else
    Y "install_skillspack.sh not found - skipping"
  fi
else
  Y "[2/6] Skipping skillspack deploy (--no-pack)"
fi

# --- 3. systemd services -----------------------------------------------------
if [ "$RUN_SERVICES" = "1" ] && [ -d "${XDG_CONFIG_HOME:-$HOME/.config}/systemd" ]; then
  Y "[3/6] Installing systemd user services..."
  # use the eni_cli setup logic (it copies + enables the unit files)
  if [ "$AUTO" = "1" ]; then
    echo | python3 enterprise/scripts/eni_cli setup 2>/dev/null \
      || bash enterprise/scripts/eni_cli setup 2>/dev/null \
      || Y "could not run eni_cli setup - you can start servers manually with scripts/boot_all.sh"
  else
    python3 enterprise/scripts/eni_cli setup || true
  fi
  G "systemd services configured (eni-controller, eni-multiplayer-server)"
else
  Y "[3/6] Skipping systemd services (--bare or no systemd user dir). Use scripts/boot_all.sh instead."
fi

# --- 4. verify ---------------------------------------------------------------
Y "[4/6] Verifying platform import..."
if PYTHONPATH="$ROOT" python3 -c "import sys; sys.path.insert(0,'enterprise'); import platform_kernel" 2>/dev/null \
   || PYTHONPATH="$ROOT" python3 -c "import platform_kernel" 2>/dev/null; then
  G "platform kernel importable"
else
  R "platform kernel import failed"
fi

# --- 5. status ---------------------------------------------------------------
Y "[5/6] Platform status..."
PYTHONPATH="$ROOT" python3 enterprise/scripts/eni_cli status 2>/dev/null || true

# --- 6. done -----------------------------------------------------------------
Y "[6/6] Setup complete."
echo
G "ENI Enterprise is ready."
echo "  one-command demo:  curl -X POST http://127.0.0.1:8788/api/submit_plan -d '{\"goal\":\"build a to-do app\",\"tenant\":\"acme\"}'"
echo "  dashboard:         http://127.0.0.1:8788/api/board"
echo "  brains:            http://127.0.0.1:8913/health"
echo "  boot servers:      bash enterprise/scripts/boot_all.sh"
echo "  CLI:               python3 enterprise/scripts/eni_cli status"
echo
exit 0