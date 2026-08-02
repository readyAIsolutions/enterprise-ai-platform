#!/usr/bin/env bash
# =============================================================================
# ENI Enterprise Platform — Test Runner
# =============================================================================
# Runs the full test suite with coverage, or targeted subsets. Supports pytest
# flags, parallel execution, and output formats.
#
# Usage:
#   ./run_tests.sh                     # Full test suite
#   ./run_tests.sh --unit              # Unit tests only
#   ./run_tests.sh --integration       # Integration tests only
#   ./run_tests.sh --module agent_coordination  # Single module
#   ./run_tests.sh --coverage          # With coverage report
#   ./run_tests.sh --parallel          # Parallel execution (xdist)
#   ./run_tests.sh --verbose           # Verbose output
#   ./run_tests.sh --fail-fast         # Stop on first failure
# =============================================================================

set -euo pipefail

# ── Configuration ────────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENTERPRISE_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
COVERAGE_DIR="${ENTERPRISE_DIR}/htmlcov"
PYTEST_CACHE="${ENTERPRISE_DIR}/.pytest_cache"

# Exit codes
readonly EXIT_TESTS_PASS=0
readonly EXIT_TESTS_FAIL=1
readonly EXIT_SETUP_FAIL=2

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

# ── Flags ────────────────────────────────────────────────────────────────────
MODE="all"                # all | unit | integration | e2e | module
TARGET_MODULE=""          # module name for --module mode
COVERAGE=false
PARALLEL=false
VERBOSE=false
FAIL_FAST=false
QUIET=false
EXTRA_PYTEST_ARGS=()

# ── Functions ────────────────────────────────────────────────────────────────

log_info()  { echo -e "${BLUE}[INFO]${NC}  $*"; }
log_ok()    { echo -e "${GREEN}[OK]${NC}    $*"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
log_error() { echo -e "${RED}[ERROR]${NC} $*" >&2; }
log_header(){ echo -e "\n${CYAN}─── $* ───${NC}"; }

die() {
    log_error "$*"
    exit "${EXIT_SETUP_FAIL}"
}

# ── Prerequisites ────────────────────────────────────────────────────────────

check_prereqs() {
    if ! command -v python3 &>/dev/null; then
        die "python3 not found. Cannot run tests."
    fi

    if ! python3 -m pytest --version &>/dev/null; then
        die "pytest not installed. Run: pip install pytest"
    fi

    if [[ ! -d "${ENTERPRISE_DIR}" ]]; then
        die "Enterprise directory not found: ${ENTERPRISE_DIR}"
    fi
}

# ── Build pytest command ─────────────────────────────────────────────────────

build_pytest_cmd() {
    local cmd=("python3" "-m" "pytest")

    # Verbose
    if [[ "${VERBOSE}" == "true" ]]; then
        cmd+=("-v")
    elif [[ "${QUIET}" == "true" ]]; then
        cmd+=("-q" "--no-header")
    else
        cmd+=("--tb=short")
    fi

    # Fail fast
    if [[ "${FAIL_FAST}" == "true" ]]; then
        cmd+=("-x")
    fi

    # Strict markers from pyproject.toml
    cmd+=("--strict-markers")

    # Suppress deprecation warnings
    cmd+=("-W" "ignore::DeprecationWarning")

    # Coverage
    if [[ "${COVERAGE}" == "true" ]]; then
        cmd+=(
            "--cov=${ENTERPRISE_DIR}"
            "--cov-report=html:${COVERAGE_DIR}"
        )
    fi

    # Parallel
    if [[ "${PARALLEL}" == "true" ]]; then
        cmd+=("-n" "auto")
    fi

    # Extra args
    cmd+=("${EXTRA_PYTEST_ARGS[@]}")

    # Determine test paths
    case "${MODE}" in
        all)
            cmd+=(
                "${ENTERPRISE_DIR}/tests/"
                "${ENTERPRISE_DIR}/modules/"
                "--ignore=${ENTERPRISE_DIR}/modules/safety_governance"
                "--ignore=${ENTERPRISE_DIR}/foundation/*_old"
            )
            ;;
        unit)
            cmd+=(
                "${ENTERPRISE_DIR}/tests/"
                "${ENTERPRISE_DIR}/modules/"
                "-m" "unit or not integration"
                "--ignore=${ENTERPRISE_DIR}/modules/safety_governance"
                "--ignore=${ENTERPRISE_DIR}/foundation/*_old"
            )
            ;;
        integration)
            cmd+=(
                "${ENTERPRISE_DIR}/tests/integration/"
                "${ENTERPRISE_DIR}/modules/"
                "-m" "integration"
            )
            ;;
        e2e)
            cmd+=(
                "${ENTERPRISE_DIR}/tests/"
                "-m" "e2e"
            )
            ;;
        module)
            if [[ -z "${TARGET_MODULE}" ]]; then
                die "No module specified. Use --module <name>"
            fi
            local module_path="${ENTERPRISE_DIR}/modules/${TARGET_MODULE}/tests/"
            if [[ -d "${module_path}" ]]; then
                cmd+=("${module_path}")
            else
                # Try foundation path
                local found_path="${ENTERPRISE_DIR}/foundation/${TARGET_MODULE}/tests/"
                if [[ -d "${found_path}" ]]; then
                    cmd+=("${found_path}")
                else
                    die "Module not found: ${TARGET_MODULE} (tried ${module_path} and ${found_path})"
                fi
            fi
            ;;
        *)
            die "Unknown mode: ${MODE}"
            ;;
    esac

    echo "${cmd[@]}"
}

# ── Main ──────────────────────────────────────────────────────────────────────

main() {
    # Parse flags
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --unit)           MODE="unit" ;;
            --integration)    MODE="integration" ;;
            --e2e)            MODE="e2e" ;;
            --all)            MODE="all" ;;
            --module)         MODE="module"; TARGET_MODULE="$2"; shift ;;
            --coverage|-c)    COVERAGE=true ;;
            --parallel|-p)    PARALLEL=true ;;
            --verbose|-v)     VERBOSE=true ;;
            --quiet|-q)       QUIET=true ;;
            --fail-fast|-x)   FAIL_FAST=true ;;
            --help|-h)
                cat <<'EOF'
Usage: ./run_tests.sh [OPTIONS]

Modes:
  --all              Full test suite (default)
  --unit             Unit tests only
  --integration      Integration tests only
  --e2e              End-to-end tests only
  --module NAME      Tests for a specific module

Options:
  --coverage, -c     Generate coverage report (htmlcov/)
  --parallel, -p     Parallel execution with pytest-xdist
  --verbose, -v      Verbose output
  --quiet, -q        Quiet output
  --fail-fast, -x    Stop on first failure
  --help, -h         Show this help

Any additional arguments are passed directly to pytest.
EOF
                exit 0
                ;;
            --) shift; EXTRA_PYTEST_ARGS+=("$@"); break ;;
            *)   EXTRA_PYTEST_ARGS+=("$1") ;;
        esac
        shift
    done

    # Check prerequisites
    check_prereqs

    # Clean cache if desired
    if [[ -d "${PYTEST_CACHE}" ]]; then
        log_info "Cleaning pytest cache..."
        rm -rf "${PYTEST_CACHE}"
    fi

    # Clean old coverage
    if [[ "${COVERAGE}" == "true" && -d "${COVERAGE_DIR}" ]]; then
        rm -rf "${COVERAGE_DIR}"
    fi

    # Build and print command
    local pytest_cmd
    pytest_cmd=$(build_pytest_cmd)
    log_header "Test Configuration"
    log_info "Mode: ${MODE}"
    [[ -n "${TARGET_MODULE}" ]] && log_info "Module: ${TARGET_MODULE}"
    [[ "${COVERAGE}" == "true" ]] && log_info "Coverage: enabled → ${COVERAGE_DIR}/"
    [[ "${PARALLEL}" == "true" ]] && log_info "Parallel: enabled"
    [[ "${FAIL_FAST}" == "true" ]] && log_info "Fail-fast: enabled"
    echo ""

    # Run tests
    log_header "Running Tests"
    log_info "Command: ${pytest_cmd}"
    echo ""

    local start_time end_time
    start_time=$(date +%s)

    local exit_code=0
    # shellcheck disable=SC2086
    if ! ${pytest_cmd}; then
        exit_code="${EXIT_TESTS_FAIL}"
    else
        exit_code="${EXIT_TESTS_PASS}"
    fi

    end_time=$(date +%s)
    local duration=$((end_time - start_time))

    echo ""
    log_header "Test Results"
    if [[ ${exit_code} -eq 0 ]]; then
        log_ok "ALL TESTS PASSED  (${duration}s)"
    else
        log_error "TESTS FAILED  (${duration}s)"
    fi

    if [[ "${COVERAGE}" == "true" && -f "${COVERAGE_DIR}/index.html" ]]; then
        log_info "Coverage report: file://${COVERAGE_DIR}/index.html"
    fi

    exit "${exit_code}"
}

main "$@"