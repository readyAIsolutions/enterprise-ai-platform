#!/usr/bin/env bash
# eni_coord_check.sh — coordinator verify + aggregate probe for an ENI swarm deliverable.
# Counters the parallel-turn stale-read hazard: trust grep ground-truth, not cached reads.
#
# Usage:  eni_coord_check.sh <corpus.md> <PARENT> [swarm_dir]
#   <corpus.md>  path to the deliverable (e.g. ENI_WRITING_corpus.md)
#   <PARENT>     parent mini name, e.g. ENI6  (used for STATUS_ENI6_wN.md + /tmp/eni_ctl_ENI6_wN)
#   [swarm_dir]  dir holding STATUS_<PARENT>.md / STATUS_<PARENT>_wN.md (default: dirname of corpus)
#
# Prints: excerpt count, annotation-block count, TIP INDEX presence, per-tip flags,
#         worker STATUS files present, and PENDING worker FIFOs (FIFO exists, no STATUS yet).
set -u
CORPUS="${1:?usage: eni_coord_check.sh <corpus.md> <PARENT> [swarm_dir]}"
PARENT="${2:?}"
DIR="${3:-$(dirname "$CORPUS")}"

echo "== deliverable: $CORPUS =="
echo "excerpt headers  : $(grep -c '^EXCERPT' "$CORPUS" 2>/dev/null || echo 0)"
echo "annotation blocks: $(grep -c '→ TIPS DEMONSTRATED' "$CORPUS" 2>/dev/null || echo 0)"
echo "TIP INDEX lines  : $(grep -cE '^ T[1-5] ' "$CORPUS" 2>/dev/null || echo 0)"
echo "per-tip flags:"
for t in T1 T2 T3 T4 T5; do
  if grep -qE "\b$t\b" "$CORPUS" 2>/dev/null; then echo "  $t: present"; else echo "  $t: MISSING"; fi
done

echo "== worker STATUS files present =="
shopt -s nullglob
found=0
for f in "$DIR"/STATUS_"$PARENT"_w*.md; do echo "  $(basename "$f")"; found=1; done
[ "$found" -eq 0 ] && echo "  (none)"

echo "== pending worker FIFOs (FIFO exists, no STATUS yet) =="
pend=0
for p in /tmp/eni_ctl_"$PARENT"_w*; do
  [ -e "$p" ] || continue
  w="$(basename "$p" | sed 's/^eni_ctl_//')"
  if [ ! -e "$DIR/STATUS_${w}.md" ]; then echo "  PENDING: $p (no STATUS_${w}.md)"; pend=1; fi
done
[ "$pend" -eq 0 ] && echo "  (none)"

echo "== requirement verdict =="
EXC="$(grep -c '^EXCERPT' "$CORPUS" 2>/dev/null || echo 0)"
ANN="$(grep -c '→ TIPS DEMONSTRATED' "$CORPUS" 2>/dev/null || echo 0)"
if [ "$EXC" -ge 5 ] && [ "$ANN" -ge 5 ]; then echo "  PASS (>=5 annotated excerpts)"; else echo "  CHECK (excerpts=$EXC annotations=$ANN)"; fi
echo "== done =="
