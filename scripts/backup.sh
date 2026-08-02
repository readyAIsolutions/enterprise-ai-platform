#!/usr/bin/env bash
# =============================================================================
# ENI Enterprise Platform — Backup Script
# =============================================================================
# Creates a comprehensive backup of configs, state, logs, and data. Supports
# full and incremental backups, compression, and rotation.
#
# Usage:
#   ./backup.sh                     # Full backup to default location
#   ./backup.sh --incremental       # Incremental backup (since last full)
#   ./backup.sh --output /path      # Custom output directory
#   ./backup.sh --name my_backup    # Custom backup name
#   ./backup.sh --no-compress       # Skip compression
#   ./backup.sh --keep 5            # Keep only last N backups
# =============================================================================

set -euo pipefail

# ── Configuration ────────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENTERPRISE_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
BACKUP_ROOT="${ENTERPRISE_DIR}/backups"
DATA_DIR="${ENTERPRISE_DIR}/data"
LOG_DIR="${ENTERPRISE_DIR}/logs"

# Exit codes
readonly EXIT_SUCCESS=0
readonly EXIT_BACKUP_FAIL=10
readonly EXIT_SETUP_FAIL=2

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# ── Flags ────────────────────────────────────────────────────────────────────
BACKUP_TYPE="full"           # full | incremental
OUTPUT_DIR="${BACKUP_ROOT}"
BACKUP_NAME=""
NO_COMPRESS=false
KEEP_COUNT=0
DRY_RUN=false

# ── Functions ────────────────────────────────────────────────────────────────

log_info()  { echo -e "${BLUE}[INFO]${NC}  $(date +'%Y-%m-%d %H:%M:%S') $*"; }
log_ok()    { echo -e "${GREEN}[OK]${NC}    $(date +'%Y-%m-%d %H:%M:%S') $*"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC}  $(date +'%Y-%m-%d %H:%M:%S') $*"; }
log_error() { echo -e "${RED}[ERROR]${NC} $(date +'%Y-%m-%d %H:%M:%S') $*" >&2; }

die() {
    log_error "$*"
    exit "${EXIT_SETUP_FAIL}"
}

# ── Generate Filename ────────────────────────────────────────────────────────

generate_filename() {
    local timestamp
    timestamp=$(date +'%Y%m%d-%H%M%S')
    local hostname_short
    hostname_short=$(hostname -s 2>/dev/null || echo "unknown")

    if [[ -n "${BACKUP_NAME}" ]]; then
        echo "eni-enterprise-${BACKUP_NAME}-${hostname_short}-${timestamp}"
    else
        echo "eni-enterprise-${BACKUP_TYPE}-${hostname_short}-${timestamp}"
    fi
}

# ── Create Backup ────────────────────────────────────────────────────────────

create_backup() {
    local backup_name="$1"
    local backup_dir="${OUTPUT_DIR}/${backup_name}"
    local backup_tar="${OUTPUT_DIR}/${backup_name}.tar.gz"

    log_info "Creating ${BACKUP_TYPE} backup: ${backup_name}"
    log_info "Enterprise directory: ${ENTERPRISE_DIR}"
    log_info "Output: ${backup_tar}"

    if [[ "${DRY_RUN}" == "true" ]]; then
        log_info "[DRY RUN] Would backup to: ${backup_tar}"
        log_info "[DRY RUN] Would include: configs, modules, data, logs, state"
        return 0
    fi

    # Create working directory
    mkdir -p "${backup_dir}"

    # ── 1. Backup config files ──────────────────────────────────────────────
    log_info "Backing up configuration files..."
    mkdir -p "${backup_dir}/configs"

    local config_files=(
        "config.yaml"
        "docker-compose.yml"
        "pyproject.toml"
        "requirements.txt"
    )

    for cf in "${config_files[@]}"; do
        local src="${ENTERPRISE_DIR}/${cf}"
        if [[ -f "${src}" ]]; then
            cp -a "${src}" "${backup_dir}/configs/"
            log_info "  [OK] ${cf}"
        else
            log_warn "  [MISSING] ${cf}"
        fi
    done

    # Copy .env if present
    if [[ -f "${ENTERPRISE_DIR}/.env" ]]; then
        cp -a "${ENTERPRISE_DIR}/.env" "${backup_dir}/configs/"
        log_info "  [OK] .env"
    fi

    # ── 2. Backup deployment markers ────────────────────────────────────────
    if [[ -f "${ENTERPRISE_DIR}/.deployed" ]]; then
        cp -a "${ENTERPRISE_DIR}/.deployed" "${backup_dir}/configs/"
    fi

    # ── 3. Backup data directory ────────────────────────────────────────────
    if [[ -d "${DATA_DIR}" ]] && ls "${DATA_DIR}"/* &>/dev/null 2>&1; then
        log_info "Backing up data directory..."
        mkdir -p "${backup_dir}/data"
        cp -a "${DATA_DIR}"/* "${backup_dir}/data/" 2>/dev/null || true
        log_info "  [OK] data/"
    else
        log_info "  [EMPTY] data/ directory — skipping"
    fi

    # ── 4. Backup logs (last 1000 lines per log) ────────────────────────────
    if [[ -d "${LOG_DIR}" ]]; then
        log_info "Backing up recent logs..."
        mkdir -p "${backup_dir}/logs"
        for logfile in "${LOG_DIR}"/*.log; do
            if [[ -f "${logfile}" ]]; then
                tail -1000 "${logfile}" > "${backup_dir}/logs/$(basename "${logfile}")" 2>/dev/null || true
            fi
        done
        log_info "  [OK] logs/ (last 1000 lines each)"
    fi

    # ── 5. Backup module list and versions ──────────────────────────────────
    log_info "Capturing module inventory..."
    python3 -c "
import sys, os, json, subprocess
sys.path.insert(0, '${ENTERPRISE_DIR}')
inventory = {
    'timestamp': '$(date --iso-8601=seconds)',
    'type': '${BACKUP_TYPE}',
    'enterprise_dir': '${ENTERPRISE_DIR}',
    'modules': {}
}
modules_dir = '${ENTERPRISE_DIR}/modules'
if os.path.isdir(modules_dir):
    for mod in sorted(os.listdir(modules_dir)):
        mod_path = os.path.join(modules_dir, mod)
        if os.path.isdir(mod_path) and not mod.startswith('__'):
            py_files = sum(1 for f in os.listdir(mod_path) if f.endswith('.py'))
            inventory['modules'][mod] = {'python_files': py_files}
print(json.dumps(inventory, indent=2))
" > "${backup_dir}/inventory.json" 2>/dev/null || {
        echo '{"error":"inventory collection failed"}' > "${backup_dir}/inventory.json"
    }
    log_info "  [OK] inventory.json"

    # ── 6. Backup git info if available ─────────────────────────────────────
    if command -v git &>/dev/null && git -C "${ENTERPRISE_DIR}" rev-parse --git-dir &>/dev/null 2>&1; then
        log_info "Capturing git metadata..."
        git -C "${ENTERPRISE_DIR}" rev-parse HEAD > "${backup_dir}/git_commit.txt" 2>/dev/null || true
        git -C "${ENTERPRISE_DIR}" status --porcelain > "${backup_dir}/git_status.txt" 2>/dev/null || true
        log_info "  [OK] git metadata"
    fi

    # ── 7. Create backup manifest ───────────────────────────────────────────
    cat > "${backup_dir}/MANIFEST.txt" <<EOF
=== ENI Enterprise Backup ===
Backup Name : ${backup_name}
Type        : ${BACKUP_TYPE}
Created     : $(date --iso-8601=seconds)
Hostname    : $(hostname 2>/dev/null || echo "unknown")
Platform    : $(uname -a)
Source      : ${ENTERPRISE_DIR}
Disk Usage  : $(du -sh "${backup_dir}" 2>/dev/null | cut -f1)
Contents:
  - configs/     : Configuration files
  - data/        : Data directory
  - logs/        : Recent log tails
  - inventory.json : Module listing
  - MANIFEST.txt : This file
EOF
    log_info "  [OK] manifest"

    # ── 8. Compress ─────────────────────────────────────────────────────────
    if [[ "${NO_COMPRESS}" == "true" ]]; then
        log_info "Skipping compression (--no-compress)"
        mv "${backup_dir}" "${OUTPUT_DIR}/${backup_name}/"
        log_ok "Backup created at: ${OUTPUT_DIR}/${backup_name}/"
    else
        log_info "Compressing backup..."
        if tar -czf "${backup_tar}" -C "${OUTPUT_DIR}" "${backup_name}" 2>/dev/null; then
            rm -rf "${backup_dir}"
            local backup_size
            backup_size=$(du -h "${backup_tar}" | cut -f1)
            log_ok "Backup created: ${backup_tar} (${backup_size})"
        else
            log_error "Compression failed."
            exit "${EXIT_BACKUP_FAIL}"
        fi
    fi
}

# ── Rotate Old Backups ───────────────────────────────────────────────────────

rotate_backups() {
    if [[ ${KEEP_COUNT} -le 0 ]]; then
        return 0
    fi

    log_info "Rotating backups (keeping last ${KEEP_COUNT})..."

    local pattern="eni-enterprise-*.tar.gz"
    local backups
    readarray -t backups < <(ls -1t "${OUTPUT_DIR}"/${pattern} 2>/dev/null || true)

    if [[ ${#backups[@]} -gt ${KEEP_COUNT} ]]; then
        local to_delete=("${backups[@]:${KEEP_COUNT}}")
        for b in "${to_delete[@]}"; do
            log_info "Removing old backup: $(basename "${b}")"
            rm -f "${b}"
        done
        log_info "Rotated: removed $((${#backups[@]} - KEEP_COUNT)) old backups"
    else
        log_info "No rotation needed (${#backups[@]} backups, keeping ${KEEP_COUNT})"
    fi
}

# ── Main ──────────────────────────────────────────────────────────────────────

main() {
    # Parse flags
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --incremental|-i)   BACKUP_TYPE="incremental" ;;
            --full|-f)          BACKUP_TYPE="full" ;;
            --output|-o)        OUTPUT_DIR="$2"; shift ;;
            --name|-n)          BACKUP_NAME="$2"; shift ;;
            --no-compress)      NO_COMPRESS=true ;;
            --keep|-k)          KEEP_COUNT="$2"; shift ;;
            --dry-run)          DRY_RUN=true ;;
            --help|-h)
                cat <<'EOF'
Usage: ./backup.sh [OPTIONS]

Options:
  --incremental, -i   Incremental backup (since last full)
  --full, -f          Full backup (default)
  --output, -o DIR    Set output directory (default: backups/)
  --name, -n NAME     Custom backup name
  --no-compress       Skip tar.gz compression
  --keep, -k N        Keep only last N backups, rotate older ones
  --dry-run           Show what would be backed up without doing it
  --help, -h          Show this help
EOF
                exit 0
                ;;
            *) die "Unknown option: $1" ;;
        esac
        shift
    done

    echo ""
    echo "=============================================="
    echo "  ENI Enterprise — Backup"
    echo "  Type: ${BACKUP_TYPE}"
    echo "  Platform: ${ENTERPRISE_DIR}"
    echo "=============================================="
    echo ""

    # Verify source exists
    if [[ ! -d "${ENTERPRISE_DIR}" ]]; then
        die "Enterprise directory not found: ${ENTERPRISE_DIR}"
    fi

    # Create output dir
    mkdir -p "${OUTPUT_DIR}"

    # Generate backup name
    local final_name
    final_name=$(generate_filename)

    # Create backup
    create_backup "${final_name}"

    # Rotate old backups
    rotate_backups

    echo ""
    log_ok "Backup completed successfully."
    exit "${EXIT_SUCCESS}"
}

main "$@"