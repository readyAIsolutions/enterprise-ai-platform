#!/usr/bin/env bash
# =============================================================================
# ENI Enterprise Platform — Stop All Services
# =============================================================================
# Gracefully stops all platform services. Supports Docker Compose and direct
# process modes. Handles cleanup of PID files and dangling processes.
#
# Usage:
#   ./stop_all.sh                  # Graceful stop (Docker or direct)
#   ./stop_all.sh --force          # Force kill all processes
#   ./stop_all.sh --direct         # Stop direct processes only
#   ./stop_all.sh --cleanup        # Full cleanup (pids, temp files, caches)
# =============================================================================

set -euo pipefail

# ── Configuration ────────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENTERPRISE_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
DOCKER_COMPOSE_FILE="${ENTERPRISE_DIR}/docker-compose.yml"
PID_DIR="${ENTERPRISE_DIR}/.pids"

# Services and their ports (for port-based cleanup)
declare -A SERVICE_PORTS=(
    ["kernel"]="8000"
    ["api_gateway"]="8080"
    ["dashboard"]="8421"
    ["dashboard_docker"]="3000"
    ["redis"]="6379"
)

# Exit codes
readonly EXIT_SUCCESS=0
readonly EXIT_STOP_FAIL=10

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# ── Flags ────────────────────────────────────────────────────────────────────
FORCE=false
DIRECT_ONLY=false
CLEANUP_MODE=false
TIMEOUT=30

# ── Functions ────────────────────────────────────────────────────────────────

log_info()  { echo -e "${BLUE}[INFO]${NC}  $(date +'%Y-%m-%d %H:%M:%S') $*"; }
log_ok()    { echo -e "${GREEN}[OK]${NC}    $(date +'%Y-%m-%d %H:%M:%S') $*"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC}  $(date +'%Y-%m-%d %H:%M:%S') $*"; }
log_error() { echo -e "${RED}[ERROR]${NC} $(date +'%Y-%m-%d %H:%M:%S') $*" >&2; }

# ── Kill process on a specific port ──────────────────────────────────────────

kill_port() {
    local port="$1" name="$2"
    local pid
    pid=$(lsof -ti ":${port}" 2>/dev/null || true)

    if [[ -z "${pid}" ]]; then
        return 1
    fi

    log_info "Stopping ${name} on port ${port} (PID ${pid})..."
    if [[ "${FORCE}" == "true" ]]; then
        kill -9 "${pid}" 2>/dev/null || true
        log_ok "Force killed ${name} (PID ${pid})"
    else
        kill -TERM "${pid}" 2>/dev/null || true
        # Wait for graceful shutdown
        local waited=0
        while [[ ${waited} -lt 10 ]]; do
            if ! kill -0 "${pid}" 2>/dev/null; then
                log_ok "${name} stopped gracefully (PID ${pid})"
                return 0
            fi
            sleep 1
            waited=$((waited + 1))
        done
        # If still running, force kill
        log_warn "${name} did not stop within 10s — force killing..."
        kill -9 "${pid}" 2>/dev/null || true
        log_ok "${name} force stopped (PID ${pid})"
    fi
}

# ── Stop Docker Compose services ─────────────────────────────────────────────

stop_docker_compose() {
    log_info "Stopping Docker Compose services..."

    local compose_cmd
    if docker compose version &>/dev/null 2>&1; then
        compose_cmd="docker compose"
    elif command -v docker-compose &>/dev/null; then
        compose_cmd="docker-compose"
    else
        log_warn "Docker Compose not available."
        return 0
    fi

    if [[ ! -f "${DOCKER_COMPOSE_FILE}" ]]; then
        log_warn "docker-compose.yml not found."
        return 0
    fi

    # Graceful stop with timeout
    log_info "Sending stop signal to Docker containers (timeout: ${TIMEOUT}s)..."
    if ${compose_cmd} -f "${DOCKER_COMPOSE_FILE}" stop -t "${TIMEOUT}" 2>&1; then
        log_ok "Docker Compose services stopped gracefully."
    else
        log_warn "Docker Compose graceful stop had issues."
        if [[ "${FORCE}" == "true" ]]; then
            log_info "Force stopping containers..."
            ${compose_cmd} -f "${DOCKER_COMPOSE_FILE}" down --remove-orphans -t 5 2>&1 || true
            log_ok "Docker containers force stopped."
        fi
    fi

    # Optionally remove containers
    if [[ "${CLEANUP_MODE}" == "true" ]]; then
        log_info "Removing stopped containers..."
        ${compose_cmd} -f "${DOCKER_COMPOSE_FILE}" down --remove-orphans 2>&1 || true
        log_ok "Containers removed."
    fi
}

# ── Stop Direct Services via PID files ───────────────────────────────────────

stop_direct_pids() {
    log_info "Stopping direct services via PID files..."

    if [[ ! -d "${PID_DIR}" ]]; then
        log_warn "No PID directory found at ${PID_DIR}"
        return 0
    fi

    local pidfiles
    pidfiles=$(ls "${PID_DIR}"/*.pid 2>/dev/null || true)

    if [[ -z "${pidfiles}" ]]; then
        log_info "No PID files found."
        return 0
    fi

    for pidfile in ${pidfiles}; do
        local service_name pid
        service_name=$(basename "${pidfile}" .pid)
        pid=$(cat "${pidfile}" 2>/dev/null || true)

        if [[ -z "${pid}" ]]; then
            log_warn "Empty PID file: ${pidfile}"
            rm -f "${pidfile}"
            continue
        fi

        # Check if process still running
        if kill -0 "${pid}" 2>/dev/null; then
            log_info "Stopping ${service_name} (PID ${pid})..."
            if [[ "${FORCE}" == "true" ]]; then
                kill -9 "${pid}" 2>/dev/null || true
            else
                kill -TERM "${pid}" 2>/dev/null || true
                sleep 2
                if kill -0 "${pid}" 2>/dev/null; then
                    log_warn "${service_name} still running — force killing..."
                    kill -9 "${pid}" 2>/dev/null || true
                fi
            fi
            log_ok "${service_name} stopped."
        else
            log_info "${service_name} (PID ${pid}) already stopped."
        fi
        rm -f "${pidfile}"
    done
}

# ── Stop Direct Services via Port Scan ──────────────────────────────────────

stop_direct_ports() {
    log_info "Checking for remaining processes on known ports..."

    for name in "${!SERVICE_PORTS[@]}"; do
        local port="${SERVICE_PORTS[${name}]}"
        kill_port "${port}" "${name}" || true
    done
}

# ── Cleanup Temporary Files ──────────────────────────────────────────────────

cleanup_files() {
    if [[ "${CLEANUP_MODE}" != "true" ]]; then
        return 0
    fi

    log_info "Cleaning up temporary files..."

    # Remove PID directory
    if [[ -d "${PID_DIR}" ]]; then
        rm -rf "${PID_DIR}"
        log_ok "Removed PID directory: ${PID_DIR}"
    fi

    # Clear Python cache files
    log_info "Clearing Python cache..."
    find "${ENTERPRISE_DIR}" -type d -name '__pycache__' -exec rm -rf {} + 2>/dev/null || true
    find "${ENTERPRISE_DIR}" -type f -name '*.pyc' -delete 2>/dev/null || true
    log_ok "Python cache cleared."

    # Clear pytest cache
    if [[ -d "${ENTERPRISE_DIR}/.pytest_cache" ]]; then
        rm -rf "${ENTERPRISE_DIR}/.pytest_cache"
        log_ok "Pytest cache cleared."
    fi

    # Clear old backup files (*.bak.*)
    local bak_count
    bak_count=$(find "${ENTERPRISE_DIR}" -maxdepth 1 -name '*.bak.*' 2>/dev/null | wc -l)
    if [[ ${bak_count} -gt 0 ]]; then
        find "${ENTERPRISE_DIR}" -maxdepth 1 -name '*.bak.*' -delete 2>/dev/null || true
        log_ok "Removed ${bak_count} .bak files."
    fi
}

# ── Verify Everything Stopped ────────────────────────────────────────────────

verify_stopped() {
    log_info "Verifying all services have stopped..."

    local running=0

    for name in "${!SERVICE_PORTS[@]}"; do
        local port="${SERVICE_PORTS[${name}]}"
        if lsof -ti ":${port}" &>/dev/null 2>&1; then
            log_warn "Port ${port} (${name}) still in use!"
            running=1
        fi
    done

    if [[ ${running} -eq 0 ]]; then
        log_ok "All services stopped. No port conflicts detected."
    else
        log_warn "Some ports are still in use. Manual intervention may be needed."
        return 1
    fi

    return 0
}

# ── Print Summary ────────────────────────────────────────────────────────────

print_summary() {
    echo ""
    echo "=============================================="
    echo "  ENI Enterprise — Shutdown Complete"
    echo "  $(date)"
    echo "=============================================="
    echo "  Docker stopped : $(if [[ "${DIRECT_ONLY}" != "true" ]]; then echo "Yes"; else echo "Skipped"; fi)"
    echo "  Direct stopped : Yes"
    echo "  Cleanup        : $(if [[ "${CLEANUP_MODE}" == "true" ]]; then echo "Yes"; else echo "No"; fi)"
    echo "  Force          : ${FORCE}"
    echo "=============================================="
    echo ""
    echo "To restart: ${SCRIPT_DIR}/start_all.sh"
    echo ""
}

# ── Main ──────────────────────────────────────────────────────────────────────

main() {
    # Parse flags
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --force|-f)       FORCE=true ;;
            --direct)         DIRECT_ONLY=true ;;
            --cleanup|-c)     CLEANUP_MODE=true ;;
            --timeout|-t)     TIMEOUT="$2"; shift ;;
            --help|-h)
                cat <<'EOF'
Usage: ./stop_all.sh [OPTIONS]

Options:
  --force, -f       Force kill (SIGKILL) instead of graceful shutdown
  --direct          Stop only direct processes, skip Docker Compose
  --cleanup, -c     Full cleanup: remove PID files, Python caches, .bak files
  --timeout, -t N   Docker stop timeout in seconds (default: 30)
  --help, -h        Show this help
EOF
                exit 0
                ;;
            *) echo "Unknown option: $1"; exit 2 ;;
        esac
        shift
    done

    echo ""
    echo "=============================================="
    echo "  ENI Enterprise — Stopping All Services"
    echo "  $(date)"
    [[ "${FORCE}" == "true" ]] && echo "  MODE: FORCE"
    echo "=============================================="
    echo ""

    local overall_ok=true

    # Stop Docker Compose services
    if [[ "${DIRECT_ONLY}" != "true" ]]; then
        stop_docker_compose || overall_ok=false
    fi

    # Stop direct services (PID files)
    stop_direct_pids || overall_ok=false

    # Stop remaining by port
    stop_direct_ports || overall_ok=false

    # Cleanup
    cleanup_files

    # Verify
    verify_stopped || overall_ok=false

    # Summary
    print_summary

    if [[ "${overall_ok}" == "true" ]]; then
        exit "${EXIT_SUCCESS}"
    else
        exit "${EXIT_STOP_FAIL}"
    fi
}

main "$@"