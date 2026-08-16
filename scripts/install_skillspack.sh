#!/usr/bin/env bash
# =============================================================================
# install_skillspack.sh — Portable Skills / LSP / MCP / Plugin Pack installer
# =============================================================================
# Copies the versioned skills_pack/ from this repo into a target Hermes home
# (default ~/.hermes), preserving the category layout:
#
#   skills_pack/skills/   -> $HERMES_HOME/skills/
#   skills_pack/lsp/      -> $HERMES_HOME/lsp_servers/
#   skills_pack/mcp/      -> $HERMES_HOME/mcp_servers/
#   skills_pack/plugins/  -> $HERMES_HOME/plugins/
#
# Idempotent: on every run, existing destination content is first backed up to
# $HERMES_HOME/.skillspack_backup_TIMESTAMP before being merged/overwritten.
# Python cache bytes (__pycache__/, *.pyc) are stripped before and after copy.
# Safe to re-run any number of times.
#
# Options:
#   --dry-run   Report what WOULD happen without copying anything.
#   --target=DIR  Override the Hermes home directory (default: ~/.hermes).
#   --force     Overwrite existing files even if identical (default is merge).
# =============================================================================
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PACK_DIR="$REPO_ROOT/skills_pack"

TERM="${TERM:-dumb}"
GREEN=""
YELLOW=""
NC=""
if [[ $TERM != "dumb" ]]; then
  GREEN=$'\033[0;32m'; YELLOW=$'\033[0;33m'; NC=$'\033[0m'
fi

# ---- arg parsing ------------------------------------------------------------
DRY_RUN=0
HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"
FORCE=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run) DRY_RUN=1; shift ;;
    --force)   FORCE=1; shift ;;
    --target=*) HERMES_HOME="${1#*=}"; shift ;;
    --target)  HERMES_HOME="$2"; shift 2 ;;
    -h|--help|help)
      grep '^#' "$0" | sed 's/^# *//' | sed 's/^ *//;s/ *$//' | grep -v '^=' | head -40
      exit 0 ;;
    --) shift; [[ $# -gt 0 ]] && HERMES_HOME="$1"; break ;;
    *)  HERMES_HOME="$1"; shift ;;
  esac
done

# ---- sanity checks ----------------------------------------------------------
if [[ ! -d "$PACK_DIR" ]]; then
  echo "ERROR: skills_pack/ not found at $PACK_DIR" >&2
  exit 1
fi
if [[ -z "${PACK_DIR##*/skills_pack}" || ! -f "$PACK_DIR/__init__.py" ]]; then
  :
fi

# ---- inventory --------------------------------------------------------------
count_files() { find "$1" -type f 2>/dev/null | wc -l; }

N_SKILLS=$(count_files "$PACK_DIR/skills")
N_LSP=$(count_files "$PACK_DIR/lsp")
N_MCP=$(count_files "$PACK_DIR/mcp")
N_PLUGINS=$(count_files "$PACK_DIR/plugins")
N_TOTAL=$(( N_SKILLS + N_LSP + N_MCP + N_PLUGINS ))
N_CATS=$(find "$PACK_DIR/skills" -mindepth 1 -maxdepth 1 -type d 2>/dev/null | wc -l)

echo "${GREEN}[ENI skillspack install]${NC} pack: $PACK_DIR"
echo "  target Hermes home : $HERMES_HOME"
echo "  skills categories  : $N_CATS"
echo "  skill files        : $N_SKILLS"
echo "  lsp server files   : $N_LSP"
echo "  mcp server files   : $N_MCP"
echo "  plugin files       : $N_PLUGINS"
echo "  total files        : $N_TOTAL"

# ---- dry run ----------------------------------------------------------------
if [[ $DRY_RUN -eq 1 ]]; then
  echo ""
  echo "${YELLOW}[DRY-RUN] no files were copied. Planned mapping:${NC}"
  printf '  %-46s -> %s\n' "$PACK_DIR/skills/"        "${HERMES_HOME}/skills/"
  printf '  %-46s -> %s\n' "$PACK_DIR/lsp/"           "${HERMES_HOME}/lsp_servers/"
  printf '  %-46s -> %s\n' "$PACK_DIR/mcp/"           "${HERMES_HOME}/mcp_servers/"
  printf '  %-46s -> %s\n' "$PACK_DIR/plugins/"       "${HERMES_HOME}/plugins/"
  echo ""
  echo "Would BACK UP existing destination to: $HERMES_HOME/.skillspack_backup_<TIMESTAMP>"
  echo "[DRY-RUN] complete."
  exit 0
fi

# ---- install ----------------------------------------------------------------
mkdir -p "$HERMES_HOME"

# strip pycache in the source pack so nothing stray ships to the host
find "$PACK_DIR" -name __pycache__ -type d -prune -exec rm -rf {} \; 2>/dev/null || true
find "$PACK_DIR" -name '*.pyc' -delete 2>/dev/null || true

# idempotent backup of pre-existing destination categories (only if present)
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
BACKUP_DIR="$HERMES_HOME/.skillspack_backup_${TIMESTAMP}"
NEED_BACKUP=0
for sub in skills lsp_servers mcp_servers plugins; do
  [[ -e "$HERMES_HOME/$sub" ]] && NEED_BACKUP=1
done

if [[ $NEED_BACKUP -eq 1 ]]; then
  mkdir -p "$BACKUP_DIR"
  for sub in skills lsp_servers mcp_servers plugins; do
    if [[ -e "$HERMES_HOME/$sub" ]]; then
      cp -r "$HERMES_HOME/$sub" "$BACKUP_DIR/" 2>/dev/null || true
    fi
  done
  echo "Backed up existing categories to: $BACKUP_DIR"
else
  echo "No pre-existing destination categories — nothing to back up."
fi

# merge each category (cp -rn with "/." source forces content-merge so reruns
# never nest a category dir inside itself when the target already exists)
mkdir -p "$HERMES_HOME/skills/" "$HERMES_HOME/lsp_servers/" "$HERMES_HOME/mcp_servers/" "$HERMES_HOME/plugins/"
OLDFLAG=""
[[ $FORCE -eq 1 ]] && OLDFLAG=""
cp -rn "$PACK_DIR/skills/."   "$HERMES_HOME/skills/"    || true
cp -rn "$PACK_DIR/lsp/."      "$HERMES_HOME/lsp_servers/" || true
cp -rn "$PACK_DIR/mcp/."      "$HERMES_HOME/mcp_servers/" || true
cp -rn "$PACK_DIR/plugins/."  "$HERMES_HOME/plugins/"   || true

# final cache strip on the live target
find "$HERMES_HOME/skills"   -name __pycache__ -type d -prune -exec rm -rf {} \; 2>/dev/null || true
find "$HERMES_HOME/lsp_servers" "$HERMES_HOME/mcp_servers" "$HERMES_HOME/plugins" \
     -name __pycache__ -type d -prune -exec rm -rf {} \; 2>/dev/null || true
find "$HERMES_HOME/skills" "$HERMES_HOME/lsp_servers" "$HERMES_HOME/mcp_servers" "$HERMES_HOME/plugins" \
     -name '*.pyc' -delete 2>/dev/null || true

# ---- summary ----------------------------------------------------------------
T_SKILLS=$(count_files "$HERMES_HOME/skills/")
T_LSP=$(count_files "$HERMES_HOME/lsp_servers/")
T_MCP=$(count_files "$HERMES_HOME/mcp_servers/")
T_PLUGINS=$(count_files "$HERMES_HOME/plugins/")
T_TOTAL=$(( T_SKILLS + T_LSP + T_MCP + T_PLUGINS ))

echo ""
echo "${GREEN}Install complete. Target: $HERMES_HOME${NC}"
echo "  skills files      : $T_SKILLS"
echo "  lsp server files  : $T_LSP"
echo "  mcp server files  : $T_MCP"
echo "  plugin files      : $T_PLUGINS"
echo "  total on disk     : $T_TOTAL"
if [[ $NEED_BACKUP -eq 1 ]]; then
  echo "  backup            : $BACKUP_DIR"
fi
echo "${GREEN}DONE.${NC}"