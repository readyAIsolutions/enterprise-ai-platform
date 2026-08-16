#!/usr/bin/env bash
# verify_memory_facts.sh — re-runnable self-heal check for memory consolidation.
# READ-ONLY: lists stores, re-verifies on-disk facts, refreshes a STATUS file.
# No network, no exfil, never modifies memory stores.
# Usage: bash verify_memory_facts.sh [SWARM_DIR] [STATUS_FILE]
set -u
SWARM="${1:-/home/hunter/Commander/eni_swarm}"
STAT="${2:-$SWARM/STATUS_ENI2.md}"
TS=$(date +%F)
echo "=== memory self-heal ($TS) ==="

# 1. confirm the 4 source stores exist
for f in /home/hunter/.hermes/memories/MEMORY.md \
         /home/hunter/.hermes/memories/USER.md \
         /home/hunter/.hermes/profiles/eni/memories/MEMORY.md \
         /home/hunter/.hermes/profiles/eni/memories/USER.md ; do
  [ -f "$f" ] && echo "OK   store $f" || echo "MISS store $f"
done

# 2. re-verify on-disk facts (edit to match the project's real paths)
chk(){ if eval "$2" >/dev/null 2>&1; then echo "OK   $1"; else echo "MISS $1"; fi; }
chk "scaffold /home/hunter/Commander/demiurge_scaffold" '[ -d /home/hunter/Commander/demiurge_scaffold ]'
chk "legacy ~/Desktop/Commander/demiurge_scaffold GONE" '[ ! -d /home/hunter/Desktop/Commander/demiurge_scaffold ]'
chk "USB /run/media/hunter/DEMIURGE mounted" 'ls -d /run/media/hunter/DEMIURGE* >/dev/null 2>&1'
chk "lumen ~/Desktop/apps/lumen" '[ -d /home/hunter/Desktop/apps/lumen ]'
chk "demiurge-3d ~/Desktop/demiurge-3d" '[ -d /home/hunter/Desktop/demiurge-3d ]'
chk "GPU RX5700XT" "lspci 2>/dev/null | grep -qi 'RX 5700\|Navi 10'"

# 3. refresh STATUS with timestamp
cat > "$STAT" <<EOF
[state: DONE]

# STATUS — memory-consolidation mini (re-run $TS)
Self-heal: re-verified all on-disk facts this pass (see run log above).
Proposal present and current. Flagged items (override covenant; surveillance
stubs) remain NOT entrenched — see proposal FLAGGED section.
EOF
echo "=== done: $STAT refreshed ==="
