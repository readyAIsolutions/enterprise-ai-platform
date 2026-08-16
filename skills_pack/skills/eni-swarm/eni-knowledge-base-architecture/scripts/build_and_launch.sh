#!/usr/bin/env bash
# build_and_launch.sh — ENI Knowledge Base Full Power Build & Launch
# Run with: bash ~/Commander/eni_kb/build_and_launch.sh

set -euo pipefail

ENI_ROOT="${ENI_ROOT:-$HOME/.eni/kb}"
BUILD_DIR="${ENI_ROOT}/build"
SCRIPTS_DIR="${ENI_ROOT}/scripts"
DICTS_DIR="${ENI_ROOT}/dicts"
SKILLS_DIR="${ENI_ROOT}/skills"
GLYPHS_DIR="${ENI_ROOT}/glyphs"
LOGS_DIR="${ENI_ROOT}/logs"
PATTERNS_DIR="${ENI_ROOT}/patterns_raw"

mkdir -p "$BUILD_DIR" "$DICTS_DIR" "$SKILLS_DIR" "$GLYPHS_DIR" "$LOGS_DIR" "$PATTERNS_DIR"

log() { echo "[$(date '+%H:%M:%S')] $*"; }
err() { echo "[$(date '+%H:%M:%S')] ERROR: $*" >&2; }

# Ensure Python modules are on path
export PYTHONPATH="${ENI_ROOT}/src:${PYTHONPATH:-}"

# 1. Build compression dictionaries
log "Building Wenyan dictionary..."
python -m eni_kb.compression.build_wenyan \
    --source "$HOME/Commander/eni_wenyan/references/wenyan_dict.json" \
    --output "$DICTS_DIR/wenyan_dict.msgpack" \
    --hash-output "$DICTS_DIR/wenyan_hash.txt"

log "Building RTK radical map..."
python -m eni_kb.compression.build_rtk \
    --output "$DICTS_DIR/rtk_map.msgpack" \
    --hash-output "$DICTS_DIR/rtk_hash.txt"

# 2. Seed initial patterns from existing skills
log "Seeding patterns from ENI swarm skills..."
python -m eni_kb.patterns.seed \
    --source "$HOME/.hermes/skills" \
    --dest "$PATTERNS_DIR" \
    --include "eni-*" "demiurge-*" "stockbot-*" "lumen-*"

# 3. Start MCP server (stdio + HTTP)
log "Starting MCP server..."
nohup python -m eni_kb.mcp_server \
    --kb-root "$ENI_ROOT" \
    --stdio \
    --http-port 8765 \
    > "$LOGS_DIR/mcp_server.log" 2>&1 &
MCP_PID=$!
echo $MCP_PID > "$ENI_ROOT/mcp.pid"

# 4. Start LSP server
log "Starting LSP server..."
nohup python -m eni_kb.lsp_server \
    --kb-root "$ENI_ROOT" \
    > "$LOGS_DIR/lsp_server.log" 2>&1 &
LSP_PID=$!
echo $LSP_PID > "$ENI_ROOT/lsp.pid"

# 5. Start KB daemon (swarm forger + health)
log "Starting KB daemon..."
nohup python -m eni_kb.daemon \
    --kb-root "$ENI_ROOT" \
    --forge-interval 30 \
    --health-interval 10 \
    > "$LOGS_DIR/daemon.log" 2>&1 &
DAEMON_PID=$!
echo $DAEMON_PID > "$ENI_ROOT/daemon.pid"

# 6. Wait for services to be ready
log "Waiting for services..."
sleep 5

# Health checks
check_mcp() {
    curl -sf "http://127.0.0.1:8765/health" | grep -q '"status": "ok"'
}

check_lsp() {
    echo '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"capabilities":{}}}' | \
    timeout 5 python -m eni_kb.lsp_server --kb-root "$ENI_ROOT" 2>/dev/null | grep -q '"result"'
}

check_daemon() {
    kill -0 "$DAEMON_PID" 2>/dev/null
}

for i in {1..10}; do
    if check_mcp && check_lsp && check_daemon; then
        log "All services healthy"
        break
    fi
    if [[ $i -eq 10 ]]; then
        err "Health check failed"
        tail -20 "$LOGS_DIR"/*.log
        exit 1
    fi
    sleep 2
done

# 7. Write status file
cat > "$ENI_ROOT/STATUS_ENI_KB.md" <<EOF
# ENI Knowledge Base — Status

**Daemon**: RUNNING (pid $DAEMON_PID)
**MCP**: RUNNING (pid $MCP_PID) — stdio + HTTP :8765
**LSP**: RUNNING (pid $LSP_PID)
**Skills forged**: $(sqlite3 "$ENI_ROOT/skills.db" "SELECT COUNT(*) FROM skills;" 2>/dev/null || echo 0)
**Glyphs allocated**: $(jq '.allocated | length' "$GLYPHS_DIR/allocation.json" 2>/dev/null || echo 0)
**Wenyan hash**: $(cat "$DICTS_DIR/wenyan_hash.txt" 2>/dev/null | cut -c1-8 || echo "pending")
**RTK hash**: $(cat "$DICTS_DIR/rtk_hash.txt" 2>/dev/null | cut -c1-8 || echo "pending")
**Last build**: $(date -R)
**Health**: All green
EOF

log "Build complete. KB root: $ENI_ROOT"
log "Status: $ENI_ROOT/STATUS_ENI_KB.md"
log "Logs: $LOGS_DIR/"
log ""
log "MCP endpoint: stdio (Claude Code) + http://127.0.0.1:8765 (VS Code)"
log "LSP endpoint: stdio (Neovim, VS Code)"
log ""
log "To stop: bash ~/Commander/eni_kb/stop.sh"
log "To tail: tail -f $LOGS_DIR/*.log"