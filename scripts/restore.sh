#!/usr/bin/env bash
# =============================================================================
# ENI Enterprise Platform — Restore Script
# =============================================================================
# Restores platform configuration, data, and state from a backup archive.
# Supports dry-run, selective restore, and safety checks.
#
# Usage:
#   ./restore.sh <backup_file>              # Full restore
#   ./restore.sh <backup_file> --configs-only # Configs only
#   ./restore.sh <backup_file> --data-only    # Data only
#   ./restore.sh <backup_file> --dry-run      # Preview what would be restored
#   ./restore.sh --list                       # List available backups
# =============================================================================

set -euo pipefail

# ── Configuration ────────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENTERPRISE_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
BACKUP_ROOT="${ENTERPRISE_DIR}/backups"
RESTORE_TMP="/tmp/eni-restore-$$"

# Exit codes
readonly EXIT_SUCCESS=0
readonly EXIT_RESTORE_FAIL=10
readonly EXIT_BACKUP_NOT_FOUND=11
readonly EXIT_SETUP_FAIL=2
readonly EXIT_USER_ABORT=3

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# ── Flags ────────────────────────────────────────────────────────────────────
DRY_RUN=false
CONFIGS_ONLY=false
DATA_ONLY=false
LIST_BACKUPS=false
RESTORE_LOGS=false
FORCE=false

# ── Functions ────────────────────────────────────────────────────────────────

log_info()  { echo -e "${BLUE}[INFO]${NC}  $(date +'%Y-%m-%d %H:%M:%S') $*"; }
log_ok()    { echo -e "${GREEN}[OK]${NC}    $(date +'%Y-%m-%d %H:%M:%S') $*"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC}  $(date +'%Y-%m-%d %H:%M:%S') $*"; }
log_error() { echo -e "${RED}[ERROR]${NC} $(date +'%Y-%m-%d %H:%M:%S') $*" >&2; }

die() {
    log_error "$*"
    exit "${EXIT_SETUP_FAIL}"
}

cleanup() {
    rm -rf "${RESTORE_TMP}" 2>/dev/null || true
}

confirm() {
    if [[ "${FORCE}" == "true" ]]; then
        return 0
    fi
    local prompt="$1"
    read -r -p "$(echo -e "${YELLOW}${prompt} [y/N]: ${NC}")" response
    case "${response,,}" in
        y|yes) return 0 ;;
        *)     return 1 ;;
    esac
}

# ── List Backups ─────────────────────────────────────────────────────────────

list_backups() {
    echo ""
    echo "Available backups in ${BACKUP_ROOT}:"
    echo ""

    if [[ ! -d "${BACKUP_ROOT}" ]]; then
        log_warn "No backup directory found."
        return
    fi

    local found=0
    for b in "${BACKUP_ROOT}"/eni-enterprise-*.tar.gz; do
        if [[ -f "${b}" ]]; then
            local name size date
            name=$(basename "${b}")
            size=$(du -h "${b}" | cut -f1)
            date=$(stat -c '%y' "${b}" 2>/dev/null | cut -d. -f1 || stat -f '%Sm' "${b}" 2>/dev/null)
            echo "  ${name}"
            echo "    Size: ${size}  Date: ${date}"
            echo ""
            found=1
        fi
    done

    # Also list uncompressed backups
    for b in "${BACKUP_ROOT}"/eni-enterprise-*/; do
        if [[ -d "${b}" ]]; then
            local name size
            name=$(basename "${b}")
            size=$(du -sh "${b}" 2>/dev/null | cut -f1)
            echo "  ${name}/ (uncompressed)"
            echo "    Size: ${size}"
            echo ""
            found=1
        fi
    done

    if [[ ${found} -eq 0 ]]; then
        log_warn "No backups found."
    fi
}

# ── Validate Backup ──────────────────────────────────────────────────────────

validate_backup() {
    local backup="$1"

    if [[ ! -f "${backup}" ]]; then
        log_error "Backup file not found: ${backup}"
        log_info "Use --list to see available backups."
        exit "${EXIT_BACKUP_NOT_FOUND}"
    fi

    # Check if it's a valid tar.gz
    if ! tar -tzf "${backup}" &>/dev/null; then
        die "Invalid or corrupt backup archive: ${backup}"
    fi

    log_ok "Backup archive validated: $(basename "${backup}")"
}

# ── Extract Backup ───────────────────────────────────────────────────────────

extract_backup() {
    local backup="$1"

    log_info "Extracting backup to temporary location..."
    mkdir -p "${RESTORE_TMP}"

    if ! tar -xzf "${backup}" -C "${RESTORE_TMP}"; then
        cleanup
        die "Failed to extract backup archive."
    fi

    # Find the extracted directory
    local dir
    dir=$(find "${RESTORE_TMP}" -maxdepth 1 -type d ! -name '.*' ! -name "${RESTORE_TMP}" -print -quit)
    if [[ -z "${dir}" ]]; then
        cleanup
        die "Could not locate extracted backup directory."
    fi

    log_ok "Extracted to: ${dir}"
    echo "${dir}"
}

# ── Restore Configs ──────────────────────────────────────────────────────────

restore_configs() {
    local src_dir="$1"

    if [[ ! -d "${src_dir}/configs" ]]; then
        log_warn "No configs directory in backup."
        return 0
    fi

    log_info "Restoring configuration files..."

    local config_files=(
        "config.yaml"
        "docker-compose.yml"
        "pyproject.toml"
        "requirements.txt"
        ".env"
        ".deployed"
    )

    for cf in "${config_files[@]}"; do
        local src="${src_dir}/configs/${cf}"
        if [[ -f "${src}" ]]; then
            if [[ "${DRY_RUN}" == "true" ]]; then
                log_info "  [DRY RUN] Would restore: ${cf}"
            else
                # Create backup of current file before overwriting
                local dst="${ENTERPRISE_DIR}/${cf}"
                if [[ -f "${dst}" ]]; then
                    cp -a "${dst}" "${dst}.bak.$(date +%Y%m%d%H%M%S)"
                    log_info "  Backed up current: ${cf} → ${cf}.bak.*"
                fi
                cp -a "${src}" "${dst}"
                log_ok "  Restored: ${cf}"
            fi
        fi
    done
}

# ── Restore Data ─────────────────────────────────────────────────────────────

restore_data() {
    local src_dir="$1"

    if [[ ! -d "${src_dir}/data" ]] || ! ls "${src_dir}/data"/* &>/dev/null 2>&1; then
        log_warn "No data directory in backup."
        return 0
    fi

    log_info "Restoring data..."

    if [[ "${DRY_RUN}" == "true" ]]; then
        log_info "  [DRY RUN] Would restore data/ contents"
        return 0
    fi

    local data_dst="${ENTERPRISE_DIR}/data"
    mkdir -p "${data_dst}"

    # Backup current data before overwriting
    local data_bak="${data_dst}.bak.$(date +%Y%m%d%H%M%S)"
    if [[ -d "${data_dst}" ]] && ls "${data_dst}"/* &>/dev/null 2>&1; then
        cp -a "${data_dst}" "${data_bak}"
        log_info "  Current data backed up to: ${data_bak}"
    fi

    cp -a "${src_dir}/data/"* "${data_dst}/"
    log_ok "  Data restored."
}

# ── Restore Logs ─────────────────────────────────────────────────────────────

restore_logs() {
    local src_dir="$1"

    if [[ ! -d "${src_dir}/logs" ]]; then
        log_warn "No logs directory in backup."
        return 0
    fi

    log_info "Restoring log tails..."
    if [[ "${DRY_RUN}" == "true" ]]; then
        log_info "  [DRY RUN] Would restore log tails"
        return 0
    fi

    local log_dst="${ENTERPRISE_DIR}/logs"
    mkdir -p "${log_dst}"
    cp -a "${src_dir}/logs/"*.log "${log_dst}/" 2>/dev/null || true
    log_ok "  Log tails restored."
}

# ── Print Backup Manifest ────────────────────────────────────────────────────

print_manifest() {
    local src_dir="$1"

    if [[ -f "${src_dir}/MANIFEST.txt" ]]; then
        echo ""
        echo "=============================================="
        echo "  Backup Manifest"
        echo "=============================================="
        cat "${src_dir}/MANIFEST.txt"
        echo "=============================================="
    fi

    if [[ -f "${src_dir}/inventory.json" ]]; then
        log_info "Backup inventory available: ${src_dir}/inventory.json"
    fi
}

# ── Main ──────────────────────────────────────────────────────────────────────

main() {
    local backup_file=""
    local extracted_dir=""

    # Parse flags
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --configs-only)    CONFIGS_ONLY=true ;;
            --data-only)       DATA_ONLY=true ;;
            --logs)            RESTORE_LOGS=true ;;
            --dry-run)         DRY_RUN=true ;;
            --list)            LIST_BACKUPS=true ;;
            --force|-f)        FORCE=true ;;
            --output|-o)
                # Allow custom output for restore
                ENTERPRISE_DIR="$(cd "$2" && pwd)" 2>/dev/null || die "Invalid output directory: $2"
                shift
                ;;
            --help|-h)
                cat <<'EOF'
Usage: ./restore.sh [OPTIONS] <backup_file>
       ./restore.sh --list

Options:
  --configs-only     Restore only configuration files
  --data-only        Restore only data directory
  --logs             Restore log tails
  --dry-run          Preview what would be restored
  --list             List available backups
  --force, -f        Skip confirmation prompts
  --output, -o DIR   Restore to a different directory
  --help, -h         Show this help
EOF
                exit 0
                ;;
            -*)
                die "Unknown option: $1"
                ;;
            *)
                backup_file="$1"
                ;;
        esac
        shift
    done

    # List mode
    if [[ "${LIST_BACKUPS}" == "true" ]]; then
        list_backups
        exit 0
    fi

    # Require backup file
    if [[ -z "${backup_file}" ]]; then
        log_error "No backup file specified."
        echo "Usage: $0 <backup_file> [OPTIONS]"
        echo "       $0 --list"
        exit "${EXIT_SETUP_FAIL}"
    fi

    echo ""
    echo "=============================================="
    echo "  ENI Enterprise — Restore"
    echo "  Backup: ${backup_file}"
    echo "  Target: ${ENTERPRISE_DIR}"
    echo "=============================================="
    echo ""

    # Resolve relative paths
    if [[ ! "${backup_file}" = /* ]]; then
        backup_file="$(pwd)/${backup_file}"
    fi

    # Validate
    validate_backup "${backup_file}"

    # Confirm
    if [[ "${DRY_RUN}" != "true" ]]; then
        if ! confirm "This will overwrite files in ${ENTERPRISE_DIR}. Continue?"; then
            log_info "Restore cancelled."
            exit "${EXIT_USER_ABORT}"
        fi
    else
        log_info "DRY RUN — no changes will be made."
    fi

    # Extract
    extracted_dir=$(extract_backup "${backup_file}")

    # Show manifest
    print_manifest "${extracted_dir}"

    # Selective or full restore
    if [[ "${CONFIGS_ONLY}" == "true" ]]; then
        restore_configs "${extracted_dir}"
    elif [[ "${DATA_ONLY}" == "true" ]]; then
        restore_data "${extracted_dir}"
    else
        restore_configs "${extracted_dir}"
        restore_data "${extracted_dir}"
        if [[ "${RESTORE_LOGS}" == "true" ]]; then
            restore_logs "${extracted_dir}"
        fi
    fi

    # Cleanup
    cleanup

    if [[ "${DRY_RUN}" == "true" ]]; then
        log_ok "Dry run complete. No changes were made."
    else
        log_ok "Restore completed successfully."
        log_info "Restart services if needed: ${SCRIPT_DIR}/start_all.sh"
    fi

    exit "${EXIT_SUCCESS}"
}

# Trap cleanup
trap cleanup EXIT INT TERM

main "$@"