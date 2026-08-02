#!/usr/bin/env bash
# =============================================================================
# ENI Enterprise Platform — Start All Services
# =============================================================================
# Starts every service in the correct dependency order: Redis → Kernel →
# API Gateway → Dashboard → Modules. Supports both Docker Compose and
# direct process management.
#
# Usage:
#   ./start_all.sh                   # Start with Docker Compose (default)
#   ./start_all.sh --direct          # Start without Docker (direct processes)
#   ./start_all.sh --daemon          # Run in background
#   ./start_all.sh --no-modules      # Core services only
# =============================================================================

set -euo pipefail

# ── Configuration ────────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENTERPRISE_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
DOCKER_COMPOSE_FILE="${ENTERPRISE_DIR}/docker-compose.yml"
PID_DIR="${ENTERPRISE_DIR}/.pids"
LOG_DIR="${ENTERPRISE_DIR}/logs"

# Ports
KERNEL_PORT="${KERNEL_PORT:-8000}"
GATEWAY_PORT="${GATEWAY_PORT:-8080}"
DASHBOARD_PORT="${DASHBOARD_PORT:-3000}"
DASHBOARD_DIRECT_PORT=8421
REDIS_PORT="${REDIS_PORT:-6379}"

# Exit codes
readonly EXIT_SUCCESS=0
readonly EXIT_START_FAIL=10
readonly EXIT_HEALTH_FAIL=11
readonly EXIT_SETUP_FAIL=2

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

# ── Flags ────────────────────────────────────────────────────────────────────
DIRECT_MODE=false
DAEMON_MODE=false
NO_MODULES=false
SKIP_HEALTH=false

# ── Functions ────────────────────────────────────────────────────────────────

log_info()  { echo -e "${BLUE}[INFO]${NC}  $(date +'%Y-%m-%d %H:%M:%S') $*"; }
log_ok()    { echo -e "${GREEN}[OK]${NC}    $(date +'%Y-%m-%d %H:%M:%S') $*"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC}  $(date +'%Y-%m-%d %H:%M:%S') $*"; }
log_error() { echo -e "${RED}[ERROR]${NC} $(date +'%Y-%m-%d %H:%M:%S') $*" >&2; }

die() {
    log_error "$*"
    exit "${EXIT_SETUP_FAIL}"
}

wait_for_http() {
    local url="$1" label="$2" timeout="${3:-30}"
    local waited=0
    local interval=2

    while [[ ${waited} -lt ${timeout} ]]; do
        if curl -sf --max-time 3 "${url}" &>/dev/null; then
            log_ok "${label} responded after ${waited}s"
            return 0
        fi
        sleep "${interval}"
        waited=$((waited + interval))
    done
    log_error "${label} did not respond within ${timeout}s"
    return 1
}

kill_port() {
    local port="$1"
    local pid
    pid=$(lsof -ti ":${port}" 2>/dev/null || true)
    if [[ -n "${pid}" ]]; then
        log_warn "Port ${port} is in use (PID ${pid}). Killing..."
        kill "${pid}" 2>/dev/null || true
        sleep 1
    fi
}

# ── Docker Compose Start ─────────────────────────────────────────────────────

start_docker_compose() {
    log_info "Starting services via Docker Compose..."

    local compose_cmd
    if docker compose version &>/dev/null 2>&1; then
        compose_cmd="docker compose"
    elif command -v docker-compose &>/dev/null; then
        compose_cmd="docker-compose"
    else
        die "Docker Compose not found. Use --direct mode or install Docker Compose."
    fi

    if [[ ! -f "${DOCKER_COMPOSE_FILE}" ]]; then
        die "docker-compose.yml not found at ${DOCKER_COMPOSE_FILE}"
    fi

    # Pull latest images
    log_info "Pulling Docker images..."
    ${compose_cmd} -f "${DOCKER_COMPOSE_FILE}" pull 2>/dev/null || true

    # Start in order with dependencies
    if [[ "${NO_MODULES}" == "true" ]]; then
        log_info "Starting core services only (redis, kernel, api-gateway, dashboard)..."
        ${compose_cmd} -f "${DOCKER_COMPOSE_FILE}" up -d redis kernel api-gateway dashboard 2>&1 || {
            log_error "Docker Compose core services failed to start."
            exit "${EXIT_START_FAIL}"
        }
    else
        log_info "Starting all services..."
        ${compose_cmd} -f "${DOCKER_COMPOSE_FILE}" up -d 2>&1 || {
            log_error "Docker Compose failed to start."
            exit "${EXIT_START_FAIL}"
        }
    fi

    log_ok "Docker Compose services started."
}

# ── Direct Start ─────────────────────────────────────────────────────────────

start_direct_redis() {
    log_info "Starting Redis..."
    if command -v redis-server &>/dev/null; then
        kill_port "${REDIS_PORT}"
        redis-server --port "${REDIS_PORT}" --daemonize yes \
            --dir "${ENTERPRISE_DIR}" \
            --logfile "${LOG_DIR}/redis.log" \
            2>/dev/null || {
            log_warn "Could not start Redis — it may already be running."
        }
        sleep 1
        if redis-cli -p "${REDIS_PORT}" ping 2>/dev/null | grep -q PONG; then
            log_ok "Redis started on port ${REDIS_PORT}"
        else
            log_warn "Redis did not respond to ping — continuing anyway"
        fi
    else
        log_warn "redis-server not found. Skipping Redis."
    fi
}

start_direct_kernel() {
    log_info "Starting Platform Kernel on :${KERNEL_PORT}..."

    kill_port "${KERNEL_PORT}"

    local cmd="python3 -c \"
import sys; sys.path.insert(0, '${ENTERPRISE_DIR}')
from platform_kernel import create_platform
platform = create_platform()
import time
print('Platform Kernel started. Uptime running...')
while True:
    time.sleep(60)
\""

    if [[ "${DAEMON_MODE}" == "true" ]]; then
        mkdir -p "${PID_DIR}" "${LOG_DIR}"
        nohup bash -c "${cmd}" > "${LOG_DIR}/kernel.log" 2>&1 &
        local pid=$!
        echo "${pid}" > "${PID_DIR}/kernel.pid"
        log_ok "Kernel started (PID ${pid})"
    else
        log_ok "Kernel start attempted (run with --daemon to background)"
    fi
}

start_direct_api_gateway() {
    log_info "Starting API Gateway on :${GATEWAY_PORT}..."

    kill_port "${GATEWAY_PORT}"

    local cmd="python3 -m uvicorn integration.api_gateway:app \
        --host 0.0.0.0 --port ${GATEWAY_PORT} \
        --log-level info"

    if [[ "${DAEMON_MODE}" == "true" ]]; then
        mkdir -p "${PID_DIR}" "${LOG_DIR}"
        nohup bash -c "cd ${ENTERPRISE_DIR} && ${cmd}" \
            > "${LOG_DIR}/api_gateway.log" 2>&1 &
        local pid=$!
        echo "${pid}" > "${PID_DIR}/api_gateway.pid"
        log_ok "API Gateway started (PID ${pid})"
    else
        log_ok "API Gateway start attempted"
    fi
}

start_direct_dashboard() {
    log_info "Starting Dashboard on :${DASHBOARD_DIRECT_PORT}..."

    kill_port "${DASHBOARD_DIRECT_PORT}"

    local cmd="python3 -m uvicorn dashboard.server:app \
        --host 0.0.0.0 --port ${DASHBOARD_DIRECT_PORT} \
        --log-level info"

    if [[ "${DAEMON_MODE}" == "true" ]]; then
        mkdir -p "${PID_DIR}" "${LOG_DIR}"
        nohup bash -c "cd ${ENTERPRISE_DIR} && ${cmd}" \
            > "${LOG_DIR}/dashboard.log" 2>&1 &
        local pid=$!
        echo "${pid}" > "${PID_DIR}/dashboard.pid"
        log_ok "Dashboard started (PID ${pid})"
    else
        log_ok "Dashboard start attempted"
    fi
}

start_direct() {
    log_info "Starting services directly (without Docker)..."

    # Check Python
    if ! command -v python3 &>/dev/null; then
        die "python3 not found."
    fi

    # Create required directories
    mkdir -p "${LOG_DIR}" "${PID_DIR}"

    # Start in correct dependency order
    start_direct_redis
    start_direct_kernel

    # Health check kernel if daemon mode
    if [[ "${DAEMON_MODE}" == "true" && "${SKIP_HEALTH}" != "true" ]]; then
        wait_for_http "http://localhost:${KERNEL_PORT}/health" "Kernel" 30 || {
            log_warn "Kernel health check failed — continuing anyway"
        }
    fi

    start_direct_api_gateway
    start_direct_dashboard

    if [[ "${DAEMON_MODE}" == "true" ]]; then
        log_info "Daemon mode — services running in background."
    else
        log_info "To run services as daemons, use --daemon flag."
    fi
}

# ── Health Verification ──────────────────────────────────────────────────────

verify_all_healthy() {
    if [[ "${SKIP_HEALTH}" == "true" ]]; then
        log_warn "Skipping health verification."
        return 0
    fi

    log_info "Verifying platform health..."
    echo ""

    # Wait a moment for services to stabilize
    sleep 2

    # Run health check
    if bash "${SCRIPT_DIR}/health_check.sh" --quick; then
        log_ok "All services healthy."
    else
        local exit_code=$?
        log_warn "Health check returned exit code ${exit_code} — some services may be degraded."
    fi
}

# ── Print Status Table ───────────────────────────────────────────────────────

print_startup_summary() {
    echo ""
    echo "=============================================="
    echo "  ENI Enterprise — Startup Summary"
    echo "=============================================="
    echo "  Mode       : $(if [[ "${DIRECT_MODE}" == "true" ]]; then echo "Direct"; else echo "Docker Compose"; fi)"
    echo "  Daemon     : ${DAEMON_MODE}"
    echo "  Modules    : $(if [[ "${NO_MODULES}" == "true" ]]; then echo "Core only"; else echo "All"; fi)"
    echo "=============================================="
    echo ""
    echo "Expected endpoints:"
    echo "  Kernel        : http://localhost:${KERNEL_PORT}/health"
    echo "  API Gateway   : http://localhost:${GATEWAY_PORT}/health"
    echo "  Dashboard     : http://localhost:${DASHBOARD_PORT} (Docker)"
    echo "  Dashboard Dir : http://localhost:${DASHBOARD_DIRECT_PORT}/api/health"
    echo "  Redis         : localhost:${REDIS_PORT}"
    echo ""
    echo "Quick commands:"
    echo "  Status : ${SCRIPT_DIR}/status.sh"
    echo "  Health : ${SCRIPT_DIR}/health_check.sh"
    echo "  Stop   : ${SCRIPT_DIR}/stop_all.sh"
    echo "=============================================="
}

# ── Main ──────────────────────────────────────────────────────────────────────

main() {
    # Parse flags
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --direct)          DIRECT_MODE=true ;;
            --daemon|-d)       DAEMON_MODE=true ;;
            --no-modules)      NO_MODULES=true ;;
            --skip-health)     SKIP_HEALTH=true ;;
            --help|-h)
                cat <<'EOF'
Usage: ./start_all.sh [OPTIONS]

Options:
  --direct          Start without Docker (direct Python processes)
  --daemon, -d      Run services as background daemons
  --no-modules      Start core services only (redis, kernel, gateway, dashboard)
  --skip-health     Skip post-startup health verification
  --help, -h        Show this help
EOF
                exit 0
                ;;
            *) die "Unknown option: $1" ;;
        esac
        shift
    done

    echo ""
    echo "=============================================="
    echo "  ENI Enterprise — Starting All Services"
    echo "  $(date)"
    echo "=============================================="
    echo ""

    # Verify environment
    if [[ ! -d "${ENTERPRISE_DIR}" ]]; then
        die "Enterprise directory not found: ${ENTERPRISE_DIR}"
    fi

    # Create log dir
    mkdir -p "${LOG_DIR}"

    if [[ "${DIRECT_MODE}" == "true" ]]; then
        start_direct
    else
        start_docker_compose
    fi

    verify_all_healthy
    print_startup_summary

    exit "${EXIT_SUCCESS}"
}

main "$@"