#!/usr/bin/env bash
# =============================================================================
# ENI Enterprise Platform — Comprehensive Health Check
# =============================================================================
# Checks every layer of the platform: processes, Docker containers, HTTP
# endpoints, disk space, memory, Python imports, and module status.
#
# Usage:
#   ./health_check.sh              # Full health check
#   ./health_check.sh --quick      # Fast check (HTTP + container status only)
#   ./health_check.sh --json       # Output in JSON format
#   ./health_check.sh --endpoint   # Check a custom endpoint
# =============================================================================

set -euo pipefail

# ── Configuration ────────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENTERPRISE_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
CONFIG_FILE="${ENTERPRISE_DIR}/config.yaml"
LOG_DIR="${ENTERPRISE_DIR}/logs"

# Exit codes
readonly EXIT_HEALTHY=0
readonly EXIT_DEGRADED=1
readonly EXIT_UNHEALTHY=2

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

# ── Flags ────────────────────────────────────────────────────────────────────
QUICK_MODE=false
JSON_MODE=false
CUSTOM_ENDPOINT=""
VERBOSE=false

# ── State ────────────────────────────────────────────────────────────────────
CHECKS_TOTAL=0
CHECKS_PASSED=0
CHECKS_FAILED=0
CHECKS_WARNINGS=0
declare -A CHECK_RESULTS
declare -a CHECK_MESSAGES

# ── Functions ────────────────────────────────────────────────────────────────

log_info()  { [[ "${JSON_MODE}" != "true" ]] && echo -e "${BLUE}[INFO]${NC}  $*"; }
log_ok()    { [[ "${JSON_MODE}" != "true" ]] && echo -e "${GREEN}[PASS]${NC} $*"; }
log_warn()  { [[ "${JSON_MODE}" != "true" ]] && echo -e "${YELLOW}[WARN]${NC} $*"; }
log_fail()  { [[ "${JSON_MODE}" != "true" ]] && echo -e "${RED}[FAIL]${NC} $*"; }
log_header(){ [[ "${JSON_MODE}" != "true" ]] && echo -e "\n${CYAN}─── $* ───${NC}"; }

record_pass() {
    local check="$1" message="$2"
    CHECK_RESULTS["${check}"]="pass"
    CHECK_MESSAGES+=("${message}")
    CHECKS_TOTAL=$((CHECKS_TOTAL + 1))
    CHECKS_PASSED=$((CHECKS_PASSED + 1))
    [[ "${JSON_MODE}" != "true" ]] && log_ok "${message}"
}

record_warn() {
    local check="$1" message="$2"
    CHECK_RESULTS["${check}"]="warn"
    CHECK_MESSAGES+=("${message}")
    CHECKS_TOTAL=$((CHECKS_TOTAL + 1))
    CHECKS_WARNINGS=$((CHECKS_WARNINGS + 1))
    [[ "${JSON_MODE}" != "true" ]] && log_warn "${message}"
}

record_fail() {
    local check="$1" message="$2"
    CHECK_RESULTS["${check}"]="fail"
    CHECK_MESSAGES+=("${message}")
    CHECKS_TOTAL=$((CHECKS_TOTAL + 1))
    CHECKS_FAILED=$((CHECKS_FAILED + 1))
    [[ "${JSON_MODE}" != "true" ]] && log_fail "${message}"
}

http_get() {
    local url="$1" timeout="${2:-5}"
    curl -sf --max-time "${timeout}" --connect-timeout 3 "${url}" 2>/dev/null || echo "FAIL"
}

# ── Check: File System ───────────────────────────────────────────────────────

check_filesystem() {
    log_header "Filesystem Health"

    # Enterprise directory exists
    if [[ -d "${ENTERPRISE_DIR}" ]]; then
        record_pass "fs_enterprise_dir" "Enterprise directory: ${ENTERPRISE_DIR}"
    else
        record_fail "fs_enterprise_dir" "Enterprise directory MISSING: ${ENTERPRISE_DIR}"
        return
    fi

    # Config file
    if [[ -f "${CONFIG_FILE}" ]]; then
        record_pass "fs_config" "Config file: ${CONFIG_FILE}"
    else
        record_fail "fs_config" "Config file MISSING: ${CONFIG_FILE}"
    fi

    # Key directories
    for dir in modules integration dashboard foundation; do
        if [[ -d "${ENTERPRISE_DIR}/${dir}" ]]; then
            record_pass "fs_dir_${dir}" "Directory present: ${dir}/"
        else
            record_warn "fs_dir_${dir}" "Directory missing: ${dir}/"
        fi
    done

    # Disk space check
    local disk_pct
    disk_pct=$(df -h "${ENTERPRISE_DIR}" | awk 'NR==2 {gsub(/%/,""); print $5}')
    if [[ ${disk_pct:-100} -lt 85 ]]; then
        record_pass "fs_disk" "Disk usage: ${disk_pct}% (OK)"
    elif [[ ${disk_pct:-100} -lt 95 ]]; then
        record_warn "fs_disk" "Disk usage: ${disk_pct}% (WARNING)"
    else
        record_fail "fs_disk" "Disk usage: ${disk_pct}% (CRITICAL)"
    fi

    # Log directory write test
    local test_file="${LOG_DIR}/health_check_test_$$"
    if touch "${test_file}" 2>/dev/null; then
        rm -f "${test_file}"
        record_pass "fs_writable" "Log directory is writable"
    else
        record_warn "fs_writable" "Log directory NOT writable"
    fi
}

# ── Check: System Resources ──────────────────────────────────────────────────

check_resources() {
    log_header "System Resources"

    # Memory
    local mem_avail_gb
    mem_avail_gb=$(free -g | awk 'NR==2 {print $7}')
    if [[ ${mem_avail_gb:-0} -ge 1 ]]; then
        record_pass "res_memory" "Available memory: ${mem_avail_gb}GB"
    elif [[ ${mem_avail_gb:-0} -ge 0 ]]; then
        record_warn "res_memory" "Low memory: ${mem_avail_gb}GB available"
    else
        record_fail "res_memory" "Cannot determine memory status"
    fi

    # CPU load
    local load
    load=$(uptime | awk -F'load average:' '{print $2}' | awk '{print $1}' | tr -d ',')
    if (( $(echo "${load:-99}" | awk '{print ($1 < 10)}') )); then
        record_pass "res_cpu" "CPU load: ${load}"
    else
        record_warn "res_cpu" "High CPU load: ${load}"
    fi

    # Open file descriptors (if available)
    if command -v lsof &>/dev/null; then
        local fd_count
        fd_count=$(lsof 2>/dev/null | wc -l) || fd_count=0
        if [[ ${fd_count} -lt 100000 ]]; then
            record_pass "res_fd" "Open file descriptors: ${fd_count}"
        else
            record_warn "res_fd" "High file descriptor count: ${fd_count}"
        fi
    fi
}

# ── Check: Python Environment ────────────────────────────────────────────────

check_python() {
    log_header "Python Environment"

    # Python available
    if command -v python3 &>/dev/null; then
        local py_ver
        py_ver=$(python3 --version 2>&1)
        record_pass "py_available" "Python: ${py_ver}"
    else
        record_fail "py_available" "Python 3 NOT found"
        return
    fi

    # Python version check
    local py_major_minor
    py_major_minor=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
    case "${py_major_minor}" in
        3.11|3.12) record_pass "py_version" "Python ${py_major_minor} (supported)" ;;
        *) record_warn "py_version" "Python ${py_major_minor} — platform targets 3.11/3.12" ;;
    esac

    # Check installed packages
    local required_packages=("fastapi" "uvicorn" "pydantic" "pyyaml" "redis" "httpx")
    for pkg in "${required_packages[@]}"; do
        if python3 -c "import ${pkg}" 2>/dev/null; then
            record_pass "py_pkg_${pkg}" "Package installed: ${pkg}"
        else
            record_warn "py_pkg_${pkg}" "Package MISSING: ${pkg}"
        fi
    done

    # Try importing core platform module
    if python3 -c "
import sys; sys.path.insert(0, '${ENTERPRISE_DIR}')
from platform_kernel import PlatformOS, HealthStatus
print('OK')
" 2>/dev/null; then
        record_pass "py_core_import" "platform_kernel module importable"
    else
        record_warn "py_core_import" "platform_kernel module NOT importable"
    fi
}

# ── Check: Docker Containers ─────────────────────────────────────────────────

check_docker() {
    log_header "Docker Containers"

    if ! command -v docker &>/dev/null; then
        record_warn "docker_available" "Docker not installed — skipping container checks"
        return
    fi

    # Determine compose command
    local compose_cmd
    if docker compose version &>/dev/null 2>&1; then
        compose_cmd="docker compose"
    elif command -v docker-compose &>/dev/null; then
        compose_cmd="docker-compose"
    else
        record_warn "docker_compose" "Docker Compose not available"
        return
    fi

    # Check containers
    local compose_file="${ENTERPRISE_DIR}/docker-compose.yml"
    if [[ ! -f "${compose_file}" ]]; then
        record_warn "docker_compose_file" "docker-compose.yml not found"
        return
    fi

    # Get container statuses
    local containers_json
    containers_json=$(${compose_cmd} -f "${compose_file}" ps --format json 2>/dev/null || echo "[]")

    if [[ "${containers_json}" == "[]" || -z "${containers_json}" ]]; then
        record_warn "docker_containers" "No containers running — services may be stopped"
        return
    fi

    # Parse and report
    echo "${containers_json}" | python3 -c "
import sys, json
for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    try:
        c = json.loads(line)
    except:
        continue
    name = c.get('Name', 'unknown')
    status = c.get('State', 'unknown')
    health = c.get('Health', '')
    print(f'{name}|{status}|{health}')
" 2>/dev/null | while IFS='|' read -r name status health; do
        local check_name="docker_${name}"
        if [[ "${status}" == "running" ]]; then
            if [[ "${health}" == "healthy" || -z "${health}" ]]; then
                record_pass "${check_name}" "Container ${name}: running (${health:-no health check})"
            else
                record_warn "${check_name}" "Container ${name}: running but ${health}"
            fi
        else
            record_fail "${check_name}" "Container ${name}: ${status}"
        fi
    done
}

# ── Check: HTTP Endpoints ────────────────────────────────────────────────────

check_http() {
    log_header "HTTP Endpoints"

    # Core endpoints
    local endpoints=(
        "http://localhost:8000/health|kernel"
        "http://localhost:8080/health|api_gateway"
        "http://localhost:3000/health|dashboard"
        "http://localhost:8421/api/health|dashboard_direct"
    )

    for entry in "${endpoints[@]}"; do
        local url="${entry%%|*}"
        local name="${entry##*|}"
        local result
        result=$(http_get "${url}" 5)

        if [[ "${result}" != "FAIL" ]]; then
            record_pass "http_${name}" "Endpoint ${name}: OK (${url})"
        else
            record_warn "http_${name}" "Endpoint ${name}: unreachable (${url})"
        fi
    done

    # Custom endpoint if specified
    if [[ -n "${CUSTOM_ENDPOINT}" ]]; then
        local result
        result=$(http_get "${CUSTOM_ENDPOINT}" 5)
        if [[ "${result}" != "FAIL" ]]; then
            record_pass "http_custom" "Custom endpoint: OK (${CUSTOM_ENDPOINT})"
        else
            record_fail "http_custom" "Custom endpoint: unreachable (${CUSTOM_ENDPOINT})"
        fi
    fi
}

# ── Check: Redis ─────────────────────────────────────────────────────────────

check_redis() {
    log_header "Redis"

    if command -v redis-cli &>/dev/null; then
        if redis-cli -h localhost -p "${REDIS_PORT:-6379}" ping 2>/dev/null | grep -q PONG; then
            record_pass "redis_ping" "Redis: PONG"
        else
            record_warn "redis_ping" "Redis: unreachable on port ${REDIS_PORT:-6379}"
        fi
    else
        # Try via Python
        if python3 -c "import redis; r=redis.Redis(host='localhost',port=${REDIS_PORT:-6379},socket_connect_timeout=3); print(r.ping())" 2>/dev/null | grep -q True; then
            record_pass "redis_ping" "Redis: OK (via Python client)"
        else
            record_warn "redis_ping" "Redis: not reachable or not configured"
        fi
    fi
}

# ── Check: Log Files ─────────────────────────────────────────────────────────

check_logs() {
    log_header "Log Files"

    local log_file="${LOG_DIR}/platform.log"

    if [[ -f "${log_file}" ]]; then
        local log_size log_lines
        log_size=$(du -h "${log_file}" 2>/dev/null | cut -f1)
        log_lines=$(wc -l < "${log_file}" 2>/dev/null || echo "0")
        record_pass "log_exists" "Platform log: ${log_size}, ${log_lines} lines"

        # Check for recent errors
        local recent_errors
        recent_errors=$(tail -500 "${log_file}" 2>/dev/null | grep -c -i -E '(ERROR|CRITICAL|FATAL|Traceback)' || echo "0")
        if [[ ${recent_errors} -gt 10 ]]; then
            record_warn "log_errors" "Recent errors in log: ${recent_errors} (last 500 lines)"
        else
            record_pass "log_errors" "Recent errors: ${recent_errors} (last 500 lines)"
        fi
    else
        record_warn "log_exists" "Platform log not found: ${log_file}"
    fi
}

# ── JSON Output ──────────────────────────────────────────────────────────────

output_json() {
    local overall
    if [[ ${CHECKS_FAILED} -gt 0 ]]; then
        overall="unhealthy"
    elif [[ ${CHECKS_WARNINGS} -gt 2 ]]; then
        overall="degraded"
    else
        overall="healthy"
    fi

    python3 -c "
import json, sys
data = {
    'overall': '${overall}',
    'timestamp': '$(date --iso-8601=seconds)',
    'platform': '${ENTERPRISE_DIR}',
    'checks': {'total': ${CHECKS_TOTAL}, 'passed': ${CHECKS_PASSED}, 'warnings': ${CHECKS_WARNINGS}, 'failed': ${CHECKS_FAILED}},
    'results': {
$(for key in "${!CHECK_RESULTS[@]}"; do
    echo "        '${key}': '${CHECK_RESULTS[$key]}',"
done)
    }
}
print(json.dumps(data, indent=2))
"
}

# ── Summary ──────────────────────────────────────────────────────────────────

print_summary() {
    echo ""
    echo "=============================================="
    if [[ ${CHECKS_FAILED} -eq 0 && ${CHECKS_WARNINGS} -eq 0 ]]; then
        echo -e "  ${GREEN}OVERALL: HEALTHY${NC}"
    elif [[ ${CHECKS_FAILED} -eq 0 ]]; then
        echo -e "  ${YELLOW}OVERALL: DEGRADED${NC}"
    else
        echo -e "  ${RED}OVERALL: UNHEALTHY${NC}"
    fi
    echo "=============================================="
    echo "  Checks : ${CHECKS_TOTAL} total"
    echo "  Passed : ${CHECKS_PASSED}"
    echo "  Warnings: ${CHECKS_WARNINGS}"
    echo "  Failed : ${CHECKS_FAILED}"
    echo "  Time   : $(date --iso-8601=seconds)"
    echo "=============================================="
    echo ""
}

# ── Main ──────────────────────────────────────────────────────────────────────

main() {
    # Parse flags
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --quick|-q) QUICK_MODE=true ;;
            --json|-j) JSON_MODE=true ;;
            --endpoint) CUSTOM_ENDPOINT="$2"; shift ;;
            --verbose|-v) VERBOSE=true ;;
            --help|-h)
                echo "Usage: $0 [OPTIONS]"
                echo ""
                echo "Options:"
                echo "  --quick, -q      Fast check (HTTP + containers only)"
                echo "  --json, -j       Output results as JSON"
                echo "  --endpoint URL   Check a custom HTTP endpoint"
                echo "  --verbose, -v    Verbose output"
                echo "  --help, -h       Show this help"
                exit 0
                ;;
            *) echo "Unknown option: $1"; exit 2 ;;
        esac
        shift
    done

    if [[ "${JSON_MODE}" != "true" ]]; then
        echo ""
        echo "=============================================="
        echo "  ENI Enterprise — Health Check"
        echo "  $(date)"
        echo "  Platform: ${ENTERPRISE_DIR}"
        echo "=============================================="
    fi

    if [[ "${QUICK_MODE}" == "true" ]]; then
        check_docker
        check_http
    else
        check_filesystem
        check_resources
        check_python
        check_docker
        check_http
        check_redis
        check_logs
    fi

    if [[ "${JSON_MODE}" == "true" ]]; then
        output_json
    else
        print_summary
    fi

    # Determine exit code
    if [[ ${CHECKS_FAILED} -gt 0 ]]; then
        exit "${EXIT_UNHEALTHY}"
    elif [[ ${CHECKS_WARNINGS} -gt 0 ]]; then
        exit "${EXIT_DEGRADED}"
    else
        exit "${EXIT_HEALTHY}"
    fi
}

main "$@"