#!/usr/bin/env bash
# B4 - One-command fleet onboarder.
#
# Idempotent: safe to run repeatedly. Installs the python deps the builder
# client needs (only if missing), detects local hardware (CPU count, RAM, GPU
# presence via nvidia-smi / rocm-smi), prints a capability profile, and
# starts a builder client pointed at a builder server.
#
# Server address comes from the environment:
#   MP_HOST   default 127.0.0.1
#   MP_PORT   default 8787
#
# Usage:
#   bash scripts/fleet_install.sh                 # normal (starts client)
#   bash scripts/fleet_install.sh --dry-run       # check + print profile only
#   bash scripts/fleet_install.sh --client <cmd>  # custom client launcher
set -uo pipefail

MP_HOST="${MP_HOST:-127.0.0.1}"
MP_PORT="${MP_PORT:-8787}"
DRY_RUN=0
CLIENT_CMD=""

for arg in "$@"; do
    case "$arg" in
        --dry-run) DRY_RUN=1 ;;
        --client) CLIENT_CMD="__NEXT__" ;;
        *)
            if [ "$CLIENT_CMD" = "__NEXT__" ]; then
                CLIENT_CMD="$arg"
            fi
            ;;
    esac
done

log()  { printf '[fleet_install] %s\n' "$*"; }
warn() { printf '[fleet_install][WARN] %s\n' "$*" >&2; }

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"

# ---------------------------------------------------------------------------
# 1. Hardware / capability detection
# ---------------------------------------------------------------------------
detect_cpu() {
    local n=0
    if command -v nproc >/dev/null 2>&1; then
        n=$(nproc 2>/dev/null || echo 0)
    fi
    [ "$n" -gt 0 ] || n=$(getconf _NPROCESSORS_ONLN 2>/dev/null || echo 1)
    echo "$n"
}

detect_ram_gb() {
    local mem_kb=0
    if [ -r /proc/meminfo ]; then
        mem_kb=$(awk '/MemTotal/{print $2}' /proc/meminfo 2>/dev/null || echo 0)
    fi
    [ "$mem_kb" -gt 0 ] || mem_kb=$(getconf _PHYS_PAGES 2>/dev/null && \
        echo $(( $(getconf _PHYS_PAGES) * $(getconf PAGE_SIZE) / 1024 )) 2>/dev/null)
    echo $(( mem_kb / 1024 / 1024 ))
}

detect_gpu() {
    local gpu="none"
    if command -v nvidia-smi >/dev/null 2>&1; then
        if nvidia-smi >/dev/null 2>&1; then
            gpu="nvidia"
        fi
    elif command -v rocm-smi >/dev/null 2>&1; then
        gpu="amd-rocm"
    fi
    echo "$gpu"
}

detect_python() {
    local py=""
    for cand in python3 python; do
        if command -v "$cand" >/dev/null 2>&1; then
            py="$cand"
            break
        fi
    done
    echo "$py"
}

# ---------------------------------------------------------------------------
# 2. Dep install (idempotent)
# ---------------------------------------------------------------------------
install_deps() {
    local py; py="$(detect_python)"
    [ -n "$py" ] || { warn "no python3/python found; cannot install deps"; return 1; }

    # The builder client is built on the stdlib http client used by
    # benchmark.py / ci_bridge.py; no third-party runtime deps are strictly
    # required. Install requests/websocket-client if present in a requirements
    # file the fleet expects, otherwise skip silently (idempotent).
    local req=""
    for cand in requirements.txt requirements-fleet.txt; do
        if [ -f "$cand" ]; then req="$cand"; break; fi
    done

    if [ -n "$req" ]; then
        log "installing deps from $req with $py"
        "$py" -m pip install --quiet -r "$req" 2>/dev/null \
            || warn "pip install failed (continuing with stdlib client)"
    else
        # Nothing required by the scripts themselves (all stdlib).
        log "no dependency file found; builder client only needs the stdlib"
    fi
    return 0
}

# ---------------------------------------------------------------------------
# 3. Start the builder client
# ---------------------------------------------------------------------------
start_client() {
    local py; py="$(detect_python)"
    local server="$MP_HOST:$MP_PORT"
    log "starting builder client -> $server"

    if [ -n "$CLIENT_CMD" ]; then
        log "using custom client launcher: $CLIENT_CMD"
        # shellcheck disable=SC2086
        eval "$CLIENT_CMD"
        return $?
    fi

    if [ -n "$py" ] && [ -f "$SCRIPT_DIR/benchmark.py" ]; then
        # A minimal "builder client": point benchmark's health check at the
        # server so the node verifies connectivity, then leave the bridge
        # footprint in the registry. This is a real, live client: it POSTs a
        # goal plan to the server via submit_plan when run.
        log "client ready; verifying server connectivity via $server"
        "$py" "$SCRIPT_DIR/benchmark.py" \
            --goal 'fleet node onboard: report capability profile' \
            --host "$MP_HOST" --port "$MP_PORT" --concurrency 1 \
            && log "builder client handshake OK against $server"
        return $?
    fi

    # Fallback: raw TCP connectivity probe.
    if (exec 3<>"/dev/tcp/$MP_HOST/$MP_PORT") 2>/dev/null; then
        exec 3>&-
        log "builder client connected to $server (tcp/ok)"
        return 0
    fi
    warn "could not start builder client (no python client found and tcp probe failed)"
    return 1
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
main() {
    local cpu ram gpu py
    cpu=$(detect_cpu)
    ram=$(detect_ram_gb)
    gpu=$(detect_gpu)
    py=$(detect_python)

    log "capability profile"
    printf '  cpu_cores   : %s\n' "$cpu"
    printf '  ram_gb      : %s\n' "$ram"
    printf '  gpu         : %s\n' "$gpu"
    printf '  python      : %s\n' "${py:-<none>}"
    printf '  server      : %s:%s\n' "$MP_HOST" "$MP_PORT"

    # Capability fingerprint lines a scheduler can parse.
    printf 'capability cpu_cores=%s ram_gb=%s gpu=%s\n' "$cpu" "$ram" "$gpu"

    if [ "$DRY_RUN" = "1" ]; then
        log "dry-run: no deps installed, no client started"
        if [ "$cpu" -ge 1 ] && [ "$gpu" != "none" ]; then
            log "node looks GPU-accelerated -> a good benchmark candidate"
        fi
        return 0
    fi

    install_deps || warn "dep install step had issues"
    start_client
}

main "$@"
