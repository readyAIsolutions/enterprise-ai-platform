#!/usr/bin/env bash
# =============================================================================
# ENI Enterprise Platform — Full Deployment Script
# =============================================================================
# Checks dependencies, installs requirements, starts all services, and verifies
# health. Designed for production deployments with proper error handling.
#
# Usage:
#   ./deploy.sh              # Interactive deploy
#   ./deploy.sh --yes        # Non-interactive (skip confirmations)
#   ./deploy.sh --check-only # Only check prerequisites, don't deploy
# =============================================================================

set -euo pipefail

# ── Configuration ────────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENTERPRISE_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
CONFIG_FILE="${ENTERPRISE_DIR}/config.yaml"
REQUIREMENTS_FILE="${ENTERPRISE_DIR}/requirements.txt"
PYPROJECT_FILE="${ENTERPRISE_DIR}/pyproject.toml"
DOCKER_COMPOSE_FILE="${ENTERPRISE_DIR}/docker-compose.yml"
LOG_DIR="${ENTERPRISE_DIR}/logs"
DATA_DIR="${ENTERPRISE_DIR}/data"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Exit codes
readonly EXIT_SUCCESS=0
readonly EXIT_PREREQ_FAIL=10
readonly EXIT_BUILD_FAIL=11
readonly EXIT_DEPLOY_FAIL=12
readonly EXIT_HEALTH_FAIL=13
readonly EXIT_USAGE=2

# ── Flags ────────────────────────────────────────────────────────────────────
YES_MODE=false
CHECK_ONLY=false
SKIP_TESTS=false
ENVIRONMENT="production"

# ── Functions ────────────────────────────────────────────────────────────────

log_info()  { echo -e "${BLUE}[INFO]${NC}  $(date +'%Y-%m-%d %H:%M:%S') $*"; }
log_ok()    { echo -e "${GREEN}[OK]${NC}    $(date +'%Y-%m-%d %H:%M:%S') $*"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC}  $(date +'%Y-%m-%d %H:%M:%S') $*"; }
log_error() { echo -e "${RED}[ERROR]${NC} $(date +'%Y-%m-%d %H:%M:%S') $*" >&2; }

die() {
    log_error "$*"
    exit "${EXIT_PREREQ_FAIL}"
}

confirm() {
    if [[ "${YES_MODE}" == "true" ]]; then
        return 0
    fi
    local prompt="$1"
    read -r -p "$(echo -e "${YELLOW}${prompt} [y/N]: ${NC}")" response
    case "${response,,}" in
        y|yes) return 0 ;;
        *)     return 1 ;;
    esac
}

check_command() {
    command -v "$1" &>/dev/null || die "Required command not found: $1. Please install it."
}

check_python_module() {
    python3 -c "import $1" 2>/dev/null || die "Python module '$1' is required but not installed (pip install $1)"
}

# ── Prerequisite Checks ──────────────────────────────────────────────────────

check_prerequisites() {
    log_info "Checking deployment prerequisites..."

    # Platform check
    local os_name
    os_name="$(uname -s)"
    log_info "Operating system: ${os_name}"

    # Check essential commands
    check_command python3
    check_command pip3
    check_command curl
    check_command tar
    check_command gzip

    # Check Python version (3.11 or 3.12)
    local python_version
    python_version=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
    log_info "Python version: ${python_version}"
    case "${python_version}" in
        3.11|3.12) ;;
        *) die "Python ${python_version} detected. ENI Enterprise requires Python 3.11 or 3.12." ;;
    esac

    # Check enterprise directory structure
    if [[ ! -d "${ENTERPRISE_DIR}" ]]; then
        die "Enterprise directory not found: ${ENTERPRISE_DIR}"
    fi

    if [[ ! -f "${CONFIG_FILE}" ]]; then
        die "Configuration file not found: ${CONFIG_FILE}"
    fi

    if [[ ! -f "${REQUIREMENTS_FILE}" ]]; then
        die "Requirements file not found: ${REQUIREMENTS_FILE}"
    fi

    # Verify key module directories exist
    local required_dirs=(
        "${ENTERPRISE_DIR}/modules"
        "${ENTERPRISE_DIR}/integration"
        "${ENTERPRISE_DIR}/dashboard"
    )
    for dir in "${required_dirs[@]}"; do
        if [[ ! -d "${dir}" ]]; then
            die "Required directory missing: ${dir}"
        fi
    done

    log_ok "All prerequisite checks passed."
}

# ── Environment Setup ────────────────────────────────────────────────────────

setup_environment() {
    log_info "Setting up environment..."

    # Create required directories
    mkdir -p "${LOG_DIR}" "${DATA_DIR}" "${ENTERPRISE_DIR}/backups"

    # Create default .env if not present
    local env_file="${ENTERPRISE_DIR}/.env"
    if [[ ! -f "${env_file}" ]]; then
        log_info "Creating default .env file..."
        cat > "${env_file}" <<'EOF'
ENI_ENV=production
LOG_LEVEL=INFO
TZ=UTC
KERNEL_PORT=8000
GATEWAY_PORT=8080
DASHBOARD_PORT=3000
REDIS_PORT=6379
EOF
    fi

    # Export environment
    export ENI_ENV="${ENVIRONMENT}"

    log_ok "Environment setup complete."
}

# ── Dependency Installation ──────────────────────────────────────────────────

install_dependencies() {
    log_info "Installing Python dependencies..."

    # Install from requirements.txt
    if ! pip3 install -r "${REQUIREMENTS_FILE}" --quiet --upgrade 2>&1 | tail -5; then
        die "Failed to install dependencies from ${REQUIREMENTS_FILE}"
    fi

    # Install package in development mode
    log_info "Installing project in development mode..."
    if ! pip3 install -e "${ENTERPRISE_DIR}" --quiet 2>&1 | tail -3; then
        log_warn "pip install -e failed (may be expected if setup.py isn't configured). Continuing..."
    fi

    log_ok "Dependencies installed successfully."
}

# ── Run Tests ────────────────────────────────────────────────────────────────

run_pre_deploy_tests() {
    if [[ "${SKIP_TESTS}" == "true" ]]; then
        log_warn "Skipping pre-deployment tests."
        return 0
    fi

    log_info "Running pre-deployment test suite..."
    if ! python3 -m pytest "${ENTERPRISE_DIR}/tests/" \
        --tb=short \
        -q \
        --timeout=120 \
        2>&1; then
        log_error "Pre-deployment tests FAILED."
        if ! confirm "Tests failed. Continue deployment anyway?"; then
            exit "${EXIT_BUILD_FAIL}"
        fi
        log_warn "Continuing deployment despite test failures."
    else
        log_ok "All pre-deployment tests passed."
    fi
}

# ── Docker Compose Deployment ────────────────────────────────────────────────

deploy_docker() {
    log_info "Deploying with Docker Compose..."

    if ! command -v docker &>/dev/null; then
        log_warn "Docker not found. Skipping container deployment."
        deploy_direct
        return
    fi

    if ! command -v docker-compose &>/dev/null && ! docker compose version &>/dev/null; then
        log_warn "Docker Compose not found. Skipping container deployment."
        deploy_direct
        return
    fi

    # Determine docker compose command
    local compose_cmd
    if docker compose version &>/dev/null 2>&1; then
        compose_cmd="docker compose"
    else
        compose_cmd="docker-compose"
    fi

    # Build images
    log_info "Building Docker images..."
    if ! ${compose_cmd} -f "${DOCKER_COMPOSE_FILE}" build --quiet; then
        die "Docker build failed."
    fi
    log_ok "Docker images built."

    # Start services
    log_info "Starting services..."
    if ! ${compose_cmd} -f "${DOCKER_COMPOSE_FILE}" up -d --remove-orphans; then
        die "Docker Compose up failed."
    fi

    log_ok "Docker Compose deployment started."
}

# ── Direct Deployment ────────────────────────────────────────────────────────

deploy_direct() {
    log_info "Setting up direct (non-Docker) deployment..."

    # Verify core Python modules are importable
    log_info "Verifying core module imports..."
    python3 -c "
import sys
sys.path.insert(0, '${ENTERPRISE_DIR}')
try:
    import platform_kernel
    print('  platform_kernel: OK')
except Exception as e:
    print(f'  platform_kernel: FAILED — {e}')
    sys.exit(1)

try:
    import dashboard.server
    print('  dashboard.server: OK')
except Exception as e:
    print(f'  dashboard.server: FAILED — {e}')
    sys.exit(1)
" || die "Core module import verification failed."

    log_ok "Direct deployment verified."

    # Create startup marker
    echo "Deployed at $(date --iso-8601=seconds)" > "${ENTERPRISE_DIR}/.deployed"
}

# ── Health Verification ──────────────────────────────────────────────────────

verify_health() {
    log_info "Verifying deployment health..."

    local max_wait=60
    local waited=0
    local interval=5

    # If Docker is running, check container health
    if command -v docker &>/dev/null; then
        local compose_cmd
        if docker compose version &>/dev/null 2>&1; then
            compose_cmd="docker compose"
        else
            compose_cmd="docker-compose"
        fi

        log_info "Waiting for containers to be healthy (max ${max_wait}s)..."
        while [[ ${waited} -lt ${max_wait} ]]; do
            local unhealthy
            unhealthy=$(${compose_cmd} -f "${DOCKER_COMPOSE_FILE}" ps --format json 2>/dev/null | \
                python3 -c "import sys,json; data=[json.loads(l) for l in sys.stdin]; unhealthy=[d['Name'] for d in data if d.get('Health','') not in ('','healthy')]; print('\n'.join(unhealthy))" 2>/dev/null || echo "")

            if [[ -z "${unhealthy}" ]]; then
                log_ok "All containers healthy after ${waited}s."
                break
            fi

            sleep "${interval}"
            waited=$((waited + interval))
        done

        if [[ ${waited} -ge ${max_wait} ]]; then
            log_error "Some containers still not healthy after ${max_wait}s."
            ${compose_cmd} -f "${DOCKER_COMPOSE_FILE}" ps 2>/dev/null || true
            exit "${EXIT_HEALTH_FAIL}"
        fi
    fi

    # Try HTTP health checks
    local http_endpoints=(
        "http://localhost:8000/health"
        "http://localhost:8080/health"
        "http://localhost:8421/api/health"
    )

    log_info "Running HTTP health checks..."
    for endpoint in "${http_endpoints[@]}"; do
        if curl -sf --max-time 5 "${endpoint}" &>/dev/null; then
            log_ok "Health check OK: ${endpoint}"
        else
            log_warn "Health check UNREACHABLE: ${endpoint} (may be normal if not deployed)"
        fi
    done

    log_ok "Health verification complete."
}

# ── Print Summary ────────────────────────────────────────────────────────────

print_summary() {
    echo ""
    echo "=============================================="
    echo "  ENI Enterprise Deployment Complete"
    echo "=============================================="
    echo "  Environment : ${ENVIRONMENT}"
    echo "  Platform    : ${ENTERPRISE_DIR}"
    echo "  Config      : ${CONFIG_FILE}"
    echo "  Deployed at : $(date --iso-8601=seconds)"
    echo "=============================================="
    echo ""
    echo "Quick commands:"
    echo "  Status    : ${SCRIPT_DIR}/status.sh"
    echo "  Health    : ${SCRIPT_DIR}/health_check.sh"
    echo "  Stop      : ${SCRIPT_DIR}/stop_all.sh"
    echo ""
}

# ── Main ──────────────────────────────────────────────────────────────────────

main() {
    echo ""
    echo "=============================================="
    echo "  ENI Enterprise Platform — Deployment"
    echo "  Version: $(grep -m1 'version:' "${CONFIG_FILE}" | awk '{print $2}' | tr -d '"')"
    echo "  Target: ${ENTERPRISE_DIR}"
    echo "=============================================="
    echo ""

    # Parse flags
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --yes|-y) YES_MODE=true ;;
            --check-only) CHECK_ONLY=true ;;
            --skip-tests) SKIP_TESTS=true ;;
            --env|--environment) ENVIRONMENT="$2"; shift ;;
            --help|-h)
                echo "Usage: $0 [OPTIONS]"
                echo ""
                echo "Options:"
                echo "  --yes, -y         Skip confirmation prompts"
                echo "  --check-only      Only check prerequisites, don't deploy"
                echo "  --skip-tests      Skip running pre-deployment tests"
                echo "  --env ENV         Set environment (production|staging|development)"
                echo "  --help, -h        Show this help"
                exit "${EXIT_SUCCESS}"
                ;;
            *) die "Unknown option: $1" ;;
        esac
        shift
    done

    # Phase 1: Prerequisites
    check_prerequisites

    if [[ "${CHECK_ONLY}" == "true" ]]; then
        log_ok "Prerequisite check complete. No deployment performed."
        exit "${EXIT_SUCCESS}"
    fi

    # Phase 2: Environment
    setup_environment

    # Phase 3: Dependencies
    install_dependencies

    # Phase 4: Tests
    run_pre_deploy_tests

    # Phase 5: Confirm
    if ! confirm "Ready to deploy to ${ENVIRONMENT} environment. Proceed?"; then
        log_info "Deployment cancelled by user."
        exit 0
    fi

    # Phase 6: Deploy
    deploy_docker

    # Phase 7: Verify
    verify_health

    # Phase 8: Summary
    print_summary

    exit "${EXIT_SUCCESS}"
}

main "$@"