#!/usr/bin/env bash
# =============================================================================
# ENI Enterprise Platform — Status Overview
# =============================================================================
# Quick status overview of all platform services, Docker containers, processes,
# port bindings, and recent activity.
#
# Usage:
#   ./status.sh                   # Full status
#   ./status.sh --short           # Compact one-line status
#   ./status.sh --json            # JSON output
#   ./status.sh --watch           # Continuous watch mode
#   ./status.sh --containers      # Docker containers only
#   ./status.sh --processes       # Running processes only
# =============================================================================

set -euo pipefail

# ── Configuration ────────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENTERPRISE_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
DOCKER_COMPOSE_FILE="${ENTERPRISE_DIR}/docker-compose.yml"
PID_DIR="${ENTERPRISE_DIR}/.pids"
CONFIG_FILE="${ENTERPRISE_DIR}/config.yaml"

# Exit codes
readonly EXIT_SUCCESS=0
readonly EXIT_DEGRADED=1
readonly EXIT_DOWN=2

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
MAGENTA='\033[0;35m'
WHITE='\033[1;37m'
NC='\033[0m'

# ── Flags ────────────────────────────────────────────────────────────────────
SHORT_MODE=false
JSON_MODE=false
WATCH_MODE=false
CONTAINERS_ONLY=false
PROCESSES_ONLY=false
WATCH_INTERVAL=5

# ── Functions ────────────────────────────────────────────────────────────────

log_info()  { echo -e "${BLUE}[INFO]${NC}  $*"; }
log_ok()    { echo -e "${GREEN}[OK]${NC}    $*"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
log_fail()  { echo -e "${RED}[FAIL]${NC}  $*"; }
log_header(){ echo -e "\n${CYAN}─── $* ───${NC}"; }

status_icon() {
    case "$1" in
        running|healthy|ok|up|pass) echo -e "${GREEN}●${NC}" ;;
        degraded|warn|warning)      echo -e "${YELLOW}●${NC}" ;;
        stopped|down|fail|error|exited) echo -e "${RED}●${NC}" ;;
        *)                          echo -e "${YELLOW}○${NC}" ;;
    esac
}

# ── Detect Docker ────────────────────────────────────────────────────────────

check_docker_available() {
    command -v docker &>/dev/null && return 0
    return 1
}

get_compose_cmd() {
    if docker compose version &>/dev/null 2>&1; then
        echo "docker compose"
    elif command -v docker-compose &>/dev/null; then
        echo "docker-compose"
    else
        echo ""
    fi
}

# ── Port Check ───────────────────────────────────────────────────────────────

port_status() {
    local port="$1"
    if lsof -ti ":${port}" &>/dev/null 2>&1; then
        echo "up"
    else
        echo "down"
    fi
}

# ── Docker Container Status ──────────────────────────────────────────────────

status_containers() {
    log_header "Docker Containers"

    if ! check_docker_available; then
        echo "  Docker not installed"
        return
    fi

    local compose_cmd
    compose_cmd=$(get_compose_cmd)
    if [[ -z "${compose_cmd}" ]]; then
        echo "  Docker Compose not available"
        return
    fi

    if [[ ! -f "${DOCKER_COMPOSE_FILE}" ]]; then
        echo "  docker-compose.yml not found"
        return
    fi

    # Header
    printf "  %-40s %-12s %-12s %s\n" "CONTAINER" "STATE" "HEALTH" "PORTS"
    printf "  %-40s %-12s %-12s %s\n" "$(printf '%.0s-' {1..40})" "$(printf '%.0s-' {1..12})" "$(printf '%.0s-' {1..12})" "$(printf '%.0s-' {1..20})"

    # Get all containers from this compose project
    ${compose_cmd} -f "${DOCKER_COMPOSE_FILE}" ps --format json 2>/dev/null | \
    while read -r line; do
        if [[ -z "${line}" ]]; then continue; fi
        local name state health ports
        name=$(echo "${line}" | python3 -c "import sys,json; print(json.loads(sys.stdin.read()).get('Name','unknown'))" 2>/dev/null || echo "unknown")
        state=$(echo "${line}" | python3 -c "import sys,json; print(json.loads(sys.stdin.read()).get('State','unknown'))" 2>/dev/null || echo "unknown")
        health=$(echo "${line}" | python3 -c "import sys,json; d=json.loads(sys.stdin.read()); print(d.get('Health','-') or '-')" 2>/dev/null || echo "-")
        ports=$(echo "${line}" | python3 -c "import sys,json; d=json.loads(sys.stdin.read()); print(d.get('Publishers','-') or '-')" 2>/dev/null | head -1 || echo "-")

        local icon state_fmt
        case "${state}" in
            running) icon="${GREEN}●${NC}"; state_fmt="${GREEN}${state}${NC}" ;;
            *)       icon="${RED}●${NC}";   state_fmt="${RED}${state}${NC}" ;;
        esac

        printf "  %s %-39s %b %-11s %-12s %s\n" "${icon}" "${name}" "${state_fmt}" "${health}" "${ports}"
    done
}

# ── Direct Process Status ────────────────────────────────────────────────────

status_processes() {
    log_header "Direct Processes"

    local services=(
        "Kernel:8000"
        "API Gateway:8080"
        "Dashboard:8421"
        "Redis:6379"
    )

    printf "  %-25s %-10s %-12s %s\n" "SERVICE" "PORT" "STATUS" "PID"
    printf "  %-25s %-10s %-12s %s\n" "$(printf '%.0s-' {1..25})" "$(printf '%.0s-' {1..10})" "$(printf '%.0s-' {1..12})" "$(printf '%.0s-' {1..8})"

    for entry in "${services[@]}"; do
        local name="${entry%%:*}"
        local port="${entry##*:}"
        local status pid
        status=$(port_status "${port}")
        pid=$(lsof -ti ":${port}" 2>/dev/null || echo "-")

        local icon status_fmt
        if [[ "${status}" == "up" ]]; then
            icon="${GREEN}●${NC}"
            status_fmt="${GREEN}running${NC}"
        else
            icon="${RED}●${NC}"
            status_fmt="${RED}stopped${NC}"
            pid="-"
        fi

        printf "  %s %-24s %-10s %b %-11s ${pid}\n" "${icon}" "${name}" "${port}" "${status_fmt}"
    done

    # Check PID files
    if [[ -d "${PID_DIR}" ]]; then
        echo ""
        log_info "PID files in ${PID_DIR}:"
        shopt -s nullglob
        for pidfile in "${PID_DIR}"/*.pid; do
            if [[ -f "${pidfile}" ]]; then
                local svc pid running
                svc=$(basename "${pidfile}" .pid)
                pid=$(cat "${pidfile}" 2>/dev/null || echo "?")
                if kill -0 "${pid}" 2>/dev/null; then
                    running="${GREEN}alive${NC}"
                else
                    running="${RED}dead${NC}"
                fi
                echo "  ${svc}: PID ${pid} (${running})"
            fi
        done
        shopt -u nullglob
    fi
}

# ── HTTP Endpoint Status ─────────────────────────────────────────────────────

status_http() {
    log_header "HTTP Endpoints"

    local endpoints=(
        "Kernel:http://localhost:8000/health"
        "API Gateway:http://localhost:8080/health"
        "Dashboard:http://localhost:8421/api/health/summary"
    )

    for entry in "${endpoints[@]}"; do
        local name="${entry%%:*}"
        local url="${entry##*:}"
        # re-add colon after host
        url="http:${url}"

        local response
        response=$(curl -sf --max-time 3 "${url}" 2>/dev/null || echo "")

        if [[ -n "${response}" ]]; then
            local summary
            summary=$(echo "${response}" | python3 -c "
import sys,json
try:
    d=json.load(sys.stdin)
    if 'overall' in d:
        print(d['overall'])
    elif 'status' in d:
        print(d['status'])
    else:
        print('OK')
except:
    print('OK')
" 2>/dev/null || echo "OK")
            echo -e "  ${GREEN}●${NC} ${name}: ${GREEN}reachable${NC} (${summary})"
        else
            echo -e "  ${RED}●${NC} ${name}: ${RED}unreachable${NC}"
        fi
    done
}

# ── Platform Info ────────────────────────────────────────────────────────────

status_platform() {
    log_header "Platform Info"

    echo "  Directory   : ${ENTERPRISE_DIR}"
    echo "  Config      : ${CONFIG_FILE}"
    echo "  Hostname    : $(hostname 2>/dev/null || echo 'unknown')"
    echo "  Kernel      : $(uname -r)"

    # Version from config
    if [[ -f "${CONFIG_FILE}" ]]; then
        local version
        version=$(grep -m1 'version:' "${CONFIG_FILE}" | awk '{print $2}' | tr -d '"')
        echo "  Version     : ${version:-unknown}"
    fi

    # Deployed marker
    if [[ -f "${ENTERPRISE_DIR}/.deployed" ]]; then
        echo "  Deployed    : $(head -1 "${ENTERPRISE_DIR}/.deployed")"
    fi

    # Uptime
    echo "  System Up   : $(uptime -p 2>/dev/null | sed 's/up //' || uptime)"

    # Disk
    local disk_pct disk_avail
    disk_pct=$(df -h "${ENTERPRISE_DIR}" | awk 'NR==2 {print $5}')
    disk_avail=$(df -h "${ENTERPRISE_DIR}" | awk 'NR==2 {print $4}')
    echo "  Disk        : ${disk_pct} used, ${disk_avail} available"

    # Python
    if command -v python3 &>/dev/null; then
        echo "  Python      : $(python3 --version 2>&1)"
    else
        echo -e "  Python      : ${RED}not found${NC}"
    fi
}

# ── Quick Stats ──────────────────────────────────────────────────────────────

status_quick() {
    log_header "Quick Stats"

    # Module count
    local module_count=0
    if [[ -d "${ENTERPRISE_DIR}/modules" ]]; then
        module_count=$(find "${ENTERPRISE_DIR}/modules" -maxdepth 1 -type d ! -name '__pycache__' ! -name 'modules' ! -name '.*' | wc -l)
    fi

    # Test file count
    local test_count=0
    test_count=$(find "${ENTERPRISE_DIR}" -name 'test_*.py' -not -path '*__pycache__*' 2>/dev/null | wc -l)

    # Python file count
    local py_count=0
    py_count=$(find "${ENTERPRISE_DIR}" -name '*.py' -not -path '*__pycache__*' 2>/dev/null | wc -l)

    # Backup count
    local backup_count=0
    if [[ -d "${ENTERPRISE_DIR}/backups" ]]; then
        backup_count=$(find "${ENTERPRISE_DIR}/backups" -name '*.tar.gz' 2>/dev/null | wc -l)
    fi

    echo "  Modules     : ${module_count}"
    echo "  Test files  : ${test_count}"
    echo "  Python files: ${py_count}"
    echo "  Backups     : ${backup_count}"
}

# ── Short Summary ────────────────────────────────────────────────────────────

status_short() {
    local kernel_status api_status dash_status redis_status
    kernel_status=$(port_status 8000)
    api_status=$(port_status 8080)
    dash_status=$(port_status 8421)
    redis_status=$(port_status 6379)

    local overall="HEALTHY"
    local color="${GREEN}"

    if [[ "${kernel_status}" == "down" || "${api_status}" == "down" ]]; then
        overall="DEGRADED"
        color="${YELLOW}"
    fi
    if [[ "${kernel_status}" == "down" && "${api_status}" == "down" && "${dash_status}" == "down" ]]; then
        overall="DOWN"
        color="${RED}"
    fi

    echo -e "ENI Enterprise: ${color}${overall}${NC} | Kernel:$(status_icon "${kernel_status}") API:$(status_icon "${api_status}") Dash:$(status_icon "${dash_status}") Redis:$(status_icon "${redis_status}") | $(date +%H:%M:%S)"
}

# ── JSON Output ──────────────────────────────────────────────────────────────

status_json() {
    python3 -c "
import json, subprocess, os

kernel = 'up' if os.system('lsof -ti :8000 >/dev/null 2>&1') == 0 else 'down'
api = 'up' if os.system('lsof -ti :8080 >/dev/null 2>&1') == 0 else 'down'
dashboard = 'up' if os.system('lsof -ti :8421 >/dev/null 2>&1') == 0 else 'down'
redis = 'up' if os.system('lsof -ti :6379 >/dev/null 2>&1') == 0 else 'down'

overall = 'healthy'
if kernel == 'down' and api == 'down' and dashboard == 'down':
    overall = 'down'
elif kernel == 'down' or api == 'down':
    overall = 'degraded'

data = {
    'platform': '${ENTERPRISE_DIR}',
    'timestamp': '$(date --iso-8601=seconds)',
    'overall': overall,
    'services': {
        'kernel': {'port': 8000, 'status': kernel},
        'api_gateway': {'port': 8080, 'status': api},
        'dashboard': {'port': 8421, 'status': dashboard},
        'redis': {'port': 6379, 'status': redis},
    }
}
print(json.dumps(data, indent=2))
" 2>/dev/null || echo '{"error":"failed to collect status"}'
}

# ── Main ──────────────────────────────────────────────────────────────────────

main() {
    # Parse flags
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --short|-s)       SHORT_MODE=true ;;
            --json|-j)        JSON_MODE=true ;;
            --watch|-w)       WATCH_MODE=true ;;
            --containers|-c)  CONTAINERS_ONLY=true ;;
            --processes|-p)   PROCESSES_ONLY=true ;;
            --help|-h)
                cat <<'EOF'
Usage: ./status.sh [OPTIONS]

Options:
  --short, -s       Compact one-line status
  --json, -j        Output in JSON format
  --watch, -w       Continuous watch mode (refresh every 5s)
  --containers, -c  Show Docker container status only
  --processes, -p   Show process status only
  --help, -h        Show this help
EOF
                exit 0
                ;;
            *) echo "Unknown option: $1"; exit 2 ;;
        esac
        shift
    done

    # JSON mode
    if [[ "${JSON_MODE}" == "true" ]]; then
        status_json
        exit 0
    fi

    # Short mode
    if [[ "${SHORT_MODE}" == "true" ]]; then
        status_short
        exit 0
    fi

    # Watch mode
    if [[ "${WATCH_MODE}" == "true" ]]; then
        while true; do
            clear 2>/dev/null || true
            echo ""
            echo "  ENI Enterprise — Status (refreshing every ${WATCH_INTERVAL}s)"
            echo "  $(date)"
            echo ""
            status_short
            echo ""
            status_containers
            echo ""
            echo "  Press Ctrl+C to exit"
            sleep "${WATCH_INTERVAL}"
        done
        exit 0
    fi

    # Full status
    echo ""
    echo "=============================================="
    echo "  ENI Enterprise Platform — Status"
    echo "  $(date)"
    echo "=============================================="

    if [[ "${CONTAINERS_ONLY}" == "true" ]]; then
        status_containers
    elif [[ "${PROCESSES_ONLY}" == "true" ]]; then
        status_processes
    else
        status_platform
        status_quick
        status_containers
        status_processes
        status_http
    fi

    echo ""
    echo "=============================================="
    echo "  Quick commands:"
    echo "    Start  : ${SCRIPT_DIR}/start_all.sh"
    echo "    Stop   : ${SCRIPT_DIR}/stop_all.sh"
    echo "    Health : ${SCRIPT_DIR}/health_check.sh"
    echo "    Deploy : ${SCRIPT_DIR}/deploy.sh"
    echo "=============================================="
    echo ""

    exit "${EXIT_SUCCESS}"
}

main "$@"